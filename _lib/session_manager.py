"""_lib/session_manager.py — Evolution Session lifecycle management.

Provides create_session, update_session, get_session, list_sessions.
Each session tracks one ASO pipeline run with full provenance.
"""

from __future__ import annotations

import json
import uuid
import os
from datetime import datetime, timezone
from typing import Optional

from _lib.path_utils import EVOLUTION_SESSIONS_DIR, EVOLUTION_INDEX_FILE


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_id() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Find next available number
    existing = []
    if EVOLUTION_SESSIONS_DIR.exists():
        for d in EVOLUTION_SESSIONS_DIR.iterdir():
            if d.is_dir() and d.name.startswith(today):
                existing.append(d.name)
    n = 1
    while f"{today}-{n:03d}" in existing:
        n += 1
    return f"{today}-{n:03d}"


def _load_index() -> dict:
    if EVOLUTION_INDEX_FILE.exists():
        with open(EVOLUTION_INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"schema_version": "v1", "sessions": [], "latest_by_target": {}}


def _save_index(index: dict) -> None:
    EVOLUTION_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(EVOLUTION_INDEX_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(EVOLUTION_INDEX_FILE))


def create_session(target: str, trigger: str = "manual", trace_count: int = 0) -> str:
    """Create a new evolution session and return its id."""
    sid = _session_id()
    session_dir = EVOLUTION_SESSIONS_DIR / sid
    session_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "session_id": sid,
        "target": target,
        "trigger": trigger,
        "trace_count": trace_count,
        "created_at": _now(),
        "status": "started",
        "timeline": [
            {"step": "session.started", "timestamp": _now(), "status": "ok"}
        ],
        "outcome": None,
    }

    manifest_path = session_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Update index
    index = _load_index()
    index["sessions"].append({
        "id": sid,
        "target": target,
        "status": "started",
        "created_at": _now(),
        "delta_id": None,
        "outcome_summary": None,
    })
    index["latest_by_target"][target] = sid
    _save_index(index)

    return sid


def update_session(
    session_id: str,
    step: str,
    status: str,
    details: Optional[dict] = None,
) -> None:
    """Record a pipeline step completion in the session manifest."""
    session_dir = EVOLUTION_SESSIONS_DIR / session_id
    manifest_path = session_dir / "manifest.json"
    if not manifest_path.exists():
        return

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    manifest["timeline"].append({
        "step": step,
        "timestamp": _now(),
        "status": status,
        **(details or {}),
    })

    if status in ("completed", "failed", "rejected"):
        manifest["status"] = status
    elif status in ("deployed", "rolled_back"):
        manifest["status"] = status

    if details and "outcome" in details:
        manifest["outcome"] = details["outcome"]

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Update index
    index = _load_index()
    for entry in index["sessions"]:
        if entry["id"] == session_id:
            entry["status"] = manifest["status"]
            if manifest.get("outcome"):
                entry["outcome_summary"] = (
                    f"pass_rate {manifest['outcome'].get('delta_pass_rate', '?')}, "
                    f"tokens {manifest['outcome'].get('delta_tokens', '?')}"
                )
            break
    _save_index(index)


def get_session(session_id: str) -> Optional[dict]:
    """Load a session manifest by id."""
    manifest_path = EVOLUTION_SESSIONS_DIR / session_id / "manifest.json"
    if not manifest_path.exists():
        return None
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_sessions(target: Optional[str] = None, limit: int = 20) -> list[dict]:
    """List recent sessions, optionally filtered by target."""
    index = _load_index()
    sessions = index.get("sessions", [])
    if target:
        sessions = [s for s in sessions if s.get("target") == target]
    return sessions[-limit:]


def save_session_artifact(session_id: str, name: str, data: dict) -> None:
    """Save a pipeline step artifact (diagnosis, reflection, proposal, etc)."""
    session_dir = EVOLUTION_SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / name
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(path))