from agents.config import _PROMPTS_FILE, get_llm, load_prompt
from .schema import StyleConfig


def run_stylist_agent(architect_json: str, user_request: str) -> StyleConfig:
    """
    Pure Stylist agent. Maps the user's natural-language style preferences
    to the specific components in the Architect's JSON.
    Returns a StyleConfig Pydantic object.
    """
    llm = get_llm(temperature=0)
    stylist = llm.with_structured_output(StyleConfig)
    prompt = load_prompt(
        _PROMPTS_FILE,
        "Stylist Prompt",
        architect_json=architect_json,
        user_request=user_request,
    )
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
