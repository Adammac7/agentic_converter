import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from .schema import RTLStructure


load_dotenv()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
_PROMPT_FILE = Path(__file__).with_name("prompt.md")


def _load_prompt(**kwargs) -> str:
    return _PROMPT_FILE.read_text(encoding="utf-8").strip().format(**kwargs)


def run_architect_agent(rtl_code: str, feedback: str = "") -> RTLStructure:
    """
    Pure Architect agent. Takes RTL source and optional auditor feedback,
    returns a validated RTLStructure Pydantic object.
    """
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    structured_llm = llm.with_structured_output(RTLStructure, method="function_calling")
    prompt = _load_prompt(rtl_code=rtl_code, feedback=feedback)
    return structured_llm.invoke(prompt)
