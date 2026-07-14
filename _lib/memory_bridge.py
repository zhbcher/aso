"""_lib/memory_bridge.py — Optimization Memory ↔ QMD Memory bridge.

Provides bidirectional conversion between ASO's structured Optimization Memory
and QMD's semantic search index. QMD handles vector search; ASO handles
structured analytics (success rates, operation statistics).

This is a skeleton implementation. QMD client calls are placeholders —
wire up to actual QMD SDK when available.
"""

from __future__ import annotations

import json
from typing import Any, Optional

try:
    from _lib.optimization_memory import query as om_query
    from _lib.optimization_memory import add_entry as om_add_entry
    from _lib.path_utils import OPTIMIZATION_MEMORY_FILE
except Exception:
    # Allow import-time without full ASO env (e.g., unit tests)
    om_query = None
    om_add_entry = None
    OPTIMIZATION_MEMORY_FILE = None


# ──────────────────────────────────────────────
# Conversion: OM entry ↔ QMD document
# ──────────────────────────────────────────────

def optimization_memory_entry_to_qmd_doc(entry: dict) -> dict:
    """
    Convert an Optimization Memory entry to a QMD document format.

    QMD expects: {id, text, metadata, ...}
    We embed structured fields in metadata; text is a natural-language summary.
    """
    ctx = entry.get("context", {})
    outcome = entry.get("outcome", {})

    text = (
        f"Optimization on skill '{entry.get('target', 'unknown')}': "
        f"failure={ctx.get('failure_pattern', 'unknown')}, "
        f"root_cause={ctx.get('root_cause', 'unknown')}, "
        f"delta={entry.get('delta_summary', '')}, "
        f"pass_rate_delta={outcome.get('pass_rate_delta', 0):.3f}, "
        f"deployed={outcome.get('deployed', False)}, "
        f"confidence={entry.get('confidence', 0):.2f}"
    )

    return {
        "id": entry.get("entry_id"),
        "text": text,
        "metadata": {
            "source": "aso_optimization_memory",
            "entry_id": entry.get("entry_id"),
            "session_id": entry.get("session_id"),
            "target": entry.get("target"),
            "operation_types": entry.get("operation_types", []),
            "failure_pattern": ctx.get("failure_pattern"),
            "root_cause": ctx.get("root_cause"),
            "delta_summary": entry.get("delta_summary"),
            "pass_rate_delta": outcome.get("pass_rate_delta", 0.0),
            "tokens_delta": outcome.get("tokens_delta", 0),
            "deployed": outcome.get("deployed", False),
            "rolled_back": outcome.get("rolled_back", False),
            "confidence": entry.get("confidence", 0.5),
        },
    }


def qmd_doc_to_optimization_memory_entry(doc: dict) -> dict | None:
    """
    Convert a QMD search result document back to an Optimization Memory entry.
    Returns None if the doc isn't an ASO optimization memory document.
    """
    meta = doc.get("metadata", {})
    if meta.get("source") != "aso_optimization_memory":
        return None

    return {
        "entry_id": meta.get("entry_id"),
        "session_id": meta.get("session_id"),
        "target": meta.get("target"),
        "operation_types": meta.get("operation_types", []),
        "context": {
            "failure_pattern": meta.get("failure_pattern"),
            "root_cause": meta.get("root_cause"),
        },
        "delta_summary": meta.get("delta_summary"),
        "outcome": {
            "pass_rate_delta": meta.get("pass_rate_delta", 0.0),
            "tokens_delta": meta.get("tokens_delta", 0),
            "deployed": meta.get("deployed", False),
            "rolled_back": meta.get("rolled_back", False),
        },
        "confidence": meta.get("confidence", 0.5),
    }


# ──────────────────────────────────────────────
# QMD sync / search (placeholders for real QMD SDK)
# ──────────────────────────────────────────────

class _QMDClient:
    """Abstract QMD client interface. Replace with real SDK calls."""

    def upsert_documents(self, docs: list[dict]) -> int:
        """Insert or update documents in QMD. Return count upserted."""
        raise NotImplementedError

    def search(self, query: str, filters: dict | None = None, top_k: int = 10) -> list[dict]:
        """Semantic search in QMD. Return list of documents."""
        raise NotImplementedError

    def delete(self, doc_ids: list[str]) -> int:
        """Delete documents by id. Return count deleted."""
        raise NotImplementedError


