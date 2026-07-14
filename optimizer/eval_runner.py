# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""eval_runner.py — Run a skill against eval cases and emit benchmark metrics.

Enhanced with ThreadPoolExecutor for parallel test execution.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Default parallelism: use all available CPUs
_DEFAULT_WORKERS: int = 4
# Minimum parallelism for small test sets
_MIN_WORKERS: int = 2
# Sequential fallback threshold — parallel overhead isn't worth it below this
_SEQUENTIAL_THRESHOLD: int = 3


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_single_test_worker(args: tuple) -> dict[str, Any]:
    """Worker function for ThreadPoolExecutor.

    Args:
        args: Tuple of (prompt, test_id, timeout_seconds).

    Returns:
        Test result dict.
    """
    prompt, test_id, timeout = args
    start = time.perf_counter()
    try:
        result = subprocess.run(
            ["openclaw", "agent", "--message", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
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
        "test_id": test_id,
    }


def run_single_test(prompt: str, timeout: int = 60) -> dict[str, Any]:
    """Run a single prompt via the OpenClaw agent (sequential helper)."""
    return _run_single_test_worker((prompt, "unknown", timeout))


def load_evals(path: str | Path) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_skill(
    skill_path: str,
    evals: list[dict[str, Any]],
    output_dir: str,
    parallel: bool = True,
    max_workers: int = _DEFAULT_WORKERS,
    test_timeout: int = 60,
) -> dict[str, Any]:
    """Run all eval cases and aggregate benchmark metrics.

    Uses ThreadPoolExecutor for parallel execution when beneficial.

    Args:
        skill_path: Path to the skill directory.
        evals: List of eval case dicts with "id" and "prompt" fields.
        output_dir: Directory for test outputs and benchmark.json.
        parallel: If True, use ThreadPoolExecutor (default: True).
        max_workers: Maximum number of parallel workers.
        test_timeout: Timeout per test in seconds.

    Returns:
        Benchmark dict with summary metrics.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Decide on parallelism
    use_parallel = parallel and len(evals) >= _SEQUENTIAL_THRESHOLD
    num_workers = min(max_workers, len(evals)) if use_parallel else 1

    results: list[dict[str, Any]] = []

    if use_parallel:
        # Parallel execution via ThreadPoolExecutor
        worker_args = [
            (test.get("prompt", ""), test.get("id", "unknown"), test_timeout)
            for test in evals
        ]
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_map = {
                executor.submit(_run_single_test_worker, args): args[1]
                for args in worker_args
            }
            for future in as_completed(future_map):
                try:
                    result = future.result()
                    results.append(result)
                    # Save output
                    out_dir = Path(output_dir) / result.get("test_id", "unknown")
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir / "output.txt").write_text(result["output"], encoding="utf-8")
                except Exception as exc:
                    tid = future_map.get(future, "unknown")
                    results.append({
                        "test_id": tid,
                        "output": str(exc),
                        "passed": False,
                        "latency_seconds": 0.0,
                        "tokens": 0,
                    })
    else:
        # Sequential execution (small test sets or parallel disabled)
        for test in evals:
            out_dir = Path(output_dir) / test.get("id", "unknown")
            out_dir.mkdir(exist_ok=True)

            result = run_single_test(prompt=test.get("prompt", ""), timeout=test_timeout)
            (out_dir / "output.txt").write_text(result["output"], encoding="utf-8")

            result["test_id"] = test.get("id")
            results.append(result)

    count = len(results)
    passed = sum(1 for r in results if r["passed"])
    total_latency = sum(r["latency_seconds"] for r in results)
    total_tokens = sum(r.get("tokens", 0) for r in results)

    benchmark: dict[str, Any] = {
        "skill_path": skill_path,
        "timestamp": _utc_iso(),
        "total_tests": count,
        "passed": passed,
        "pass_rate": {
            "mean": passed / count if count else 0.0,
        },
        "tokens": {
            "mean": total_tokens / count if count else 0.0,
            "total": total_tokens,
        },
        "time_seconds": {
            "mean": round(total_latency / count, 4) if count else 0.0,
            "total": round(total_latency, 4),
        },
        "parallel": use_parallel,
        "workers": num_workers,
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
    parser.add_argument("--no-parallel", action="store_true", help="Disable parallel execution")
    parser.add_argument("--workers", type=int, default=_DEFAULT_WORKERS, help="Max parallel workers")
    parser.add_argument("--timeout", type=int, default=60, help="Per-test timeout in seconds")
    parser.add_argument("--help", action="help", help="Show this help message")

    args = parser.parse_args(argv)

    evals = load_evals(args.evals)
    results = evaluate_skill(
        args.skill_path,
        evals,
        args.output,
        parallel=not args.no_parallel,
        max_workers=args.workers,
        test_timeout=args.timeout,
    )

    # Human-readable summary to stderr
    print(
        f"Pass rate: {results['pass_rate']['mean']:.2%} ({results['passed']}/{results['total_tests']})",
        file=sys.stderr,
    )
    print(f"Wrote benchmark to: {Path(args.output) / 'benchmark.json'}", file=sys.stderr)
    if results.get("parallel"):
        print(f"Parallel execution: {results['workers']} workers", file=sys.stderr)

    # Machine-readable output to stdout
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
