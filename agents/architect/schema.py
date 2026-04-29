from pydantic import BaseModel, Field
from typing import Dict, List, Literal


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
    Represents a functional block within the design — either an explicit sub-module
    instantiation (hierarchical RTL) or a virtual block grouping related always/assign
    logic (flat behavioral RTL). Each block becomes a cluster box in the DOT diagram.
    """

    instance_name: str = Field(description="The name of the instance or virtual block (e.g., 'u_ctrl', 'u_wr_ctrl')")
    module_type: str = Field(
        description="Short snake_case identifier used for DOT node IDs; must be unique across all instances (e.g., 'ctrl', 'wr_ctrl')"
    )
    block_kind: Literal["instantiated", "virtual"] = Field(
        default="virtual",
        description="Whether this block comes from explicit RTL instantiation or inferred functional grouping"
    )
    label: str = Field(
        description="Human-readable name describing this block's function, used as the diagram cluster header (e.g., 'Write Controller', 'Memory Array', 'SPI Clock Divider')"
    )
    port_mapping: Dict[str, str] = Field(
        description=(
            "A simple flat dictionary where the KEY is the module port name and "
            "the VALUE is the connected wire name. Example: {'clk': 'clk', 'start': 'w_start'}"
        )
    )
    output_ports: List[str] = Field(
        default_factory=list,
        description=(
            "List of port keys from port_mapping that are OUTPUTS of this block. "
            "For instantiated blocks, derive from the sub-module's 'output' port declarations. "
            "For virtual blocks, list port keys whose wire is driven/written by this block. "
            "Example: ['data_out', 'valid', 'mem_ack']"
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
