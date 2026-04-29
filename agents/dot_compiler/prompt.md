# DOT Compiler Prompt

You are a Graphviz DOT compiler for hierarchical hardware block diagrams.
Convert the RTL structure JSON and style map into a single valid DOT file
that renders a professional chip block diagram with encapsulated sub-modules,
orthogonal wiring, and color-coded signal paths.

## INPUTS

STRUCTURE JSON:
{verified_json}

STYLE MAP:
{style_map}

## STRICT OUTPUT RULES

1. Output ONLY raw DOT syntax. No markdown, no code fences, no explanation.
2. The first line must be: digraph <module_name from JSON> {{
3. The last line must be: }}
4. Because splines=ortho does not support the `label` attribute on edges,
   use `xlabel` for all wire net names on inter-module and external edges.
5. Emit DOT sections in this exact order:
   a. Graph-level attributes
   b. cluster_ext_in (external input ports)
   c. cluster_ext_out (external output ports)
   d. cluster_top containing:
      i.   Sub-module clusters in instances[] array order
      ii.  Invisible ordering edges (between core nodes)
      iii. Bus relay point nodes
      iv.  Bus relay edge chains (trunk + taps)
   e. External I/O edges (outside cluster_top)
   f. Inter-module edges (outside cluster_top)
   g. Backward/feedback edges (outside cluster_top)
   h. Closing brace

---

## GRAPH ATTRIBUTES

Add these immediately inside the digraph:

```
graph [rankdir=LR, splines=ortho, fontname="Helvetica", compound=true, nodesep=0.4, ranksep=0.7];
node [fontname="Helvetica", fontsize=10, style=filled, fillcolor=white];
edge [fontname="Helvetica", fontsize=8, dir=none, arrowhead=tee];
```

### DOT syntax guardrail (critical)

`graph`, `node`, and `edge` default attributes MUST be emitted as three separate statements.

Valid:
```
graph [rankdir=LR, splines=ortho];
node [fontname="Helvetica", fontsize=10];
edge [fontname="Helvetica", fontsize=8];
```

Invalid (never do this):
```
graph [rankdir=LR, node [fontname="Helvetica"], edge [fontsize=8]];
```

---

## EXTERNAL I/O PORTS

Build from `top_level_ports[]` in the structure JSON.

cluster_ext_in — for every port where `direction == "input"`:
```
subgraph cluster_ext_in {{
    label="External Inputs";
    style=filled; color=black; fillcolor="#E6F1FB";
    <port_name> [label="<label>", shape=Mdiamond, fillcolor="#B5D4F4",
        width=<0.9 if int(port.width) > 1 else 0.7>, height=0.25];
}}
```

cluster_ext_out — for every port where `direction == "output"`:
```
subgraph cluster_ext_out {{
    label="External Outputs";
    style=filled; color=black; fillcolor="#EAF3DE";
    <port_name>_ext [label="<label>", shape=Msquare, fillcolor="#C0DD97",
        width=<0.9 if int(port.width) > 1 else 0.7>, height=0.25];
}}
```

Label formatting:
- If `int(port.width) == 1`: label = port.name (e.g. `"clk"`)
- If `int(port.width) > 1`: label = port.name + `[` + str(int(width)-1) + `:0]` (e.g. `"data_in[7:0]"`)

External output node IDs get an `_ext` suffix to avoid collision with internal signal names.

---

## SUB-MODULE CLUSTERS

Build from `instances[]` in the structure JSON. Process them **in array order** —
this order represents dataflow and controls left-to-right placement.

Each instance becomes a `subgraph cluster_<module_type>` inside `cluster_top`.
Use the `label` field from the JSON directly as the cluster header — do not compute
or translate it. The Architect has already supplied the human-readable label.

Each cluster contains **exactly one node**: the core node. No port nodes are emitted.
All edges (inter-module, external I/O, bus) connect directly to the core node.

