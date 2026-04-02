import os
import sys
import json
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 1. LangChain & OpenAI Imports
from langchain_openai import ChatOpenAI

# 2. Local Imports
from .tools.json_schema import RTLStructure

load_dotenv()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

_PROMPTS_FILE = Path(__file__).parent / "prompts.md"

def load_prompt(section: str, **kwargs) -> str:
    """
    Reads a named section from prompts.md and injects keyword arguments.

    Sections are delimited by '# <Name>' headers. The text between the
    requested header and the next header (or end-of-file) is extracted,
    then .format(**kwargs) is called to fill in any {placeholders}.
    """
    text = _PROMPTS_FILE.read_text(encoding="utf-8")
    # Split on any line that starts with '# '
    parts = {}
    current_key = None
    for line in text.splitlines(keepends=True):
        if line.startswith("# "):
            current_key = line[2:].strip()
            parts[current_key] = ""
        elif current_key is not None:
            parts[current_key] += line

    if section not in parts:
        raise KeyError(f"Section '{section}' not found in {_PROMPTS_FILE}. "
                       f"Available: {list(parts.keys())}")

    return parts[section].strip().format(**kwargs)

# --- ANSI color codes (safe on Windows via sys.stdout with UTF-8) ---
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def _log(text: str = ""):
    """Print with explicit UTF-8 encoding so ANSI codes work on Windows."""
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()

def _sep(char: str = "=", width: int = 60, color: str = ""):
    _log(f"{color}{char * width}{RESET}")

# --- Auditor Schema (The TA's Grading Sheet) ---
class AuditReport(BaseModel):
    is_valid: bool = Field(description="True if JSON perfectly matches RTL, False if there are errors.")
    discrepancies: List[str] = Field(description="List of specific errors found in the Architect's JSON.")
    feedback: str = Field(description="Direct instructions for the Architect on how to fix the JSON.")

# --- Auditor Agent (The TA) ---
def run_auditor_agent(rtl_code, generated_json):
    """Checks the Architect's work against the original source code."""
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    auditor = llm.with_structured_output(AuditReport, method="function_calling")

    prompt = load_prompt("Auditor Prompt", rtl_code=rtl_code, generated_json=generated_json)
    return auditor.invoke(prompt)

# --- The Architect (The Student) ---
def generate_validated_rtl_json(rtl_code, max_attempts=3):
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    structured_llm = llm.with_structured_output(RTLStructure, method="function_calling")

    attempt = 0
    feedback = ""

    while attempt < max_attempts:
        # ── ARCHITECT HEADER ──────────────────────────────────────────
        _sep("=", color=CYAN)
        _log(f"{BOLD}{CYAN}  ROUND {attempt + 1} | ARCHITECT AGENT{RESET}")
        _sep("=", color=CYAN)
        if feedback:
            _log(f"{YELLOW}  [Carrying forward Auditor feedback]{RESET}")
            _log(f"{YELLOW}  {feedback.strip()}{RESET}")
            _sep("-", color=YELLOW)

        prompt = load_prompt("Architect Prompt", rtl_code=rtl_code, feedback=feedback)

        try:
            _log(f"  Calling {BOLD}gpt-4o{RESET} (Architect) ...")
            architect_json = structured_llm.invoke(prompt)
            json_str = json.dumps(architect_json.model_dump(), indent=2)

            # ── JSON SNIPPET (first 20 lines) ─────────────────────────
            _sep("-", color=CYAN)
            _log(f"{BOLD}  Architect Output (first 20 lines):{RESET}")
            _sep("-", color=CYAN)
            snippet = json_str.splitlines()[:20]
            for line in snippet:
                _log(f"    {line}")
            if len(json_str.splitlines()) > 20:
                _log(f"    ... ({len(json_str.splitlines()) - 20} more lines)")

            # ── AUDITOR HEADER ────────────────────────────────────────
            _sep("=", color=YELLOW)
            _log(f"{BOLD}{YELLOW}  ROUND {attempt + 1} | AUDITOR AGENT{RESET}")
            _sep("=", color=YELLOW)
            _log(f"  Calling {BOLD}gpt-4o{RESET} (Auditor) ...")
            audit_report = run_auditor_agent(rtl_code, json_str)

            # ── AUDIT RESULT ──────────────────────────────────────────
            _sep("-", color=YELLOW)
            if audit_report.is_valid:
                _log(f"  Verdict:       {GREEN}{BOLD}VALID{RESET}")
            else:
                _log(f"  Verdict:       {RED}{BOLD}INVALID{RESET}")

            _log(f"  Discrepancies: {len(audit_report.discrepancies)} found")
            for i, issue in enumerate(audit_report.discrepancies, 1):
                _log(f"    {i}. {issue}")

            _log(f"  Feedback to Architect:")
            _log(f"    \"{audit_report.feedback}\"")
            _sep("=", color=YELLOW)

            if audit_report.is_valid:
                _log(f"\n{GREEN}{BOLD}  [PASS] Auditor approved the JSON!{RESET}\n")
                return architect_json.model_dump()
            else:
                attempt += 1
                feedback = f"\nCRITICAL FEEDBACK FROM AUDITOR: {audit_report.feedback}"

        except Exception as e:
            _sep("-", color=RED)
            _log(f"{RED}  [ERROR] {e}{RESET}")
            _sep("-", color=RED)
            attempt += 1
            feedback = f"\nSystem Error: {str(e)}. Please ensure you follow the RTLStructure schema exactly."

    raise Exception("Max attempts reached. Architect and Auditor could not agree on a valid JSON.")

def main():
    _here = Path(__file__).parent          # = agents/converter_agent/
    input_path = _here / "data" / "raw" / "top.sv"
    output_path = _here / "data" / "processed" / "top_structure.json"

    _sep("*", color=BOLD)
    _log(f"{BOLD}  RTL-to-JSON Multi-Agent Pipeline{RESET}")
    _log(f"  Input:  {input_path}")
    _log(f"  Output: {output_path}")
    _sep("*", color=BOLD)

    if not input_path.exists():
        _log(f"{RED}  Error: Input file not found: {input_path}{RESET}")
        return

    with open(input_path, "r") as f:
        rtl_content = f.read()

    try:
        final_json = generate_validated_rtl_json(rtl_content)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(final_json, f, indent=4)

        _sep("*", color=GREEN)
        _log(f"{GREEN}{BOLD}  [SUCCESS] Final verified JSON saved to:{RESET}")
        _log(f"{GREEN}  {output_path}{RESET}")
        _sep("*", color=GREEN)

    except Exception as e:
        _sep("*", color=RED)
        _log(f"{RED}{BOLD}  [PIPELINE FAILED] {e}{RESET}")
        _sep("*", color=RED)

if __name__ == "__main__":
    main()
