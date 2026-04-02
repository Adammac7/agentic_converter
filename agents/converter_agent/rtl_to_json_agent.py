from langchain_openai import ChatOpenAI
from .config import OPENAI_MODEL, load_prompt
from .tools.json_schema import RTLStructure


def run_architect_agent(rtl_code: str, feedback: str = "") -> RTLStructure:
    """
    Pure Architect agent. Takes RTL source and optional auditor feedback,
    returns a validated RTLStructure Pydantic object.
    """
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    structured_llm = llm.with_structured_output(RTLStructure, method="function_calling")
    prompt = load_prompt("Architect Prompt", rtl_code=rtl_code, feedback=feedback)
    return structured_llm.invoke(prompt)
