"""
orchestrator.py
"""

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from agents.converter_agent.orchestrator import run_conversion_pipeline


# ── Shared state ──────────────────────────────────────────────────────────────

class PipelineState(TypedDict):
    rtl_code: str
    user_style_prompt: str
    user_edit_prompt: Optional[str]   # set when the user requests a change

    verified_json: Optional[dict]
    style_map: Optional[dict]
    dot_source: Optional[str]
    svg_output: Optional[str]           # FIXME: for now this is a string. Will change appropriately later.


# ── Node functions ────────────────────────────────────────────────────────────

def rtl_to_json_to_dot(state: PipelineState) -> PipelineState:
    """
    Runs the Architect -> Auditor loop from converter_agent.
    Produces a validated RTLStructure JSON and style map.
    """
    result = run_conversion_pipeline(
        rtl_code=state["rtl_code"],
        user_style_prompt=state["user_style_prompt"],
    )
    return {
        "verified_json": result["verified_json"],
        "style_map":     result["style_map"],
        "dot_source":    result["dot_source"],
    }


def dot_to_graph(state: PipelineState) -> PipelineState:
    """
    Converts the DOT source into an SVG Diagram.
    TODO: call Graphviz (via subprocess or graphviz Python package).
    """
    print("[dot_to_graph] Rendering DOT -> SVG  (placeholder)")
    print(f"  DOT preview: {state['dot_source'][:80]}...")
    return { 
        "svg_output": "<svg><!-- placeholder --></svg>"
    }


def update_dot(state: PipelineState) -> PipelineState:
    """
    Applies programmatic edits to the DOT source based on user_edit_prompt.
    TODO: parse user_edit_prompt and mutate dot_source accordingly. (MAY NEED ANOTHER AGENT OR PIPELINE TO HANDLE THIS)
    """
    print("[update_dot] Updating DOT source based on user request (placeholder)")
    print(f"  User edit: {state.get('user_edit_prompt')}")
    return {
        "user_edit_prompt": None
    }   # clear prompt after handling


def should_customize(state: PipelineState) -> str:
    """
    Routing function: if the user has provided an edit prompt, loop back
    through update_dot -> dot_to_graph; otherwise finish.
    """
    if state.get("user_edit_prompt"):
        return "yes"
    return "no"


# ── Graph definition ──────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("rtl_to_json_to_dot",  rtl_to_json_to_dot)
    graph.add_node("dot_to_graph", dot_to_graph)
    graph.add_node("update_dot",   update_dot)

    graph.set_entry_point("rtl_to_json")

    graph.add_edge("rtl_to_json_to_dot",  "dot_to_graph")

    graph.add_conditional_edges(
        "dot_to_graph",
        should_customize,
        {"yes": "update_dot", "no": END},
    )

    graph.add_edge("update_dot", "dot_to_graph")

    return graph


# ── Entry point ───────────────────────────────────────────────────────────────

def run_pipeline(rtl_code: str, user_style_prompt: str) -> PipelineState:
    """Compile and run the graph; return the final state."""
    app = build_graph().compile()

    initial_state: PipelineState = {
        "rtl_code":          rtl_code,
        "user_style_prompt": user_style_prompt,
        "user_edit_prompt":  None,
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
    )

    print("\n── Final state ──")
    print(f"  SVG length : {len(final['svg_output'] or '')} chars")
    print(f"  DOT preview: {(final['dot_source'] or '')[:120]}")