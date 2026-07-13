# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""Delta calculator for ASO / skill-opt.

Compares a new benchmark result against baseline(s) and emits a JSON delta
with pass-rate, token, and time changes plus an overall verdict.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _safe_mean(data: dict[str, Any]) -> float:
    """Extract mean value from benchmark data structure."""
    return float(data.get("mean", 0.0)) if data else 0.0


def compute_delta(
    baseline_with: dict[str, Any],
    new_with: dict[str, Any],
    baseline_without: dict[str, Any],
) -> dict[str, Any]:
    """Compute performance deltas.

    Returns a dict with pass-rate, token, and time deltas, plus a verdict.
    """
    new_pass = _safe_mean(new_with.get("pass_rate", {}))
    old_pass = _safe_mean(baseline_with.get("pass_rate", {}))
    base_pass = _safe_mean(baseline_without.get("pass_rate", {}))

    new_tokens = _safe_mean(new_with.get("tokens", {}))
    old_tokens = _safe_mean(baseline_with.get("tokens", {}))

    new_time = _safe_mean(new_with.get("time_seconds", {}))
    old_time = _safe_mean(baseline_with.get("time_seconds", {}))

    delta: dict[str, Any] = {
        "pass_rate_vs_without": new_pass - base_pass,
        "pass_rate_vs_old": new_pass - old_pass,
        "tokens_vs_old_pct": (
            ((new_tokens - old_tokens) / old_tokens) * 100 if old_tokens != 0 else 0.0
        ),
        "time_vs_old_pct": (
            ((new_time - old_time) / old_time) * 100 if old_time != 0 else 0.0
        ),
    }

    if delta["pass_rate_vs_old"] <= 0 and delta["tokens_vs_old_pct"] > 20:
        delta["verdict"] = "failed"
    elif delta["pass_rate_vs_old"] > 0 or delta["tokens_vs_old_pct"] < 0:
        delta["verdict"] = "improved"
    else:
        delta["verdict"] = "neutral"

    return delta


def init_baseline(skill_path: str, baseline_file: str) -> dict[str, Any]:
    """Create initial baseline.json template."""
    baseline = {
        "without_skill": {
            "pass_rate": {"mean": 0.0},
            "time_seconds": {"mean": 0.0},
            "tokens": {"mean": 0.0},
        },
        "with_skill": {
            "pass_rate": {"mean": 0.0},
            "time_seconds": {"mean": 0.0},
            "tokens": {"mean": 0.0},
        },
        "metadata": {
            "skill_path": skill_path,
            "created_at": "auto-init",
        },
    }
    Path(baseline_file).parent.mkdir(parents=True, exist_ok=True)
    Path(baseline_file).write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    return baseline


def main() -> int:
    parser = argparse.ArgumentParser(description="Skill Delta Calculator")
    parser.add_argument("--init", action="store_true", help="Initialize baseline template")
    parser.add_argument("--skill-path", help="Path to skill directory (required for --init)")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare new benchmark against baseline",
    )
    parser.add_argument(
        "--new-result",
        help="Path to new benchmark.json (required for --compare)",
    )
    parser.add_argument(
        "--baseline-file",
        default="baseline.json",
        help="Baseline file path",
    )
    args = parser.parse_args()

    if args.init:
        if not args.skill_path:
            print("--skill-path required for --init", file=sys.stderr)
            return 1
        result = init_baseline(args.skill_path, args.baseline_file)
        print(json.dumps({"status": "baseline_initialized", "file": args.baseline_file, "template": result}, indent=2))
        return 0

    if not args.compare:
        parser.print_help(sys.stderr)
        return 1

    if not args.new_result:
        print("--new-result required for --compare", file=sys.stderr)
        return 1

    baseline_path = Path(args.baseline_file)
    if not baseline_path.exists():
        print(f"baseline file not found: {args.baseline_file}", file=sys.stderr)
        return 1

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    new_data = json.loads(Path(args.new_result).read_text(encoding="utf-8"))

    delta = compute_delta(
        baseline_with=baseline["with_skill"],
        new_with=new_data.get("with_skill", {}),
        baseline_without=baseline["without_skill"],
    )

    delta["metadata"] = {
        "baseline_file": args.baseline_file,
        "new_result": args.new_result,
        "timestamp": "now",
    }

    print(json.dumps(delta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
