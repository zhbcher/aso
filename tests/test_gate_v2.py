"""Tests for gate.skill v2 — delta operations, risk consistency, change budget."""

import importlib.util
import os
from importlib.machinery import SourceFileLoader

_SKILL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def _load_gate():
    """Lazy-load gate.skill to avoid pytest import caching issues."""
    path = os.path.join(_SKILL_DIR, "gate.skill")
    spec = importlib.util.spec_from_file_location(
        "gate_loader", path,
        loader=SourceFileLoader("gate_loader", path)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def verify(candidate, target):
    return _load_gate().verify(candidate, target)


def _make_v1_candidate(risk="low"):
    return {
        "type": "aso_optimization",
        "mechanism": "add_instruction",
        "changes": [{"action": "modify_skill_file", "file_path": "planner.skill", "new_content": "x = 1"}],
        "risk": risk,
        "description": "Add verification step to planner workflow",
        "expected_improvement": "reduce failure rate",
    }


def _make_delta_op(type="instruction_add", reason="Reason for change", before=None, after="new content"):
    return {
        "type": type,
        "target": {"file": "planner.skill", "selector_type": "text_section", "selector": "workflow"},
        "before": before,
        "after": after,
        "reason": reason,
    }


_SENTINEL = object()


def _make_v2_candidate(operations=None, risk="low", rollback=_SENTINEL):
    if operations is None:
        operations = [_make_delta_op()]
    if rollback is _SENTINEL:
        rollback = {"type": "reverse_delta", "notes": "Simple reverse"}
    return {
        "delta_id": "delta-001",
        "type": "aso_optimization",
        "mechanism": "delta",
        "changes": [],
        "risk": risk,
        "description": "Add verification step to planner workflow",
        "operations": operations,
        "rollback_plan": rollback,
    }


class TestGateV2Delta:
    def test_v2_delta_passes(self):
        result = verify(_make_v2_candidate(), "planner")
        assert result["passed"], result["summary"]

    def test_v2_unknown_operation_type(self):
        ops = [_make_delta_op(type="unknown_type")]
        result = verify(_make_v2_candidate(operations=ops), "planner")
        assert not result["passed"]

    def test_v2_reason_too_short(self):
        ops = [_make_delta_op(reason="Short")]
        result = verify(_make_v2_candidate(operations=ops), "planner")
        assert not result["passed"]

    def test_v2_missing_target_file(self):
        op = {"type": "instruction_add", "target": {"selector_type": "text", "selector": "s"},
              "before": None, "after": "x", "reason": "Reason for change"}
        result = verify(_make_v2_candidate(operations=[op]), "planner")
        assert not result["passed"]

    def test_v2_missing_rollback(self):
        result = verify(_make_v2_candidate(rollback=None), "planner")
        assert not result["passed"]

    def test_v2_invalid_rollback_type(self):
        result = verify(_make_v2_candidate(rollback={"type": "invalid"}), "planner")
        assert not result["passed"]

    def test_v2_risk_consistency_low_risk_3_ops(self):
        ops = [_make_delta_op() for _ in range(3)]
        result = verify(_make_v2_candidate(operations=ops, risk="low"), "planner")
        assert not result["passed"]

    def test_v2_risk_consistency_high_risk_1_op(self):
        ops = [_make_delta_op()]
        cand = _make_v2_candidate(operations=ops, risk="high")
        cand["expected_improvement"] = "Major improvement expected"
        result = verify(cand, "planner")
        assert result["passed"]

    def test_v2_change_budget_exceeds_max_ops(self):
        ops = [_make_delta_op() for _ in range(6)]
        result = verify(_make_v2_candidate(operations=ops), "planner")
        assert not result["passed"]

    def test_v2_add_op_before_must_be_null(self):
        op = _make_delta_op(type="instruction_add", before="should not exist")
        result = verify(_make_v2_candidate(operations=[op]), "planner")
        assert not result["passed"]

    def test_v2_remove_op_after_must_be_null(self):
        op = _make_delta_op(type="instruction_remove", before="old text", after="should not exist")
        result = verify(_make_v2_candidate(operations=[op]), "planner")
        assert not result["passed"]

    def test_v1_still_passes(self):
        """Ensure v1 candidates still work."""
        result = verify(_make_v1_candidate(), "planner")
        assert result["passed"], result["summary"]

    def test_gate_checks_contain_all(self):
        result = verify(_make_v2_candidate(), "planner")
        # Should have: structure, scope_lock, risk, mechanism, delta_operations,
        #              delta_risk_consistency, delta_rollback, change_budget
        names = [c["name"] for c in result["checks"]]
        assert "delta_operations" in names
        assert "delta_risk_consistency" in names
        assert "delta_rollback" in names
        assert "change_budget" in names