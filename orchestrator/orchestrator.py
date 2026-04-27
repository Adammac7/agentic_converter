"""
orchestrator/orchestrator.py

LangGraph orchestrator for the RTL-to-Diagram pipeline.

Graph nodes:
    rtl_to_json_to_dot — Architect + Auditor retry loop, then Stylist and DOT Compiler.
    dot_to_graph       — Renders DOT -> SVG.
    update_dot         — Applies user edits to DOT source, loops back to dot_to_graph.

Persistence:
    When SUPABASE_DB_URL is set, the graph is compiled with a PostgresSaver
    checkpointer so state — including the accumulated prompt history — is
    persisted to Supabase, keyed by thread_id.
"""
import json
import os
import re
import shutil
import tempfile
from operator import add
from functools import lru_cache
from hashlib import sha256
from datetime import datetime
from pathlib import Path
from typing import TypedDict, Optional, Annotated

from langgraph.graph import StateGraph, START, END

from agents.architect.agent import run_architect_agent
from agents.auditor.agent import run_auditor_agent
from agents.stylist.agent import run_stylist_agent
from agents.dot_compiler.agent import run_dot_compiler_agent
from tools.graphviz_quickchart import render_dot_to_svg, GraphvizRenderError


MAX_ATTEMPTS = 3


# Checkpointer ──────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_checkpointer():
    """Return a persistent PostgresSaver, or None if SUPABASE_DB_URL is unset.

    Backed by a process-wide psycopg ConnectionPool; safe to reuse across
    requests. Tables are created on first call via .setup() (idempotent).
    """
    conn_str = os.environ.get("SUPABASE_DB_URL")
    if not conn_str:
        return None

    from psycopg_pool import ConnectionPool
    from langgraph.checkpoint.postgres import PostgresSaver

    # prepare_threshold=None disables prepared statements entirely.
    # Supabase's Transaction Pooler recycles connections between statements,
    # so any server-side named prepared statement from one logical connection
    # collides on the next checkout (→ DuplicatePreparedStatement).
    pool = ConnectionPool(
        conninfo=conn_str,
        min_size=1,
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": None},
    )
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    return checkpointer


# Session/artifact helpers ──────────────────────────────────────────────────

def _sanitize_label(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", (label or "").strip())
    return cleaned or "run"


def _create_session_output_dir(
    session_label: str,
    output_root: Optional[str] = None,
    ephemeral: bool = True,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{timestamp}_{_sanitize_label(session_label)}"
    if ephemeral and output_root is None:
        session_dir = Path(tempfile.mkdtemp(prefix=f"{folder_name}_"))
    else:
        root = Path(output_root) if output_root else Path.cwd()
        session_dir = root / folder_name

    (session_dir / "library").mkdir(parents=True, exist_ok=True)
    (session_dir / "runs").mkdir(parents=True, exist_ok=True)
    return session_dir


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, payload: str) -> None:
    path.write_text(payload, encoding="utf-8")


def _store_artifact(
    session_dir: Path,
    artifact_type: str,
    extension: str,
    payload: str,
) -> dict:
    content = payload.encode("utf-8")
    digest = sha256(content).hexdigest()
    artifact_dir = session_dir / "library" / artifact_type
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{digest}.{extension}"
    is_new = not artifact_path.exists()
    if is_new:
        artifact_path.write_bytes(content)
    return {
        "artifact_type": artifact_type,
        "sha256": digest,
        "extension": extension,
        "relative_path": str(artifact_path.relative_to(session_dir)),
        "is_new": is_new,
    }


def _create_run_dir(session_dir: Path, run_label: str) -> tuple[str, Path]:
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_sanitize_label(run_label)}"
    run_dir = session_dir / "runs" / run_id
    (run_dir / "iterations").mkdir(parents=True, exist_ok=True)
    return run_id, run_dir


