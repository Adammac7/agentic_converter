"""
orchestrator/orchestrator.py

LangGraph orchestrator for the RTL-to-Diagram pipeline.

Graph nodes:
    rtl_to_json       — Architect + Auditor retry loop.
    json_to_dot       — Stylist + DOT Compiler with diagram validation loop.
    dot_to_graph       — Renders DOT -> SVG.
    update_dot         — Applies user edits to DOT source, loops back to dot_to_graph (placeholder).
"""
import json
import re
import shutil
import tempfile
from hashlib import sha256
from datetime import datetime
from pathlib import Path
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END

from agents.architect.agent import run_architect_agent
from agents.auditor.agent import run_auditor_agent
from agents.stylist.agent import run_stylist_agent
from agents.dot_compiler.agent import run_dot_compiler_agent
from agents.config import TokenUsageTracker
from tools.graphviz_quickchart import render_dot_to_svg, GraphvizRenderError


MAX_ATTEMPTS = 3
MAX_DIAGRAM_ATTEMPTS = 3


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


def _has_balanced_braces(source: str) -> bool:
    depth = 0
    for char in source:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _validate_diagram_candidate(dot_source: str) -> tuple[bool, str]:
    candidate = (dot_source or "").strip()
    if not candidate:
        return False, "DOT output is empty."
    if "```" in candidate:
        return False, "DOT output contains markdown fences."
    lowered = candidate.lower()
    if "digraph" not in lowered:
        return False, "DOT output is missing a 'digraph' declaration."
    if "{" not in candidate or "}" not in candidate:
        return False, "DOT output is missing braces."
    if not _has_balanced_braces(candidate):
        return False, "DOT output has unbalanced braces."
    return True, "DOT output passed validation."


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
    user_style_prompt:  str             # beginning prompt
    user_edit_prompt:   Optional[str]   # set when the user requests a change

    verified_json:      Optional[dict]
    style_map:          Optional[dict]
    dot_source:         Optional[str]
    svg_output:         Optional[str]
    session_output_dir: str
    run_id:             str
    run_dir:            str


# Node functions ────────────────────────────────────────────────────────────

def rtl_to_json(state: PipelineState) -> dict:
    """
    Runs the Architect -> Auditor retry loop.
    """

    feedback = ""
    verified_json = None

    # Step 1 & 2 — Architect / Auditor retry loop
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"[rtl_to_json] Attempt {attempt}/{MAX_ATTEMPTS}")
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
            missing_csv = ", ".join(audit_report.missing_items) if audit_report.missing_items else "none"
            hallucinations_csv = ", ".join(audit_report.hallucinations) if audit_report.hallucinations else "none"
            feedback = (
                "CRITICAL FEEDBACK FROM AUDITOR\n"
                f"MISSING=[{missing_csv}]\n"
                f"HALLUCINATIONS=[{hallucinations_csv}]\n"
                f"DETAIL={audit_report.feedback}\n"
                "ACTION=Keep all correct existing entries unchanged. "
                "Only add missing RTL-grounded items and remove true hallucinations."
            )
            print("  [Auditor] Invalid — retrying.")
        _write_text(iter_dir / "feedback.txt", feedback)

    if verified_json is None:
        raise RuntimeError(f"Pipeline failed: could not produce valid JSON after {MAX_ATTEMPTS} attempts.")

    return {"verified_json": verified_json}


def _run_json_to_dot_with_validation(
    verified_json: dict,
    user_style_prompt: str,
    run_dir: str,
) -> tuple[dict, str]:
    style_feedback = ""
    style_dict = None
    dot_source = None
    last_validation_error = "Diagram validation did not run."

    for diagram_attempt in range(1, MAX_DIAGRAM_ATTEMPTS + 1):
        print(f"[diagram_validation] Attempt {diagram_attempt}/{MAX_DIAGRAM_ATTEMPTS}")
        diagram_iter_dir = Path(run_dir) / "iterations" / f"diagram_iter_{diagram_attempt:02d}"
        diagram_iter_dir.mkdir(parents=True, exist_ok=True)

        stylist_request = user_style_prompt
        if style_feedback:
            stylist_request = (
                f"{user_style_prompt}\n\n"
                f"CRITICAL DIAGRAM FEEDBACK: {style_feedback}"
            )

        try:
            style_result = run_stylist_agent(
                architect_json=json.dumps(verified_json, indent=2),
                user_request=stylist_request,
            )
            style_dict = style_result.model_dump()
            _write_json(diagram_iter_dir / "style.json", style_dict)
        except Exception as e:
            style_feedback = f"Stylist error: {e}"
            _write_text(diagram_iter_dir / "stylist_error.txt", str(e))
            print(f"  [Stylist error] {e}")
            continue

        try:
            dot_source = run_dot_compiler_agent(verified_json, style_dict)
            _write_text(diagram_iter_dir / "dot.dot", dot_source or "")
        except Exception as e:
            style_feedback = f"DOT compiler error: {e}"
            _write_text(diagram_iter_dir / "dot_error.txt", str(e))
            print(f"  [DOT Compiler error] {e}")
            continue

        is_valid_dot, validation_message = _validate_diagram_candidate(dot_source)
        _write_text(diagram_iter_dir / "diagram_validation.txt", validation_message)
        if is_valid_dot:
            last_validation_error = ""
            break

        style_feedback = validation_message
        last_validation_error = validation_message
        print(f"  [Diagram invalid] {validation_message}")

    if not style_dict or not dot_source:
        raise RuntimeError("Pipeline failed: could not produce DOT output for diagram generation.")
    if last_validation_error:
        raise RuntimeError(
            "Pipeline failed: diagram validation did not pass after "
            f"{MAX_DIAGRAM_ATTEMPTS} attempts. Last error: {last_validation_error}"
        )
    return style_dict, dot_source


