import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_aws import ChatBedrockConverse

load_dotenv(override=True)

# Backend selector: "bedrock" (default), "gemini", or "openai"
LLM_BACKEND = os.getenv("LLM_BACKEND", "bedrock").lower()

if LLM_BACKEND == "gemini":
    MODEL_NAME = os.getenv("GOOGLE_MODEL")
    API_KEY = os.getenv("GOOGLE_API_KEY")
elif LLM_BACKEND == "openai":
    MODEL_NAME = os.getenv("OPENAI_MODEL")
    API_KEY = os.getenv("OPENAI_API_KEY")
elif LLM_BACKEND == "bedrock":
    MODEL_NAME = os.getenv("BEDROCK_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
else:
    raise ValueError(f"Unknown LLM_BACKEND: {LLM_BACKEND!r}. Use 'bedrock', 'gemini', or 'openai'.")

_ARCHITECT_PROMPT_FILE = Path(__file__).parent / "architect" / "prompt.md"
_AUDITOR_PROMPT_FILE   = Path(__file__).parent / "auditor"   / "prompt.md"
_STYLIST_PROMPT_FILE   = Path(__file__).parent / "stylist"   / "prompt.md"
_DIAGRAM_SPEC_FILE     = Path(__file__).parent / "dot_compiler" / "prompt.md"

def load_prompt(file_path: str, section: str, **kwargs) -> str:
    """
    Reads a named section from a markdown file and injects keyword arguments.

    Sections are delimited by '# <Name>' headers. The text between the
    requested header and the next header (or end-of-file) is extracted,
    then .format(**kwargs) is called to fill in any {placeholders}.

    Args:
        file_path: Path to the markdown file
        section:   The '# Header' name to extract (without the '# ')
        **kwargs:  Placeholder values to inject via .format()
    """
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

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
            f"Section '{section}' not found in {file_path}. "
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


def get_llm(temperature=0):
    if LLM_BACKEND == "gemini":
        return ChatGoogleGenerativeAI(
            model=MODEL_NAME,
            google_api_key=API_KEY,
            temperature=temperature,
        )
    if LLM_BACKEND == "openai":
        return ChatOpenAI(
            model=MODEL_NAME,
            openai_api_key=API_KEY,
            temperature=temperature,
        )
    # bedrock — credentials picked up from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars
    return ChatBedrockConverse(
        model=MODEL_NAME,
        region_name=AWS_REGION,
        temperature=temperature,
    )


def _normalize_llm_content(raw) -> str:
    """
    Normalize provider-specific message content into plain text.
    LangChain chat models may return either a string or a list of parts.
    """
    if isinstance(raw, str):
        return raw

    if isinstance(raw, list):
        parts: list[str] = []
        for part in raw:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text", "")))
            else:
                parts.append(str(part))
        return "".join(parts)

    return str(raw)


def invoke_text(llm, prompt: str) -> str:
    """
    Invoke an LLM and always return normalized text content.
    """
    response = llm.invoke(prompt)
    return _normalize_llm_content(getattr(response, "content", response))


class TokenUsageTracker(BaseCallbackHandler):
    """Accumulates token usage across all LLM calls in a pipeline run."""

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        for generations in response.generations:
            for gen in generations:
                usage = getattr(getattr(gen, "message", None), "usage_metadata", None)
                if usage:
                    self.input_tokens += usage.get("input_tokens", 0)
                    self.output_tokens += usage.get("output_tokens", 0)
                    self.calls += 1

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def print_summary(self) -> None:
        _sep(color=CYAN)
        _log(f"{CYAN}{BOLD}Token Usage{RESET}")
        _log(f"  LLM calls : {self.calls}")
        _log(f"  Input     : {self.input_tokens:,}")
        _log(f"  Output    : {self.output_tokens:,}")
        _log(f"  Total     : {self.total_tokens:,}")
        _sep(color=CYAN)