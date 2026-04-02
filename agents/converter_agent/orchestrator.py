import json
from pathlib import Path

from .config import (
    _log, _sep,
    GREEN, RED, YELLOW, CYAN, BOLD, RESET,
)
from .rtl_to_json_agent import run_architect_agent
from .rtl_and_json_auditor_agent import run_auditor_agent
from .stylist_agent import run_stylist_agent
from .dot_compiler_agent import run_dot_compiler_agent


def run_conversion_pipeline(
    rtl_code: str,
    user_style_prompt: str,
    max_attempts: int = 3,
) -> dict:
    """
    Conductor for the full RTL-to-Diagram pipeline.

    Steps:
      1. Architect    — extract RTLStructure from raw RTL.
      2. Audit loop   — Auditor validates; on failure, feedback is fed back to
                        the Architect for up to max_attempts rounds.
      3. Stylist      — maps user style preferences onto the verified JSON.
      4. DOT Compiler — combines structure + styles into a Graphviz DOT string.

    Returns:
      {
        "verified_json": dict,   # RTLStructure as a plain dict
        "style_map":     dict,   # StyleConfig as a plain dict
        "dot_source":    str,    # raw Graphviz DOT syntax
      }
    """

    feedback = ""
    verified_json = None

    # ── ARCHITECT / AUDITOR LOOP ──────────────────────────────────────────────
    for attempt in range(1, max_attempts + 1):

        # Step 1 — Architect
        _sep("=", color=CYAN)
        _log(f"{BOLD}{CYAN}  ROUND {attempt}/{max_attempts} | ARCHITECT AGENT{RESET}")
        _sep("=", color=CYAN)
        if feedback:
            _log(f"{YELLOW}  [Carrying forward Auditor feedback]{RESET}")
            _log(f"{YELLOW}  {feedback.strip()}{RESET}")
            _sep("-", color=YELLOW)

        _log(f"  Calling {BOLD}{RESET} Architect ...")
        try:
            architect_result = run_architect_agent(rtl_code, feedback=feedback)
        except Exception as e:
            _sep("-", color=RED)
            _log(f"{RED}  [ARCHITECT ERROR] {e}{RESET}")
            _sep("-", color=RED)
            feedback = f"System error on previous attempt: {e}. Strictly follow the RTLStructure schema."
            continue

        json_str = json.dumps(architect_result.model_dump(), indent=2)

        # JSON snippet (first 20 lines)
        _sep("-", color=CYAN)
        _log(f"{BOLD}  Architect Output (first 20 lines):{RESET}")
        _sep("-", color=CYAN)
        lines = json_str.splitlines()
        for line in lines[:20]:
            _log(f"    {line}")
        if len(lines) > 20:
            _log(f"    ... ({len(lines) - 20} more lines)")

        # Step 2 — Auditor
        _sep("=", color=YELLOW)
        _log(f"{BOLD}{YELLOW}  ROUND {attempt}/{max_attempts} | AUDITOR AGENT{RESET}")
        _sep("=", color=YELLOW)
        _log(f"  Calling Auditor ...")

        try:
            audit_report = run_auditor_agent(rtl_code, json_str)
        except Exception as e:
            _sep("-", color=RED)
            _log(f"{RED}  [AUDITOR ERROR] {e}{RESET}")
            _sep("-", color=RED)
            feedback = f"Auditor system error: {e}. Ensure output matches schema exactly."
            continue

        _sep("-", color=YELLOW)
        if audit_report.is_valid:
            _log(f"  Verdict:       {GREEN}{BOLD}VALID{RESET}")
        else:
            _log(f"  Verdict:       {RED}{BOLD}INVALID{RESET}")

        if audit_report.missing_items:
            _log(f"  Missing items ({len(audit_report.missing_items)}):")
            for item in audit_report.missing_items:
                _log(f"    - {item}")

        if audit_report.hallucinations:
            _log(f"  Hallucinations ({len(audit_report.hallucinations)}):")
            for item in audit_report.hallucinations:
                _log(f"    - {item}")

        _log(f"  Feedback to Architect:")
        _log(f"    \"{audit_report.feedback}\"")
        _sep("=", color=YELLOW)

        if audit_report.is_valid:
            _log(f"\n{GREEN}{BOLD}  [PASS] Auditor approved the JSON!{RESET}\n")
            verified_json = architect_result.model_dump()
            break
        else:
            feedback = f"CRITICAL FEEDBACK FROM AUDITOR: {audit_report.feedback}"

    if verified_json is None:
        raise RuntimeError(
            f"Pipeline failed: Architect and Auditor could not agree after {max_attempts} attempts."
        )

    # Step 3 — Stylist
    _sep("=", color=CYAN)
    _log(f"{BOLD}{CYAN}  STYLIST AGENT{RESET}")
    _sep("=", color=CYAN)
    _log(f"  User request: \"{user_style_prompt}\"")
    _log(f"  Calling Stylist ...")

    try:
        style_result = run_stylist_agent(
            architect_json=json.dumps(verified_json, indent=2),
            user_request=user_style_prompt,
        )
    except Exception as e:
        _sep("-", color=RED)
        _log(f"{RED}  [STYLIST ERROR] {e}{RESET}")
        _sep("-", color=RED)
        raise

    _sep("-", color=CYAN)
    _log(f"{BOLD}  Style Map:{RESET}")
    style_dict = style_result.model_dump()
    for instance, styles in style_dict.get("module_styles", {}).items():
        _log(f"    {instance}: {styles}")
    for wire, styles in style_dict.get("wire_styles", {}).items():
        _log(f"    {wire}: {styles}")
    _sep("=", color=CYAN)

    # Step 4 — DOT Compiler
    _sep("=", color=CYAN)
    _log(f"{BOLD}{CYAN}  DOT COMPILER AGENT{RESET}")
    _sep("=", color=CYAN)
    _log(f"  Calling DOT Compiler ...")

    try:
        dot_source = run_dot_compiler_agent(verified_json, style_dict)
    except Exception as e:
        _sep("-", color=RED)
        _log(f"{RED}  [DOT COMPILER ERROR] {e}{RESET}")
        _sep("-", color=RED)
        raise

    _sep("-", color=CYAN)
    _log(f"{BOLD}  DOT Output (first 15 lines):{RESET}")
    _sep("-", color=CYAN)
    dot_lines = dot_source.splitlines()
    for line in dot_lines[:15]:
        _log(f"    {line}")
    if len(dot_lines) > 15:
        _log(f"    ... ({len(dot_lines) - 15} more lines)")
    _sep("=", color=CYAN)

    # Step 5 — Return final package
    return {
        "verified_json": verified_json,
        "style_map": style_dict,
        "dot_source": dot_source,
    }


