from .config import load_prompt, get_llm, _PROMPTS_FILE
from .tools.auditor_schema import AuditReport


def run_auditor_agent(rtl_code: str, generated_json: str) -> AuditReport:
    """
    Pure Auditor agent. Compares RTL source against the Architect's JSON
    and returns a structured AuditReport with pass/fail verdict and feedback.
    """
    llm = get_llm(temperature=0)
    #auditor = llm.with_structured_output(AuditReport, method="function_calling")
    auditor = llm.with_structured_output(AuditReport)
    prompt = load_prompt(_PROMPTS_FILE, "Auditor Prompt", rtl_code=rtl_code, generated_json=generated_json)
    return auditor.invoke(prompt)
