"""Tests for the Architect → Auditor retry loop in the orchestrator.

These tests mock the agent functions so we can inject specific failure
scenarios and verify that the retry loop in rtl_to_json_to_dot behaves
correctly: retries on bad JSON, passes feedback, and gives up after
MAX_ATTEMPTS.

No LLM calls are made — all agent responses are controlled by the test.

Run:
    python -m pytest tests/test_json_retry_loop.py -v -s
    (use -s to see the retry loop print statements in real time)
"""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from agents.architect.schema import RTLStructure
from agents.auditor.schema import AuditReport
from agents.stylist.schema import StyleConfig
from orchestrator.orchestrator import rtl_to_json_to_dot, MAX_ATTEMPTS


# ── Fixtures ────────────────────────────────────────────────────────────────

_GOLDEN_PATH = (
    Path(__file__).parent / "test_data" / "top_structure.json"
)
_GOLDEN = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))

_RTL_PATH = (
    Path(__file__).parent / "test_data" / "top.sv"
)
_RTL_CODE = _RTL_PATH.read_text(encoding="utf-8")


def _good_rtl_structure() -> RTLStructure:
    """Return a valid RTLStructure from the golden JSON."""
    return RTLStructure(**deepcopy(_GOLDEN))


def _bad_rtl_structure_missing_ports() -> RTLStructure:
    """Return an RTLStructure where u_ctrl is missing most port mappings."""
    data = deepcopy(_GOLDEN)
    data["instances"][0]["port_mapping"] = {"clk": "clk"}  # missing 7 ports
    return RTLStructure(**data)


def _passing_audit() -> AuditReport:
    return AuditReport(
        is_valid=True,
        missing_items=[],
        hallucinations=[],
        feedback="All checks passed.",
    )


def _failing_audit(missing: list[str], feedback: str) -> AuditReport:
    return AuditReport(
        is_valid=False,
        missing_items=missing,
        hallucinations=[],
        feedback=feedback,
    )


def _empty_style() -> StyleConfig:
    return StyleConfig(module_styles={}, wire_styles={})


def _make_state(run_dir: Path, rtl_code: str = _RTL_CODE) -> dict:
    (run_dir / "iterations").mkdir(parents=True, exist_ok=True)
    return {
        "rtl_code": rtl_code,
        "user_style_prompt": "no styling",
        "user_edit_prompt": None,
        "verified_json": None,
        "style_map": None,
        "dot_source": None,
        "svg_output": None,
        "session_output_dir": str(run_dir.parent),
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
    }


# ── Patch targets ───────────────────────────────────────────────────────────
_ARCH = "orchestrator.orchestrator.run_architect_agent"
_AUDIT = "orchestrator.orchestrator.run_auditor_agent"
_STYLE = "orchestrator.orchestrator.run_stylist_agent"
_DOT = "orchestrator.orchestrator.run_dot_compiler_agent"


# ── Tests ───────────────────────────────────────────────────────────────────

class TestRetryOnAuditorRejection:
    """Auditor rejects the JSON, loop retries with feedback, then succeeds."""

    def test_fails_once_then_passes(self, tmp_path: Path):
        """Attempt 1: auditor rejects (missing ports). Attempt 2: passes."""
        bad_struct = _bad_rtl_structure_missing_ports()
        good_struct = _good_rtl_structure()

        with (
            patch(_ARCH, side_effect=[bad_struct, good_struct]) as mock_arch,
            patch(_AUDIT, side_effect=[
                _failing_audit(
                    missing=["u_ctrl.rst_n", "u_ctrl.enable"],
                    feedback="u_ctrl is missing ports: rst_n, enable, cfg_mode, start, done, mem_req, mem_addr",
                ),
                _passing_audit(),
            ]) as mock_audit,
            patch(_STYLE, return_value=_empty_style()),
            patch(_DOT, return_value="digraph top {}"),
        ):
            result = rtl_to_json_to_dot(_make_state(run_dir=tmp_path / "run"))

        # Architect was called twice (attempt 1 failed, attempt 2 passed)
        assert mock_arch.call_count == 2
        assert mock_audit.call_count == 2

        # Second architect call should have received feedback
        second_call_kwargs = mock_arch.call_args_list[1]
        feedback_arg = second_call_kwargs[1].get("feedback", second_call_kwargs[0][1] if len(second_call_kwargs[0]) > 1 else "")
        assert "CRITICAL FEEDBACK FROM AUDITOR" in feedback_arg

        # Pipeline produced output
        assert result["verified_json"] is not None
        assert result["dot_source"] == "digraph top {}"

    def test_fails_twice_then_passes(self, tmp_path: Path):
        """Attempts 1 & 2: auditor rejects. Attempt 3: passes."""
        bad = _bad_rtl_structure_missing_ports()
        good = _good_rtl_structure()
        fail = _failing_audit(["u_ctrl.rst_n"], "missing ports on u_ctrl")

        with (
            patch(_ARCH, side_effect=[bad, bad, good]) as mock_arch,
            patch(_AUDIT, side_effect=[fail, fail, _passing_audit()]) as mock_audit,
            patch(_STYLE, return_value=_empty_style()),
            patch(_DOT, return_value="digraph top {}"),
        ):
            result = rtl_to_json_to_dot(_make_state(run_dir=tmp_path / "run"))

        assert mock_arch.call_count == 3
        assert mock_audit.call_count == 3
        assert result["verified_json"] is not None