# Global client instance — inject at runtime
_qmd_client: _QMDClient | None = None


def set_qmd_client(client: _QMDClient) -> None:
    """Inject a real QMD client implementation."""
    global _qmd_client
    _qmd_client = client


def get_qmd_client() -> _QMDClient | None:
    return _qmd_client


def sync_to_qmd(target: str | None = None, limit: int = 100) -> int:
    """
    Push Optimization Memory entries to QMD for semantic search.

    Args:
        target: Optional skill target to filter (e.g., 'planner')
        limit: Max entries to sync

    Returns:
        Number of documents upserted.
    """
    if _qmd_client is None:
        return 0  # No QMD client configured

    if om_query is None:
        return 0  # Not in ASO environment

    entries = om_query(target=target, limit=limit)
    docs = [optimization_memory_entry_to_qmd_doc(e) for e in entries]
    return _qmd_client.upsert_documents(docs)


def search_qmd(
    query: str,
    target: str | None = None,
    top_k: int = 10,
    min_confidence: float = 0.0,
) -> list[dict]:
    """
    Semantic search over optimization history via QMD.

    Args:
        query: Natural language question (e.g., "how to fix tool timeout")
        target: Optional skill target filter
        top_k: Max results
        min_confidence: Filter by confidence in metadata

    Returns:
        List of Optimization Memory entries (converted from QMD results).
    """
    if _qmd_client is None:
        return []

    filters = {"source": "aso_optimization_memory"}
    if target:
        filters["target"] = target
    if min_confidence > 0:
        filters["confidence_min"] = min_confidence

    results = _qmd_client.search(query, filters=filters, top_k=top_k)
    entries = [qmd_doc_to_optimization_memory_entry(d) for d in results]
    return [e for e in entries if e is not None]


# ──────────────────────────────────────────────
# Local fallback: no QMD, just OM
# ──────────────────────────────────────────────

def local_search(
    query: str,
    target: str | None = None,
    top_k: int = 10,
) -> list[dict]:
    """
    Fallback search when QMD is unavailable — simple text match on OM entries.
    """
    if om_query is None:
        return []

    entries = om_query(target=target, limit=top_k * 5)
    query_lower = query.lower()

    def score(entry: dict) -> int:
        text = (
            f"{entry.get('target', '')} "
            f"{entry.get('context', {}).get('failure_pattern', '')} "
            f"{entry.get('context', {}).get('root_cause', '')} "
            f"{entry.get('delta_summary', '')}"
        ).lower()
        return sum(1 for word in query_lower.split() if word in text)

    scored = [(e, score(e)) for e in entries]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [e for e, s in scored[:top_k] if s > 0]


# ──────────────────────────────────────────────
# Stats / analytics (from OM, not QMD)
# ──────────────────────────────────────────────

def get_operation_success_rates(target: str | None = None) -> dict:
    """
    Get success rates per operation type from Optimization Memory.
    This is structured analytics — QMD doesn't do aggregations.
    """
    from _lib.optimization_memory import get_statistics
    return get_statistics(target=target)


def recommend_strategy_for_failure(
    failure_pattern: str,
    target: str | None = None,
    top_k: int = 3,
) -> list[dict]:
    """
    Given a failure pattern, recommend operation types that historically worked.
    Uses OM statistics (success_rate), not QMD semantic search.
    """
    stats = get_operation_success_rates(target=target)
    # Filter by failure_pattern via local search, then rank by success_rate
    candidates = local_search(failure_pattern, target=target, top_k=top_k * 2)

    # Build operation_type -> success_rate mapping
    op_rates = {op: s["success_rate"] for op, s in stats.items()}

    # Rank candidates by their operation types' success rates
    def entry_score(e: dict) -> float:
        return max((op_rates.get(op, 0) for op in e.get("operation_types", [])), default=0)

    candidates.sort(key=entry_score, reverse=True)
    return candidates[:top_k]