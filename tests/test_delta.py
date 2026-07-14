"""Tests for _lib/delta.py — SkillDelta types and apply_delta."""

import json
import pytest
from _lib.delta import (
    SkillDelta, DeltaOperation, TargetPath, RollbackPlan,
    apply_delta, apply_delta_to_file, reverse_operation,
)


class TestTargetPath:
    def test_from_to_dict(self):
        tp = TargetPath(file="planner.skill", selector_type="text_section", selector="workflow.step3")
        d = tp.to_dict()
        assert d["file"] == "planner.skill"
        tp2 = TargetPath.from_dict(d)
        assert tp2.file == tp.file
        assert tp2.selector_type == tp.selector_type


class TestDeltaOperation:
    def test_validate_add_ok(self):
        op = DeltaOperation(
            type="instruction_add",
            target=TargetPath("planner.skill", "text_section", "workflow"),
            before=None,
            after="New instruction",
            reason="Need to add verification step",
        )
        assert op.validate() == []

    def test_validate_add_with_before_fails(self):
        op = DeltaOperation(
            type="instruction_add",
            target=TargetPath("planner.skill", "text_section", "workflow"),
            before="Old text",
            after="New text",
            reason="Test",
        )
        errors = op.validate()
        assert len(errors) > 0

    def test_validate_remove_ok(self):
        op = DeltaOperation(
            type="instruction_remove",
            target=TargetPath("planner.skill", "text_section", "workflow"),
            before="Old text",
            after=None,
            reason="Remove redundant instruction",
        )
        assert op.validate() == []

    def test_validate_reason_too_short(self):
        op = DeltaOperation(
            type="instruction_modify",
            target=TargetPath("planner.skill", "text_section", "workflow"),
            before="Old",
            after="New",
            reason="Short",
        )
        errors = op.validate()
        assert any("reason" in e for e in errors)


class TestSkillDelta:
    def test_create_and_validate(self):
        op = DeltaOperation(
            type="instruction_add",
            target=TargetPath("planner.skill", "text_section", "Constraints"),
            before=None,
            after="After turn 8, force context compression",
            reason="Context window overflow in long conversations",
        )
        rp = RollbackPlan(type="reverse_delta", notes="Simple reverse")
        delta = SkillDelta.create(
            session_id="2026-07-14-001",
            target="planner",
            base_version="v3",
            operations=[op],
            risk="low",
            generation_confidence=0.85,
            expected_effect="reduce multi-turn failure rate",
            change_rationale="Missing compression step",
            rollback_plan=rp,
        )
        assert delta.delta_id.startswith("delta-")
        assert delta.session_id == "2026-07-14-001"
        result = delta.validate()
        assert result["valid"], result["errors"]

    def test_serialize_roundtrip(self):
        op = DeltaOperation(
            type="instruction_modify",
            target=TargetPath("planner.skill", "text_section", "workflow.step3"),
            before="Execute tool call",
            after="Verify params then execute",
            reason="Add parameter validation",
        )
        rp = RollbackPlan(type="reverse_delta", notes="Simple reverse")
        delta = SkillDelta.create(
            session_id="s1", target="planner", base_version="v2",
            operations=[op], rollback_plan=rp,
        )
        data = delta.to_dict()
        delta2 = SkillDelta.from_dict(data)
        assert delta2.delta_id == delta.delta_id
        assert delta2.operations[0].type == "instruction_modify"
        assert delta2.rollback_plan.type == "reverse_delta"

    def test_to_json(self):
        op = DeltaOperation(
            type="constraint_add",
            target=TargetPath("planner.skill", "text_section", "Constraints"),
            before=None,
            after="Verify before execution",
            reason="Add verification constraint",
        )
        delta = SkillDelta.create(
            session_id="s1", target="planner", base_version="v1",
            operations=[op],
        )
        js = delta.to_json()
        parsed = json.loads(js)
        assert parsed["delta_id"] == delta.delta_id

    def test_too_many_operations(self):
        ops = [
            DeltaOperation(type="instruction_add", target=TargetPath("p", "text_section", "s"),
                           before=None, after="X", reason="R" * 10)
            for _ in range(6)
        ]
        delta = SkillDelta.create(session_id="s1", target="p", base_version="v1", operations=ops)
        result = delta.validate()
        assert not result["valid"]
        assert any("too many" in e for e in result["errors"])

    def test_low_risk_with_3_ops_fails(self):
        ops = [
            DeltaOperation(type="instruction_add", target=TargetPath("p", "text_section", "s"),
                           before=None, after="X", reason="R" * 10)
            for _ in range(3)
        ]
        delta = SkillDelta.create(session_id="s1", target="p", base_version="v1", operations=ops, risk="low")
        result = delta.validate()
        assert not result["valid"]
        assert any("low risk" in e for e in result["errors"])


