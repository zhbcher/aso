"""_lib/version_manager.py — Skill version tracking for ASO v2.

Manages skill version history with support for parent references
(linear chain, not branching — for now).
"""

from __future__ import annotations

import json
import os
from typing import Optional

from _lib.path_utils import MANIFESTS_FILE
from _lib.time_utils import utcnow_iso


def _load() -> list:
    """Load manifests, filtering out old-format entries (pre-v2)."""
    if MANIFESTS_FILE.exists():
        with open(MANIFESTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            # Filter: only keep entries with the new schema (has current_version)
            return [e for e in data if isinstance(e, dict) and "current_version" in e]
        return []
    return []


def _save(data: list) -> None:
    tmp = str(MANIFESTS_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(MANIFESTS_FILE))


def _get_skill_entry(data: list, target: str) -> Optional[dict]:
    for entry in data:
        if entry.get("target") == target and "current_version" in entry:
            return entry
    return None


def init_skill(target: str, initial_version: str = "v1") -> str:
    """Register a new skill and return its initial version."""
    data = _load()
    entry = _get_skill_entry(data, target)
    if entry:
        return entry.get("current_version", initial_version)

    entry = {
        "target": target,
        "current_version": initial_version,
        "versions": [
            {
                "version": initial_version,
                "delta_id": None,
                "parent_version": None,
                "deployed_at": utcnow_iso(),
            }
        ],
        "rollback_target": None,
    }
    data.append(entry)
    _save(data)
    return initial_version


def bump_version(target: str, delta_id: str) -> str:
    """Increment the version after a successful delta deployment.

    Version format: v1, v2, v3, ...
    Returns the new version string.
    """
    data = _load()
    entry = _get_skill_entry(data, target)

    if not entry:
        # Auto-init if not registered
        init_skill(target, "v0")  # v0 so bump goes to v1
        entry = _get_skill_entry(data, target)
        if not entry:
            entry = {
                "target": target,
                "current_version": "v0",
                "versions": [],
                "rollback_target": None,
            }
            data.append(entry)

    current = entry.get("current_version", "v0")
    if not current.startswith("v"):
        current_num = 0
    else:
        current_num = int(current.lstrip("v")) if current.lstrip("v").isdigit() else 0
    new_version = f"v{current_num + 1}"

    entry["versions"].append({
        "version": new_version,
        "delta_id": delta_id,
        "parent_version": current,
        "deployed_at": utcnow_iso(),
    })
    entry["current_version"] = new_version
    entry["rollback_target"] = current
    _save(data)
    return new_version


def rollback_version(target: str) -> Optional[str]:
    """Roll back to the previous version. Returns the rolled-back-to version or None."""
    data = _load()
    entry = _get_skill_entry(data, target)
    if not entry:
        return None

    rollback_target = entry.get("rollback_target")
    if not rollback_target:
        return None

    current = entry.get("current_version", "")
    entry["current_version"] = rollback_target
    entry["rollback_target"] = None  # Can only roll back once

    # Add rollback record
    entry["versions"].append({
        "version": f"{rollback_target} (rollback from {current})",
        "delta_id": None,
        "parent_version": current,
        "deployed_at": utcnow_iso(),
    })
    _save(data)
    return rollback_target


def get_current_version(target: str) -> Optional[str]:
    """Get the current version for a skill."""
    data = _load()
    entry = _get_skill_entry(data, target)
    return entry.get("current_version") if entry else None


def get_version_history(target: str) -> list[dict]:
    """Get the full version history for a skill."""
    data = _load()
    entry = _get_skill_entry(data, target)
    return entry.get("versions", []) if entry else []


def get_all_skills() -> list[dict]:
    """Get all registered skills with their current versions."""
    return _load()