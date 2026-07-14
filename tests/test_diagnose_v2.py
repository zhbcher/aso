"""Tests for diagnose.skill v2 — trend awareness + failure clustering."""

import importlib.util
import os
from importlib.machinery import SourceFileLoader

_SKILL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_SKILL_PATH = os.path.join(_SKILL_DIR, "diagnose.skill")
_SPEC = importlib.util.spec_from_file_location(
    "diagnose", _SKILL_PATH,
    loader=SourceFileLoader("diagnose", _SKILL_PATH)
)
_DIAGNOSE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_DIAGNOSE)
diagnose = _DIAGNOSE.diagnose


def _trace(task_id: str, success: bool = True, tokens: int = 1000,
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


class TestDiagnoseV2BackwardCompat:
    """v1 兼容性：原有输出字段不变"""

    def test_v1_fields_present(self):
        traces = [_trace(f"t{i}") for i in range(10)]
        report = diagnose(traces)
        assert "tool_efficiency" in report
        assert "task_quality" in report
        assert "skill_success" in report
        assert "context_utilization" in report
        assert "skills" in report
        assert "priority" in report
        assert "trace_count" in report
        assert "analysis_confidence" in report
        assert "data_source" in report

    def test_v1_field_structure(self):
        traces = [_trace(f"t{i}") for i in range(10)]
        report = diagnose(traces)
        te = report["tool_efficiency"]
        assert "score" in te
        assert "trend" in te
        assert "confidence" in te

    def test_empty_traces(self):
        report = diagnose([])
        assert "error" in report
        assert report["trace_count"] == 0


class TestDiagnoseV2FailureClustering:
    """v2 新增：失败模式聚类"""

    def test_failure_clusters_field_present(self):
        traces = [_trace(f"t{i}") for i in range(10)]
        report = diagnose(traces)
        assert "failure_clusters" in report

    def test_no_failures_empty_clusters(self):
        traces = [_trace(f"t{i}", success=True) for i in range(10)]
        report = diagnose(traces)
        assert report["failure_clusters"] == []

    def test_failure_clusters_with_errors(self):
        skills = [{"id": "Read", "success": False, "error": "timeout"}]
        traces = [_trace(f"t{i}", success=False, skills=skills) for i in range(5)]
        report = diagnose(traces)
        assert len(report["failure_clusters"]) > 0
        cluster = report["failure_clusters"][0]
        assert "pattern" in cluster
        assert "count" in cluster
        assert cluster["count"] == 5

    def test_failure_clusters_sorted_by_frequency(self):
        skills_a = [{"id": "Read", "success": False, "error": "timeout"}]
        skills_b = [{"id": "Write", "success": False, "error": "auth_error"}]
        traces = (
            [_trace(f"a{i}", success=False, skills=skills_a) for i in range(10)]
            + [_trace(f"b{i}", success=False, skills=skills_b) for i in range(3)]
        )
        report = diagnose(traces)
        clusters = report["failure_clusters"]
        assert len(clusters) >= 2
        assert clusters[0]["count"] >= clusters[1]["count"]


class TestDiagnoseV2CrossSession:
    """v2 新增：跨 session 趋势"""

    def test_cross_session_field_present(self):
        traces = [_trace(f"t{i}") for i in range(10)]
        report = diagnose(traces)
        assert "cross_session_trends" in report

    def test_no_history(self):
        traces = [_trace(f"t{i}") for i in range(10)]
        report = diagnose(traces)
        assert report["cross_session_trends"]["available"] is False

    def test_with_history_detects_improvement(self):
        # 历史诊断：低分
        prev = [
            {"tool_efficiency": {"score": 0.3}, "task_quality": {"score": 0.4},
             "skill_success": {"score": 0.5}, "context_utilization": {"score": 0.3}},
        ]
        # 当前：高分
        traces = [_trace(f"t{i}", success=True) for i in range(10)]
        report = diagnose(traces, previous_diagnoses=prev)
        trends = report["cross_session_trends"]
        assert trends["available"] is True
        assert trends["sessions_compared"] == 1
        assert "dimensions" in trends

    def test_with_history_detects_decline(self):
        # 历史诊断：高分
        prev = [
            {"tool_efficiency": {"score": 0.9}, "task_quality": {"score": 0.95},
             "skill_success": {"score": 0.95}, "context_utilization": {"score": 0.9}},
        ]
        # 当前：低分
        traces = [_trace(f"t{i}", success=(i < 3)) for i in range(10)]
        report = diagnose(traces, previous_diagnoses=prev)
        trends = report["cross_session_trends"]
        dim = trends["dimensions"]["task_quality"]
        assert dim["trend"] == "declining"
        assert dim["delta"] < 0


class TestDiagnoseV2FailedTraceAnalysis:
    """v2 新增：失败 trace 详细分析"""

    def test_failed_analysis_field_present(self):
        traces = [_trace(f"t{i}") for i in range(10)]
        report = diagnose(traces)
        assert "failed_trace_analysis" in report

    def test_no_failures(self):
        traces = [_trace(f"t{i}", success=True) for i in range(10)]
        report = diagnose(traces)
        assert report["failed_trace_analysis"]["has_failures"] is False

    def test_failures_present(self):
        traces = [_trace(f"t{i}", success=(i < 7)) for i in range(10)]
        report = diagnose(traces)
        analysis = report["failed_trace_analysis"]
        assert analysis["has_failures"] is True
        assert analysis["total_failed"] == 3
        assert "top_failed_tools" in analysis