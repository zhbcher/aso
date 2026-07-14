"""Tests for _lib/memory_bridge.py"""

import pytest
import sys
import os

# Add _lib to path
_lib_dir = os.path.join(os.path.dirname(__file__), "..", "_lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from _lib.memory_bridge import (
    optimization_memory_entry_to_qmd_doc,
    qmd_doc_to_optimization_memory_entry,
    _QMDClient,
    set_qmd_client,
    get_qmd_client,
    local_search,
    recommend_strategy_for_failure,
)


class TestConversion:
    """Test OM entry ↔ QMD document conversion."""

    def sample_entry(self):
        return {
            "entry_id": "om-abc12345",
            "session_id": "sess-xyz",
            "target": "planner",
            "operation_types": ["add_param", "modify_prompt"],
            "context": {
                "failure_pattern": "TOOL_TIMEOUT",
                "root_cause": "LLM call exceeded timeout budget",
            },
            "delta_summary": "Increased timeout from 30s to 60s",
            "outcome": {
                "pass_rate_delta": 0.15,
                "tokens_delta": 120,
                "deployed": True,
                "rolled_back": False,
            },
            "confidence": 0.85,
        }

    def test_om_to_qmd_roundtrip(self):
        entry = self.sample_entry()
        doc = optimization_memory_entry_to_qmd_doc(entry)
        assert doc["id"] == "om-abc12345"
        assert doc["metadata"]["source"] == "aso_optimization_memory"
        assert doc["metadata"]["target"] == "planner"
        assert "TOOL_TIMEOUT" in doc["text"]
        assert "0.150" in doc["text"] or "0.15" in doc["text"]

        # Round-trip
        entry2 = qmd_doc_to_optimization_memory_entry(doc)
        assert entry2 is not None
        assert entry2["entry_id"] == entry["entry_id"]
        assert entry2["target"] == entry["target"]
        assert entry2["operation_types"] == entry["operation_types"]
        assert entry2["context"]["failure_pattern"] == "TOOL_TIMEOUT"
        assert entry2["outcome"]["pass_rate_delta"] == 0.15

    def test_qmd_doc_rejects_non_aso(self):
        doc = {"id": "x", "text": "foo", "metadata": {"source": "other"}}
        assert qmd_doc_to_optimization_memory_entry(doc) is None

    def test_qmd_doc_rejects_missing_metadata(self):
        doc = {"id": "x", "text": "foo", "metadata": {}}
        assert qmd_doc_to_optimization_memory_entry(doc) is None


class TestLocalSearch:
    """Test fallback local_search when QMD unavailable."""

    def test_local_search_matches_failure_pattern(self, monkeypatch):
        # Mock om_query to return known entries
        def mock_query(target=None, limit=20):
            return [
                {
                    "entry_id": "om-1",
                    "target": "planner",
                    "context": {"failure_pattern": "TOOL_TIMEOUT", "root_cause": "timeout"},
                    "delta_summary": "increase timeout",
                    "operation_types": ["modify_config"],
                },
                {
                    "entry_id": "om-2",
                    "target": "router",
                    "context": {"failure_pattern": "PARAM_MISSING", "root_cause": "missing arg"},
                    "delta_summary": "add default param",
                    "operation_types": ["add_param"],
                },
            ]

        import _lib.memory_bridge as mb
        monkeypatch.setattr(mb, "om_query", mock_query)

        results = local_search("timeout", target="planner", top_k=5)
        assert len(results) == 1
        assert results[0]["entry_id"] == "om-1"

    def test_local_search_filters_by_target(self, monkeypatch):
        def mock_query(target=None, limit=20):
            # Return entries matching the target filter
            if target == "planner":
                return [
                    {
                        "entry_id": "om-1",
                        "target": "planner",
                        "context": {"failure_pattern": "TOOL_TIMEOUT"},
                        "delta_summary": "fix",
                        "operation_types": ["modify_config"],
                    }
                ]
            elif target == "router":
                return []  # no entries for router
            return []

        import _lib.memory_bridge as mb
        monkeypatch.setattr(mb, "om_query", mock_query)

        results = local_search("timeout", target="router", top_k=5)
        assert len(results) == 0  # filtered by target

        # Verify target="planner" works
        results = local_search("timeout", target="planner", top_k=5)
        assert len(results) == 1
        assert results[0]["entry_id"] == "om-1"


class TestQMDClientInterface:
    """Test abstract client interface."""

    def test_client_must_implement_methods(self):
        class IncompleteClient(_QMDClient):
            pass

        client = IncompleteClient()
        with pytest.raises(NotImplementedError):
            client.upsert_documents([])

    def test_set_get_client(self):
        class DummyClient(_QMDClient):
            def upsert_documents(self, docs):
                return len(docs)

            def search(self, query, filters=None, top_k=10):
                return []

            def delete(self, doc_ids):
                return 0

        client = DummyClient()
        set_qmd_client(client)
        assert get_qmd_client() is client

        # Reset
        set_qmd_client(None)
        assert get_qmd_client() is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])