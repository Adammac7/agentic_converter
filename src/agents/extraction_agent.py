import os
import yaml
from dotenv import load_dotenv
from openai import OpenAI

# -----------------------------------------------------------------------------
# Configuration & Environment Setup
# -----------------------------------------------------------------------------
# Load settings (API keys, Model name) from the .env file
load_dotenv()

class ExtractionAgent:
    """
    The ExtractionAgent acts as the 'Hardware Architect.'
    Its primary responsibility is to translate unstructured SystemVerilog (RTL) 
    into a structured JSON netlist that matches our Pydantic schema.
    """

    def __init__(self):
        """
        Initializes the AI client and loads the prompt configurations from YAML.
        """
        # Fetch configuration from environment variables
        self.api_key = os.getenv("OPENAI_API_KEY")
        
        # NOTE: Using gpt-4o for complex designs is recommended to avoid hallucinations.
        self.model_name = os.getenv("OPENAI_MODEL")
        
        # Initialize the OpenAI connection
        self.client = OpenAI(api_key=self.api_key)
        
        # --- MODULAR PROMPT LOADING ---
        # We load instructions from an external YAML. This allows us to update
        # bit-width rules or JSON keys without modifying this Python code.
        prompt_path = "config/prompts.yaml"
        
        try:
            with open(prompt_path, 'r') as f:
                config = yaml.safe_load(f)
                self.prompts = config['extraction_agent']
        except FileNotFoundError:
            print(f"Error: {prompt_path} not found. Please check your project root.")
            raise

    def extract_schema(self, cleaned_rtl, feedback=""):
        """
        Converts RTL to JSON. Supports self-correction via a feedback loop.

        Args:
            cleaned_rtl (str): The preprocessed RTL code (no comments/whitespace).
            feedback (str, optional): Error messages from the AuditorAgent if a retry is needed.

        Returns:
            str: Raw JSON string representing the design.
        """
        
        # --- SELF-CORRECTION LOGIC ---
        # If the 'feedback' variable is populated, it means the Auditor failed the last attempt.
        # We wrap the instructions to force the AI to focus on the specific errors.
        if feedback:
            user_content = (
                f"### REVISION GUIDANCE ###\n"
                f"Your previous attempt failed the audit. Fix these specific errors:\n{feedback}\n\n"
                f"### RE-EXTRACTION RULES ###\n"
                f"1. Re-read the RTL source carefully.\n"
                f"2. You MUST use the exact JSON keys: 'design_name', 'definitions', 'instantiations'.\n"
                f"3. Do NOT omit or summarize any modules. Extract all sub-modules present.\n\n"
                f"RTL SOURCE CODE:\n{cleaned_rtl}"
            )
        else:
            # Standard "First Attempt" prompt
            user_content = f"{self.prompts['instructions']}\n\nCode:\n{cleaned_rtl}"

        # --- DETERMINISTIC API CALL ---
        # We use temperature=0 to ensure the AI doesn't get 'creative' with hardware ports.
        # response_format={"type": "json_object"} ensures we get a parseable result.
        response = self.client.chat.completions.create(
            model=self.model_name,
            temperature=0, 
            messages=[
                {
                    "role": "system", 
                    "content": self.prompts['system_role']
                },
                {
                    "role": "user", 
                    "content": user_content
                }
            ],
            response_format={"type": "json_object"}
        )
        
        return response.choices[0].message.content