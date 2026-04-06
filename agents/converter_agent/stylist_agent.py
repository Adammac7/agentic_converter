from langchain_openai import ChatOpenAI
from .config import OPENAI_MODEL, load_prompt
from .tools.style_schema import StyleConfig, ComponentStyle


def _clean_keys(d: dict) -> dict:
    """Strip extra quotes and whitespace that the LLM sometimes wraps around dict keys."""
    return {k.strip().strip('"').strip("'"): v for k, v in d.items()}


def run_stylist_agent(architect_json: str, user_request: str) -> StyleConfig:
    """
    Pure Stylist agent. Maps the user's natural-language style preferences
    to the specific components in the Architect's JSON.
    Returns a StyleConfig Pydantic object.
    """
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    stylist = llm.with_structured_output(StyleConfig, method="function_calling")
    prompt = load_prompt("Stylist Prompt", architect_json=architect_json, user_request=user_request)
    result = stylist.invoke(prompt)

    # Sanitize keys in case the LLM wrapped them in extra quotes/whitespace
    clean_module_styles = {
        k.strip().strip('"').strip("'"): v
        for k, v in result.module_styles.items()
    }
    clean_wire_styles = {
        k.strip().strip('"').strip("'"): v
        for k, v in result.wire_styles.items()
    }

    return StyleConfig(
        module_styles=clean_module_styles,
        wire_styles=clean_wire_styles,
    )
