"""_lib/delta.py — SkillDelta: incremental skill modification model.

Defines the typed data structures for delta-based skill evolution,
replacing raw file-level modifications with structured, verifiable patches.

Reference: docs/skill-delta-spec.md
"""

from __future__ import annotations

import json
import os
import uuid
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


# ─── TargetPath ───

@dataclass
class TargetPath:
    """Structured location for a modification target.

    Supports multiple selector types:
    - text_section: section name in a markdown/text file
    - line_range: explicit line range (format: "start-end")
    - yaml_path: dot-delimited YAML path
    - workflow_node: workflow node selector
    """
    file: str
    selector_type: str  # text_section | line_range | yaml_path | workflow_node
    selector: str

    @classmethod
    def from_dict(cls, d: dict) -> TargetPath:
        return cls(
            file=str(d.get("file", "")),
            selector_type=str(d.get("selector_type", "text_section")),
            selector=str(d.get("selector", "")),
        )

    def to_dict(self) -> dict:
        return {"file": self.file, "selector_type": self.selector_type, "selector": self.selector}


# ─── DeltaOperation ───

VALID_OPERATION_TYPES = frozenset({
    "instruction_add", "instruction_remove", "instruction_modify",
    "constraint_add", "constraint_remove", "constraint_modify",
    "step_add", "step_remove", "step_modify",
    "workflow_reorder",
    "tool_call_add", "tool_call_remove", "tool_call_modify",
})


@dataclass
class DeltaOperation:
    """A single incremental change operation."""
    type: str
    target: TargetPath
    before: Optional[str] = None
    after: Optional[str] = None
    reason: str = ""

    def validate(self) -> list[str]:
        errors = []
        if self.type not in VALID_OPERATION_TYPES:
            errors.append(f"Unknown operation type: {self.type}")
        add_types = {"instruction_add", "constraint_add", "step_add", "tool_call_add"}
        remove_types = {"instruction_remove", "constraint_remove", "step_remove", "tool_call_remove"}
        if self.type in add_types and self.before is not None:
            errors.append(f"{self.type}: before must be null")
        if self.type in add_types and self.after is None:
            errors.append(f"{self.type}: after must not be null")
        if self.type in remove_types and self.after is not None:
            errors.append(f"{self.type}: after must be null")
        if self.type in remove_types and self.before is None:
            errors.append(f"{self.type}: before must not be null")
        if not self.reason or len(self.reason) < 10:
            errors.append(f"reason too short ({len(self.reason)} chars, need >= 10)")
        return errors

    @classmethod
    def from_dict(cls, d: dict) -> DeltaOperation:
        return cls(
            type=str(d.get("type", "")),
            target=TargetPath.from_dict(d.get("target", {})),
            before=d.get("before"),
            after=d.get("after"),
            reason=str(d.get("reason", "")),
        )

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "target": self.target.to_dict(),
            "before": self.before,
            "after": self.after,
            "reason": self.reason,
        }


# ─── RollbackPlan ───

@dataclass
class RollbackPlan:
    """Each delta carries its own rollback strategy."""
    type: str  # version_restore | reverse_delta | manual
    target_version: Optional[str] = None
    reverse_operations: Optional[list[DeltaOperation]] = None
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> RollbackPlan:
        reverse = d.get("reverse_operations")
        if reverse is not None:
            reverse = [DeltaOperation.from_dict(op) for op in reverse]
        return cls(
            type=str(d.get("type", "manual")),
            target_version=d.get("target_version"),
            reverse_operations=reverse,
            notes=str(d.get("notes", "")),
        )

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "target_version": self.target_version,
            "reverse_operations": [op.to_dict() for op in self.reverse_operations] if self.reverse_operations else None,
            "notes": self.notes,
        }


# ─── SkillDelta ───

