#!/usr/bin/env python3
"""trace_to_eval.py — Convert failed/noteworthy ASO traces into eval cases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_trace(trace_path: str | Path) -> Any:
    path = Path(trace_path)
    if not path.exists():
        raise FileNotFoundError(f"trace file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def convert_trace_to_evals(trace_data: dict[str, Any], skill_name: str | None = None) -> list[dict[str, Any]]:
    """Convert failure / warning traces into eval cases."""
    entries = trace_data.get("entries")
    if not entries:
        return []

    cases: list[dict[str, Any]] = []
    for entry in entries:
        if not entry.get("failed") and not entry.get("warning"):
            continue

        prompt = entry.get("prompt", "")
        assertions: list[str] = []
        assertion_severity = "medium"

        error = (entry.get("error") or "").lower()
        if entry.get("failed"):
            assertions.append("Output must match expected output")
            assertion_severity = "high"
        if "timeout" in error:
            assertions.append("Response must arrive within timeout")
        if "token" in error:
            assertions.append("Token consumption must be within budget")

        cases.append({
            "id": f"aso-trace-{entry.get('id', 'unknown')}",
            "description": entry.get("context") or "Auto-generated from ASO trace",
            "prompt": prompt,
            "files": [],
            "setup": {
                "skill_name": skill_name,
                "trace_id": entry.get("id"),
            },
            "expected_output": {
                "should_contain": [],
                "should_not_contain": [],
            },
            "assertions": assertions,
            "severity": assertion_severity,
        })

    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="trace_to_eval",
        description="Convert failed ASO traces into skill-opt eval cases.",
    )
    parser.add_argument("--skill-name", help="Target skill name for eval case metadata")
    parser.add_argument("--input", default="state/trace_store.json", help="Path to ASO trace store")
    parser.add_argument("--output", default="evals/aso_self_evals.json", help="Output eval cases path")
    parser.add_argument("--help", action="help", help="Show this help message")

    args = parser.parse_args(argv)

    try:
        trace_data = load_trace(args.input)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    cases = convert_trace_to_evals(trace_data, skill_name=args.skill_name)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(cases, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps({
            "status": "ok",
            "created": len(cases),
            "output": str(out_path),
        }),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
