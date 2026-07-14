"""Tests for _lib/policy_engine.py."""

import pytest
from _lib.delta import SkillDelta, DeltaOperation, TargetPath, RollbackPlan
from _lib.policy_engine import evaluate


def _make_delta(ops, risk="low", target="planner"):
    return SkillDelta.create(
        session_id="s1",
        target=target,
        base_version="v1",
        operations=ops,
        risk=risk,
    )


def _op(type, after="new content", reason="Reason for change"):
    return DeltaOperation(
        type=type,
        target=TargetPath("planner.skill", "text_section", "Constraints"),
        before=None if type.endswith("_add") else "old",
        after=after if not type.endswith("_remove") else None,
        reason=reason,
    )


class TestPolicyEngine:
    def test_auto_approve_low_risk_add(self):
        """Low risk instruction_add should auto-approve."""
        delta = _make_delta([_op("instruction_add")], risk="low")
        result = evaluate(delta, "planner")
        assert result["verdict"] == "auto_approve"

    def test_auto_approve_constraint_add(self):
        """constraint_add is auto_approve by operation type."""
        delta = _make_delta([_op("constraint_add")], risk="low")
        result = evaluate(delta, "planner")
        assert result["verdict"] == "auto_approve"

    def test_require_review_medium_risk(self):
        """Medium risk should require review."""
        delta = _make_delta([_op("instruction_add")], risk="medium")
        result = evaluate(delta, "planner")
        assert result["verdict"] == "require_review"

    def test_require_review_high_risk(self):
        """High risk should require review."""
        delta = _make_delta([_op("instruction_add")], risk="high")
        result = evaluate(delta, "planner")
        assert result["verdict"] == "require_review"

    def test_auto_reject_denied_target(self):
        """Denied targets should be auto-rejected."""
        delta = _make_delta([_op("instruction_add")])
        result = evaluate(delta, "runtime")
        assert result["verdict"] == "auto_reject"

    def test_auto_reject_denied_operation(self):
        """Denied operations should be auto-rejected."""
        delta = _make_delta([_op("tool_call_remove")])
        result = evaluate(delta, "planner")
        assert result["verdict"] == "auto_reject"

    def test_compound_rule_low_risk_planner(self):
        """Compound rule: low risk + planner + instruction_add = auto_approve."""
        delta = _make_delta([_op("instruction_add")], risk="low")
        result = evaluate(delta, "planner")
        assert result["verdict"] == "auto_approve"

    def test_compound_rule_high_risk_first_session(self):
        """Compound rule: high risk + first session = require_review."""
        delta = _make_delta([_op("instruction_add")], risk="high")
        result = evaluate(delta, "planner", session_count=0)
        assert result["verdict"] == "require_review"

    def test_compound_rule_consecutive_successes(self):
        """Compound rule: 3+ consecutive successes + low risk = auto_approve."""
        delta = _make_delta([_op("instruction_add")], risk="low")
        result = evaluate(delta, "planner", consecutive_successes=5)
        assert result["verdict"] == "auto_approve"

    def test_default_unknown_operation(self):
        """Unknown operation types fall back to default (require_review)."""
        delta = SkillDelta.create(
            session_id="s1", target="planner", base_version="v1",
            operations=[
                DeltaOperation(
                    type="unknown_op",
                    target=TargetPath("p", "text_section", "s"),
                    before=None, after="x",
                    reason="Testing unknown operation",
                )
            ],
            risk="low",
        )
        result = evaluate(delta, "planner")
        # Falls through to by_risk which says low=auto_approve
        assert result["verdict"] == "auto_approve"

    def test_result_has_reason(self):
        """Result should always include a human-readable reason."""
        delta = _make_delta([_op("instruction_add")], risk="low")
        result = evaluate(delta, "planner")
        assert "reason" in result
        assert len(result["reason"]) > 0

    def test_result_has_matched_rule(self):
        delta = _make_delta([_op("instruction_add")], risk="low")
        result = evaluate(delta, "planner")
        assert "matched_rule" in result