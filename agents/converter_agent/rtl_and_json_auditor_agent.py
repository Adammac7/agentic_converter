from langchain_openai import ChatOpenAI
from .auditor_schema import AuditReport

def run_auditor_agent(rtl_code: str, generated_json: str):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    # We use function_calling to ensure the Auditor follows our AuditReport format
    auditor = llm.with_structured_output(AuditReport, method="function_calling")

    prompt = f"""
    You are a Hardware Verification Engineer. Your job is to find discrepancies between the 
    original RTL code and the JSON representation created by another agent.

    CHECKLIST:
    1. Every 'module' instance in the RTL (e.g., u_ctrl, u_fifo) must exist in the JSON 'instances'.
    2. Every 'input' and 'output' in the RTL must exist in the 'top_level_ports'.
    3. The 'port_mapping' for each instance must match the connections in the RTL.
       Example: If RTL says '.clk(w_clk)', the JSON must have "clk": "w_clk".

    RTL SOURCE CODE:
    {rtl_code}

    GENERATED JSON:
    {generated_json}

    If you find ANY error, set is_valid to False and provide detailed feedback.
    """
    
    return auditor.invoke(prompt)