def json_to_dot(state: PipelineState) -> dict:
    """
    Runs Stylist + DOT Compiler with programmatic diagram validation retries.
    """
    style_dict, dot_source = _run_json_to_dot_with_validation(
        verified_json=state["verified_json"],
        user_style_prompt=state["user_style_prompt"],
        run_dir=state["run_dir"],
    )

    return {
        "style_map": style_dict,
        "dot_source": dot_source,
    }


def rtl_to_json_to_dot(state: PipelineState) -> dict:
    """
    Backward-compatible wrapper retained for tests and temporary direct callers.
    The LangGraph runtime now uses the split nodes: rtl_to_json -> json_to_dot.
    """
    json_step = rtl_to_json(state)
    dot_step = json_to_dot({**state, **json_step})

    # Step 5 - Return final package
    return {
        "verified_json": json_step["verified_json"],
        "style_map": dot_step["style_map"],
        "dot_source": dot_step["dot_source"],
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
        if e.body:
            print(f"[dot_to_graph] API response: {e.body}")
        print(f"[dot_to_graph] DOT source that failed:\n{state['dot_source']}")
        raise


def update_dot(state: PipelineState) -> dict:
    style_dict, dot_source = _run_json_to_dot_with_validation(
        verified_json=state["verified_json"],
        user_style_prompt=state["user_edit_prompt"],
        run_dir=state["run_dir"],
    )
    return {
        "style_map":      style_dict,
        "dot_source":     dot_source,
        "user_edit_prompt": None,
    }


def should_customize(state: PipelineState) -> str:
    """
    Routes to update_dot if user want to make another edit, otherwise ends.
    """
    if state.get("user_edit_prompt"):
        return "yes"
    return "no"


# Graph definition ──────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("rtl_to_json", rtl_to_json)
    graph.add_node("json_to_dot", json_to_dot)
    graph.add_node("dot_to_graph", dot_to_graph)
    graph.add_node("update_dot", update_dot)

    graph.set_entry_point("rtl_to_json")

    # Add edges between nodes
    graph.add_edge("rtl_to_json", "json_to_dot")
    graph.add_edge("json_to_dot", "dot_to_graph")
    graph.add_conditional_edges(
        "dot_to_graph",
        should_customize,
        {"yes": "update_dot", "no": END},
    )
    graph.add_edge("update_dot", "dot_to_graph")

    return graph


# Entry point ───────────────────────────────────────────────────────────────

def run_pipeline(
    rtl_code: str,
    user_style_prompt: str,
    user_edit_prompt: str,
    session_label: str = "run",
    output_root: Optional[str] = None,
    session_output_dir: Optional[str] = None,
    ephemeral_session: bool = True,
) -> PipelineState:
    """Compile and run the graph; return the final state."""
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

    app = build_graph().compile()
    tracker = TokenUsageTracker()

    initial_state: PipelineState = {
        "rtl_code":          rtl_code,
        "user_style_prompt": user_style_prompt,
        "user_edit_prompt":  user_edit_prompt,
        "verified_json":     None,
        "style_map":         None,
        "dot_source":        None,
        "svg_output":        None,
        "session_output_dir": str(session_dir),
        "run_id":            run_id,
        "run_dir":           str(run_dir),
    }
    try:
        result = app.invoke(initial_state, config={"callbacks": [tracker]})

        tracker.print_summary()

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


def run_regeneration_pipeline(
    verified_json: dict,
    user_style_prompt: str,
    session_label: str = "regenerate",
    output_root: Optional[str] = None,
    session_output_dir: Optional[str] = None,
    ephemeral_session: bool = True,
) -> dict:
    """
    Regenerate diagram artifacts from an already-verified JSON structure.
    Skips the Architect/Auditor stage and only runs style->DOT->SVG.
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

    try:
        style_map, dot_source = _run_json_to_dot_with_validation(
            verified_json=verified_json,
            user_style_prompt=user_style_prompt,
            run_dir=str(run_dir),
        )
        svg_output = render_dot_to_svg(dot_source)

        artifacts = {
            "structured": _store_artifact(
                session_dir,
                "structured",
                "json",
                json.dumps(verified_json, indent=2),
            ),
            "style": _store_artifact(
                session_dir,
                "style",
                "json",
                json.dumps(style_map, indent=2),
            ),
            "dot": _store_artifact(session_dir, "dot", "dot", dot_source or ""),
            "diagram": _store_artifact(session_dir, "diagram", "svg", svg_output or ""),
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
            "verified_json": verified_json,
            "style_map": style_map,
            "dot_source": dot_source,
            "svg_output": svg_output,
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