class TestApplyDelta:
    SAMPLE_SKILL = """# Planner Skill

## Overview
This is the planner skill.

## Workflow
### step1
Gather requirements.

### step2
Execute tool call.

### step3
Return result.

## Constraints
- Must be fast.
- Must be accurate.
"""

    def test_instruction_add(self):
        op = DeltaOperation(
            type="instruction_add",
            target=TargetPath("planner.skill", "text_section", "Constraints"),
            before=None,
            after="- After turn 8, compress context.",
            reason="Add compression constraint",
        )
        result = apply_delta(self.SAMPLE_SKILL, op)
        assert "- After turn 8, compress context." in result
        assert "- Must be fast." in result  # Original preserved

    def test_instruction_modify(self):
        op = DeltaOperation(
            type="instruction_modify",
            target=TargetPath("planner.skill", "text_section", "Constraints"),
            before="- Must be fast.",
            after="- Must be very fast (< 500ms).",
            reason="Tighten speed requirement",
        )
        result = apply_delta(self.SAMPLE_SKILL, op)
        assert "- Must be very fast (< 500ms)." in result
        assert "- Must be fast." not in result

    def test_instruction_remove(self):
        op = DeltaOperation(
            type="instruction_remove",
            target=TargetPath("planner.skill", "text_section", "Constraints"),
            before="- Must be accurate.",
            after=None,
            reason="Remove redundant constraint",
        )
        result = apply_delta(self.SAMPLE_SKILL, op)
        assert "- Must be accurate." not in result
        assert "- Must be fast." in result

    def test_workflow_modify(self):
        op = DeltaOperation(
            type="instruction_modify",
            target=TargetPath("planner.skill", "workflow_node", "step2"),
            before="Execute tool call.",
            after="Verify parameters, then execute tool call.",
            reason="Add verification before execution",
        )
        result = apply_delta(self.SAMPLE_SKILL, op)
        assert "Verify parameters, then execute tool call." in result
        assert "Execute tool call." not in result

    def test_workflow_add(self):
        op = DeltaOperation(
            type="step_add",
            target=TargetPath("planner.skill", "workflow_node", "step3"),
            before=None,
            after="### step4\nVerify result quality.",
            reason="Add verification step",
        )
        result = apply_delta(self.SAMPLE_SKILL, op)
        assert "### step4" in result
        assert "Verify result quality." in result

    def test_line_range_modify(self):
        op = DeltaOperation(
            type="instruction_modify",
            target=TargetPath("planner.skill", "line_range", "5"),
            before="This is the planner skill.",
            after="This is the planner skill v2.",
            reason="Update description",
        )
        result = apply_delta(self.SAMPLE_SKILL, op)
        assert "This is the planner skill v2." in result

    def test_section_not_found_does_not_crash(self):
        op = DeltaOperation(
            type="instruction_add",
            target=TargetPath("planner.skill", "text_section", "NonExistent"),
            before=None,
            after="Some content",
            reason="Test section not found",
        )
        result = apply_delta(self.SAMPLE_SKILL, op)
        assert "Some content" in result  # Should append new section

    def test_workflow_node_not_found_does_not_crash(self):
        op = DeltaOperation(
            type="instruction_modify",
            target=TargetPath("planner.skill", "workflow_node", "nonexistent_step"),
            before="Old",
            after="New",
            reason="Test node not found",
        )
        result = apply_delta(self.SAMPLE_SKILL, op)
        assert result == self.SAMPLE_SKILL  # Unchanged


class TestReverseOperation:
    def test_reverse_add_becomes_remove(self):
        op = DeltaOperation(
            type="instruction_add",
            target=TargetPath("p", "text_section", "s"),
            before=None,
            after="New content",
            reason="Add something",
        )
        rev = reverse_operation(op)
        assert rev.type == "instruction_remove"
        assert rev.before == "New content"
        assert rev.after is None

    def test_reverse_remove_becomes_add(self):
        op = DeltaOperation(
            type="constraint_remove",
            target=TargetPath("p", "text_section", "s"),
            before="Old content",
            after=None,
            reason="Remove something",
        )
        rev = reverse_operation(op)
        assert rev.type == "constraint_add"
        assert rev.before is None
        assert rev.after == "Old content"

    def test_reverse_modify_swaps_before_after(self):
        op = DeltaOperation(
            type="instruction_modify",
            target=TargetPath("p", "text_section", "s"),
            before="Old",
            after="New",
            reason="Modify something",
        )
        rev = reverse_operation(op)
        assert rev.type == "instruction_modify"
        assert rev.before == "New"
        assert rev.after == "Old"