@dataclass
class SkillDelta:
    """Incremental skill modification — a structured, verifiable patch."""
    delta_id: str
    session_id: str
    target: str
    base_version: str
    operations: list[DeltaOperation]
    risk: str = "low"  # low | medium | high
    generation_confidence: float = 0.0
    expected_effect: str = ""
    change_rationale: str = ""
    rollback_plan: Optional[RollbackPlan] = None

    def validate(self) -> dict:
        """Validate the entire delta. Returns {valid: bool, errors: [str]}."""
        errors = []
        if not self.delta_id:
            errors.append("delta_id is required")
        if not self.session_id:
            errors.append("session_id is required")
        if not self.target:
            errors.append("target is required")
        if not self.base_version:
            errors.append("base_version is required")
        if not self.operations:
            errors.append("at least one operation required")
        if self.risk not in ("low", "medium", "high"):
            errors.append(f"invalid risk: {self.risk}")
        if len(self.operations) > 5:
            errors.append(f"too many operations ({len(self.operations)}), max 5")
        if self.generation_confidence < 0 or self.generation_confidence > 1:
            errors.append(f"generation_confidence out of range: {self.generation_confidence}")
        if self.risk == "low" and len(self.operations) >= 3:
            errors.append("3+ operations cannot be low risk")
        for op in self.operations:
            errors.extend(op.validate())
        if not self.rollback_plan:
            errors.append("rollback_plan is required")
        return {"valid": len(errors) == 0, "errors": errors}

    def estimated_changed_lines(self) -> int:
        """Estimate total changed lines across all operations."""
        total = 0
        for op in self.operations:
            if op.before:
                total += len(op.before.split("\n"))
            if op.after:
                total += len(op.after.split("\n"))
        return total

    @classmethod
    def create(cls, session_id: str, target: str, base_version: str,
               operations: list[DeltaOperation], risk: str = "low",
               generation_confidence: float = 0.0,
               expected_effect: str = "",
               change_rationale: str = "",
               rollback_plan: Optional[RollbackPlan] = None) -> SkillDelta:
        delta_id = f"delta-{uuid.uuid4().hex[:8]}"
        if rollback_plan is None:
            rollback_plan = RollbackPlan(type="manual", notes="No auto-rollback defined")
        return cls(
            delta_id=delta_id,
            session_id=session_id,
            target=target,
            base_version=base_version,
            operations=operations,
            risk=risk,
            generation_confidence=generation_confidence,
            expected_effect=expected_effect,
            change_rationale=change_rationale,
            rollback_plan=rollback_plan,
        )

    @classmethod
    def from_dict(cls, d: dict) -> SkillDelta:
        ops = [DeltaOperation.from_dict(op) for op in d.get("operations", [])]
        rp = d.get("rollback_plan")
        return cls(
            delta_id=str(d.get("delta_id", "")),
            session_id=str(d.get("session_id", "")),
            target=str(d.get("target", "")),
            base_version=str(d.get("base_version", "")),
            operations=ops,
            risk=str(d.get("risk", "low")),
            generation_confidence=float(d.get("generation_confidence", 0.0)),
            expected_effect=str(d.get("expected_effect", "")),
            change_rationale=str(d.get("change_rationale", "")),
            rollback_plan=RollbackPlan.from_dict(rp) if rp else None,
        )

    def to_dict(self) -> dict:
        return {
            "delta_id": self.delta_id,
            "session_id": self.session_id,
            "target": self.target,
            "base_version": self.base_version,
            "operations": [op.to_dict() for op in self.operations],
            "risk": self.risk,
            "generation_confidence": self.generation_confidence,
            "expected_effect": self.expected_effect,
            "change_rationale": self.change_rationale,
            "rollback_plan": self.rollback_plan.to_dict() if self.rollback_plan else None,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# ─── apply_delta ───

def apply_delta(skill_content: str, operation: DeltaOperation) -> str:
    """Apply a single DeltaOperation to skill file content.

    Supports:
    - text_section: find section by header (# Section) and modify content
    - line_range: direct line replacement
    - workflow_node: find workflow step by name

    Returns modified content.
    """
    target = operation.target

    if target.selector_type == "line_range":
        return _apply_line_range(skill_content, operation)

    elif target.selector_type == "text_section":
        return _apply_text_section(skill_content, operation)

    elif target.selector_type == "workflow_node":
        return _apply_workflow_node(skill_content, operation)

    else:
        # Fallback: try text_section
        return _apply_text_section(skill_content, operation)


def _apply_line_range(content: str, op: DeltaOperation) -> str:
    """Apply operation to a line range (format: 'start-end' or just 'line')."""
    lines = content.split("\n")
    selector = op.target.selector

    if "-" in selector:
        parts = selector.split("-")
        start = max(0, int(parts[0]) - 1)
        end = int(parts[1]) if len(parts) > 1 else start + 1
    else:
        start = max(0, int(selector) - 1)
        end = start + 1

    if op.type.endswith("_remove"):
        # Remove the range
        return "\n".join(lines[:start] + lines[end:])

    elif op.type.endswith("_add"):
        # Insert after the range
        after_line = op.after or ""
        return "\n".join(lines[:end] + [after_line] + lines[end:])

    elif op.type.endswith("_modify"):
        # Replace the range
        after_line = op.after or ""
        return "\n".join(lines[:start] + [after_line] + lines[end:])

    return content


def _apply_text_section(content: str, op: DeltaOperation) -> str:
    """Find a section by markdown header and modify its body."""
    lines = content.split("\n")
    section_header = op.target.selector

    # Find section start
    section_start = -1
    section_end = len(lines)
    for i, line in enumerate(lines):
        if line.strip().startswith("#") and section_header.lower() in line.lower():
            section_start = i
            break

    if section_start < 0:
        # Section not found, append
        if op.type.endswith("_add"):
            return content.rstrip("\n") + f"\n\n# {section_header}\n{op.after or ''}\n"
        return content

    # Find section end (next header or EOF)
    for i in range(section_start + 1, len(lines)):
        if lines[i].strip().startswith("#"):
            section_end = i
            break

    section_body = "\n".join(lines[section_start + 1:section_end])
    add_types = {"instruction_add", "constraint_add", "step_add", "tool_call_add"}
    remove_types = {"instruction_remove", "constraint_remove", "step_remove", "tool_call_remove"}

    if op.type in remove_types:
        # Remove matching content from section
        if op.before and op.before in section_body:
            section_body = section_body.replace(op.before, "")
            return "\n".join(lines[:section_start + 1] + [section_body.strip()] + lines[section_end:])
        return content  # Content not found, no change

    elif op.type in add_types:
        # Append to section
        new_body = section_body.strip() + "\n" + (op.after or "") if section_body.strip() else (op.after or "")
        return "\n".join(lines[:section_start + 1] + [new_body] + lines[section_end:])

    elif op.type.endswith("_modify"):
        # Replace matching before with after
        if op.before and op.before in section_body:
            section_body = section_body.replace(op.before, op.after or "", 1)
            return "\n".join(lines[:section_start + 1] + [section_body.strip()] + lines[section_end:])
        return content  # No match, no change

    elif op.type == "workflow_reorder":
        # Replace entire section body
        section_body = op.after or section_body
        return "\n".join(lines[:section_start + 1] + [section_body.strip()] + lines[section_end:])

    return content


def _apply_workflow_node(content: str, op: DeltaOperation) -> str:
    """Find a workflow step by name and modify."""
    lines = content.split("\n")
    step_name = op.target.selector
    target_idx = -1

    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if stripped.startswith("##") and step_name.lower() in stripped:
            target_idx = i
            break

    if target_idx < 0:
        return content  # Step not found

    # Find block end (next ## or EOF)
    block_end = len(lines)
    for i in range(target_idx + 1, len(lines)):
        if lines[i].strip().startswith("##"):
            block_end = i
            break

    if op.type.endswith("_modify"):
        before = op.before or ""
        after = op.after or ""
        block_text = "\n".join(lines[target_idx:block_end])
        if before in block_text:
            block_text = block_text.replace(before, after, 1)
        else:
            block_text = block_text + "\n" + after
        return "\n".join(lines[:target_idx] + [block_text] + lines[block_end:])

    if op.type.endswith("_remove"):
        before = op.before or ""
        block_text = "\n".join(lines[target_idx:block_end])
        if before in block_text:
            block_text = block_text.replace(before, "", 1)
            lines_out = lines[:target_idx] + ([""] if not block_text.strip() else [block_text.strip()]) + lines[block_end:]
            return "\n".join(lines_out)
        return content

    if op.type.endswith("_add"):
        after = op.after or ""
        block_text = "\n".join(lines[target_idx:block_end])
        block_text = block_text + "\n" + after
        return "\n".join(lines[:target_idx] + [block_text] + lines[block_end:])

    return content


def apply_delta_to_file(file_path: str, delta: SkillDelta) -> str:
    """Apply a full SkillDelta to a skill file. Returns the modified content."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    for operation in delta.operations:
        content = apply_delta(content, operation)

    return content


# ─── reverse delta helper ───

def reverse_operation(op: DeltaOperation) -> DeltaOperation:
    """Create the reverse of a DeltaOperation for rollback."""
    add_types = {"instruction_add", "constraint_add", "step_add", "tool_call_add"}
    remove_types = {"instruction_remove", "constraint_remove", "step_remove", "tool_call_remove"}

    if op.type in add_types:
        reverse_type = op.type.replace("_add", "_remove")
        return DeltaOperation(
            type=reverse_type,
            target=op.target,
            before=op.after,
            after=None,
            reason=f"Rollback: {op.reason}",
        )
    elif op.type in remove_types:
        reverse_type = op.type.replace("_remove", "_add")
        return DeltaOperation(
            type=reverse_type,
            target=op.target,
            before=None,
            after=op.before,
            reason=f"Rollback: {op.reason}",
        )
    else:
        # modify -> modify (swap before/after)
        return DeltaOperation(
            type=op.type,
            target=op.target,
            before=op.after,
            after=op.before,
            reason=f"Rollback: {op.reason}",
        )