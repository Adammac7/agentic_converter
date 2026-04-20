"""
orchestrator/orchestrator.py

LangGraph orchestrator for the RTL-to-Diagram pipeline.

Graph nodes:
    rtl_to_json_to_dot — Architect + Auditor retry loop, then Stylist and DOT Compiler.
    dot_to_graph       — Renders DOT -> SVG.
    update_dot         — Applies user edits to DOT source, loops back to dot_to_graph (placeholder).
"""
import json
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END

from agents.converter_agent.rtl_to_json_agent import run_architect_agent
from agents.converter_agent.rtl_and_json_auditor_agent import run_auditor_agent
from agents.converter_agent.stylist_agent import run_stylist_agent
from agents.converter_agent.dot_compiler_agent import run_dot_compiler_agent
from tools.graphviz_quickchart import render_dot_to_svg, GraphvizRenderError


MAX_ATTEMPTS = 3


# Shared state ──────────────────────────────────────────────────────────────

class PipelineState(TypedDict):
    rtl_code:           str
    user_style_prompt:  str             # beginning prompt
    user_edit_prompt:   Optional[str]   # set when the user requests a change

    verified_json:      Optional[dict]
    style_map:          Optional[dict]
    dot_source:         Optional[str]
    svg_output:         Optional[str]


# Node functions ────────────────────────────────────────────────────────────

def rtl_to_json_to_dot(state: PipelineState) -> dict:
    """
    Runs the Architect -> Auditor retry loop, then Stylist and DOT Compiler.

    Pipeline: RTL -> JSON (validated) -> styles -> DOT
    """

    feedback = ""
    verified_json = None

    # Step 1 & 2 — Architect / Auditor retry loop
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

    # Step 3 — Stylist
    try:
        style_result = run_stylist_agent(
            architect_json=json.dumps(verified_json, indent=2),
            user_request=state["user_style_prompt"],
        )
        style_dict = style_result.model_dump()
    except Exception as e:
        print(f"  [Stylist error] {e}")
        raise

    # Step 4 - DOT Compiler
    try:
        dot_source = run_dot_compiler_agent(verified_json, style_dict)
    except Exception as e:
        print(f"  [DOT Compiler error] {e}")
        raise

    # Step 5 - Return final package
    return {
        "verified_json": verified_json,
        "style_map":     style_dict,
        "dot_source":    dot_source,
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
    style_result = run_stylist_agent(
        architect_json=json.dumps(state["verified_json"], indent=2),
        user_request=state["user_edit_prompt"],
    )
    dot_source = run_dot_compiler_agent(
        state["verified_json"], 
        style_result.model_dump()
    )
    return {
        "style_map":      style_result.model_dump(),
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

    graph.add_node("rtl_to_json_to_dot", rtl_to_json_to_dot)
    graph.add_node("dot_to_graph", dot_to_graph)
    graph.add_node("update_dot", update_dot)

    graph.set_entry_point("rtl_to_json_to_dot")

    # Add edges between nodes
    graph.add_edge("rtl_to_json_to_dot", "dot_to_graph")
    graph.add_conditional_edges(
        "dot_to_graph",
        should_customize,
        {"yes": "update_dot", "no": END},
    )
    graph.add_edge("update_dot", "dot_to_graph")

    return graph


# Entry point ───────────────────────────────────────────────────────────────

def run_pipeline(rtl_code: str, user_style_prompt: str, user_edit_prompt: str) -> PipelineState:
    """Compile and run the graph; return the final state."""
    app = build_graph().compile()

    initial_state: PipelineState = {
        "rtl_code":          rtl_code,
        "user_style_prompt": user_style_prompt,
        "user_edit_prompt":  user_edit_prompt,
        "verified_json":     None,
        "style_map":         None,
        "dot_source":        None,
        "svg_output":        None,
    }

    return app.invoke(initial_state)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Path is relative to the project root (one level above this file)
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
        user_edit_prompt =(
            "Make the controller Red, the memory interface orange, "
            "and use dashed lines for all clock signals."
        )
    )

    print("\n── Final state ──")
    print(f"  SVG length : {len(final['svg_output'] or '')} chars")
    print(f"  DOT preview: {(final['dot_source'] or '')[:120]}")

    # write svg to disk so we can read it. 
    # FIXME: later pass this into the frontend
    svg_path = Path("output.svg")
    svg_path.write_text(final["svg_output"], encoding="utf-8")
    print(f"  SVG saved to: {svg_path.resolve()}")