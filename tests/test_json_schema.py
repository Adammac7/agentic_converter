"""Tests for the RTLStructure schema (agents/architect/schema.py).

Focus: invalid / malformed JSON that the Architect agent might produce.
Each test targets a single field or constraint so failures point directly
to what the LLM got wrong.
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from agents.architect.schema import (
    InternalWire,
    LogicBlock,
    Port,
    RTLStructure,
)

# ── Golden reference ────────────────────────────────────────────────────────
# Load the known-good structure so we can corrupt one field at a time.

_GOLDEN_PATH = Path(__file__).parent / "test_data" / "top_structure.json"
_GOLDEN = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))


def _golden() -> dict:
    """Return a fresh deep copy of the golden JSON."""
    return deepcopy(_GOLDEN)


# ── Sanity: golden JSON must parse ──────────────────────────────────────────

def test_golden_json_is_valid():
    """Baseline: the reference file parses without error."""
    result = RTLStructure(**_golden())
    assert result.module_name == "top"
    assert len(result.instances) == 5


# ── RTLStructure: missing required top-level fields ─────────────────────────

@pytest.mark.parametrize("field", [
    "module_name",
    "top_level_ports",
    "internal_wires",
    "instances",
])
def test_missing_top_level_field(field):
    data = _golden()
    del data[field]
    with pytest.raises(ValidationError):
        RTLStructure(**data)


# ── RTLStructure: wrong types for top-level fields ──────────────────────────

@pytest.mark.parametrize("field, bad_value", [
    ("module_name", 123),
    ("module_name", None),
    ("top_level_ports", "not a list"),
    ("internal_wires", {"wrong": "type"}),
    ("instances", "should be a list"),
])
def test_wrong_type_top_level(field, bad_value):
    data = _golden()
    data[field] = bad_value
    with pytest.raises(ValidationError):
        RTLStructure(**data)


# ── RTLStructure: empty lists where items are expected ──────────────────────

def test_empty_instances_still_parses():
    """An RTL with no sub-modules is structurally valid at the schema level."""
    data = _golden()
    data["instances"] = []
    result = RTLStructure(**data)
    assert result.instances == []


def test_empty_top_level_ports_still_parses():
    data = _golden()
    data["top_level_ports"] = []
    result = RTLStructure(**data)
    assert result.top_level_ports == []


# ── Port: missing or bad fields ────────────────────────────────────────────

@pytest.mark.parametrize("field", ["name", "direction", "width"])
def test_port_missing_field(field):
    port_data = {"name": "clk", "direction": "input", "width": "1"}
    del port_data[field]
    with pytest.raises(ValidationError):
        Port(**port_data)


@pytest.mark.parametrize("field, bad_value", [
    ("name", 42),
    ("direction", 99),
    ("width", ["not", "a", "string"]),
])
def test_port_wrong_type(field, bad_value):
    port_data = {"name": "clk", "direction": "input", "width": "1"}
    port_data[field] = bad_value
    with pytest.raises(ValidationError):
        Port(**port_data)


# ── LogicBlock: missing or bad fields ───────────────────────────────────────

def test_logic_block_missing_port_mapping():
    """The #1 LLM failure mode: omitting port_mapping entirely."""
    with pytest.raises(ValidationError):
        LogicBlock(instance_name="u_ctrl", module_type="ctrl", label="Controller", description="Ctrl block")


def test_logic_block_missing_label():
    """LLM omits the human-readable label field."""
    with pytest.raises(ValidationError):
        LogicBlock(instance_name="u_ctrl", module_type="ctrl", description="Ctrl block", port_mapping={"clk": "clk"})


def test_logic_block_missing_description():
    """LLM omits the functional description field."""
    with pytest.raises(ValidationError):
        LogicBlock(instance_name="u_ctrl", module_type="ctrl", label="Controller", port_mapping={"clk": "clk"})


def test_logic_block_port_mapping_wrong_type():
    """port_mapping must be a flat dict, not a list."""
    with pytest.raises(ValidationError):
        LogicBlock(
            instance_name="u_ctrl",
            module_type="ctrl",
            label="Controller",
            description="Ctrl block",
            port_mapping=[("clk", "clk")],
        )


def test_logic_block_missing_instance_name():
    with pytest.raises(ValidationError):
        LogicBlock(module_type="ctrl", label="Controller", description="Ctrl block", port_mapping={"clk": "clk"})


def test_logic_block_missing_module_type():
    with pytest.raises(ValidationError):
        LogicBlock(instance_name="u_ctrl", label="Controller", description="Ctrl block", port_mapping={"clk": "clk"})


def test_logic_block_empty_port_mapping_parses():
    """Empty port_mapping is schema-valid (auditor catches the semantic error)."""
    block = LogicBlock(
        instance_name="u_ctrl", module_type="ctrl", label="Controller", description="Ctrl block", port_mapping={}
    )
    assert block.port_mapping == {}


def test_logic_block_nested_port_mapping_rejected():
    """port_mapping values must be strings, not nested dicts."""
    with pytest.raises(ValidationError):
        LogicBlock(
            instance_name="u_ctrl",
            module_type="ctrl",
            label="Controller",
            description="Ctrl block",
            port_mapping={"clk": {"wire": "clk", "width": 1}},
        )


# ── InternalWire: missing or bad fields ─────────────────────────────────────

@pytest.mark.parametrize("field", ["name", "width"])
def test_internal_wire_missing_field(field):
    wire_data = {"name": "w_start", "width": "1"}
    del wire_data[field]
    with pytest.raises(ValidationError):
        InternalWire(**wire_data)


# ── Corrupt a single instance inside the golden JSON ────────────────────────

def test_instance_with_port_mapping_removed():
    """Simulates the LLM dropping port_mapping from one instance."""
    data = _golden()
    del data["instances"][0]["port_mapping"]
    with pytest.raises(ValidationError):
        RTLStructure(**data)


def test_instance_with_extra_unknown_field():
    """Extra fields should be silently ignored (Pydantic default)."""
    data = _golden()
    data["instances"][0]["unknown_random_field"] = "should be ignored"
    result = RTLStructure(**data)
    assert len(result.instances) == 5


def test_port_with_int_width_rejected():
    """LLMs sometimes return width as int instead of str. Pydantic rejects it."""
    data = _golden()
    data["top_level_ports"][0]["width"] = 1
    with pytest.raises(ValidationError):
        RTLStructure(**data)


def test_duplicate_module_type_rejected():
    """When the same RTL module is instantiated twice, the LLM must derive a unique
    module_type per instance — duplicates would collide as DOT node IDs."""
    data = _golden()
    data["instances"][1]["module_type"] = data["instances"][0]["module_type"]
    with pytest.raises(ValidationError):
        RTLStructure(**data)
