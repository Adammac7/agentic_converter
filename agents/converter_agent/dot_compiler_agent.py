import json
import re
from .config import load_prompt, get_llm, _DIAGRAM_SPEC_FILE


def _strip_code_fences(text: str) -> str:
    """
    Remove markdown code fences the LLM sometimes wraps around DOT output.
    Handles ```dot ... ```, ``` ... ```, and stray leading/trailing whitespace.
    """
    text = text.strip()
    # Remove opening fence (```dot or ```)
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    # Remove closing fence
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def run_dot_compiler_agent(verified_json: dict, style_map: dict) -> str:
    """
    Pure DOT Compiler agent. Combines the verified RTL structure and style map
    into a valid Graphviz DOT string.

    Returns a raw DOT string (no Pydantic schema — the output is free-form text).
    """
    llm = get_llm(temperature=0)

    # prompt = load_prompt(
    #     "DOT Compiler Prompt",
    #     verified_json=json.dumps(verified_json, indent=2),
    #     style_map=json.dumps(style_map, indent=2),
    # )

    prompt = load_prompt(_DIAGRAM_SPEC_FILE, "DOT Compiler Prompt", verified_json=json.dumps(verified_json, indent=2), style_map=json.dumps(style_map, indent=2))

    response = llm.invoke(prompt)
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in raw
        )
    dot_source = _strip_code_fences(str(raw))
    return dot_source
