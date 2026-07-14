# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""Delta calculator for ASO / skill-opt.

Compares a new benchmark result against baseline(s), emits a JSON delta, and
optionally enforces a statistical significance gate (bootstrap or t-test).

Business rules (ASO hard gate):
- Pass Rate 提升 >= 1%
- Token 降低 >= 5%
- 或: Pass Rate 提升 >= 5% 且 Token 小幅上升
- 统计显著性: p_value < 0.05 or bootstrap CI 下限跨零
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
from pathlib import Path
from typing import Any


def _safe_mean(data: dict[str, Any]) -> float:
    return float(data.get("mean", 0.0)) if data else 0.0


def _safe_list(data: dict[str, Any], key: str) -> list[float]:
    raw = data.get(key)
    if isinstance(raw, list):
        return [float(x) for x in raw if isinstance(x, (int, float))]
    return []


def compute_delta(
    baseline_with: dict[str, Any],
    new_with: dict[str, Any],
    baseline_without: dict[str, Any],
) -> dict[str, Any]:
    """Compute performance deltas including multi-dimensional metrics."""
    # 样本量保护：如果基线总测试数 < 20，不具统计意义
    total_tests = baseline_with.get("total_tests") or baseline_without.get("total_tests")
    if total_tests is not None and total_tests < 20:
        return {
            "pass_rate_vs_without": 0.0,
            "pass_rate_vs_old": 0.0,
            "tokens_vs_old_pct": 0.0,
            "time_vs_old_pct": 0.0,
            "tool_call_rate_vs_old": 0.0,
            "latency_ms_vs_old": 0.0,
            "verdict": "neutral",
        }

    def _safe_mean(data: dict[str, Any]) -> float:
        return float(data.get("mean", 0.0)) if data else 0.0

    new_pass = _safe_mean(new_with.get("pass_rate", {}))
    old_pass = _safe_mean(baseline_with.get("pass_rate", {}))
    base_pass = _safe_mean(baseline_without.get("pass_rate", {}))

    new_tokens = _safe_mean(new_with.get("tokens", {}))
    old_tokens = _safe_mean(baseline_with.get("tokens", {}))

    new_time = _safe_mean(new_with.get("time_seconds", {}))
    old_time = _safe_mean(baseline_with.get("time_seconds", {}))

    # Multi-dimensional: tool call rate and latency median
    new_tool_rate = _safe_mean(new_with.get("tool_call_rate", {}))
    old_tool_rate = _safe_mean(baseline_with.get("tool_call_rate", {}))
    new_latency = _safe_mean(new_with.get("latency_ms", {}))
    old_latency = _safe_mean(baseline_with.get("latency_ms", {}))

    delta: dict[str, Any] = {
        "pass_rate_vs_without": new_pass - base_pass,
        "pass_rate_vs_old": new_pass - old_pass,
        "tokens_vs_old_pct": (
            ((new_tokens - old_tokens) / old_tokens) * 100 if old_tokens != 0 else 0.0
        ),
        "time_vs_old_pct": (
            ((new_time - old_time) / old_time) * 100 if old_time != 0 else 0.0
        ),
        "tool_call_rate_vs_old": new_tool_rate - old_tool_rate,
        "latency_ms_vs_old": new_latency - old_latency,
    }

    # Token 膨胀硬上限：增长 >20% 且 Pass Rate 有提升则拒绝；否则维持原有失败判定
    if delta["tokens_vs_old_pct"] > 20.0:
        if delta["pass_rate_vs_old"] > 0:
            delta["verdict"] = "rejected"
            delta["description"] = f"Token 增长超过 20% ({delta['tokens_vs_old_pct']:.1f}%)，视为敷衍回复"
        else:
            delta["verdict"] = "failed"
    else:
        if delta["pass_rate_vs_old"] > 0 or delta["tokens_vs_old_pct"] < 0:
            delta["verdict"] = "improved"
        else:
            delta["verdict"] = "neutral"

    return delta


