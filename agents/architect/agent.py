from agents.config import _ARCHITECT_PROMPT_FILE, get_llm, load_prompt
from .schema import RTLStructure


def run_architect_agent(rtl_code: str, feedback: str = "") -> RTLStructure:
    """
    Pure Architect agent. Takes RTL source and optional auditor feedback,
    returns a validated RTLStructure Pydantic object.
    """
    llm = get_llm(temperature=0)
    structured_llm = llm.with_structured_output(RTLStructure)
    prompt = load_prompt(
        _ARCHITECT_PROMPT_FILE,
        "Architect Prompt",
        rtl_code=rtl_code,
        feedback=feedback,
    )
    return structured_llm.invoke(prompt)
