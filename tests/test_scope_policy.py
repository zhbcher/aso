import importlib.util
from pathlib import Path

ASO_DIR = Path(__file__).resolve().parents[1]
SCOPE_MOD = ASO_DIR / "_lib" / "scope_policy.py"
spec = importlib.util.spec_from_file_location("scope_policy", SCOPE_MOD)
scope_policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope_policy)


def _write_policy(tmp_path, allow):
    p = tmp_path / "evolution-policy.yaml"
    p.write_text("policy:\n  allow:\n" + "\n".join(f"    - {item}" for item in allow) + "\n  deny:\n    - runtime\n", encoding="utf-8")
    return str(p)


def test_allowed_target_is_accepted(tmp_path):
    policy_path = _write_policy(tmp_path, ["planner", "workflow"])
    assert scope_policy.validate_target("planner", policy_path=policy_path) is True
    assert scope_policy.validate_target("workflow", policy_path=policy_path) is True


def test_disallowed_target_is_rejected(tmp_path):
    policy_path = _write_policy(tmp_path, ["planner"])
    assert scope_policy.validate_target("gateway", policy_path=policy_path) is False


def test_deny_blocklist_is_respected(tmp_path):
    policy_path = _write_policy(tmp_path, ["*"])
    assert scope_policy.validate_target("runtime", policy_path=policy_path) is False


def test_missing_policy_allows_all(tmp_path):
    assert scope_policy.validate_target("planner", policy_path=str(tmp_path / "missing.yaml")) is True


def test_path_validation_blocks_traversal():
    skills_dir = str((ASO_DIR / "tests" / "fake_skills"))
    assert scope_policy.validate_sandbox_path("SKILL.md", "planner", skills_dir) == "SKILL.md"
    assert scope_policy.validate_sandbox_path("../../etc/passwd", "planner", skills_dir) is None
    assert scope_policy.validate_sandbox_path("/etc/passwd", "planner", skills_dir) is None
    assert scope_policy.validate_sandbox_path("", "planner", skills_dir) is None


def test_denied_substrings_are_exposed():
    subs = scope_policy.denied_substrings()
    assert "gateway" in subs
    assert "runtime" in subs
