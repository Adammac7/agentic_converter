import os
import sys
from pathlib import Path
from dotenv import load_dotenv

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
    parts = {}
    current_key = None
    for line in text.splitlines(keepends=True):
        if line.startswith("# "):
            current_key = line[2:].strip()
            parts[current_key] = ""
        elif current_key is not None:
            parts[current_key] += line

    if section not in parts:
        raise KeyError(
            f"Section '{section}' not found in {_PROMPTS_FILE}. "
            f"Available: {list(parts.keys())}"
        )

    return parts[section].strip().format(**kwargs)


# --- ANSI color codes (safe on Windows via sys.stdout with UTF-8) ---
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def _log(text: str = "") -> None:
    """Write a line to stdout with explicit UTF-8 encoding."""
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def _sep(char: str = "=", width: int = 60, color: str = "") -> None:
    _log(f"{color}{char * width}{RESET}")
