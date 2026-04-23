"""End-to-end tests for LLM self-correction via the Architect → Auditor retry loop.

Strategy:
    1. Feed good RTL (top.sv) into the pipeline.
    2. On the FIRST attempt, intercept the Architect's output and replace it
       with a programmatically corrupted JSON.
    3. The real Auditor (LLM) inspects the corrupted JSON against the good RTL
       and should flag it as invalid with specific feedback.
    4. On attempt 2+, the real Architect (LLM) runs with the auditor's feedback
       and should produce a corrected JSON that passes.

This tests the LLM's ability to self-correct, not just the retry mechanism.
Requires a valid API key in .env. Each test makes 2-4 LLM calls.

Run:
    python -m pytest tests/test_json_llm_self_correction.py -v -s -m slow
    (use -s to watch the retry loop in real time)
"""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch, wraps

import pytest

from agents.converter_agent.tools.json_schema import RTLStructure
from agents.converter_agent.rtl_to_json_agent import run_architect_agent
from agents.converter_agent.rtl_and_json_auditor_agent import run_auditor_agent
from orchestrator.orchestrator import rtl_to_json_to_dot


# ── Mark all tests in this file as slow (LLM calls) ────────────────────────

pytestmark = pytest.mark.slow


# ── Test data ───────────────────────────────────────────────────────────────

_GOLDEN_PATH = (
    Path(__file__).parent.parent
    / "agents" / "converter_agent" / "data" / "processed" / "top_structure.json"
)
_GOLDEN = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))

_RTL_PATH = (
    Path(__file__).parent.parent
    / "agents" / "converter_agent" / "data" / "raw" / "top.sv"
)
_RTL_CODE = _RTL_PATH.read_text(encoding="utf-8")


def _make_state() -> dict:
    return {
        "rtl_code": _RTL_CODE,
        "user_style_prompt": "no styling",
        "user_edit_prompt": None,
        "verified_json": None,
        "style_map": None,
        "dot_source": None,
        "svg_output": None,
    }


# ── Corruption helpers ──────────────────────────────────────────────────────
# Each returns a corrupted RTLStructure. Add new corruption types here
# to expand test coverage.


def corrupt_missing_ports(golden: dict) -> RTLStructure:
    """Remove most port mappings from u_ctrl — the auditor should catch this."""
    data = deepcopy(golden)
    # Keep only clk, drop the other 7 ports
    data["instances"][0]["port_mapping"] = {"clk": "clk"}
    return RTLStructure(**data)


def corrupt_hallucinated_instance(golden: dict) -> RTLStructure:
    """Add a fake instance that doesn't exist in the RTL."""
    data = deepcopy(golden)
    data["instances"].append({
        "instance_name": "u_fake_dma",
        "module_type": "dma_controller",
        "port_mapping": {"clk": "clk", "rst_n": "rst_n", "data": "w_fake"},
    })
    return RTLStructure(**data)


def corrupt_wrong_wire_names(golden: dict) -> RTLStructure:
    """Replace wire names in u_datapath with incorrect ones."""
    data = deepcopy(golden)
    dp = data["instances"][1]["port_mapping"]
    dp["start"] = "w_wrong_signal"
    dp["data_out"] = "w_nonexistent_wire"
    return RTLStructure(**data)


def corrupt_missing_instance(golden: dict) -> RTLStructure:
    """Remove u_fifo entirely — auditor should flag the missing instance."""
    data = deepcopy(golden)
    data["instances"] = [i for i in data["instances"] if i["instance_name"] != "u_fifo"]
    return RTLStructure(**data)


# ── Architect wrapper factory ───────────────────────────────────────────────

def _make_corrupted_architect(corrupt_fn):
    """
    Returns a wrapper around run_architect_agent that:
      - On call 1: ignores the LLM and returns the corrupted RTLStructure
      - On call 2+: calls the real LLM so it can self-correct with feedback
    Also tracks call count and what feedback was received.
    """
    call_log = {"count": 0, "feedbacks": []}

    def wrapper(rtl_code, feedback=""):
        call_log["count"] += 1
        call_log["feedbacks"].append(feedback)

        if call_log["count"] == 1:
            print(f"    [TEST] Injecting corrupted JSON on attempt 1")
            return corrupt_fn(deepcopy(_GOLDEN))
        else:
            print(f"    [TEST] Real LLM running with feedback on attempt {call_log['count']}")
            return run_architect_agent(rtl_code, feedback=feedback)

    return wrapper, call_log


