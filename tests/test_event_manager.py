"""Tests for _lib/event_manager.py."""

import pytest
import json


@pytest.fixture(autouse=True)
def clean_events(tmp_path, monkeypatch):
    from _lib import path_utils
    monkeypatch.setattr(path_utils, "EVOLUTION_EVENTS_FILE", tmp_path / "journal.jsonl")
    import importlib
    import _lib.event_manager as em
    importlib.reload(em)
    global emit, query, get_session_events, count_by_type
    from _lib.event_manager import emit, query, get_session_events, count_by_type


class TestEventManager:
    def test_emit_event(self):
        eid = emit("session.started", "planner", "s1")
        assert eid.startswith("evt-")

    def test_emit_with_payload(self):
        eid = emit("delta.generated", "planner", "s1",
                   payload={"delta_id": "d1", "operation_count": 2})
        assert eid.startswith("evt-")

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Unknown event type"):
            emit("invalid.type", "planner", "s1")

    def test_query_by_session(self):
        emit("session.started", "planner", "s1")
        emit("session.started", "router", "s2")
        results = query(session_id="s1")
        assert len(results) == 1
        assert results[0]["session_id"] == "s1"

    def test_query_by_target(self):
        emit("session.started", "planner", "s1")
        emit("session.started", "router", "s2")
        results = query(target="planner")
        assert len(results) == 1
        assert results[0]["target"] == "planner"

    def test_query_by_type(self):
        emit("session.started", "planner", "s1")
        emit("delta.generated", "planner", "s1")
        results = query(event_type="session.started")
        assert len(results) == 1

    def test_query_by_source(self):
        emit("session.started", "planner", "s1", source="user")
        results = query(source="user")
        assert len(results) == 1

    def test_query_limit(self):
        for i in range(5):
            emit("session.started", "planner", f"s{i}")
        results = query(limit=3)
        assert len(results) == 3

    def test_get_session_events_chronological(self):
        emit("session.started", "planner", "s1")
        emit("delta.generated", "planner", "s1")
        emit("delta.applied", "planner", "s1")
        events = get_session_events("s1")
        assert len(events) == 3
        assert events[0]["type"] == "session.started"
        assert events[1]["type"] == "delta.generated"
        assert events[2]["type"] == "delta.applied"

    def test_count_by_type(self):
        emit("session.started", "planner", "s1")
        emit("session.started", "router", "s2")
        emit("delta.generated", "planner", "s1")
        assert count_by_type("session.started") == 2
        assert count_by_type("delta.generated") == 1
        assert count_by_type() == 3

    def test_event_schema(self):
        eid = emit("session.started", "planner", "s1",
                   payload={"trace_count": 100}, source="user")
        events = query(limit=1)
        evt = events[0]
        assert "event_id" in evt
        assert "type" in evt
        assert "target" in evt
        assert "session_id" in evt
        assert "timestamp" in evt
        assert "payload" in evt
        assert "source" in evt
        assert evt["type"] == "session.started"
        assert evt["target"] == "planner"
        assert evt["session_id"] == "s1"
        assert evt["source"] == "user"