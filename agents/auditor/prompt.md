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
