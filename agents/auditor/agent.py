import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from .schema import AuditReport


load_dotenv()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
_PROMPT_FILE = Path(__file__).with_name("prompt.md")


def _load_prompt(**kwargs) -> str:
    return _PROMPT_FILE.read_text(encoding="utf-8").strip().format(**kwargs)


def run_auditor_agent(rtl_code: str, generated_json: str) -> AuditReport:
    """
    Pure Auditor agent. Compares RTL source against the Architect's JSON
    and returns a structured AuditReport with pass/fail verdict and feedback.
    """
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    auditor = llm.with_structured_output(AuditReport, method="function_calling")
    prompt = _load_prompt(rtl_code=rtl_code, generated_json=generated_json)
    return auditor.invoke(prompt)