def _write_session_meta(
    session_dir: Path,
    session_label: str,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    error: Optional[str] = None,
) -> None:
    payload = {
        "session_label": session_label,
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (finished_at - started_at).total_seconds(),
    }
    if error:
        payload["error"] = error
    _write_json(session_dir / "session_meta.json", payload)


# Shared state ──────────────────────────────────────────────────────────────

class PipelineState(TypedDict):
    rtl_code:           str
    user_style_prompt:  str             # initial prompt (first run)
    user_edit_prompt:   Optional[str]   # set when the user requests a change

    # Accumulates every prompt on this thread. The `add` reducer appends
    # node returns of the form {"prompt_history": ["new prompt"]}.
    prompt_history:     Annotated[list[str], add]

    verified_json:      Optional[dict]
    style_map:          Optional[dict]
    dot_source:         Optional[str]
    svg_output:         Optional[str]
    session_output_dir: str
    run_id:             str
    run_dir:            str


def _stylist_request(history: list[str], current: str) -> str:
    """Combine prompt history with the current prompt for the Stylist agent."""
    if not history:
        return current
    lines = ["Previous styling requests on this diagram (oldest first):"]
    for i, p in enumerate(history, start=1):
        lines.append(f"  {i}. {p}")
    lines.append(f"\nLatest request (take precedence where it conflicts): {current}")
    return "\n".join(lines)


# Node functions ────────────────────────────────────────────────────────────

def rtl_to_json_to_dot(state: PipelineState) -> dict:
    """
    Runs the Architect -> Auditor retry loop, then Stylist and DOT Compiler.

    Pipeline: RTL -> JSON (validated) -> styles -> DOT
    """
    print("[rtl_to_json_to_dot] FRESH RUN (Architect/Auditor will fire)")

    feedback = ""
    verified_json = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"[rtl_to_json_to_dot] Attempt {attempt}/{MAX_ATTEMPTS}")
        iter_dir = Path(state["run_dir"]) / "iterations" / f"iter_{attempt:02d}"
        iter_dir.mkdir(parents=True, exist_ok=True)

        try:
            architect_result = run_architect_agent(state["rtl_code"], feedback=feedback)
            json_str = json.dumps(architect_result.model_dump(), indent=2)
            _write_json(iter_dir / "architect.json", architect_result.model_dump())
        except Exception as e:
            feedback = f"System error on previous attempt: {e}. Strictly follow the RTLStructure schema."
            _write_text(iter_dir / "architect_error.txt", str(e))
            print(f"  [Architect error] {e}")
            continue

        try:
            audit_report = run_auditor_agent(state["rtl_code"], json_str)
            _write_json(iter_dir / "auditor_report.json", audit_report.model_dump())
        except Exception as e:
            feedback = f"Auditor system error: {e}. Ensure output matches schema exactly."
            _write_text(iter_dir / "auditor_error.txt", str(e))
            print(f"  [Auditor error] {e}")
            continue

        if audit_report.missing_items:
            print(f"  [Auditor] Missing: {audit_report.missing_items}")
        if audit_report.hallucinations:
            print(f"  [Auditor] Hallucinations: {audit_report.hallucinations}")

        if audit_report.is_valid:
            print("  [Auditor] Valid — moving on.")
            verified_json = architect_result.model_dump()
            break
        else:
            feedback = f"CRITICAL FEEDBACK FROM AUDITOR: {audit_report.feedback}"
            print("  [Auditor] Invalid — retrying.")
        _write_text(iter_dir / "feedback.txt", feedback)

    if verified_json is None:
        raise RuntimeError(f"Pipeline failed: could not produce valid JSON after {MAX_ATTEMPTS} attempts.")

    style_prompt = state["user_style_prompt"]
    style_result = run_stylist_agent(
        architect_json=json.dumps(verified_json, indent=2),
        user_request=_stylist_request(state.get("prompt_history") or [], style_prompt),
    )
    style_dict = style_result.model_dump()

    dot_source = run_dot_compiler_agent(verified_json, style_dict)

    return {
        "verified_json":  verified_json,
        "style_map":      style_dict,
        "dot_source":     dot_source,
        "prompt_history": [style_prompt] if style_prompt else [],
    }


