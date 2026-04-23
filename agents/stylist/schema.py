from typing import Dict, Optional

from pydantic import BaseModel, Field


class ComponentStyle(BaseModel):
    color: Optional[str] = Field(
        None, description="Hex code or standard color name (e.g., 'red', '#4287f5')"
    )
    fillcolor: Optional[str] = Field(None, description="Background color for the module box")
    style: Optional[str] = Field(
        None, description="Style like 'filled', 'dashed', or 'dotted'"
    )
    shape: Optional[str] = Field(
        None, description="Shape of the node like 'box', 'octagon', or 'ellipse'"
    )


class StyleConfig(BaseModel):
    module_styles: Dict[str, ComponentStyle] = Field(
        default_factory=dict,
        description="Mapping of instance names (u_ctrl) to their visual styles",
    )
    wire_styles: Dict[str, ComponentStyle] = Field(
        default_factory=dict,
        description="Mapping of signal names (clk) to their line styles",
    )
