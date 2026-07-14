"""_lib/optimization_memory.py — Structured optimization experience store.

Records what optimization operations were performed, on which skill,
what the outcome was, and the confidence level. Used by Meta Optimization
Memory (Phase 3) to recommend high-success-rate strategies.

Compatible with QMD Memory: data can be fed into QMD for semantic retrieval.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Optional

from _lib.path_utils import OPTIMIZATION_MEMORY_FILE


def _load() -> dict:
    if OPTIMIZATION_MEMORY_FILE.exists():
        with open(OPTIMIZATION_MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"schema_version": "v1", "entries": []}


def _save(data: dict) -> None:
    tmp = str(OPTIMIZATION_MEMORY_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(OPTIMIZATION_MEMORY_FILE))


def add_entry(
    session_id: str,
    target: str,
    operation_types: list[str],
    failure_pattern: str,
    root_cause: str,
    delta_summary: str,
    outcome: dict,
    confidence: float = 0.5,
) -> str:
    """Record one optimization experience entry.

    Args:
        session_id: Associated evolution session
        target: Skill being optimized (planner, router, etc.)
        operation_types: List of delta operation types used
        failure_pattern: What problem was being solved
        root_cause: Reflect engine's root cause analysis
        delta_summary: Brief description of the delta applied
        outcome: {'pass_rate_delta': float, 'tokens_delta': float,
                  'deployed': bool, 'rolled_back': bool}
        confidence: How confident we are in this entry (0.0-1.0)

    Returns:
        The entry id.
    """
    entry_id = f"om-{uuid.uuid4().hex[:8]}"
    entry = {
        "entry_id": entry_id,
        "session_id": session_id,
        "target": target,
        "operation_types": operation_types,
        "context": {
            "failure_pattern": failure_pattern,
            "root_cause": root_cause,
        },
        "delta_summary": delta_summary,
        "outcome": {
            "pass_rate_delta": outcome.get("pass_rate_delta", 0.0),
            "tokens_delta": outcome.get("tokens_delta", 0.0),
            "deployed": outcome.get("deployed", False),
            "rolled_back": outcome.get("rolled_back", False),
        },
        "confidence": confidence,
    }
    data = _load()
    data["entries"].append(entry)
    _save(data)
    return entry_id


def query(target: Optional[str] = None,
          operation_type: Optional[str] = None,
          min_confidence: float = 0.0,
          limit: int = 20) -> list[dict]:
    """Query optimization memory with optional filters."""
    data = _load()
    entries = data.get("entries", [])

    if target:
        entries = [e for e in entries if e.get("target") == target]
    if operation_type:
        entries = [e for e in entries if operation_type in e.get("operation_types", [])]
    if min_confidence > 0:
        entries = [e for e in entries if e.get("confidence", 0) >= min_confidence]

    # Sort by confidence descending
    entries.sort(key=lambda e: e.get("confidence", 0), reverse=True)
    return entries[:limit]


def get_statistics(target: Optional[str] = None) -> dict:
    """Get success/failure statistics for optimization operations.

    Returns dict mapping operation_type -> {attempts, successes, success_rate}.
    """
    data = _load()
    entries = data.get("entries", [])
    if target:
        entries = [e for e in entries if e.get("target") == target]

    stats: dict = {}
    for entry in entries:
        for op_type in entry.get("operation_types", []):
            if op_type not in stats:
                stats[op_type] = {"attempts": 0, "successes": 0}
            stats[op_type]["attempts"] += 1
            if entry.get("outcome", {}).get("deployed") and not entry.get("outcome", {}).get("rolled_back"):
                stats[op_type]["successes"] += 1

    for op_type, s in stats.items():
        s["success_rate"] = round(s["successes"] / s["attempts"], 4) if s["attempts"] > 0 else 0.0

    return stats


def get_entry_count() -> int:
    """Total number of optimization memory entries."""
    data = _load()
    return len(data.get("entries", []))