```
subgraph cluster_top {{
    label="<module_name from JSON>";
    style=filled; color=black; fillcolor="#F1EFE8"; fontsize=14;

    // bus relay nodes go here (see BUS RELAY section)

    subgraph cluster_<module_type> {{
        label="<instances[i].label>\n<instance_name>";
        style=filled; color=black; fillcolor="<FAMILY.CLUSTER>";
        class="<sort_order> abstract_w1.25_h0.9 port_dir_LR";
        margin=12;

        <module_type>_core [label="<module_type>", shape=box3d, fillcolor="<FAMILY.CORE>",
            width=<1.0 if len≤10, 1.2 if 11-16, 1.4 if >16>, height=0.6];
    }}
}}
```

### StyleConfig overrides

If `style_map.module_styles` contains a key matching `instance_name`:
- `fillcolor` -> replaces FAMILY.CLUSTER on the cluster
- `color` -> replaces `black` on the cluster border
- `style` -> replaces `filled` on the cluster
- `shape` -> replaces `box3d` on the core node

---

## BUS RELAY PATTERN

For global signals that fan out to **3 or more** instances (typically clk, rst_n):

1. Count how many instances have each wire name in their `port_mapping` values.
2. For each global signal, create relay point nodes inside `cluster_top` but
   outside all sub-module clusters:
   ```
   <signal>_tap_<module_type> [shape=point, width=0.06, fillcolor=black];
   ```

3. Wire as a daisy chain. Bus color lookup:
   - Signal matches `clk*` -> `#4466AA`
   - Signal matches `rst*` or `reset*` -> `#AA4444`
   - Otherwise -> `#666666`
   - StyleConfig `wire_styles` override takes precedence.

4. Edge pattern:
   ```
   // trunk (tap to tap): weight=1
   <signal> -> <signal>_tap_<mod1> [color="<bus_color>", weight=1, class="bus <type>"];
   <signal>_tap_<mod1> -> <signal>_tap_<mod2> [color="<bus_color>", weight=1, class="bus <type>"];

   // taps (into each module): weight=5
   <signal>_tap_<mod1> -> <mod1>_core [color="<bus_color>", weight=5, class="bus <type>"];
   ```

Signals connecting to only 1-2 instances: wire directly, no relay nodes.

---

## INTER-MODULE EDGES

Derived from shared wire names across `instances[].port_mapping`:

When two instances both have a `port_mapping` value that matches the same
`internal_wires[].name`, draw an edge from the source instance's core node
to the destination instance's core node.

```
<src_module>_core -> <dest_module>_core [xlabel="<wire_name>",
    color="<wire_color>", weight=<3 if adjacent else 2>,
    class="crosscluster"];
```

### Wire color assignment

Use this pool, cycling by unique (source->dest) pair index:
```
#7B68EE  #6A5ACD  #CD853F  #2E8B57  #DAA520
#4682B4  #D2691E  #5F9EA0  #BC8F8F  #6B8E23
#9370DB  #E9967A  #20B2AA  #DB7093  #808000
```
Assignment: pair_index % 15.

StyleConfig `wire_styles` override: if the wire name has an entry, use its `color`
and/or `style` instead.

### Backward/feedback edges

If the source instance has a **higher** index in `instances[]` than the destination
(signal flows against dataflow order):
```
<src>_core -> <dest>_core [xlabel="<wire>", color="#C71585",
    weight=0, dir=back, class="crosscluster"];
```

---

## EXTERNAL I/O EDGES

For each `top_level_port`, find which instance port_mapping value matches the port name:

- Input: `<port_name> -> <module_type>_core [xlabel="w_<port_name>", weight=3, class="crosscluster"];`
  (If destination module is not in the first two positions in instances[], use weight=2.)
- Output: `<module_type>_core -> <port_name>_ext [xlabel="w_<port_name>", weight=<3 if source module is in the last two positions else 2>, class="crosscluster"];`

---

## INVISIBLE ORDERING EDGES

