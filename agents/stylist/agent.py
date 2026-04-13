import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from .schema import StyleConfig

load_dotenv()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
_PROMPT_FILE = Path(__file__).with_name("prompt.md")


def _load_prompt(**kwargs) -> str:
    return _PROMPT_FILE.read_text(encoding="utf-8").strip().format(**kwargs)


def run_stylist_agent(architect_json: str, user_request: str) -> StyleConfig:
    """
    Pure Stylist agent. Maps the user's natural-language style preferences
    to the specific components in the Architect's JSON.
    Returns a StyleConfig Pydantic object.
    """
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    stylist = llm.with_structured_output(StyleConfig, method="function_calling")
    prompt = _load_prompt(architect_json=architect_json, user_request=user_request)
    result = stylist.invoke(prompt)

    clean_module_styles = {
        k.strip().strip('"').strip("'"): v for k, v in result.module_styles.items()
    }
    clean_wire_styles = {
        k.strip().strip('"').strip("'"): v for k, v in result.wire_styles.items()
    }

    return StyleConfig(
        module_styles=clean_module_styles,
        wire_styles=clean_wire_styles,
    )
