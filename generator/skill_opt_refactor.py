"""generator/skill_opt_refactor.py — ASO v2 Generator with SkillDelta output.

Upgraded from v1:
- Outputs SkillDelta structure (incremental patches) instead of full file replacement
- Integrates with Reflection result for change rationale
- Supports both "aso" and "delta" generation strategies
- Backward compatible: v1 output format still available via "aso" strategy

Reference: docs/skill-delta-spec.md
"""

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

ASO_DIR = Path(__file__).parent.parent


class SkillOptRefactor:
    """ASO v2 Generator — produces SkillDelta-structured candidates.

    Two generation modes:
    - "aso" (default): v1-compatible output (dict with changes list)
    - "delta": v2 SkillDelta output (dict with operations + rollback_plan)
    """
    name = "aso"

    def generate(self, target: str, traces: Optional[list] = None,
                 budget: Optional[dict] = None,
                 report: Optional[dict] = None,
                 reflection: Optional[dict] = None,
                 strategy: str = "delta",
                 **kwargs) -> dict:
        """
        Generate a SkillDelta candidate for the given target.

        Args:
            target: Skill to optimize
            traces: Trace data (for context)
            budget: Budget constraints
            report: Diagnosis report (for bottleneck analysis)
            reflection: Reflection result (for root cause and change rationale)
            strategy: "aso" (v1 compat) or "delta" (v2 SkillDelta)

        Returns:
            dict: Candidate with SkillDelta structure (v2) or v1 format.
        """
        if strategy == "delta":
            return self._generate_delta(target, traces, budget, report, reflection)
        else:
            return self._generate_v1(target, traces, budget, report, reflection)

    def _generate_delta(self, target: str, traces: Optional[list],
                        budget: Optional[dict],
                        report: Optional[dict],
                        reflection: Optional[dict]) -> dict:
        """Generate a SkillDelta-structured candidate.

        Uses the reflection result to determine:
        - What type of change is needed
        - Where to apply it
        - What the rationale is
        - Risk level and confidence

        Returns a dict matching the SkillDelta schema.
        """
        # Determine operation type from reflection
        recommended_change = "instruction_add"
        failure_type = "UNCLEAR"
        root_cause = ""
        confidence = 0.5

        if reflection:
            recommended_change = reflection.get("recommended_change_type", "instruction_add")
            failure_type = reflection.get("failure_type", "UNCLEAR")
            root_cause = reflection.get("root_cause", "")
            confidence = reflection.get("confidence", 0.5)

        # Build operations based on reflection
        operations = self._build_operations(target, recommended_change, failure_type, root_cause)

        # Determine risk
        risk = self._determine_risk(failure_type, len(operations), confidence)

        # Build rollback plan
        rollback_plan = {
            "type": "reverse_delta",
            "notes": f"Reverse {len(operations)} delta operations"
        }

        return {
            "delta_id": f"delta-{uuid.uuid4().hex[:8]}",
            "session_id": "",
            "target": target,
            "base_version": "current",
            "type": "delta_optimization",
            "mechanism": "skill_delta",
            "description": f"Apply {len(operations)} delta operations based on {failure_type} analysis",
            "changes": [],
            "operations": operations,
            "risk": risk,
            "generation_confidence": round(confidence, 4),
            "expected_effect": f"Address {failure_type.lower()}: {root_cause[:100]}" if root_cause else "Improve skill reliability",
            "change_rationale": root_cause,
            "rollback_plan": rollback_plan,
            "success": True,
            "proposal_type": "skill_delta",
        }

    def _build_operations(self, target: str, change_type: str,
                          failure_type: str, root_cause: str) -> list:
        """Build delta operations based on the recommended change type.

        This is a template-based generator. In production, this would be
        driven by LLM analysis of the actual traces.
        """
        ops = []

        if change_type == "instruction_add":
            ops.append({
                "type": "instruction_add",
                "target": {
                    "file": f"{target}.skill",
                    "selector_type": "text_section",
                    "selector": "Workflow",
                },
                "before": None,
                "after": f"# Auto-generated: {root_cause[:60] if root_cause else 'Improvement step'}",
                "reason": root_cause or f"Address {failure_type}",
            })

        elif change_type == "instruction_modify":
            ops.append({
                "type": "instruction_modify",
                "target": {
                    "file": f"{target}.skill",
                    "selector_type": "text_section",
                    "selector": "Workflow",
                },
                "before": "Previous instruction",
                "after": f"# Modified: {root_cause[:60] if root_cause else 'Improved instruction'}",
                "reason": root_cause or f"Modify based on {failure_type}",
            })

        elif change_type == "constraint_add":
            ops.append({
                "type": "constraint_add",
                "target": {
                    "file": f"{target}.skill",
                    "selector_type": "text_section",
                    "selector": "Constraints",
                },
                "before": None,
                "after": f"- {root_cause[:80] if root_cause else 'New constraint from analysis'}",
                "reason": root_cause or f"Add constraint based on {failure_type}",
            })

        elif change_type == "tool_call_modify":
            ops.append({
                "type": "tool_call_modify",
                "target": {
                    "file": f"{target}.skill",
                    "selector_type": "workflow_node",
                    "selector": "tool_execution",
                },
                "before": "Previous tool call",
                "after": "Verified tool call with parameter validation",
                "reason": root_cause or f"Modify tool call based on {failure_type}",
            })

        else:
            # Default: add instruction
            ops.append({
                "type": "instruction_add",
                "target": {
                    "file": f"{target}.skill",
                    "selector_type": "text_section",
                    "selector": "Workflow",
                },
                "before": None,
                "after": "# Improvement based on analysis",
                "reason": f"Address {failure_type}",
            })

        return ops

    def _determine_risk(self, failure_type: str, n_ops: int, confidence: float) -> str:
        """Determine risk level based on failure type and number of changes."""
        if n_ops >= 3:
            return "high"
        if failure_type in ("SKILL_DEFECT", "TOOL_DEFECT"):
            return "medium"
        if failure_type == "ENVIRONMENT_ISSUE":
            return "medium"
        return "low"

    def _generate_v1(self, target: str, traces: Optional[list],
                     budget: Optional[dict],
                     report: Optional[dict],
                     reflection: Optional[dict]) -> dict:
        """v1-compatible generation (kept for backward compatibility)."""
        # Extract priority from report
        priority = (report or {}).get("priority", ["context_utilization"])
        failure_type = (reflection or {}).get("failure_type", "UNCLEAR")

        return {
            "success": True,
            "modified_skill": True,
            "type": "aso_optimization",
            "mechanism": "skill_opt_refactor",
            "description": f"Applied optimization: target={target}, priority={priority[0] if priority else 'unknown'}, failure={failure_type}",
            "changes": [
                {
                    "action": "modify_skill_file",
                    "file_path": f"{target}.skill",
                    "new_content": "# Auto-optimized content",
                }
            ],
            "risk": "low",
            "expected_improvement": f"Improve {priority[0] if priority else 'performance'}",
            "metrics": {
                "pass_rate_improvement": 0.0,
                "token_reduction_pct": 0.0,
            },
            "files_modified": [f"{target}.skill"],
            "files_added": [],
            "proposal_type": "aso_optimization",
        }


def get_generator():
    """Registry entry point."""
    return SkillOptRefactor()