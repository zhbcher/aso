"""Tests for sandbox.skill v2 — SkillDelta application + tier evaluation."""

import importlib.util
import os
import json
import tempfile
from importlib.machinery import SourceFileLoader

_SKILL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_SKILL_PATH = os.path.join(_SKILL_DIR, "sandbox.skill")


def _load_sandbox():
    """Lazy-load sandbox.skill."""
    spec = importlib.util.spec_from_file_location(
        "sandbox_loader", _SKILL_PATH,
        loader=SourceFileLoader("sandbox_loader", _SKILL_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSandboxV2:
    def test_sandbox_with_delta_basic(self):
        """Test that sandbox_with_delta can be called."""
        sb = _load_sandbox()
        assert hasattr(sb, "sandbox_with_delta")
        assert callable(sb.sandbox_with_delta)

    def test_evaluate_golden_tier_empty(self):
        """Test _evaluate_golden_tier with no golden traces."""
        sb = _load_sandbox()
        result = sb._evaluate_golden_tier("nonexistent_target")
        assert result["verdict"] == "ok"
        assert result["total"] == 0

    def test_evaluate_failures_tier_empty(self):
        """Test _evaluate_failures_tier with no failure traces."""
        sb = _load_sandbox()
        result = sb._evaluate_failures_tier("nonexistent_target")
        assert result["verdict"] == "ok"
        assert result["total"] == 0

    def test_evaluate_golden_tier_with_data(self):
        """Test _evaluate_golden_tier with golden traces."""
        sb = _load_sandbox()

        # Add a golden trace first
        from _lib.experience_tier import add_golden
        trace = {
            "task_id": "golden-test",
            "success": True,
            "agent": {"id": "test-planner"},
            "skills": [],
            "total_tokens": 100,
        }
        add_golden(trace, description="test golden", source_session="test")

        result = sb._evaluate_golden_tier("test-planner")
        assert result["total"] >= 1
        assert result["verdict"] in ("ok", "regression")

    def test_evaluate_failures_tier_with_data(self):
        """Test _evaluate_failures_tier with failure traces."""
        sb = _load_sandbox()

        from _lib.experience_tier import add_failure
        trace = {
            "task_id": "failure-test",
            "success": False,
            "agent": {"id": "test-planner"},
            "skills": [{"id": "Read", "success": False, "error": "timeout"}],
            "total_tokens": 100,
        }
        add_failure(trace, failure_reason="timeout", failure_type="TOOL_DEFECT")

        result = sb._evaluate_failures_tier("test-planner")
        assert result["total"] >= 1

    def test_delta_apply_and_restore(self):
        """Test applying a delta to a temp file and restoring."""
        sb = _load_sandbox()

        # Create a temp skill file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".skill", delete=False) as f:
            f.write("# Test Skill\n\n## Workflow\nExecute tool call.\n\n## Constraints\n- Be fast\n")
            f.flush()
            skill_path = f.name

        try:
            # Create a delta candidate
            candidate = {
                "delta_id": "delta-test-001",
                "session_id": "test-session",
                "target": "test",
                "base_version": "v1",
                "operations": [
                    {
                        "type": "instruction_add",
                        "target": {
                            "file": "test.skill",
                            "selector_type": "text_section",
                            "selector": "Constraints",
                        },
                        "before": None,
                        "after": "- After turn 8, compress context.",
                        "reason": "Add context compression constraint",
                    }
                ],
                "risk": "low",
                "generation_confidence": 0.85,
                "expected_effect": "Improve long conversations",
                "change_rationale": "Missing compression",
                "rollback_plan": {"type": "reverse_delta", "notes": "Simple reverse"},
            }

            # Read original content
            with open(skill_path, "r") as f:
                original = f.read()

            # Apply via sandbox_with_delta with tier evaluation
            result = sb.sandbox_with_delta(
                target="test",
                candidate=candidate,
                skill_file_path=skill_path,
                evaluate_tiers=["recent"],
            )

            assert "delta_applied" in result
            assert "tier_results" in result
            assert "verdict" in result

            # Verify file was restored
            with open(skill_path, "r") as f:
                restored = f.read()
            assert restored == original, "File was not restored to original"

        finally:
            os.unlink(skill_path)

    def test_sandbox_with_delta_multiple_tiers(self):
        """Test with multiple tiers."""
        sb = _load_sandbox()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".skill", delete=False) as f:
            f.write("# Test\n")
            f.flush()
            skill_path = f.name

        try:
            candidate = {
                "delta_id": "delta-test-002",
                "session_id": "test",
                "target": "test",
                "base_version": "v1",
                "operations": [],
                "risk": "low",
                "generation_confidence": 0.5,
                "expected_effect": "test",
                "change_rationale": "test",
                "rollback_plan": {"type": "manual"},
            }

            result = sb.sandbox_with_delta(
                target="test",
                candidate=candidate,
                skill_file_path=skill_path,
                evaluate_tiers=["recent", "golden", "failures"],
            )

            tiers = result.get("tier_results", {})
            assert "recent" in tiers
            assert "golden" in tiers
            assert "failures" in tiers
        finally:
            os.unlink(skill_path)