def dot_to_graph(state: PipelineState) -> dict:
    """
    Converts the DOT source into an SVG string via the QuickChart Graphviz API.
    """
    try:
        svg = render_dot_to_svg(state["dot_source"])
        print("[dot_to_graph] SVG rendered successfully.")
        return {"svg_output": svg}
    except GraphvizRenderError as e:
        print(f"[dot_to_graph] Render error: {e}")
        raise


def update_dot(state: PipelineState) -> dict:
    """Re-style the existing diagram with a new edit prompt, preserving history."""
    print("[update_dot] RESUME (skipping Architect/Auditor; only Stylist+DOT will fire)")
    edit_prompt = state["user_edit_prompt"] or ""
    history = state.get("prompt_history") or []
    stylist_request = _stylist_request(history, edit_prompt)
    print(f"[update_dot] stylist_request:\n{stylist_request}")
    print(f"[update_dot] available wires: {[w.get('name') for w in (state['verified_json'].get('internal_wires') or [])]}")
    style_result = run_stylist_agent(
        architect_json=json.dumps(state["verified_json"], indent=2),
        user_request=stylist_request,
    )
    style_dict = style_result.model_dump()
    print(f"[update_dot] style_map: {json.dumps(style_dict, indent=2)}")
    dot_source = run_dot_compiler_agent(
        state["verified_json"],
        style_dict,
    )
    # Show edges for any styled wire so we can see whether the override
    # actually landed in the DOT.
    styled_wires = list((style_dict.get("wire_styles") or {}).keys())
    for wire in styled_wires:
        for line in dot_source.splitlines():
            if wire in line and "->" in line:
                print(f"[update_dot] DOT edge for '{wire}': {line.strip()}")
    return {
        "style_map":        style_result.model_dump(),
        "dot_source":       dot_source,
        "user_edit_prompt": None,
        "prompt_history":   [edit_prompt] if edit_prompt else [],
    }


def _decide_entry(state: PipelineState) -> str:
    """Fresh runs hit the full pipeline; edits skip straight to update_dot."""
    if state.get("verified_json") and state.get("user_edit_prompt"):
        return "edit"
    return "fresh"


# Graph definition ──────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("rtl_to_json_to_dot", rtl_to_json_to_dot)
    graph.add_node("dot_to_graph",       dot_to_graph)
    graph.add_node("update_dot",         update_dot)

    graph.add_conditional_edges(
        START,
        _decide_entry,
        {"fresh": "rtl_to_json_to_dot", "edit": "update_dot"},
    )
    graph.add_edge("rtl_to_json_to_dot", "dot_to_graph")
    graph.add_edge("update_dot",         "dot_to_graph")
    graph.add_edge("dot_to_graph",       END)

    return graph


# Entry point ───────────────────────────────────────────────────────────────

