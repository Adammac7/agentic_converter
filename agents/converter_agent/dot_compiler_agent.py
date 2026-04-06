import json
import re
from langchain_openai import ChatOpenAI
from .config import OPENAI_MODEL, load_prompt


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
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)

    prompt = load_prompt(
        "DOT Compiler Prompt",
        verified_json=json.dumps(verified_json, indent=2),
        style_map=json.dumps(style_map, indent=2),
    )

    response = llm.invoke(prompt)
    dot_source = _strip_code_fences(response.content)
    return dot_source
