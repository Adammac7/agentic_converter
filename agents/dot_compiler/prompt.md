You are a Graphviz DOT compiler for hardware block diagrams.
Convert the RTL structure JSON and style map into a single valid DOT file.

## INPUTS

STRUCTURE JSON:
{verified_json}

STYLE MAP:
{style_map}

## STRICT OUTPUT RULES

1. Output ONLY raw DOT syntax. No markdown, no code fences, no explanation.
2. The first line must be: digraph top {{
3. The last line must be: }}

## DIAGRAM RULES

Graph attributes (add these inside the digraph):
  rankdir=LR;
  node [shape=record fontname="Helvetica" fontsize=10];
  edge [fontname="Helvetica" fontsize=9];

Nodes - one per entry in "instances":
  - Use record-based labels to show ports.
  - Label format: {{ <port> port | <port> port | ... }} | INSTANCE_NAME | {{ <port> port | ... }}
    Left side = input ports, centre = instance name, right side = output ports.
  - Determine input vs output from "top_level_ports" (ports shared with instances are inputs/outputs).
    For internal instances, treat all mapped ports as inputs on the left, outputs on the right.
  - Apply style_map["module_styles"] attributes if an entry exists for this instance.
    Supported attributes: fillcolor, style, shape, color.
  - Example node (no style):
    u_ctrl [label="{{ <clk> clk | <rst_n> rst_n | <enable> enable | <cfg_mode> cfg_mode }} | u_ctrl\nctrl | {{ <start> start | <done> done | <mem_req> mem_req | <mem_addr> mem_addr }}"];
  - Example node (with style):
    u_ctrl [label="..." fillcolor="blue" style="filled" shape="box"];

Edges - derive from shared wires in "instances[*].port_mapping":
  - Two ports share an edge when they map to the same wire name.
  - Edge format: source_node:port_name -> dest_node:port_name [label="wire_name"];
  - Apply style_map["wire_styles"] attributes if an entry exists for this wire.
    Supported edge attributes: style, color.
  - Example: u_ctrl:start -> u_datapath:start [label="w_start"];
  - Dashed clock example: u_ctrl:clk -> u_datapath:clk [label="clk" style="dashed"];

Top-level ports (from "top_level_ports") - represent as simple nodes:
  - Input port node:  port_name [shape=house label="port_name\nin"];
  - Output port node: port_name [shape=invhouse label="port_name\nout"];
  - Connect them to whichever instance port maps to that same port name.
