import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
_PROMPT_FILE = Path(__file__).with_name("prompt.md")


def _load_prompt(**kwargs) -> str:
    return _PROMPT_FILE.read_text(encoding="utf-8").strip().format(**kwargs)


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
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    prompt = _load_prompt(
        verified_json=json.dumps(verified_json, indent=2),
        style_map=json.dumps(style_map, indent=2),
    )
    response = llm.invoke(prompt)
    return _strip_code_fences(response.content)
