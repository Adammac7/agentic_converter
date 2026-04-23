from pydantic import BaseModel, Field
from typing import Dict, List


class Port(BaseModel):
    """
    Represents the physical boundaries (I/O) of the top-level module.
    Used to define the diagram's external entry and exit points.
    """

    name: str = Field(description="The name of the port (e.g., 'clk', 'result')")
    direction: str = Field(
        description="Specifies if signal flows into (input) or out of (output) the module"
    )
    width: str = Field(
        description="Bit-width of the signal, essential for labeling bus vs. single wire"
    )


class LogicBlock(BaseModel):
    """
    Represents an instantiation of a sub-module within the design.
    Each instance becomes a 'node' (box) in the generated DOT diagram.
    """

    instance_name: str = Field(description="The name of the instance (e.g., 'u_ctrl')")
    module_type: str = Field(
        description="The name of the module being used (e.g., 'ctrl')"
    )
    port_mapping: Dict[str, str] = Field(
        description=(
            "A simple flat dictionary where the KEY is the module port name and "
            "the VALUE is the connected wire name. Example: {'clk': 'clk', 'start': 'w_start'}"
        )
    )


class InternalWire(BaseModel):
    """
    Represents 'logic' declarations within the top-level module.
    These act as the 'glue' that connects different sub-module instances together.
    """

    name: str = Field(description="The unique name of the internal signal (e.g., 'w_start')")
    width: str = Field(
        description="Bit-width of the wire, helps in visual weight of diagram lines"
    )


class RTLStructure(BaseModel):
    """
    The root container for the entire parsed RTL design.
    This class is the source of truth for downstream styling and DOT generation.
    """

    module_name: str = Field(description="The primary parent module name (e.g., 'top')")
    top_level_ports: List[Port] = Field(description="List of all global inputs and outputs")
    internal_wires: List[InternalWire] = Field(
        description="List of all signals defined for inter-module connectivity"
    )
    instances: List[LogicBlock] = Field(
        description="List of all sub-components found inside the design"
    )
