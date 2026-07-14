"""Tests for _lib/version_manager.py."""

import json
import pytest
from _lib.version_manager import (
    init_skill, bump_version, rollback_version,
    get_current_version, get_version_history, get_all_skills,
)


@pytest.fixture(autouse=True)
def clean_manifests(tmp_path, monkeypatch):
    """Use a temp manifests.json for each test, clear module cache to force reload."""
    from _lib import path_utils
    monkeypatch.setattr(path_utils, "MANIFESTS_FILE", tmp_path / "manifests.json")
    # Clear any cached imports of version_manager so it picks up the monkeypatched path
    import _lib.version_manager as vm
    monkeypatch.setattr(vm, "MANIFESTS_FILE", tmp_path / "manifests.json")
    yield


class TestVersionManager:
    def test_init_skill(self):
        v = init_skill("planner")
        assert v == "v1"
        assert get_current_version("planner") == "v1"

    def test_init_skill_idempotent(self):
        init_skill("planner")
        v = init_skill("planner")  # second call should return same
        assert v == "v1"

    def test_bump_version(self):
        init_skill("planner")
        v = bump_version("planner", "delta-001")
        assert v == "v2"
        assert get_current_version("planner") == "v2"

    def test_bump_auto_init(self):
        """bump_version on unregistered skill should auto-init."""
        v = bump_version("router", "delta-001")
        assert v == "v1"

    def test_version_history(self):
        init_skill("planner")
        bump_version("planner", "delta-001")
        bump_version("planner", "delta-002")
        history = get_version_history("planner")
        assert len(history) == 3  # v1 + v2 + v3
        assert history[0]["version"] == "v1"
        assert history[1]["version"] == "v2"
        assert history[1]["delta_id"] == "delta-001"
        assert history[1]["parent_version"] == "v1"
        assert history[2]["version"] == "v3"
        assert history[2]["parent_version"] == "v2"

    def test_rollback(self):
        init_skill("planner")
        bump_version("planner", "delta-001")
        bump_version("planner", "delta-002")
        assert get_current_version("planner") == "v3"

        rolled = rollback_version("planner")
        assert rolled == "v2"
        assert get_current_version("planner") == "v2"

    def test_rollback_no_history(self):
        init_skill("planner")
        rolled = rollback_version("planner")
        assert rolled is None  # No rollback target

    def test_rollback_unknown_skill(self):
        rolled = rollback_version("nonexistent")
        assert rolled is None

    def test_get_all_skills(self):
        init_skill("planner")
        init_skill("router")
        all_skills = get_all_skills()
        assert len(all_skills) == 2
        targets = {s["target"] for s in all_skills}
        assert targets == {"planner", "router"}

    def test_manifest_schema(self):
        """Verify the manifest file has the correct schema after operations."""
        init_skill("planner")
        bump_version("planner", "delta-001")
        from _lib.path_utils import MANIFESTS_FILE
        with open(MANIFESTS_FILE, "r") as f:
            data = json.load(f)
        entry = data[0]
        assert "target" in entry
        assert "current_version" in entry
        assert "versions" in entry
        assert "rollback_target" in entry
        assert len(entry["versions"]) == 2
        assert entry["versions"][0]["parent_version"] is None
        assert entry["versions"][1]["parent_version"] == "v1"