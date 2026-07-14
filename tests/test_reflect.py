"""Tests for reflect.skill — Reflection Engine."""

import importlib.util
import os
import sys
import pytest
from importlib.machinery import SourceFileLoader

_SKILL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_SKILL_PATH = os.path.join(_SKILL_DIR, "reflect.skill")
_SPEC = importlib.util.spec_from_file_location(
    "reflect", _SKILL_PATH,
    loader=SourceFileLoader("reflect", _SKILL_PATH)
)
_REFLECT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_REFLECT)
reflect = _REFLECT.reflect
FAILURE_TYPES = _REFLECT.FAILURE_TYPES


def _make_trace(task_id: str, success: bool = True, tokens: int = 1000,
                skills: list = None, agent_id: str = "planner") -> dict:
    if skills is None:
        skills = [{"id": "Read", "version": "v1", "success": True, "retry_count": 0}]
    return {
        "task_id": task_id,
        "timestamp": "2026-07-14T10:00:00Z",
        "source": "test",
        "total_tokens": tokens,
        "total_duration_ms": 500,
        "agent": {"id": agent_id, "version": "v1", "success": success, "latency_ms": 200},
        "skills": skills,
        "success": success,
    }


def _make_diagnosis(scores: dict = None) -> dict:
    default = {
        "tool_efficiency": {"score": 0.85, "trend": "stable", "confidence": 0.7},
        "task_quality": {"score": 0.9, "trend": "stable", "confidence": 0.7},
        "skill_success": {"score": 0.85, "trend": "stable", "confidence": 0.7},
        "context_utilization": {"score": 0.8, "trend": "stable", "confidence": 0.7},
    }
    if scores:
        default.update(scores)
    return default


class TestReflect:
    def test_empty_traces(self):
        result = reflect([])
        assert result["failure_type"] == "UNCLEAR"
        assert result["root_cause"] == "no trace data"

    def test_all_success(self):
        traces = [_make_trace(f"t{i}", success=True) for i in range(10)]
        result = reflect(traces, _make_diagnosis())
        assert result["failure_type"] == "UNCLEAR"

    def test_skill_defect_high_failure(self):
        """High failure rate should detect SKILL_DEFECT."""
        traces = [_make_trace(f"t{i}", success=(i < 3)) for i in range(10)]
        diag = _make_diagnosis({"task_quality": {"score": 0.3}})
        result = reflect(traces, diag)
        assert result["failure_type"] == "SKILL_DEFECT"

    def test_tool_defect_specific_tool_fails(self):
        """Specific tool failing repeatedly should detect TOOL_DEFECT."""
        skills = [
            {"id": "Read", "version": "v1", "success": False, "retry_count": 2},
            {"id": "Write", "version": "v1", "success": True, "retry_count": 0},
        ]
        traces = [_make_trace(f"t{i}", success=False, skills=skills) for i in range(10)]
        diag = _make_diagnosis({"task_quality": {"score": 0.2}})
        result = reflect(traces, diag)
        assert result["failure_type"] in ("TOOL_DEFECT", "SKILL_DEFECT")

    def test_execution_lapse_low_tool_eff_high_quality(self):
        """Low tool efficiency with good quality should detect EXECUTION_LAPSE."""
        traces = [_make_trace(f"t{i}") for i in range(10)]
        diag = _make_diagnosis({
            "tool_efficiency": {"score": 0.3},
            "task_quality": {"score": 0.85},
        })
        result = reflect(traces, diag)
        assert result["failure_type"] == "EXECUTION_LAPSE"

    def test_memory_defect_low_context_util(self):
        """Low context utilization with long traces should detect MEMORY_DEFECT."""
        traces = [
            _make_trace("t1", tokens=8000, skills=[{"id": "Read", "success": True}] * 20),
            _make_trace("t2", tokens=6000, skills=[{"id": "Read", "success": True}] * 15),
        ]
        diag = _make_diagnosis({"context_utilization": {"score": 0.3}})
        result = reflect(traces, diag)
        assert result["failure_type"] == "MEMORY_DEFECT"

    def test_environment_issue_low_quality_high_tool_eff(self):
        """Low quality despite good tool efficiency should detect ENVIRONMENT_ISSUE."""
        traces = [_make_trace(f"t{i}") for i in range(10)]
        diag = _make_diagnosis({
            "task_quality": {"score": 0.3},
            "tool_efficiency": {"score": 0.85},
        })
        result = reflect(traces, diag)
        assert result["failure_type"] == "ENVIRONMENT_ISSUE"

    def test_no_diagnosis_fallback(self):
        """Should work without diagnosis input."""
        traces = [_make_trace(f"t{i}", success=False) for i in range(5)]
        result = reflect(traces)
        assert "failure_type" in result

    def test_failure_types_all_valid(self):
        traces = [_make_trace(f"t{i}", success=False) for i in range(10)]
        diag = _make_diagnosis({"task_quality": {"score": 0.2}})
        result = reflect(traces, diag)
        assert result["failure_type"] in FAILURE_TYPES

    def test_confidence_scales_with_sample(self):
        small = reflect([_make_trace("t1", success=False)], _make_diagnosis({"task_quality": {"score": 0.2}}))
        large = reflect([_make_trace(f"t{i}", success=(i < 30)) for i in range(100)],
                        _make_diagnosis({"task_quality": {"score": 0.3}}))
        assert large["confidence"] >= small["confidence"]

    def test_recommended_change_type_present(self):
        traces = [_make_trace(f"t{i}", success=False) for i in range(10)]
        diag = _make_diagnosis({"task_quality": {"score": 0.2}})
        result = reflect(traces, diag)
        assert "recommended_change_type" in result
        assert result["recommended_change_type"] in (
            "instruction_add", "instruction_modify", "constraint_add", "tool_call_modify"
        )

    def test_evidence_non_empty_when_defect(self):
        traces = [_make_trace(f"t{i}", success=False) for i in range(10)]
        diag = _make_diagnosis({"task_quality": {"score": 0.2}})
        result = reflect(traces, diag)
        assert len(result.get("evidence", [])) > 0