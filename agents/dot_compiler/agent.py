import json
import re
from agents.config import _DIAGRAM_SPEC_FILE, get_llm, invoke_text, load_prompt


def _strip_code_fences(text: str) -> str:
    """
    Remove markdown code fences the LLM sometimes wraps around DOT output.
    Handles ```dot ... ```, ``` ... ```, and stray leading/trailing whitespace.
    """
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def run_dot_compiler_agent(verified_json: dict, style_map: dict) -> str:
    """
    Pure DOT Compiler agent. Combines the verified RTL structure and style map
    into a valid Graphviz DOT string.
    """
    llm = get_llm(temperature=0)

    prompt = load_prompt(
        _DIAGRAM_SPEC_FILE,
        "DOT Compiler Prompt",
        verified_json=json.dumps(verified_json, indent=2),
        style_map=json.dumps(style_map, indent=2),
    )

    raw_text = invoke_text(llm, prompt)
    dot_source = _strip_code_fences(raw_text)
    return dot_source