def main():
    _here = Path(__file__).parent
    input_path  = _here / "data" / "raw" / "top.sv"
    json_out    = _here / "data" / "processed" / "top_structure.json"
    style_out   = _here / "data" / "processed" / "top_style.json"
    dot_out     = _here / "data" / "processed" / "top.dot"

    _sep("*", color=BOLD)
    _log(f"{BOLD}  RTL-to-Diagram Multi-Agent Pipeline{RESET}")
    _log(f"  Input:  {input_path}")
    _log(f"  JSON:   {json_out}")
    _log(f"  Style:  {style_out}")
    _log(f"  DOT:    {dot_out}")
    _sep("*", color=BOLD)

    if not input_path.exists():
        _log(f"{RED}  Error: Input file not found: {input_path}{RESET}")
        return

    rtl_code = input_path.read_text(encoding="utf-8")

    # Edit this string to change the style without touching any Python code
    user_style_prompt = (
        "Make the controller blue, the memory interface orange, "
        "and use dashed lines for all clock signals."
    )

    try:
        result = run_conversion_pipeline(rtl_code, user_style_prompt)

        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps(result["verified_json"], indent=4), encoding="utf-8"
        )
        style_out.write_text(
            json.dumps(result["style_map"], indent=4), encoding="utf-8"
        )
        dot_out.write_text(result["dot_source"], encoding="utf-8")

        _sep("*", color=GREEN)
        _log(f"{GREEN}{BOLD}  [SUCCESS] Outputs saved:{RESET}")
        _log(f"{GREEN}  Structure: {json_out}{RESET}")
        _log(f"{GREEN}  Styles:    {style_out}{RESET}")
        _log(f"{GREEN}  DOT:       {dot_out}{RESET}")
        _sep("*", color=GREEN)

    except Exception as e:
        _sep("*", color=RED)
        _log(f"{RED}{BOLD}  [PIPELINE FAILED] {e}{RESET}")
        _sep("*", color=RED)


if __name__ == "__main__":
    main()