Between every adjacent pair in `instances[]` array order. These edges must be
placed **inside** `cluster_top` (after the last sub-module cluster, before the
relay nodes):
```
<module_type_A>_core -> <module_type_B>_core [style=invis, weight=10];
```

---

## PRECOMPUTED COLOR BANK

Each instance gets a color family by its 0-based index in `instances[]`:
family = `BANK[index % 16]`.

```
INDEX  CLUSTER     INPUT_PORT  CORE        OUTPUT_PORT  WIRE
-----  ----------  ----------  ----------  -----------  ----------
 0     #EEEDFE     #D8D5FA     #CECBF6     #B5B0EE      #9993D6
 1     #FAECE7     #F5D5CA     #F5C4B3     #E8A88E      #C4856B
 2     #E1F5EE     #C0EBDA     #9FE1CB     #7FD4B2      #6BBF9E
 3     #FAEEDA     #F5DEB8     #FAC775     #E8B45D      #C49644
 4     #FBEAF0     #F5D0DE     #F4C0D1     #E8A0B5      #C4808E
 5     #E6F0FA     #C4DCF5     #A3C8EF     #7AADE0      #5B93CC
 6     #F5EEE6     #E8D5C4     #DBBEA3     #C9A07A      #B0845C
 7     #E6F5F0     #C0E8DC     #99DBC8     #73CEB4      #55B89A
 8     #F0E6F5     #DCC4E8     #C8A3DB     #B47ACE      #9A5CB8
 9     #F5F0E6     #E8DCC4     #DBC8A3     #CEB47A      #B89A55
10     #E6F5F5     #C4E8E8     #A3DBDB     #7ACECE      #5CB8B8
11     #F5E6EA     #E8C4CC     #DBA3AE     #CE7A8E      #B85C6E
12     #EAF5E6     #CCE8C4     #AEDBA3     #8ECE7A      #6EB85C
13     #F0E6F0     #DCC4DC     #C8A3C8     #B47AB4      #9A5C9A
14     #F5F5E6     #E8E8C4     #DBDBA3     #CECE7A      #B8B85C
15     #E6EAF5     #C4CCE8     #A3AEDB     #7A8ECE      #5C6EB8
```

StyleConfig `module_styles` overrides replace the corresponding family value
for that specific instance.

---

## CLASS ATTRIBUTE REFERENCE

These are not rendered by Graphviz but are preserved in SVG output for
interactive viewers that support collapse/expand.

### On sub-module clusters:
```
class="<sort_order> abstract_w<W>_h<H> port_dir_LR"
```

sort_order = (instance_index + 1) * 1000

abstract size from total port count in port_mapping:
- <= 10 ports: `abstract_w1.25_h0.9`
- 11-20 ports: `abstract_w1.5_h0.9`
- > 20 ports: `abstract_w2.0_h1.2`

### On inter-module edges:
```
class="crosscluster"   // forward
class="crosscluster"   // backward
```

### On bus edges:
```
class="bus clock"   // trunk
class="bus clock"   // tap
class="bus reset"   // trunk
class="bus reset"   // tap
```

---

## VALIDATION

Before returning, verify:
- No edge uses `label`. All wire names use `xlabel`.
- Every instance produced exactly one *_core node with shape=box3d. No port nodes emitted.
- All inter-module edges connect `_core` nodes, not `_in_` or `_out_` nodes.
- Global signals (3+ fanout) use the relay pattern with taps connecting to `_core` nodes.
- Bus port labels show [N-1:0] not [N:0] for multi-bit signals.
- The digraph name matches module_name from the structure JSON.
- StyleConfig overrides are applied where present.
- DOT parses cleanly with no syntax errors.
- The first non-empty statements inside `digraph ... {{` are exactly:
  1) `graph [...]`
  2) `node [...]`
  3) `edge [...]`
- `graph [...]` does not contain nested `node [...]` or `edge [...]` blocks.