class TestRetryOnArchitectException:
    """Architect raises an exception, loop catches it and retries."""

    def test_architect_crashes_once_then_recovers(self, tmp_path: Path):
        """Attempt 1: architect throws. Attempt 2: succeeds."""
        good = _good_rtl_structure()

        with (
            patch(_ARCH, side_effect=[
                ValueError("LLM returned unparseable garbage"),
                good,
            ]) as mock_arch,
            patch(_AUDIT, return_value=_passing_audit()) as mock_audit,
            patch(_STYLE, return_value=_empty_style()),
            patch(_DOT, return_value="digraph top {}"),
        ):
            result = rtl_to_json_to_dot(_make_state(run_dir=tmp_path / "run"))

        # Architect called twice, but auditor only once (skipped on crash)
        assert mock_arch.call_count == 2
        assert mock_audit.call_count == 1
        assert result["verified_json"] is not None

    def test_architect_crashes_all_attempts(self, tmp_path: Path):
        """Architect throws on every attempt → pipeline raises RuntimeError."""
        with (
            patch(_ARCH, side_effect=ValueError("bad output")) as mock_arch,
            patch(_AUDIT) as mock_audit,
        ):
            with pytest.raises(RuntimeError, match="could not produce valid JSON"):
                rtl_to_json_to_dot(_make_state(run_dir=tmp_path / "run"))

        assert mock_arch.call_count == MAX_ATTEMPTS
        assert mock_audit.call_count == 0  # never reached


class TestAllAttemptsExhausted:
    """Auditor rejects every attempt → pipeline gives up."""

    def test_max_attempts_then_raises(self, tmp_path: Path):
        bad = _bad_rtl_structure_missing_ports()
        fail = _failing_audit(["u_ctrl.rst_n"], "still missing ports")

        with (
            patch(_ARCH, return_value=bad) as mock_arch,
            patch(_AUDIT, return_value=fail) as mock_audit,
        ):
            with pytest.raises(RuntimeError, match="could not produce valid JSON"):
                rtl_to_json_to_dot(_make_state(run_dir=tmp_path / "run"))

        assert mock_arch.call_count == MAX_ATTEMPTS
        assert mock_audit.call_count == MAX_ATTEMPTS


class TestPassesOnFirstAttempt:
    """Happy path: architect nails it on attempt 1."""

    def test_no_retries_needed(self, tmp_path: Path):
        good = _good_rtl_structure()

        with (
            patch(_ARCH, return_value=good) as mock_arch,
            patch(_AUDIT, return_value=_passing_audit()) as mock_audit,
            patch(_STYLE, return_value=_empty_style()),
            patch(_DOT, return_value="digraph top {}"),
        ):
            result = rtl_to_json_to_dot(_make_state(run_dir=tmp_path / "run"))

        assert mock_arch.call_count == 1
        assert mock_audit.call_count == 1
        assert result["verified_json"]["module_name"] == "top"
        assert len(result["verified_json"]["instances"]) == 5


class TestFeedbackContent:
    """Verify that the feedback string passed to the architect contains
    the auditor's message so the LLM knows what to fix."""

    def test_auditor_feedback_forwarded_to_architect(self, tmp_path: Path):
        bad = _bad_rtl_structure_missing_ports()
        good = _good_rtl_structure()
        specific_feedback = "u_ctrl is missing port mappings for rst_n, enable, cfg_mode"

        with (
            patch(_ARCH, side_effect=[bad, good]) as mock_arch,
            patch(_AUDIT, side_effect=[
                _failing_audit(["u_ctrl.rst_n"], specific_feedback),
                _passing_audit(),
            ]),
            patch(_STYLE, return_value=_empty_style()),
            patch(_DOT, return_value="digraph top {}"),
        ):
            rtl_to_json_to_dot(_make_state(run_dir=tmp_path / "run"))

        # The second call to the architect should include the auditor's feedback
        second_call = mock_arch.call_args_list[1]
        # feedback is the second positional arg or keyword arg
        if len(second_call[0]) > 1:
            feedback_passed = second_call[0][1]
        else:
            feedback_passed = second_call[1].get("feedback", "")

        assert specific_feedback in feedback_passed
