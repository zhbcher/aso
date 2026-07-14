"""_lib/experience_tier.py — Experience Tier management for ASO v2.

Manages Golden, Failures, and Recent trace tiers for evaluation.
Replaces ML train/test split with production-appropriate test layering.

Tiers:
- Recent: Latest traces from observe (auto-populated, ephemeral)
- Golden: Manually confirmed high-quality tasks (persistent, regression-protected)
- Failures: Historical failure traces (persistent, auto-archived)
- Historical: Archived traces (persistent, long-term regression)

Golden supports auto-candidate flow: automatically scored traces
can be promoted to golden after human confirmation.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Optional, List
from datetime import datetime, timezone

from _lib.path_utils import EVOLVE_DIR


# ─── Paths ───

GOLDEN_DIR = EVOLVE_DIR / "evals" / "golden"
FAILURES_DIR = EVOLVE_DIR / "evals" / "failures"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Golden Tier ───

def add_golden(
    trace: dict,
    description: str = "",
    tags: Optional[List[str]] = None,
    source_session: str = "",
) -> str:
    """Add a trace to the Golden tier.

    Args:
        trace: The trace dict (must include task_id).
        description: Human-readable description of this golden task.
        tags: Optional tags (e.g. ["multi-turn", "summarization"]).
        source_session: Session id that produced this golden.

    Returns:
        The golden entry id.
    """
    golden_id = f"golden-{uuid.uuid4().hex[:8]}"
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    entry = {
        "golden_id": golden_id,
        "task_id": trace.get("task_id", ""),
        "target": trace.get("agent", {}).get("id", ""),
        "description": description,
        "expected_outcome": {
            "success": trace.get("success", True),
            "max_tokens": trace.get("total_tokens", 0) * 2,
            "max_steps": len(trace.get("skills", [])) * 2,
        },
        "added_by": source_session or "",
        "added_at": _now(),
        "tags": tags or [],
        "status": "active",
        "trace": trace,
    }

    path = GOLDEN_DIR / f"{golden_id}.json"
    _atomic_write(path, entry)
    return golden_id


def add_golden_candidate(
    trace: dict,
    description: str = "",
    tags: Optional[List[str]] = None,
    source_session: str = "",
    auto_score: float = 0.0,
) -> str:
    """Add a trace as a golden candidate (needs human confirmation).

    Same as add_golden but with status="candidate" and auto_score.
    """
    golden_id = f"golden-{uuid.uuid4().hex[:8]}"
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    entry = {
        "golden_id": golden_id,
        "task_id": trace.get("task_id", ""),
        "target": trace.get("agent", {}).get("id", ""),
        "description": description,
        "expected_outcome": {
            "success": trace.get("success", True),
            "max_tokens": trace.get("total_tokens", 0) * 2,
            "max_steps": len(trace.get("skills", [])) * 2,
        },
        "added_by": source_session or "",
        "added_at": _now(),
        "tags": tags or [],
        "status": "candidate",
        "auto_score": auto_score,
        "trace": trace,
    }

    path = GOLDEN_DIR / f"{golden_id}.json"
    _atomic_write(path, entry)
    return golden_id


def promote_golden(golden_id: str) -> bool:
    """Promote a golden candidate to active golden.

    Returns True if promoted, False if not found or already active.
    """
    path = GOLDEN_DIR / f"{golden_id}.json"
    if not path.exists():
        return False

    entry = json.loads(path.read_text(encoding="utf-8"))
    if entry.get("status") != "candidate":
        return False

    entry["status"] = "active"
    entry["promoted_at"] = _now()
    _atomic_write(path, entry)
    return True


def demote_golden(golden_id: str, reason: str = "") -> bool:
    """Demote a golden entry (set status to demoted).

    Returns True if demoted, False if not found.
    """
    path = GOLDEN_DIR / f"{golden_id}.json"
    if not path.exists():
        return False

    entry = json.loads(path.read_text(encoding="utf-8"))
    entry["status"] = "demoted"
    entry["demoted_at"] = _now()
    entry["demote_reason"] = reason
    _atomic_write(path, entry)
    return True


def list_golden(target: Optional[str] = None,
                status: str = "active",
                tags: Optional[List[str]] = None,
                limit: int = 50) -> List[dict]:
    """List golden entries with optional filters.

    Returns metadata only (without full trace) for listing efficiency.
    """
    if not GOLDEN_DIR.exists():
        return []

    entries = []
    for f in sorted(GOLDEN_DIR.glob("*.json")):
        entry = json.loads(f.read_text(encoding="utf-8"))
        if status and entry.get("status") != status:
            continue
        if target and entry.get("target") != target:
            continue
        if tags and not any(t in entry.get("tags", []) for t in tags):
            continue
        # Return metadata only
        entries.append({
            "golden_id": entry["golden_id"],
            "task_id": entry["task_id"],
            "target": entry["target"],
            "description": entry["description"],
            "status": entry["status"],
            "tags": entry["tags"],
            "added_at": entry["added_at"],
        })
        if len(entries) >= limit:
            break

    return entries


def get_golden(golden_id: str) -> Optional[dict]:
    """Get a full golden entry by id (includes trace)."""
    path = GOLDEN_DIR / f"{golden_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_all_golden_traces(target: Optional[str] = None) -> List[dict]:
    """Get all active golden traces for evaluation.

    Returns full traces (for use in benchmark/sandbox evaluation).
    """
    if not GOLDEN_DIR.exists():
        return []

    traces = []
    for f in sorted(GOLDEN_DIR.glob("*.json")):
        entry = json.loads(f.read_text(encoding="utf-8"))
        if entry.get("status") != "active":
            continue
        if target and entry.get("target") != target:
            continue
        traces.append(entry.get("trace", {}))
    return traces


def count_golden(target: Optional[str] = None) -> int:
    """Count active golden entries."""
    return len(list_golden(target=target, status="active", limit=1000))


# ─── Failures Tier ───

def add_failure(
    trace: dict,
    failure_reason: str = "",
    source_session: str = "",
    failure_type: str = "UNCLEAR",
) -> str:
    """Add a failure trace to the Failures tier.

    Args:
        trace: The failed trace dict.
        failure_reason: Why this task failed (from reflect or diagnose).
        source_session: Session id that produced this failure.
        failure_type: Classification (SKILL_DEFECT, EXECUTION_LAPSE, etc.)

    Returns:
        The failure entry id.
    """
    failure_id = f"failure-{uuid.uuid4().hex[:8]}"
    FAILURES_DIR.mkdir(parents=True, exist_ok=True)

    entry = {
        "failure_id": failure_id,
        "task_id": trace.get("task_id", ""),
        "target": trace.get("agent", {}).get("id", ""),
        "failure_reason": failure_reason,
        "failure_type": failure_type,
        "source_session": source_session,
        "added_at": _now(),
        "tags": [],
        "trace": trace,
    }

    path = FAILURES_DIR / f"{failure_id}.json"
    _atomic_write(path, entry)
    return failure_id


def list_failures(target: Optional[str] = None,
                  failure_type: Optional[str] = None,
                  limit: int = 100) -> List[dict]:
    """List failure entries with optional filters.

    Returns metadata only.
    """
    if not FAILURES_DIR.exists():
        return []

    entries = []
    for f in sorted(FAILURES_DIR.glob("*.json")):
        entry = json.loads(f.read_text(encoding="utf-8"))
        if target and entry.get("target") != target:
            continue
        if failure_type and entry.get("failure_type") != failure_type:
            continue
        entries.append({
            "failure_id": entry["failure_id"],
            "task_id": entry["task_id"],
            "target": entry["target"],
            "failure_reason": entry["failure_reason"],
            "failure_type": entry["failure_type"],
            "added_at": entry["added_at"],
        })
        if len(entries) >= limit:
            break

    return entries


def get_all_failure_traces(target: Optional[str] = None,
                           failure_type: Optional[str] = None) -> List[dict]:
    """Get all failure traces for evaluation."""
    if not FAILURES_DIR.exists():
        return []

    traces = []
    for f in sorted(FAILURES_DIR.glob("*.json")):
        entry = json.loads(f.read_text(encoding="utf-8"))
        if target and entry.get("target") != target:
            continue
        if failure_type and entry.get("failure_type") != failure_type:
            continue
        traces.append(entry.get("trace", {}))
    return traces


# ─── Helpers ───

def _atomic_write(path, data):
    """Atomic JSON write."""
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(path))