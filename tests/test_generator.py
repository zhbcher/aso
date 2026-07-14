"""Tests for generator/skill_opt_refactor.py — SkillDelta output."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "generator"))
from skill_opt_refactor import SkillOptRefactor


class TestGeneratorV1:
    """v1 backward compatibility"""

    def test_v1_output_has_changes(self):
        gen = SkillOptRefactor()
        result = gen.generate("planner", strategy="aso")
        assert "changes" in result
        assert result["type"] == "aso_optimization"
        assert result["success"] is True

    def test_v1_with_report(self):
        gen = SkillOptRefactor()
        report = {"priority": ["tool_efficiency"]}
        result = gen.generate("planner", strategy="aso", report=report)
        assert "tool_efficiency" in result["description"]


class TestGeneratorDelta:
    """v2 SkillDelta output"""

    def test_delta_output_has_required_fields(self):
        gen = SkillOptRefactor()
        result = gen.generate("planner", strategy="delta")
        assert "delta_id" in result
        assert "operations" in result
        assert "rollback_plan" in result
        assert "risk" in result
        assert "generation_confidence" in result
        assert "change_rationale" in result

    def test_delta_with_reflection_instruction_add(self):
        gen = SkillOptRefactor()
        reflection = {
            "failure_type": "SKILL_DEFECT",
            "root_cause": "Missing verification step",
            "recommended_change_type": "instruction_add",
            "confidence": 0.85,
        }
        result = gen.generate("planner", strategy="delta", reflection=reflection)
        assert result["operations"][0]["type"] == "instruction_add"
        assert result["generation_confidence"] == 0.85
        assert result["risk"] == "medium"

    def test_delta_with_reflection_tool_call_modify(self):
        gen = SkillOptRefactor()
        reflection = {
            "failure_type": "TOOL_DEFECT",
            "root_cause": "Read tool timeout",
            "recommended_change_type": "tool_call_modify",
            "confidence": 0.9,
        }
        result = gen.generate("planner", strategy="delta", reflection=reflection)
        assert result["operations"][0]["type"] == "tool_call_modify"

    def test_delta_with_reflection_constraint_add(self):
        gen = SkillOptRefactor()
        reflection = {
            "failure_type": "EXECUTION_LAPSE",
            "root_cause": "Low efficiency",
            "recommended_change_type": "constraint_add",
            "confidence": 0.7,
        }
        result = gen.generate("planner", strategy="delta", reflection=reflection)
        assert result["operations"][0]["type"] == "constraint_add"
        assert result["risk"] == "low"

    def test_delta_with_reflection_instruction_modify(self):
        gen = SkillOptRefactor()
        reflection = {
            "failure_type": "MEMORY_DEFECT",
            "root_cause": "Context overflow",
            "recommended_change_type": "instruction_modify",
            "confidence": 0.6,
        }
        result = gen.generate("planner", strategy="delta", reflection=reflection)
        assert result["operations"][0]["type"] == "instruction_modify"

    def test_delta_operation_has_correct_structure(self):
        gen = SkillOptRefactor()
        result = gen.generate("planner", strategy="delta")
        op = result["operations"][0]
        assert "type" in op
        assert "target" in op
        assert "before" in op
        assert "after" in op
        assert "reason" in op
        assert "file" in op["target"]
        assert "selector_type" in op["target"]
        assert "selector" in op["target"]

    def test_delta_rollback_plan_valid(self):
        gen = SkillOptRefactor()
        result = gen.generate("planner", strategy="delta")
        rp = result["rollback_plan"]
        assert "type" in rp
        assert rp["type"] == "reverse_delta"

    def test_delta_target_file_matches_target(self):
        gen = SkillOptRefactor()
        result = gen.generate("router", strategy="delta")
        op = result["operations"][0]
        assert "router" in op["target"]["file"]

    def test_delta_high_risk_with_many_ops(self):
        """Multiple operations should result in high risk."""
        gen = SkillOptRefactor()
        # We can't force multiple ops from the current template generator,
        # but we can check the risk logic directly
        assert gen._determine_risk("SKILL_DEFECT", 3, 0.8) == "high"

    def test_no_reflection_fallback(self):
        """Without reflection, should still produce a valid delta."""
        gen = SkillOptRefactor()
        result = gen.generate("planner", strategy="delta")
        assert result["operations"][0]["type"] == "instruction_add"