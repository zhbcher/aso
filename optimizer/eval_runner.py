# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""eval_runner.py — Run a skill against eval cases and emit benchmark metrics."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_single_test(prompt: str) -> dict[str, Any]:
    """Run a single prompt via the OpenClaw agent."""
    start = time.perf_counter()
    try:
        result = subprocess.run(
            ["openclaw", "agent", "--message", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout + result.stderr
        passed = result.returncode == 0 and "error" not in output[:100].lower()
    except subprocess.TimeoutExpired:
        output = "TIMEOUT"
        passed = False
    except Exception as exc:
        output = str(exc)
        passed = False

    return {
        "output": output,
        "passed": passed,
        "latency_seconds": round(time.perf_counter() - start, 4),
        "tokens": 0,
    }


def load_evals(path: str | Path) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_skill(skill_path: str, evals: list[dict[str, Any]], output_dir: str) -> dict[str, Any]:
    """Run all eval cases and aggregate benchmark metrics."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    passed = 0
    total_latency = 0.0

    for test in evals:
        out_dir = Path(output_dir) / test.get("id", "unknown")
        out_dir.mkdir(exist_ok=True)

        result = run_single_test(prompt=test.get("prompt", ""))
        (out_dir / "output.txt").write_text(result["output"], encoding="utf-8")

        result["test_id"] = test.get("id")
        results.append(result)
        if result["passed"]:
            passed += 1
        total_latency += result["latency_seconds"]

    count = len(results)
    benchmark = {
        "skill_path": skill_path,
        "timestamp": _utc_iso(),
        "total_tests": count,
        "passed": passed,
        "pass_rate": {
            "mean": passed / count if count else 0.0,
        },
        "tokens": {
            "mean": 0.0,
            "total": 0,
        },
        "time_seconds": {
            "mean": round(total_latency / count, 4) if count else 0.0,
            "total": round(total_latency, 4),
        },
        "test_results": results,
    }

    benchmark_path = Path(output_dir) / "benchmark.json"
    benchmark_path.write_text(json.dumps(benchmark, indent=2) + "\n", encoding="utf-8")
    return benchmark


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eval_runner",
        description="Run a skill against eval cases and output benchmark metrics.",
    )
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument("--evals", required=True, help="Path to evals JSON")
    parser.add_argument("--output", required=True, help="Directory for test outputs and benchmark.json")
    parser.add_argument("--skill-name", help="Optional skill name for metadata")
    parser.add_argument("--help", action="help", help="Show this help message")

    args = parser.parse_args(argv)

    evals = load_evals(args.evals)
    results = evaluate_skill(args.skill_path, evals, args.output)

    # Human-readable summary to stderr
    print(
        f"Pass rate: {results['pass_rate']['mean']:.2%} ({results['passed']}/{results['total_tests']})",
        file=sys.stderr,
    )
    print(f"Wrote benchmark to: {Path(args.output) / 'benchmark.json'}", file=sys.stderr)

    # Machine-readable output to stdout
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
