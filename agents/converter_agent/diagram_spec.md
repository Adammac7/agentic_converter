# RTL Block Diagram — DOT Specification

## 1. Graph-Level Settings

| Attribute     | Value         | Purpose |
|---------------|---------------|---------|
| `rankdir`     | `LR`          | Signal flow left-to-right (inputs on west, outputs on east) |
| `splines`     | `ortho`       | Orthogonal (right-angle) wire routing; use `xlabel` instead of `label` on edges since ortho does not support edge labels |
| `fontname`    | `"Helvetica"` | Graph-level default font |
| `arrowType`   | `tee`         | T-shaped arrowheads (EDA bus-tap convention) |
| `compound`    | `true`        | Allows edges to target clusters (required for `lhead`/`ltail`) |
| `nodesep`     | `0.4`         | Vertical spacing between nodes within the same rank |
| `ranksep`     | `0.7`         | Horizontal spacing between ranks (i.e. between module columns) |

## 2. Node Defaults

Set via `node [...]` at graph scope:

| Attribute   | Value         |
|-------------|---------------|
| `fontname`  | `"Helvetica"` |
| `fontsize`  | `10`          |
| `style`     | `filled`      |
| `fillcolor` | `white`       |

All nodes inherit these unless overridden at the individual node level.

## 3. Edge Defaults

Set via `edge [...]` at graph scope:

| Attribute  | Value         |
|------------|---------------|
| `fontname` | `"Helvetica"` |
| `fontsize` | `8`           |
| `dir`      | `none`        |

Edges are **undirected by default** (`dir=none`). Arrowheads are only added on specific edges that need directional indication (e.g. backward links use `dir=back`).

## 4. Color Palette

### 4.1 Module Cluster Backgrounds (three-tone per module)

Each module uses a **three-shade hue family**: a light cluster fill, a medium input-port fill, and a darker output-port fill. The core node uses the medium-dark shade.

| Module             | Cluster Fill | Input Port Fill | Core Fill  | Output Port Fill | Internal Wire Color |
|--------------------|-------------|-----------------|------------|------------------|---------------------|
| **ctrl**           | `#EEEDFE`   | `#D8D5FA`       | `#CECBF6`  | `#B5B0EE`        | `#9993D6`           |
| **memory_intf**    | `#FAECE7`   | `#F5D5CA`       | `#F5C4B3`  | `#E8A88E`        | `#C4856B`           |
| **datapath**       | `#E1F5EE`   | `#C0EBDA`       | `#9FE1CB`  | `#7FD4B2`        | `#6BBF9E`           |
| **fifo**           | `#FAEEDA`   | `#F5DEB8`       | `#FAC775`  | `#E8B45D`        | `#C49644`           |
| **output_formatter** | `#FBEAF0` | `#F5D0DE`       | `#F4C0D1`  | `#E8A0B5`        | `#C4808E`           |

**Rule**: For each module, define five related hex values progressing from lightest (cluster bg) to darkest (internal wire). The input port fill is one step darker than the cluster, the core is one step darker, the output port is one step darker, and the wire color is the darkest.

### 4.2 External I/O

| Element           | Fill        | Cluster Fill |
|-------------------|-------------|-------------|
| External input    | `#B5D4F4`   | `#E6F1FB`   |
| External output   | `#C0DD97`   | `#EAF3DE`   |

### 4.3 Top-level and Infrastructure

| Element             | Color       | Usage |
|---------------------|-------------|-------|
| Top module cluster  | `#F1EFE8`   | fillcolor of `cluster_top` |
| Cluster border      | `black`     | `color=black` on all clusters |
| Clock bus wires     | `#4466AA`   | All edges in the clock daisy chain |
| Reset bus wires     | `#AA4444`   | All edges in the reset daisy chain |
| Bus relay nodes     | `black`     | `shape=point` fillcolor |

### 4.4 Inter-Module Wire Colors

