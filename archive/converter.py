#!/usr/bin/env python3
"""
RTL to Yosys JSON converter
Usage: python converter.py <input.v> [output.json] [--top <module>]
"""

import subprocess
import sys
import os
import json


def rtl_to_yosys_json(input_file, output_file=None, top_module="top"):
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Default output filename
    if output_file is None:
        base = os.path.splitext(os.path.basename(input_file))[0]
        output_dir = os.path.join(os.path.dirname(os.path.abspath(input_file)), "json_output")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"{base}.json")

    ext = os.path.splitext(input_file)[1].lower()

    # Build yosys commands based on file type
    if ext in [".v", ".sv"]:
        read_cmd = f"read_verilog -sv {input_file}"
    elif ext in [".vhd", ".vhdl"]:
        read_cmd = f"read_vhdl {input_file}"
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    yosys_script = (
        f"{read_cmd}; "
        f"hierarchy -check -top {top_module}; "
        f"proc; "
        f"flatten; "
        f"write_json {output_file}"
    )

    print(f"Converting {input_file} → {output_file} ...")

    result = subprocess.run(
        ["yosys", "-p", yosys_script],
        capture_output=True,
        text=True
    )

    if result.stdout:
        print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(f"Yosys failed:\n{result.stderr}")

    print("Done! Validating JSON...")

    # Validate and pretty-print the output
    with open(output_file, "r") as f:
        data = json.load(f)

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    # Print a small summary
    modules = data.get("modules", {})
    print(f"  Modules found: {list(modules.keys())}")
    for mod_name, mod in modules.items():
        ports = list(mod.get("ports", {}).keys())
        cells = mod.get("cells", {})
        print(f"  [{mod_name}] ports: {ports}, cells: {len(cells)}")

    print(f"\nJSON written to: {output_file}")
    return output_file


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert RTL to Yosys JSON")
    parser.add_argument("input_file", help="Input RTL file (.v, .sv, .vhd, .vhdl)")
    parser.add_argument("output_file", nargs="?", help="Output JSON file (default: input basename + .json)")
    parser.add_argument("--top", default="top", help="Top module name (default: top)")
    args = parser.parse_args()

    try:
        rtl_to_yosys_json(args.input_file, args.output_file, top_module=args.top)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
