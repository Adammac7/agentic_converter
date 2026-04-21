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
from operator import add
from functools import lru_cache
from typing import TypedDict, Optional, Annotated

from langgraph.graph import StateGraph, START, END

from agents.converter_agent.rtl_to_json_agent import run_architect_agent
from agents.converter_agent.rtl_and_json_auditor_agent import run_auditor_agent
from agents.converter_agent.stylist_agent import run_stylist_agent
from agents.converter_agent.dot_compiler_agent import run_dot_compiler_agent
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

    feedback = ""
    verified_json = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"[rtl_to_json] Attempt {attempt}/{MAX_ATTEMPTS}")

        try:
            architect_result = run_architect_agent(state["rtl_code"], feedback=feedback)
            json_str = json.dumps(architect_result.model_dump(), indent=2)
        except Exception as e:
            feedback = f"System error on previous attempt: {e}. Strictly follow the RTLStructure schema."
            print(f"  [Architect error] {e}")
            continue

        try:
            audit_report = run_auditor_agent(state["rtl_code"], json_str)
        except Exception as e:
            feedback = f"Auditor system error: {e}. Ensure output matches schema exactly."
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
    edit_prompt = state["user_edit_prompt"] or ""
    style_result = run_stylist_agent(
        architect_json=json.dumps(state["verified_json"], indent=2),
        user_request=_stylist_request(state.get("prompt_history") or [], edit_prompt),
    )
    dot_source = run_dot_compiler_agent(
        state["verified_json"],
        style_result.model_dump(),
    )
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
) -> PipelineState:
    """Compile and run the graph; return the final state.

    When `thread_id` is provided and `SUPABASE_DB_URL` is set, state is
    persisted via PostgresSaver. Re-invoking with the same thread_id and
    a non-empty user_edit_prompt resumes from the last checkpoint and
    routes through update_dot, skipping the Architect/Auditor loop.
    """
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

    if existing_values.get("verified_json") and user_edit_prompt:
        input_state: dict = {"user_edit_prompt": user_edit_prompt}
    else:
        input_state = {
            "rtl_code":          rtl_code,
            "user_style_prompt": user_style_prompt,
            "user_edit_prompt":  user_edit_prompt or None,
            "prompt_history":    [],
            "verified_json":     None,
            "style_map":         None,
            "dot_source":        None,
            "svg_output":        None,
        }

    return compiled.invoke(input_state, config=config) if config else compiled.invoke(input_state)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    rtl_path = Path(__file__).parent.parent / "agents" / "converter_agent" / "data" / "raw" / "top.sv"
    if not rtl_path.exists():
        print(f"Error: {rtl_path} not found.")
        sys.exit(1)

    final = run_pipeline(
        rtl_code=rtl_path.read_text(encoding="utf-8"),
        user_style_prompt=(
            "Make the controller blue, the memory interface orange, "
            "and use dashed lines for all clock signals."
        ),
    )

    print("\n── Final state ──")
    print(f"  SVG length     : {len(final['svg_output'] or '')} chars")
    print(f"  DOT preview    : {(final['dot_source'] or '')[:120]}")
    print(f"  Prompt history : {final.get('prompt_history')}")

    svg_path = Path("output.svg")
    svg_path.write_text(final["svg_output"], encoding="utf-8")
    print(f"  SVG saved to: {svg_path.resolve()}")
