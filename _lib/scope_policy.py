"""Shared target and path policy for ASO.

Single source of truth for:
- evolution-policy allow/deny checks
- skill-local path traversal validation
- policy fallback when PyYAML is absent
"""

from __future__ import annotations

import os
import re
from pathlib import Path


def load_policy(policy_path: str | Path) -> dict:
    """Best-effort load of evolution-policy.yaml.

    Tries PyYAML first; if unavailable, falls back to regex parsing.
    On any structural failure, returns the safest allowed-empty policy.
    """
    policy_path = Path(policy_path)
    if not policy_path.exists():
        return {"policy": {"allow": [], "deny": []}}
    try:
        import yaml  # type: ignore

        with open(policy_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict) and "policy" in data:
            return data
    except Exception:
        pass
    return _parse_yaml_simple(policy_path)


def _parse_yaml_simple(path: Path) -> dict:  # pragma: no cover — fallback only
    policy: dict = {"policy": {"allow": [], "deny": []}}
    current: str | None = None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return policy
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "allow:":
            current = "allow"
        elif stripped == "deny:":
            current = "deny"
        elif current and stripped.startswith("- "):
            policy["policy"][current].append(stripped[2:])
    return policy


def validate_target(target: str, *, policy: dict | None = None, policy_path: str | Path | None = None) -> bool:
    """Return True if target is allowed by evolution-policy.

    Caller may pass an already-loaded policy dict, or a path. When neither is
    provided the policy is loaded from the default location guessed from the
    caller via os.path.
    """
    if policy is None:
        if policy_path is not None:
            policy = load_policy(policy_path)
        else:
            guess = Path(os.path.dirname(os.path.abspath(__file__))).parent / "evolution-policy.yaml"
            policy = load_policy(guess)
    inner = policy.get("policy", {}) if isinstance(policy, dict) else {}
    allow: list[str] = inner.get("allow", []) if isinstance(inner, dict) else []
    deny: list[str] = inner.get("deny", []) if isinstance(inner, dict) else []
    if target in deny:
        return False
    if not allow:
        return True
    return target in allow


DENY_SUBSTRINGS = ("runtime", "gateway", "scheduler", "kernel", "evolution-policy.yaml", "trace_schema.yaml")


def validate_sandbox_path(file_path_relative: str, skill_name: str, skills_dir: str | Path) -> str | None:
    """Validate a relative file path intended for a skill directory.

    Returns the normalized relative path on success or ``None`` if the path is
    rejected (absolute, traversal, or outside ``skills_dir/skill_name``).
    """
    if not file_path_relative:
        return None
    normalized = os.path.normpath(file_path_relative)
    if os.path.isabs(normalized) or normalized.startswith(".."):
        return None
    skill_base = Path(skills_dir) / skill_name
    try:
        resolved = (skill_base / normalized).resolve()
        resolved.relative_to(skill_base.resolve())
    except ValueError:
        return None
    return normalized


def denied_substrings() -> tuple[str, ...]:
    """Strings whose presence in a target/module path should be rejected."""
    return DENY_SUBSTRINGS
