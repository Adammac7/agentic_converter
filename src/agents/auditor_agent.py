import os
import yaml
import json
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables (API Keys, Model Selection)
load_dotenv()

class AuditorAgent:
    """
    The AuditorAgent acts as a Verification Engineer. 
    It performs a 'Cross-Check' between the original RTL (Source of Truth) 
    and the Generated JSON to ensure zero-defect data extraction.
    """
    
    def __init__(self):
        # Configuration setup from .env
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model_name = os.getenv("OPENAI_MODEL")
        self.client = OpenAI(api_key=self.api_key)
        
        # Load the 'Verification Persona' and 'Audit Instructions' from YAML
        # This keeps the agent logic modular and easy to tune without code changes
        try:
            with open("config/prompts.yaml", "r") as f:
                config = yaml.safe_load(f)
                self.prompts = config["auditor_agent"]
        except FileNotFoundError:
            print("Error: config/prompts.yaml not found.")
            raise

    def audit_design(self, rtl_content, json_content):
        """
        Main entry point for design verification.
        
        Args:
            rtl_content (str): The cleaned/preprocessed SystemVerilog code.
            json_content (str): The JSON string produced by the Extraction Agent.
            
        Returns:
            str: A JSON-formatted string containing 'status' (PASSED/FAILED) and 'errors'.
        """
        
        # We use 'response_format={"type": "json_object"}' to ensure the AI 
        # returns data that the Orchestrator can immediately convert to a Python dict.
        response = self.client.chat.completions.create(
            model=self.model_name,
            temperature=0,  # Zero temperature for maximum objectivity and precision
            messages=[
                {
                    "role": "system", 
                    "content": self.prompts["system_role"]
                },
                {
                    "role": "user", 
                    "content": (
                        f"### SOURCE RTL ###\n{rtl_content}\n\n"
                        f"### GENERATED JSON NETLIST ###\n{json_content}\n\n"
                        f"INSTRUCTIONS:\n{self.prompts['instructions']}"
                    )
                }
            ],
            response_format={"type": "json_object"}
        )
        
        # Return the raw JSON response for the Orchestrator to handle
        return response.choices[0].message.content