def bootstrap_significance(
    baseline_values: list[float],
    candidate_values: list[float],
    *,
    n_samples: int = 10000,
    alpha: float = 0.05,
    seed: int = 42,
) -> dict[str, Any]:
    """Bootstrap confidence interval for the difference in means.

    Returns dict with:
      - p_value: proportion of bootstrap samples where diff <= 0
      - ci_lower / ci_upper: percentile CI
      - diff_mean: mean difference
      - significant: True iff CI excludes 0 at alpha level
    """
    if not baseline_values or not candidate_values:
        return {
            "p_value": 1.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "diff_mean": 0.0,
            "significant": False,
            "method": "bootstrap",
            "n": 0,
        }

    rng = random.Random(seed)
    baseline = list(map(float, baseline_values))
    candidate = list(map(float, candidate_values))
    diffs = []
    n = min(len(baseline), len(candidate))
    for _ in range(n_samples):
        b_sample = [rng.choice(baseline) for _ in range(n)]
        c_sample = [rng.choice(candidate) for _ in range(n)]
        diffs.append(statistics.mean(c_sample) - statistics.mean(b_sample))

    diffs.sort()
    diff_mean = statistics.mean(diffs)
    ci_lower = diffs[int(alpha / 2 * n_samples)]
    ci_upper = diffs[int((1 - alpha / 2) * n_samples)]
    p_value = sum(1 for d in diffs if d <= 0) / n_samples
    return {
        "p_value": round(p_value, 4),
        "ci_lower": round(ci_lower, 4),
        "ci_upper": round(ci_upper, 4),
        "diff_mean": round(diff_mean, 4),
        "significant": p_value < alpha and ci_lower > 0,
        "method": "bootstrap",
        "n": n_samples,
    }


def check_gate(
    delta: dict[str, Any],
    *,
    significance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check both the absolute threshold gate and optional statistical gate.

    Returns dict with fields:
      - passed: bool
      - reason: str
      - checks: list of (name, passed, detail)
    """
    checks: list[tuple[str, bool, str]] = []

    pr = delta.get("pass_rate_vs_old", 0.0)
    tk = delta.get("tokens_vs_old_pct", 0.0)

    # Threshold checks
    checks.append(("pass_rate_gain", pr >= 0.01, f"{pr:+.2%} need >= +1%"))
    checks.append(("token_savings", tk <= -5.0, f"{tk:+.2f}% need <= -5%"))
    threshold_passed = (
        pr >= 0.01 and tk <= -5.0  # strict savings
        or pr >= 0.05  # or gain big enough to tolerate token increase
    )

    # Significance check (when provided)
    sig_passed = True
    sig_detail = "no significance test applied"
    if significance is not None:
        sig_passed = bool(significance.get("significant", False))
        sig_detail = (
            f"p={significance.get('p_value')} CI=[{significance.get('ci_lower')}, "
            f"{significance.get('ci_upper')}] significant={sig_passed}"
        )
        checks.append(("statistical_significance", sig_passed, sig_detail))

    passed = bool(threshold_passed and sig_passed)
    return {
        "passed": passed,
        "reason": "approved" if passed else "rejected",
        "checks": [{"name": n, "passed": p, "detail": d} for n, p, d in checks],
    }


def init_baseline(skill_path: str, baseline_file: str) -> dict[str, Any]:
    """Create initial baseline.json template."""
    baseline = {
        "without_skill": {
            "pass_rate": {"mean": 0.0},
            "time_seconds": {"mean": 0.0},
            "tokens": {"mean": 0.0},
            "tool_call_rate": {"mean": 0.0},
            "latency_ms": {"mean": 0.0},
        },
        "with_skill": {
            "pass_rate": {"mean": 0.0},
            "time_seconds": {"mean": 0.0},
            "tokens": {"mean": 0.0},
            "tool_call_rate": {"mean": 0.0},
            "latency_ms": {"mean": 0.0},
        },
        "metadata": {
            "skill_path": skill_path,
            "created_at": "auto-init",
        },
    }
    Path(baseline_file).parent.mkdir(parents=True, exist_ok=True)
    # Atomic write via temporary file
    tmp_path = f"{baseline_file}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, baseline_file)
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
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Significance level for bootstrap test",
    )
    parser.add_argument(
        "--bootstrap-samples",
        type=int,
        default=10000,
        help="Bootstrap sample count",
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

    # Optional statistical significance on per-test pass rate
    old_list = _safe_list(baseline["with_skill"], "pass_rate")
    new_list = _safe_list(new_data.get("with_skill", {}), "pass_rate")
    sig = bootstrap_significance(old_list, new_list, alpha=args.alpha, n_samples=args.bootstrap_samples)
    gate = check_gate(delta, significance=sig)

    delta["metadata"] = {
        "baseline_file": args.baseline_file,
        "new_result": args.new_result,
        "timestamp": "now",
    }
    delta["significance"] = sig
    delta["gate"] = gate

    print(json.dumps(delta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
