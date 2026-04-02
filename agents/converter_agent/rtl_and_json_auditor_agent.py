from langchain_openai import ChatOpenAI
from .config import OPENAI_MODEL, load_prompt
from .tools.auditor_schema import AuditReport


def run_auditor_agent(rtl_code: str, generated_json: str) -> AuditReport:
    """
    Pure Auditor agent. Compares RTL source against the Architect's JSON
    and returns a structured AuditReport with pass/fail verdict and feedback.
    """
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    auditor = llm.with_structured_output(AuditReport, method="function_calling")
    prompt = load_prompt("Auditor Prompt", rtl_code=rtl_code, generated_json=generated_json)
    return auditor.invoke(prompt)
