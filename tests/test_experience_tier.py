"""Tests for _lib/experience_tier.py — Golden / Failures tier management."""

import json
import os
import pytest

from _lib.experience_tier import (
    add_golden, add_golden_candidate, promote_golden, demote_golden,
    list_golden, get_golden, get_all_golden_traces, count_golden,
    add_failure, list_failures, get_all_failure_traces,
)


def _trace(task_id="t1", success=True, tokens=1000, agent_id="planner"):
    return {
        "task_id": task_id,
        "timestamp": "2026-07-14T10:00:00Z",
        "source": "test",
        "total_tokens": tokens,
        "total_duration_ms": 500,
        "agent": {"id": agent_id, "version": "v1", "success": success, "latency_ms": 200},
        "skills": [{"id": "Read", "version": "v1", "success": True, "retry_count": 0}],
        "success": success,
    }


class TestGoldenTier:
    def test_add_golden(self):
        gid = add_golden(_trace(), description="multi-turn summary", tags=["multi-turn"])
        assert gid.startswith("golden-")
        entry = get_golden(gid)
        assert entry is not None
        assert entry["status"] == "active"
        assert "multi-turn" in entry["tags"]

    def test_list_golden(self):
        add_golden(_trace(task_id="t1", agent_id="planner"), tags=["a"])
        add_golden(_trace(task_id="t2", agent_id="router"), tags=["b"])
        entries = list_golden()
        assert len(entries) >= 2

    def test_list_golden_by_target(self):
        add_golden(_trace(agent_id="planner"))
        add_golden(_trace(agent_id="router"))
        entries = list_golden(target="planner")
        assert all(e["target"] == "planner" for e in entries)

    def test_list_golden_by_tags(self):
        add_golden(_trace(), tags=["multi-turn", "summarization"])
        add_golden(_trace(), tags=["single-turn"])
        entries = list_golden(tags=["multi-turn"])
        assert len(entries) >= 1

    def test_get_all_golden_traces(self):
        add_golden(_trace(task_id="t1", agent_id="planner"))
        add_golden(_trace(task_id="t2", agent_id="router"))
        traces = get_all_golden_traces(target="planner")
        assert len(traces) >= 1
        assert all(t.get("agent", {}).get("id") == "planner" for t in traces)

    def test_count_golden(self):
        c = count_golden()
        assert c >= 0

    def test_golden_candidate_flow(self):
        gid = add_golden_candidate(_trace(), auto_score=0.85)
        entry = get_golden(gid)
        assert entry["status"] == "candidate"
        assert entry["auto_score"] == 0.85

        promoted = promote_golden(gid)
        assert promoted
        entry = get_golden(gid)
        assert entry["status"] == "active"

    def test_demote_golden(self):
        gid = add_golden(_trace())
        demoted = demote_golden(gid, reason="obsolete")
        assert demoted
        entry = get_golden(gid)
        assert entry["status"] == "demoted"

    def test_demote_nonexistent(self):
        assert demote_golden("nonexistent") is False

    def test_list_golden_metadata_only(self):
        """list_golden should not include the full trace in metadata."""
        gid = add_golden(_trace(), description="test")
        entries = list_golden()
        for e in entries:
            assert "trace" not in e


class TestFailuresTier:
    def test_add_failure(self):
        fid = add_failure(_trace(success=False), failure_reason="timeout",
                          failure_type="TOOL_DEFECT")
        assert fid.startswith("failure-")

    def test_list_failures(self):
        add_failure(_trace(task_id="t1", success=False), failure_type="SKILL_DEFECT")
        add_failure(_trace(task_id="t2", success=False), failure_type="TOOL_DEFECT")
        entries = list_failures()
        assert len(entries) >= 2

    def test_list_failures_by_type(self):
        add_failure(_trace(task_id="t1", success=False), failure_type="SKILL_DEFECT")
        add_failure(_trace(task_id="t2", success=False), failure_type="TOOL_DEFECT")
        entries = list_failures(failure_type="SKILL_DEFECT")
        assert all(e["failure_type"] == "SKILL_DEFECT" for e in entries)

    def test_get_all_failure_traces(self):
        add_failure(_trace(task_id="t1", success=False, agent_id="planner"),
                    failure_type="SKILL_DEFECT")
        add_failure(_trace(task_id="t2", success=False, agent_id="router"),
                    failure_type="TOOL_DEFECT")
        traces = get_all_failure_traces(target="planner")
        assert len(traces) >= 1

    def test_list_failures_metadata_only(self):
        add_failure(_trace(success=False), failure_reason="timeout")
        entries = list_failures()
        for e in entries:
            assert "trace" not in e