def run_pipeline(
    rtl_code: str,
    user_style_prompt: str,
    user_edit_prompt: str = "",
    thread_id: Optional[str] = None,
    session_label: str = "run",
    output_root: Optional[str] = None,
    session_output_dir: Optional[str] = None,
    ephemeral_session: bool = True,
) -> PipelineState:
    """Compile and run the graph; return the final state.

    When `thread_id` is provided and `SUPABASE_DB_URL` is set, state is
    persisted via PostgresSaver. Re-invoking with the same thread_id and
    a non-empty user_edit_prompt resumes from the last checkpoint and
    routes through update_dot, skipping the Architect/Auditor loop.
    """
    started_at = datetime.now()
    session_dir = (
        Path(session_output_dir)
        if session_output_dir
        else _create_session_output_dir(
            session_label=session_label,
            output_root=output_root,
            ephemeral=ephemeral_session,
        )
    )
    run_id, run_dir = _create_run_dir(session_dir=session_dir, run_label=session_label)

    checkpointer = _get_checkpointer()
    compiled = (
        build_graph().compile(checkpointer=checkpointer)
        if checkpointer
        else build_graph().compile()
    )

    config = {"configurable": {"thread_id": thread_id}} if thread_id else None

    existing_values = {}
    if config and checkpointer:
        snapshot = compiled.get_state(config)
        existing_values = snapshot.values if snapshot else {}

    has_checkpoint_json = bool(existing_values.get("verified_json"))
    print(
        f"[run_pipeline] thread_id={thread_id} "
        f"checkpointer={'yes' if checkpointer else 'no'} "
        f"has_checkpoint_json={has_checkpoint_json} "
        f"user_edit_prompt={'yes' if user_edit_prompt else 'no'} "
        f"resume={'yes' if (has_checkpoint_json and user_edit_prompt) else 'no'}"
    )

    if has_checkpoint_json and user_edit_prompt:
        input_state: dict = {
            "user_edit_prompt":   user_edit_prompt,
            "session_output_dir": str(session_dir),
            "run_id":             run_id,
            "run_dir":            str(run_dir),
        }
    else:
        input_state = {
            "rtl_code":           rtl_code,
            "user_style_prompt":  user_style_prompt,
            "user_edit_prompt":   user_edit_prompt or None,
            "prompt_history":     [],
            "verified_json":      None,
            "style_map":          None,
            "dot_source":         None,
            "svg_output":         None,
            "session_output_dir": str(session_dir),
            "run_id":             run_id,
            "run_dir":            str(run_dir),
        }

    try:
        result = (
            compiled.invoke(input_state, config=config)
            if config
            else compiled.invoke(input_state)
        )

        artifacts = {
            "rtl": _store_artifact(session_dir, "rtl", "sv", rtl_code),
            "structured": _store_artifact(
                session_dir,
                "structured",
                "json",
                json.dumps(result["verified_json"], indent=2),
            ),
            "style": _store_artifact(
                session_dir,
                "style",
                "json",
                json.dumps(result["style_map"], indent=2),
            ),
            "dot": _store_artifact(session_dir, "dot", "dot", result["dot_source"] or ""),
            "diagram": _store_artifact(session_dir, "diagram", "svg", result["svg_output"] or ""),
        }
        changed_artifacts = [name for name, meta in artifacts.items() if meta["is_new"]]
        _write_json(
            run_dir / "run.json",
            {
                "run_id": run_id,
                "session_output_dir": str(session_dir),
                "created_at": datetime.now().isoformat(),
                "artifacts": artifacts,
                "changed_artifacts": changed_artifacts,
            },
        )

        _write_session_meta(
            session_dir=session_dir,
            session_label=session_label,
            status="success",
            started_at=started_at,
            finished_at=datetime.now(),
        )
        return {
            **result,
            "session_output_dir": str(session_dir),
            "run_id": run_id,
            "run_dir": str(run_dir),
        }
    except Exception as exc:
        _write_json(
            run_dir / "run.json",
            {
                "run_id": run_id,
                "session_output_dir": str(session_dir),
                "created_at": datetime.now().isoformat(),
                "status": "failed",
                "error": str(exc),
            },
        )
        _write_session_meta(
            session_dir=session_dir,
            session_label=session_label,
            status="failed",
            started_at=started_at,
            finished_at=datetime.now(),
            error=str(exc),
        )
        raise


def export_session_output(session_output_dir: str, export_root: str, label: Optional[str] = None) -> str:
    source = Path(session_output_dir)
    if not source.exists():
        raise FileNotFoundError(f"Session output directory not found: {source}")
    export_name = label or source.name
    destination = Path(export_root) / _sanitize_label(export_name)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    return str(destination)


def cleanup_session_output(session_output_dir: str) -> None:
    path = Path(session_output_dir)
    if path.exists():
        shutil.rmtree(path)
