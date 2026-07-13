# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Skill Evaluation Runner

Runs a skill against a set of test cases and collects metrics:
- Pass/Fail per test case
- Token consumption
- Latency
- Output logs

Usage:
  python eval_runner.py --skill-path ./my-skill --evals evals.json --output results/
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

def run_single_test(prompt: str, files: List[str] = None, skill_name: str = None) -> Dict[str, Any]:
    """
    Run a single test case via openclaw agent.
    
    Note: In OpenClaw 2026.6.11, file attachments are not passed via CLI.
    Instead, the prompt should contain instructions for the agent to use
    the `read` tool to access files. This function simply sends the prompt.
    """
    start_time = time.time()

    # Build openclaw agent command
    cmd = ["openclaw", "agent", "--message", prompt]

    # TODO: add skill selection if needed
    # if skill_name:
    #   cmd.extend(["--skill", skill_name])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
        success = result.returncode == 0 and "error" not in output.lower()[:100]
    except subprocess.TimeoutExpired:
        output = "TIMEOUT"
        success = False
    except Exception as e:
        output = str(e)
        success = False

    end_time = time.time()

    # Placeholder token count - would need OpenClaw JSON output with usage
    tokens = 0

    return {
        "output": output,
        "success": success,
        "latency_seconds": end_time - start_time,
        "tokens": tokens
    }

def load_evals(evals_file: str) -> List[Dict[str, Any]]:
    with open(evals_file) as f:
        return json.load(f)

def evaluate_skill(skill_path: str, evals: List[Dict], output_dir: str) -> Dict[str, Any]:
    """
    Run all test cases and aggregate results.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    results = []
    passed = 0
    total_tokens = 0
    total_latency = 0

    for test in evals:
        test_id = test["id"]
        print(f"Running test {test_id}...", file=sys.stderr)

        test_result = run_single_test(
            prompt=test["prompt"],
            skill_name=Path(skill_path).name
        )

        # Save per-test output
        test_dir = Path(output_dir) / test_id
        test_dir.mkdir(exist_ok=True)
        (test_dir / "output.txt").write_text(test_result["output"])

        # Simple pass/fail based on success flag (should be enhanced with assertions)
        test_result["test_id"] = test_id
        test_result["passed"] = test_result["success"]  # placeholder, should use assertions
        results.append(test_result)

        if test_result["passed"]:
            passed += 1
        total_tokens += test_result["tokens"]
        total_latency += test_result["latency_seconds"]

    count = len(results)
    benchmark = {
        "skill_path": skill_path,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_tests": count,
        "passed": passed,
        "pass_rate": {"mean": passed / count if count else 0},
        "tokens": {"mean": total_tokens / count if count else 0, "total": total_tokens},
        "time_seconds": {"mean": total_latency / count if count else 0, "total": total_latency},
        "test_results": results
    }

    # Write aggregate
    with open(Path(output_dir) / "benchmark.json", "w") as f:
        json.dump(benchmark, f, indent=2)

    return benchmark

def main():
    parser = argparse.ArgumentParser(description="Skill Evaluation Runner")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument("--evals", required=True, help="Path to evals.json")
    parser.add_argument("--output", required=True, help="Output directory for results")
    parser.add_argument("--skill-name", help="Skill name (optional)")

    args = parser.parse_args()

    evals = load_evals(args.evals)
    print(f"Loaded {len(evals)} test cases", file=sys.stderr)

    results = evaluate_skill(args.skill_path, evals, args.output)

    print(json.dumps(results, indent=2))
    print(f"Pass rate: {results['pass_rate']['mean']:.2%}", file=sys.stderr)

if __name__ == "__main__":
    main()
