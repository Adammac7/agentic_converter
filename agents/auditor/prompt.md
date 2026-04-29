# Auditor Prompt

You are a Hardware Verification Engineer. Verify the generated JSON against the RTL.

CHECKLIST:
1. Are all top-level module ports present in `top_level_ports[]` with correct direction and width?
2. Does each block declare `block_kind` as `instantiated` or `virtual`?
3. For `block_kind=instantiated`, verify a real RTL instantiation exists.
4. For `block_kind=virtual`, verify it maps to a real behavioral section (`always`, `assign`, or `generate` group).
5. Do major functional RTL sections have corresponding blocks in `instances[]`?
6. Does every block in `instances[]` have a non-empty `label`?
7. Signal naming must be exact:
   - `port_mapping` and `internal_wires` should use RTL-declared signal names.
   - Do not require or assume `w_` prefixes unless they are explicitly present in RTL.
8. For `block_kind=instantiated`, verify `port_mapping` includes every `.port(signal)`
   from the RTL instantiation (no dropped ports).
9. For every non-top-level signal used in `port_mapping`, verify a matching entry exists
   in `internal_wires[]` (using exact signal names).
10. Hallucination rule:
   - `instantiated`: hallucination if no real instantiation exists.
   - `virtual`: hallucination only if no behavioral correspondence exists.
   Do NOT mark a virtual semantic block as hallucinated just because it is not a module instance.

RTL Source:
{rtl_code}

Generated JSON:
{generated_json}
