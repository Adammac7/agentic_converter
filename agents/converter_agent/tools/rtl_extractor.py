import re
from langchain.tools import tool

@tool
def rtl_extractor(rtl_text: str):
    """
    Acts as a structural scanner for RTL code. 
    It identifies module boundaries, I/O ports, and internal signal connections.
    """
    # Find the main module name
    module_name = re.search(r"module\s+(\w+)", rtl_text)
    
    # Find all signal declarations (inputs/outputs/logic/wires)
    # This looks for the pattern: [direction] [type] [width] [name]
    signals = re.findall(r"(input|output|logic|wire)\s+(?:logic\s+)?(?:\[.*?\])?\s*(\w+)", rtl_text)
    
    # Find sub-module instantiations (like u_ctrl, u_fifo)
    # RTL usually follows: module_type instance_name (.port(wire))
    instances = re.findall(r"(\w+)\s+(u_\w+)\s*\(", rtl_text)

    return {
        "detected_module": module_name.group(1) if module_name else "Unknown",
        "signal_list": signals,
        "sub_components": instances
    }