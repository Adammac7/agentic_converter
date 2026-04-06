from pydantic import BaseModel, Field
from typing import List

class AuditReport(BaseModel):
    is_valid: bool = Field(description="True if JSON perfectly matches RTL, False if there are errors.")
    missing_items: List[str] = Field(description="List of any wires or modules found in RTL but missing in JSON.")
    hallucinations: List[str] = Field(description="List of any items in the JSON that DO NOT exist in the RTL.")
    feedback: str = Field(description="Direct instructions to the Architect Agent on what to fix.")