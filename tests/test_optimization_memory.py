"""Tests for _lib/optimization_memory.py."""

import pytest


@pytest.fixture(autouse=True)
def clean_memory(tmp_path, monkeypatch):
    from _lib import path_utils
    monkeypatch.setattr(path_utils, "OPTIMIZATION_MEMORY_FILE", tmp_path / "opt_memory.json")
    import importlib
    import _lib.optimization_memory as om
    importlib.reload(om)  # Force reload so it picks up the patched path
    global add_entry, query, get_statistics, get_entry_count
    from _lib.optimization_memory import add_entry, query, get_statistics, get_entry_count


class TestOptimizationMemory:
    def test_add_entry(self):
        eid = add_entry(
            session_id="s1",
            target="planner",
            operation_types=["constraint_add", "instruction_modify"],
            failure_pattern="multi-turn context overflow",
            root_cause="missing compression step",
            delta_summary="added verification + compression",
            outcome={"pass_rate_delta": 0.08, "tokens_delta": -0.12, "deployed": True, "rolled_back": False},
            confidence=0.85,
        )
        assert eid.startswith("om-")
        assert get_entry_count() == 1

    def test_add_entry_minimal(self):
        eid = add_entry(
            session_id="s1", target="router",
            operation_types=["instruction_add"],
            failure_pattern="bad routing",
            root_cause="missing negative trigger",
            delta_summary="added negative trigger",
            outcome={"pass_rate_delta": 0.05, "tokens_delta": 0, "deployed": True, "rolled_back": False},
        )
        assert eid.startswith("om-")

    def test_query_by_target(self):
        add_entry(session_id="s1", target="planner", operation_types=["add"], failure_pattern="a",
                  root_cause="b", delta_summary="c", outcome={"deployed": True})
        add_entry(session_id="s1", target="router", operation_types=["add"], failure_pattern="a",
                  root_cause="b", delta_summary="c", outcome={"deployed": True})
        results = query(target="planner")
        assert len(results) == 1
        assert results[0]["target"] == "planner"

    def test_query_by_operation_type(self):
        add_entry(session_id="s1", target="planner", operation_types=["constraint_add", "instruction_modify"],
                  failure_pattern="a", root_cause="b", delta_summary="c", outcome={"deployed": True})
        add_entry(session_id="s1", target="planner", operation_types=["instruction_remove"],
                  failure_pattern="a", root_cause="b", delta_summary="c", outcome={"deployed": True})
        results = query(operation_type="constraint_add")
        assert len(results) == 1

    def test_query_by_confidence(self):
        add_entry(session_id="s1", target="planner", operation_types=["add"], failure_pattern="a",
                  root_cause="b", delta_summary="c", outcome={"deployed": True}, confidence=0.3)
        add_entry(session_id="s1", target="planner", operation_types=["add"], failure_pattern="a",
                  root_cause="b", delta_summary="c", outcome={"deployed": True}, confidence=0.9)
        results = query(min_confidence=0.5)
        assert len(results) == 1
        assert results[0]["confidence"] == 0.9

    def test_get_statistics(self):
        add_entry(session_id="s1", target="planner", operation_types=["constraint_add"],
                  failure_pattern="a", root_cause="b", delta_summary="c",
                  outcome={"pass_rate_delta": 0.1, "tokens_delta": -0.1, "deployed": True, "rolled_back": False},
                  confidence=0.8)
        add_entry(session_id="s1", target="planner", operation_types=["constraint_add"],
                  failure_pattern="a", root_cause="b", delta_summary="c",
                  outcome={"pass_rate_delta": 0.0, "tokens_delta": 0, "deployed": False, "rolled_back": True},
                  confidence=0.8)
        add_entry(session_id="s1", target="router", operation_types=["instruction_add"],
                  failure_pattern="a", root_cause="b", delta_summary="c",
                  outcome={"deployed": True, "rolled_back": False})

        stats = get_statistics(target="planner")
        assert "constraint_add" in stats
        assert stats["constraint_add"]["attempts"] == 2
        assert stats["constraint_add"]["successes"] == 1
        assert stats["constraint_add"]["success_rate"] == 0.5

        # Router entry should not be in planner stats
        assert "instruction_add" not in stats

    def test_get_statistics_all(self):
        add_entry(session_id="s1", target="planner", operation_types=["add"], failure_pattern="a",
                  root_cause="b", delta_summary="c", outcome={"deployed": True})
        add_entry(session_id="s1", target="router", operation_types=["remove"], failure_pattern="a",
                  root_cause="b", delta_summary="c", outcome={"deployed": True})
        stats = get_statistics()
        assert "add" in stats
        assert "remove" in stats