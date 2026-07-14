"""_lib/policy_engine.py — Evolution Policy Engine for ASO v2.

Evaluates SkillDelta against the evolution policy to determine:
- auto_approve: gate can pass directly
- require_review: needs human approval
- auto_reject: blocked by policy

Reference: docs/evolution-policy.md
"""

from __future__ import annotations

import os
import yaml
from typing import Optional

from _lib.path_utils import EVOLUTION_POLICY_FILE
from _lib.default_policy import _default_policy
from _lib.delta import SkillDelta


def _load_policy() -> dict:
    """Load policy from file, falling back to defaults if not found."""
    if EVOLUTION_POLICY_FILE.exists():
        with open(EVOLUTION_POLICY_FILE, "r", encoding="utf-8") as f:
            try:
                return yaml.safe_load(f) or {}
            except yaml.YAMLError:
                pass
    # Fall back to default
    return yaml.safe_load(_default_policy) or {}


def evaluate(
    delta: SkillDelta,
    target: str,
    session_count: int = 0,
    consecutive_successes: int = 0,
) -> dict:
    """Evaluate a SkillDelta against policy.

    Returns:
        {
            "verdict": "auto_approve" | "require_review" | "auto_reject",
            "reason": "human-readable explanation",
            "matched_rule": "rule description",
        }
    """
    policy = _load_policy()
    policy_data = policy.get("policy", {})

    # 1. Check deny targets
    deny_targets = policy_data.get("deny", {}).get("targets", [])
    if target in deny_targets:
        return {
            "verdict": "auto_reject",
            "reason": f"Target '{target}' is in deny list",
            "matched_rule": "deny.targets",
        }

    # 2. Check deny operations
    deny_ops = policy_data.get("deny", {}).get("operations", [])
    for op in delta.operations:
        if op.type in deny_ops:
            return {
                "verdict": "auto_reject",
                "reason": f"Operation type '{op.type}' is denied",
                "matched_rule": "deny.operations",
            }

    # 3. Check compound rules (first match wins)
    compound_rules = policy_data.get("compound_rules", [])
    for rule in compound_rules:
        condition = rule.get("if", {})
        result = _check_compound_condition(condition, delta, target, session_count, consecutive_successes)
        if result:
            return {
                "verdict": rule.get("then", "require_review"),
                "reason": f"Compound rule matched: {condition}",
                "matched_rule": f"compound_rules[{compound_rules.index(rule)}]",
            }

    # 4. Check by operation type
    by_op = policy_data.get("by_operation_type", {})
    for op in delta.operations:
        verdict = by_op.get(op.type, policy_data.get("default", "require_review"))
        if verdict == "auto_reject":
            return {
                "verdict": "auto_reject",
                "reason": f"Operation type '{op.type}' is auto-rejected",
                "matched_rule": "by_operation_type",
            }

    # 5. Check by risk
    by_risk = policy_data.get("by_risk", {})
    risk_verdict = by_risk.get(delta.risk, policy_data.get("default", "require_review"))

    if risk_verdict == "auto_reject":
        return {
            "verdict": "auto_reject",
            "reason": f"Risk level '{delta.risk}' is auto-rejected",
            "matched_rule": "by_risk",
        }

    return {
        "verdict": risk_verdict,
        "reason": f"Risk '{delta.risk}' → {risk_verdict}",
        "matched_rule": "by_risk",
    }


def _check_compound_condition(
    condition: dict,
    delta: SkillDelta,
    target: str,
    session_count: int,
    consecutive_successes: int,
) -> bool:
    """Check if a compound rule condition matches."""
    # Check risk
    risk_condition = condition.get("risk")
    if risk_condition and risk_condition != delta.risk:
        return False

    # Check target
    target_condition = condition.get("target")
    if target_condition:
        if target_condition == "any":
            pass
        elif isinstance(target_condition, list) and target not in target_condition:
            return False
        elif isinstance(target_condition, str) and target != target_condition:
            return False

    # Check operation types
    op_type_condition = condition.get("operation_type")
    if op_type_condition:
        delta_types = {op.type for op in delta.operations}
        if isinstance(op_type_condition, list):
            if not delta_types.intersection(op_type_condition):
                return False
        elif isinstance(op_type_condition, str):
            if op_type_condition not in delta_types:
                return False

    # Check session count
    session_condition = condition.get("session_count")
    if session_condition is not None:
        if isinstance(session_condition, int) and session_count < session_condition:
            return False

    # Check consecutive successes
    success_condition = condition.get("consecutive_successes")
    if success_condition is not None:
        if isinstance(success_condition, str) and success_condition.startswith(">="):
            threshold = int(success_condition.replace(">=", "").strip())
            if consecutive_successes < threshold:
                return False

    return True