# ── Tests ───────────────────────────────────────────────────────────────────

class TestLLMSelfCorrectionMissingPorts:
    """Inject JSON with missing port mappings → auditor flags it → LLM fixes it."""

    def test_recovers_from_missing_ports(self):
        wrapper, log = _make_corrupted_architect(corrupt_missing_ports)

        with patch(
            "orchestrator.orchestrator.run_architect_agent",
            side_effect=wrapper,
        ):
            result = rtl_to_json_to_dot(_make_state())

        # The LLM should have needed at least 2 attempts
        assert log["count"] >= 2, "Expected retry — auditor should have rejected attempt 1"

        # Attempt 2+ should have received feedback mentioning the missing ports
        assert any("CRITICAL FEEDBACK" in fb for fb in log["feedbacks"][1:]), \
            "Architect didn't receive auditor feedback on retry"

        # Final output should be valid
        assert result["verified_json"] is not None
        final = RTLStructure(**result["verified_json"])
        u_ctrl = next(i for i in final.instances if i.instance_name == "u_ctrl")
        assert len(u_ctrl.port_mapping) > 1, "u_ctrl should have its ports restored"


class TestLLMSelfCorrectionHallucinatedInstance:
    """Inject a fake instance → auditor flags hallucination → LLM removes it."""

    def test_recovers_from_hallucinated_instance(self):
        wrapper, log = _make_corrupted_architect(corrupt_hallucinated_instance)

        with patch(
            "orchestrator.orchestrator.run_architect_agent",
            side_effect=wrapper,
        ):
            result = rtl_to_json_to_dot(_make_state())

        assert log["count"] >= 2
        assert result["verified_json"] is not None

        # The fake instance should not be in the final output
        final = RTLStructure(**result["verified_json"])
        instance_names = [i.instance_name for i in final.instances]
        assert "u_fake_dma" not in instance_names, \
            "Hallucinated instance should have been removed by the LLM"


class TestLLMSelfCorrectionWrongWires:
    """Inject wrong wire names → auditor flags them → LLM corrects them."""

    def test_recovers_from_wrong_wire_names(self):
        wrapper, log = _make_corrupted_architect(corrupt_wrong_wire_names)

        with patch(
            "orchestrator.orchestrator.run_architect_agent",
            side_effect=wrapper,
        ):
            result = rtl_to_json_to_dot(_make_state())

        assert log["count"] >= 2
        assert result["verified_json"] is not None

        # The wrong wire names should be fixed
        final = RTLStructure(**result["verified_json"])
        dp = next(i for i in final.instances if i.instance_name == "u_datapath")
        assert dp.port_mapping.get("start") == "w_start", \
            f"Expected 'w_start', got '{dp.port_mapping.get('start')}'"
        assert "w_nonexistent_wire" not in dp.port_mapping.values(), \
            "Fake wire name should have been corrected"


class TestLLMSelfCorrectionMissingInstance:
    """Remove an instance entirely → auditor flags it → LLM adds it back."""

    def test_recovers_from_missing_instance(self):
        wrapper, log = _make_corrupted_architect(corrupt_missing_instance)

        with patch(
            "orchestrator.orchestrator.run_architect_agent",
            side_effect=wrapper,
        ):
            result = rtl_to_json_to_dot(_make_state())

        assert log["count"] >= 2
        assert result["verified_json"] is not None

        # u_fifo should be back in the final output
        final = RTLStructure(**result["verified_json"])
        instance_names = [i.instance_name for i in final.instances]
        assert "u_fifo" in instance_names, \
            "u_fifo should have been restored by the LLM"
        assert len(final.instances) == 5, \
            f"Expected 5 instances, got {len(final.instances)}"