| Wire(s)                          | Color       | Semantic |
|----------------------------------|-------------|----------|
| ctrl → memory_intf               | `#7B68EE`   | Control-to-memory (purple) |
| ctrl → datapath (w_start)        | `#6A5ACD`   | Control-to-datapath (indigo) |
| memory_intf → datapath           | `#CD853F`   | Memory-to-datapath (tan) |
| datapath → fifo, datapath → of   | `#2E8B57`   | Datapath-to-downstream (green) |
| output_formatter → fifo (backlink) | `#C71585` | Backward flow (magenta) |
| fifo → output_formatter          | `#DAA520`   | FIFO-to-output (goldenrod) |

**Rule**: Each inter-module path gets a unique color. Backward (feedback) links use a distinct warm/magenta tone.

## 5. Typography Rules

| Context                  | Font        | Size | Notes |
|--------------------------|-------------|------|-------|
| Graph/cluster labels     | Helvetica   | 14   | Only `cluster_top` overrides to 14; others inherit default 10 |
| Core node labels         | Helvetica   | 10   | Default; two-line label with `\n` (e.g. `"ctrl\ncore"`) |
| Port node labels         | Helvetica   | 8    | Explicitly set `fontsize=8` on every port node |
| Edge xlabel              | Helvetica   | 8    | From edge default; used for wire net names |
| External I/O labels      | Helvetica   | 10   | Default; bus widths shown as `signal[N:0]` |

## 6. Structural Patterns

### 6.1 Cluster Hierarchy (3 levels)

```
digraph top                          ← root graph (the chip/design)
  └─ cluster_ext_in                  ← external input port group
  └─ cluster_ext_out                 ← external output port group
  └─ cluster_top                     ← top-level RTL module
       ├─ cluster_ctrl               ← sub-module
       ├─ cluster_memory_intf        ← sub-module
       ├─ cluster_datapath           ← sub-module
       ├─ cluster_fifo               ← sub-module
       └─ cluster_output_formatter   ← sub-module
```

**Rule**: Every cluster name begins with `cluster_`. The top RTL module is always `cluster_top`. Sub-module clusters are `cluster_{module_name}`.

### 6.2 All Clusters Share This Boilerplate

```dot
style=filled; color=black; fillcolor="<hex>";
```

Sub-module clusters additionally include:
```dot
class="<type> <id> abstract_w1.25_h0.9 port_dir_LR";
margin=12;
```

### 6.3 Subgraph Declaration Order = Dataflow Order

Declare sub-module clusters in **signal-flow order** so Graphviz naturally places them left-to-right. In this file: ctrl → memory_intf → datapath → fifo → output_formatter.

### 6.4 Invisible Ordering Edges

To enforce linear left-to-right placement, add invisible edges between core nodes of adjacent modules:

```dot
ctrl_core -> mem_core  [style=invis, weight=10];
mem_core  -> dp_core   [style=invis, weight=10];
dp_core   -> fifo_core [style=invis, weight=10];
fifo_core -> of_core   [style=invis, weight=10];
```

**Rule**: `weight=10` on invisible edges; this is the highest weight in the file and overrides all other placement pressure.

### 6.5 Bus Relay Nodes (Clock/Reset Distribution)

To prevent global signals from routing through intermediate module clusters, use **daisy-chained point nodes** placed outside all sub-module clusters but inside `cluster_top`:

```
source → tap_mod1 → tap_mod2 → tap_mod3 → ...
              ↓          ↓          ↓
          mod1_in     mod2_in    mod3_in
```

Each relay node: `shape=point, width=0.06, fillcolor=black`.

**Trunk edges** (tap-to-tap): `weight=1` — allows flexible horizontal routing.
**Tap edges** (tap-to-module-port): `weight=5` — pulls the tap node close to its target module.

## 7. Naming Conventions

### 7.1 Node IDs

| Category          | Pattern                              | Example |
|-------------------|--------------------------------------|---------|
| Input port        | `{module}_in_{signal}`               | `ctrl_in_clk`, `dp_in_mem_data` |
| Output port       | `{module}_out_{signal}`              | `ctrl_out_start`, `mem_out_mem_ack` |
| Core logic        | `{module}_core`                      | `ctrl_core`, `fifo_core` |
| External input    | `{signal}`                           | `clk`, `rst_n`, `data_in` |
| External output   | `{signal}_ext`                       | `done_ext`, `result_ext` |
| Clock relay       | `clk_tap_{module}`                   | `clk_tap_ctrl`, `clk_tap_dp` |
| Reset relay       | `rst_tap_{module}`                   | `rst_tap_mem`, `rst_tap_of` |

