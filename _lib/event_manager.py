"""_lib/event_manager.py — Evolution event journal for ASO v2.

Append-only event journal for audit, statistics, and MRX integration.
Each event is a JSON line in journal.jsonl.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from _lib.path_utils import EVOLUTION_EVENTS_FILE


VALID_EVENT_TYPES = frozenset({
    # Skill lifecycle
    "skill.registered", "skill.version_created", "skill.rollback",
    # Session
    "session.started", "session.step_completed", "session.failed", "session.completed",
    # Delta
    "delta.generated", "delta.applied", "delta.rejected",
    # Validation
    "validation.passed", "validation.failed", "validation.regression",
    # Experience
    "experience.added", "golden.promoted", "golden.demoted",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(
    event_type: str,
    target: str,
    session_id: str,
    payload: Optional[dict] = None,
    source: str = "system",
) -> str:
    """Emit an evolution event to the journal.

    Args:
        event_type: One of VALID_EVENT_TYPES
        target: The skill/target this event relates to
        session_id: The evolution session id
        payload: Event-specific data
        source: system | user | policy

    Returns:
        The event id.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Unknown event type: {event_type}. Valid: {sorted(VALID_EVENT_TYPES)}")

    event = {
        "event_id": f"evt-{uuid.uuid4().hex[:8]}",
        "type": event_type,
        "target": target,
        "session_id": session_id,
        "timestamp": _now(),
        "payload": payload or {},
        "source": source,
    }

    EVOLUTION_EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False)
    with open(str(EVOLUTION_EVENTS_FILE), "a", encoding="utf-8") as f:
        f.write(line + "\n")

    return event["event_id"]


def query(
    session_id: Optional[str] = None,
    target: Optional[str] = None,
    event_type: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Query events from the journal with optional filters.

    Returns events in reverse chronological order (newest first).
    """
    if not EVOLUTION_EVENTS_FILE.exists():
        return []

    events = []
    with open(str(EVOLUTION_EVENTS_FILE), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    if session_id:
        events = [e for e in events if e.get("session_id") == session_id]
    if target:
        events = [e for e in events if e.get("target") == target]
    if event_type:
        events = [e for e in events if e.get("type") == event_type]
    if source:
        events = [e for e in events if e.get("source") == source]

    events.reverse()
    return events[:limit]


def get_session_events(session_id: str) -> list[dict]:
    """Get all events for a specific session, in chronological order."""
    if not EVOLUTION_EVENTS_FILE.exists():
        return []

    events = []
    with open(str(EVOLUTION_EVENTS_FILE), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                evt = json.loads(line)
                if evt.get("session_id") == session_id:
                    events.append(evt)

    return events


def count_by_type(event_type: Optional[str] = None) -> int:
    """Count events, optionally filtered by type."""
    if not EVOLUTION_EVENTS_FILE.exists():
        return 0

    count = 0
    with open(str(EVOLUTION_EVENTS_FILE), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                if event_type:
                    try:
                        if json.loads(line).get("type") == event_type:
                            count += 1
                    except json.JSONDecodeError:
                        pass
                else:
                    count += 1
    return count