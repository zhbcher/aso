#!/usr/bin/env python3
"""
ASO (Automatic Skill Optimizer): Convert evolve trace failures into skill-opt evals.

This script reads the trace_store.json from evolve, identifies failed or suboptimal
runs, and generates test cases in the skill-opt evals format.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

def load_trace(trace_path="state/trace_store.json"):
    with open(trace_path) as f:
        return json.load(f)

def convert_trace_to_evals(trace_data, skill_name=None):
    """
    Convert trace entries into skill-opt eval format.
    We focus on:
      - Cases with 'failed' flag
      - Cases with high token usage (optional threshold)
      - Cases with low success rate
    """
    evals = []
    if "entries" not in trace_data:
        return evals

    for entry in trace_data["entries"]:
        # Only convert failures or notable warnings
        if not entry.get("failed") and not entry.get("warning"):
            continue

        test_id = f"aso-trace-{entry['id']}"
        prompt = entry.get("prompt", "")
        expected = entry.get("expected_output", "")
        actual = entry.get("actual_output", "")

        # Build assertions based on failure type
        assertions = []
        if entry.get("failed"):
            assertions.append("Output must match expected exactly")
        if "timeout" in entry.get("error", "").lower():
            assertions.append("Response must arrive within timeout")
        if "token" in entry.get("error", "").lower():
            assertions.append("Token consumption must be within limit")

        eval_case = {
            "id": test_id,
            "description": f"Auto-generated from trace: {entry.get('context', 'unknown')}",
            "prompt": prompt,
            "files": [],  # TODO: attach referenced files if present
            "setup": {
                "skill_name": skill_name,
                "trace_id": entry["id"]
            },
            "expected_output": {
                "should_contain": [],
                "should_not_contain": [],
                "exact_match": expected
            },
            "assertions": assertions,
            "severity": "high" if entry.get("failed") else "medium"
        }
        evals.append(eval_case)

    return evals

def main():
    skill_name = sys.argv[1] if len(sys.argv) > 1 else None
    trace_path = Path("state/trace_store.json")
    if not trace_path.exists():
        print(f"Trace file not found: {trace_path}", file=sys.stderr)
        sys.exit(1)

    trace_data = load_trace(trace_path)
    evals = convert_trace_to_evals(trace_data, skill_name)

    out_path = Path("evals/trace_based_evals.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(evals, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(evals)} eval cases to {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