### 7.2 Cluster Labels

Format: `"u_{instance}  ({module_type})"` — two spaces between instance and parenthetical.

Examples: `"u_ctrl  (ctrl)"`, `"u_memory_intf  (memory_intf)"`.

### 7.3 Wire Net Names (edge xlabels)

Format: `"w_{signal}"` — the `w_` prefix denotes a wire/net.

Examples: `"w_start"`, `"w_mem_req"`, `"w_fifo_dout"`.

## 8. Hardware-Specific Conventions

### 8.1 Node Shapes by Role

| Shape        | Role                              |
|--------------|-----------------------------------|
| `Mdiamond`   | External input port (pad/pin)    |
| `Msquare`    | External output port (pad/pin)   |
| `box`        | Module-level I/O port (interface pin on a sub-block) |
| `box3d`      | Core processing logic (the "guts" of a module) |
| `point`      | Wire junction / bus tap relay     |

### 8.2 Port Node Sizing

| Port type              | `width` | `height` |
|------------------------|---------|----------|
| Single-bit signal      | `0.7`   | `0.25`   |
| Bus signal (`[N:0]`)   | `0.9`   | `0.25`   |

**Rule**: Any signal label containing `[` and `]` gets `width=0.9`. All others get `width=0.7`. Height is always `0.25`.

### 8.3 Core Node Sizing

Default: `width=1.0, height=0.6`. If the module name is long (e.g. `memory_intf`, `output_formatter`), increase width to `1.2` or `1.4` to fit the two-line label.

### 8.4 Internal Module Wiring Style

All edges **within** a module cluster (port → core, core → port) use:
```dot
style=dashed, color="<module_internal_wire_color>"
```

This visually distinguishes intra-module wiring from inter-module nets.

### 8.5 Inter-Module Wiring Style

All edges **between** module clusters use:
- Solid style (default; no `style` attribute needed)
- A unique `color` per source→destination pair (see §4.4)
- `xlabel` for the wire net name (not `label`, due to ortho incompatibility)
- `weight=3` for adjacent-module connections; `weight=2` for connections that skip a module

### 8.6 Bus Width Annotation

Bus widths are encoded in the port node **label** using Verilog-style bit-range notation: `signal[MSB:LSB]`.

Examples: `data_in[7:0]`, `mem_addr[7:0]`, `cfg_mode[1:0]`.

Single-bit signals have no range suffix.

### 8.7 Backward / Feedback Links

When a downstream module drives an upstream module (e.g. output_formatter's `rd_en` driving fifo's `rd_en` input), set:
```dot
dir=back, weight=0
```

`dir=back` draws the arrowhead at the source end. `weight=0` tells Graphviz this edge should not influence rank placement (it opposes the dataflow direction).

### 8.8 `class` Attribute Metadata (Viewer Hints)

The `class` attribute is not rendered by Graphviz but is preserved in SVG output for interactive viewers.

**On clusters:**
```
class="<functional_type> <sort_order> abstract_w<W>_h<H> port_dir_LR"
```

| Token                  | Meaning |
|------------------------|---------|
| `<functional_type>`    | Semantic role: `control`, `memory`, `datapath`, `buffer`, `output` |
| `<sort_order>`         | Numeric; controls collapsed-view ordering (1000, 2000, ...) |
| `abstract_w1.25_h0.9` | When collapsed, render the abstract box at 1.25× width, 0.9× height vs. default |
| `port_dir_LR`          | When collapsed, attach all wires on left (inputs) and right (outputs) only — never top/bottom |

**On port nodes:**
```
class="input port"   or   class="output port"
```

**On inter-module edges:**
```
class="crosscluster port_exit_e port_entry_w"
```
Tells the viewer: source port exits east, destination port enters west.

**On backward edges:**
```
class="crosscluster port_exit_w port_entry_e"
```

**On bus edges:**
```
class="bus clock"              (trunk segment)
class="bus clock port_entry_w" (tap into module)
class="bus reset"              (trunk segment)
class="bus reset port_entry_w" (tap into module)
```
