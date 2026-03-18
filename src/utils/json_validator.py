"""
JSON Schema Validation Layer
----------------------------
This module utilizes Pydantic to enforce strict data types and structures 
on the AI's output. It acts as a bridge between the 'unstructured' 
nature of LLM responses and the 'structured' requirements of EDA (Electronic 
Design Automation) tools.
"""

from pydantic import BaseModel, Field, ValidationError
from typing import List, Dict, Any, Optional

# 1. Port Schema: Enforces individual signal integrity
class Port(BaseModel):
    """
    Defines the structure of a single hardware port (e.g., clk, rst).
    Ensures that every signal has a name, a valid direction, and a numerical width.
    """
    name: str
    dir: str   # Expected: 'input', 'output', or 'inout'
    width: int # Calculated as |X-Y| + 1 for buses (e.g., 8 for [7:0])

# 2. Module Definition Schema: Enforces component library structure
class ModuleDef(BaseModel):
    """
    Defines a unique module template found in the RTL code.
    This serves as the 'Class' definition for hardware components.
    """
    module_name: str
    ports: List[Port]

# 3. Master Design Schema: The 'Gold Standard' for the netlist
class RTLDesign(BaseModel):
    """
    The Top-Level Schema: This is the definitive structure for our JSON netlist.
    Every JSON object produced by the AI must match this structure perfectly 
    to be considered 'Valid' by the pipeline.
    """
    design_name: str 
    definitions: List[ModuleDef]
    
    # We allow flexibility in 'instantiations' to accommodate various 
    # SystemVerilog connection styles (ordered vs. named).
    instantiations: List[Dict[str, Any]] 

def validate_json_output(data: dict):
    """
    Validates a raw dictionary against the RTLDesign Pydantic schema.
    
    Args:
        data (dict): The raw dictionary returned by the OpenAI JSON mode.
        
    Returns:
        dict: The sanitized and validated dictionary if successful.
        None: If the data fails type-checking or is missing required keys.
    """
    try:
        # Step 1: 'Splat' the dictionary into the RTLDesign class (**data).
        # Pydantic will raise a ValidationError if types or keys don't match.
        validated_model = RTLDesign(**data)
        
        # Step 2: Convert the validated object back to a clean Python dictionary.
        return validated_model.model_dump() 
        
    except ValidationError as e:
        # This captures exactly WHERE the AI failed (e.g., "Field 'width' is not an integer")
        print(f"❌ Pydantic Schema Mismatch: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected Validation Error: {e}")
        return None