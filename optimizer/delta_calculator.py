# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Delta Calculator for Skill Optimizer.

This script computes performance deltas between baseline and new benchmark results.
It supports two modes:
  --init    : Initialize baseline.json from skill directory (placeholder)
  --compare : Compare new benchmark.json against baseline and output delta

Output is always JSON to stdout.

Example:
  python delta_calculator.py --init --skill-path ./my-skill
  python delta_calculator.py --compare --new-result ./workspace/iteration-1/benchmark.json
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, Any

def safe_mean(data: Dict[str, Any]) -> float:
    """Extract mean value from benchmark data structure."""
    if not data:
        return 0.0
    return float(data.get("mean", 0.0))

def compute_delta(
    baseline_with: Dict[str, Any],
    baseline_without: Dict[str, Any],
    new_with: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compute performance deltas.

    Returns dict with:
      - pass_rate_vs_without: improvement vs no-skill baseline
      - pass_rate_vs_old: change vs previous skill version
      - tokens_vs_old_pct: token change percentage
      - time_vs_old_pct: time change percentage
      - verdict: "improved" | "failed" | "neutral"
    """
    new_pass = safe_mean(new_with.get("pass_rate", {}))
    old_pass = safe_mean(baseline_with.get("pass_rate", {}))
    base_pass = safe_mean(baseline_without.get("pass_rate", {}))

    new_tokens = safe_mean(new_with.get("tokens", {}))
    old_tokens = safe_mean(baseline_with.get("tokens", {}))
    new_time = safe_mean(new_with.get("time_seconds", {}))
    old_time = safe_mean(baseline_with.get("time_seconds", {}))

    # Compute deltas
    delta = {
        "pass_rate_vs_without": new_pass - base_pass,
        "pass_rate_vs_old": new_pass - old_pass,
        "tokens_vs_old_pct": ((new_tokens - old_tokens) / old_tokens * 100) if old_tokens != 0 else 0,
        "time_vs_old_pct": ((new_time - old_time) / old_time * 100) if old_time != 0 else 0,
    }

    # Verdict logic
    if delta["pass_rate_vs_old"] <= 0 and delta["tokens_vs_old_pct"] > 20:
        verdict = "failed"
    else:
        if delta["pass_rate_vs_old"] > 0 or delta["tokens_vs_old_pct"] < 0:
            verdict = "improved"
        else:
            verdict = "neutral"

    delta["verdict"] = verdict
    return delta

def init_baseline(skill_path: str, baseline_file: str) -> Dict[str, Any]:
    """Create initial baseline.json template."""
    baseline = {
        "without_skill": {
            "pass_rate": {"mean": 0.0},
            "time_seconds": {"mean": 0.0},
            "tokens": {"mean": 0.0}
        },
        "with_skill": {
            "pass_rate": {"mean": 0.0},
            "time_seconds": {"mean": 0.0},
            "tokens": {"mean": 0.0}
        },
        "metadata": {
            "skill_path": skill_path,
            "created_at": "auto-init"
        }
    }
    Path(baseline_file).parent.mkdir(parents=True, exist_ok=True)
    with open(baseline_file, "w") as f:
        json.dump(baseline, f, indent=2)
    return baseline

def main():
    parser = argparse.ArgumentParser(description="Skill Delta Calculator")
    parser.add_argument("--init", action="store_true", help="Initialize baseline template")
    parser.add_argument("--skill-path", help="Path to skill directory (required for --init)")
    parser.add_argument("--compare", action="store_true", help="Compare new benchmark against baseline")
    parser.add_argument("--new-result", help="Path to new benchmark.json (required for --compare)")
    parser.add_argument("--baseline-file", default="baseline.json", help="Baseline file path")
    args = parser.parse_args()

    if args.init:
        if not args.skill_path:
            print("Error: --skill-path required for --init", file=sys.stderr)
            sys.exit(1)
        result = init_baseline(args.skill_path, args.baseline_file)
        print(json.dumps({
            "status": "baseline_initialized",
            "file": args.baseline_file,
            "template": result
        }, indent=2))

    elif args.compare:
        if not args.new_result:
            print("Error: --new-result required for --compare", file=sys.stderr)
            sys.exit(1)
        if not Path(args.baseline_file).exists():
            print(f"Error: baseline file not found: {args.baseline_file}", file=sys.stderr)
            sys.exit(1)
        with open(args.baseline_file) as f:
            baseline = json.load(f)
        with open(args.new_result) as f:
            new_data = json.load(f)

        delta = compute_delta(
            baseline["with_skill"],
            baseline["without_skill"],
            new_data.get("with_skill", {})
        )
        # Add metadata
        delta["metadata"] = {
            "baseline_file": args.baseline_file,
            "new_result": args.new_result,
            "timestamp": "now"
        }
        print(json.dumps(delta, indent=2))

    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
