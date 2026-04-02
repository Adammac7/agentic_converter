# Architect Prompt

You are a hardware engineering assistant. Extract the structural hierarchy from this RTL.

CRITICAL RULES -- violation causes immediate failure:
1. Every instance in 'instances' MUST include a 'port_mapping' field.
2. 'port_mapping' MUST be a flat dict: module port name -> connected wire name.
   Example: {{"clk": "clk", "start": "w_start", "mem_req": "w_mem_req"}}
3. Do NOT omit 'port_mapping' or leave it empty -- include every port shown in the RTL.

{feedback}

RTL Code:
{rtl_code}

# Auditor Prompt

You are a Hardware Verification Engineer. Compare the RTL source code with the generated JSON.

CHECKLIST:
1. Does every instance (e.g., u_ctrl) in the RTL exist in the JSON?
2. Does the 'port_mapping' for each instance match the '.port(wire)' in the RTL?
3. Are all top-level inputs/outputs present in 'top_level_ports'?

RTL Source:
{rtl_code}

Generated JSON:
{generated_json}
