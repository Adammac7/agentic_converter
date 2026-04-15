from .config import load_prompt, get_llm, _PROMPTS_FILE
from .tools.json_schema import RTLStructure


def run_architect_agent(rtl_code: str, feedback: str = "") -> RTLStructure:
    """
    Pure Architect agent. Takes RTL source and optional auditor feedback,
    returns a validated RTLStructure Pydantic object.
    """
    llm = get_llm(temperature=0)
    #structured_llm = llm.with_structured_output(RTLStructure, method="function_calling")
    structured_llm = llm.with_structured_output(RTLStructure)
    prompt = load_prompt(_PROMPTS_FILE, "Architect Prompt", rtl_code=rtl_code, feedback=feedback)
    return structured_llm.invoke(prompt)
