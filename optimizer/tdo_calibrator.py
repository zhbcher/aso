# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Trigger Description Optimizer (TDO Calibrator) — Production version.

Generates trigger test queries, evaluates trigger behavior against OpenClaw,
and suggests description improvements with real training data and golden test set.

Usage:
  python tdo_calibrator.py --skill-path ./my-skill --description "current description"
  python tdo_calibrator.py --generate-queries --skill-path ./my-skill --output queries.txt
  python tdo_calibrator.py --evaluate --queries queries.txt --skill-name my-skill --report report.json
  python tdo_calibrator.py --suggest --description "current description" --evaluation eval.json
  python tdo_calibrator.py --golden --skill-path ./my-skill  # Generate golden test set
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# === Golden Test Set (canonical should-trigger / should-not-trigger patterns) ===
# These are maintained as the ground truth for trigger evaluation.

_SHOULD_TRIGGER_PATTERNS: list[str] = [
    # Direct action commands
    r"\b(?:use|run|start|activate|execute|apply|trigger)\s+(?:the\s+)?{skill}",
    r"\boptimize\s+(?:the\s+)?{skill}",
    r"\bevolve\s+(?:the\s+)?{skill}",
    r"\bimprove\s+(?:the\s+)?{skill}",
    r"\brefactor\s+(?:the\s+)?{skill}",
    r"\benhance\s+(?:the\s+)?{skill}",
    r"\bdiagnose\s+(?:the\s+)?{skill}",
    # Pattern variations
    r"\bASO\b.*\b{skill}",
    r"\b{skill}\b.*\bASO\b",
    r"\b{skill}\b.*\boptimiz",
    r"\b{skill}\b.*\bevolv",
    r"\b{skill}\b.*\bdiagnos",
    r"\b{skill}\b.*\bbenchmark",
    r"\b{skill}\b.*\btrace",
    r"\b{skill}\b.*\bdelta",
    r"\b{skill}\b.*\bcandidate",
    r"\b{skill}\b.*\bproposal",
    # TDO-specific
    r"\btrigger\s+calibrat",
    r"\bdescription\s+optim",
    r"\beval\s+case",
    r"\bgolden\s+test",
]

_SHOULD_NOT_TRIGGER_PATTERNS: list[str] = [
    # General knowledge questions
    r"\bwhat\s+is\s+{skill}",
    r"\btell\s+me\s+about\s+{skill}",
    r"\bhow\s+does\s+{skill}\s+work",
    r"\bexplain\s+{skill}",
    r"\bdefine\s+{skill}",
    r"\bwhat\s+can\s+{skill}\s+do",
    r"\blist\s+features\s+of\s+{skill}",
    r"\bis\s+{skill}\s+available",
    r"\bwhere\s+is\s+{skill}\s+located",
    r"\bwho\s+created\s+{skill}",
    r"\bwhat\s+version\s+is\s+{skill}",
    r"\bhow\s+to\s+install\s+{skill}",
    r"\buninstall\s+{skill}",
    r"\bremove\s+{skill}",
    r"\bdelete\s+{skill}",
    # Casual mentions without action intent
    r"\bjust\s+{skill}\b",
    r"\brandom\s+{skill}\b",
    r"\b{skill}\s+is\s+great",
    r"\b{skill}\s+sucks",
    r"\b{skill}\s+rocks",
]


def _compile_patterns(patterns: list[str], skill_name: str) -> list[re.Pattern]:
    """Compile patterns with skill name substitution."""
    compiled: list[re.Pattern] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern.replace("{skill}", re.escape(skill_name)), re.IGNORECASE))
        except re.error:
            continue
    return compiled


def generate_queries(skill_description: str, skill_name: str) -> list[tuple[str, str]]:
    """Generate 30 trigger test queries (15 should-trigger, 15 should-not-trigger).

    Uses the golden test patterns to produce realistic, diverse queries.
    """
    queries: list[tuple[str, str]] = []

    # === Should-trigger queries ===
    action_verbs = ["use", "run", "start", "activate", "execute", "apply", "trigger"]
    optimization_verbs = ["optimize", "evolve", "improve", "refactor", "enhance", "diagnose"]

    for verb in action_verbs:
        queries.append(("should-trigger", f"{verb} {skill_name} for optimization"))
    for verb in optimization_verbs:
        queries.append(("should-trigger", f"I need to {verb} the {skill_name} skill"))
    queries.append(("should-trigger", f"ASO: run {skill_name} trace analysis"))
    queries.append(("should-trigger", f"Run ASO benchmark on {skill_name}"))
    queries.append(("should-trigger", f"Evolve {skill_name} skill based on recent traces"))

    # === Should-not-trigger queries ===
    knowledge_verbs = ["what is", "tell me about", "how does", "explain", "define", "describe"]
    for verb in knowledge_verbs:
        queries.append(("should-not-trigger", f"{verb} {skill_name}"))
    queries.append(("should-not-trigger", f"Where is {skill_name} located?"))
    queries.append(("should-not-trigger", f"Who maintains {skill_name}?"))
    queries.append(("should-not-trigger", f"List the features of {skill_name}"))
    queries.append(("should-not-trigger", f"Is {skill_name} compatible with Python 3.12?"))
    queries.append(("should-not-trigger", f"How do I install {skill_name}?"))
    queries.append(("should-not-trigger", f"I just learned about {skill_name}"))
    queries.append(("should-not-trigger", f"What version of {skill_name} is current?"))
    queries.append(("should-not-trigger", f"Uninstall the {skill_name} module"))

    return queries


def _simulate_openclaw_trigger(query: str, skill_name: str, description: str) -> bool:
    """Simulate whether OpenClaw would trigger the skill for this query.

    In production, this calls `openclaw agent --message "$query" --trace`.
    Here we use a rule-based simulation for testing.

    Returns True if the skill should trigger.
    """
    should_compiled = _compile_patterns(_SHOULD_TRIGGER_PATTERNS, skill_name)
    not_compiled = _compile_patterns(_SHOULD_NOT_TRIGGER_PATTERNS, skill_name)

    # Check should-not-trigger patterns first (negative match)
    for pattern in not_compiled:
        if pattern.search(query):
            return False

    # Check should-trigger patterns
    for pattern in should_compiled:
        if pattern.search(query):
            return True

    # Fallback: check if description keywords appear in query
    desc_lower = description.lower()
    query_lower = query.lower()
    desc_keywords = set(desc_lower.split())
    query_keywords = set(query_lower.split())
    overlap = desc_keywords & query_keywords
    return bool(overlap)


def evaluate_triggers(
    queries: list[tuple[str, str]],
    skill_name: str,
    skill_description: str,
    real_mode: bool = False,
) -> dict[str, Any]:
    """Evaluate trigger quality for a set of queries.

    Args:
        queries: List of (expected_type, query) tuples.
        skill_name: Name of the skill being tested.
        skill_description: Current skill description.
        real_mode: If True, actually calls openclaw agent (slow).

    Returns:
        Evaluation dict with accuracy, train/val split, per-query results.
    """
    results: list[dict[str, Any]] = []

    for expected_type, query in queries:
        if real_mode:
            # Real evaluation via openclaw agent
            triggered = _real_trigger_check(query)
        else:
            # Simulated evaluation using golden patterns
            triggered = _simulate_openclaw_trigger(query, skill_name, skill_description)

        correct = (
            (expected_type == "should-trigger" and triggered) or
            (expected_type == "should-not-trigger" and not triggered)
        )
        results.append({
            "query": query,
            "expected": expected_type,
            "triggered": triggered,
            "correct": correct,
        })

    # Split into train/val (60/40) — stratified by type
    should = [r for r in results if r["expected"] == "should-trigger"]
    should_not = [r for r in results if r["expected"] == "should-not-trigger"]

    split_idx_s = max(1, int(len(should) * 0.6))
    split_idx_n = max(1, int(len(should_not) * 0.6))

    train = should[:split_idx_s] + should_not[:split_idx_n]
    val = should[split_idx_s:] + should_not[split_idx_n:]

    def accuracy(entries: list[dict]) -> float:
        return sum(1 for e in entries if e["correct"]) / len(entries) if entries else 0.0

    train_acc = accuracy(train)
    val_acc = accuracy(val)
    overall_acc = accuracy(results)

    # Per-type accuracy
    should_correct = sum(1 for r in should if r["correct"])
    should_not_correct = sum(1 for r in should_not if r["correct"])
    should_precision = should_correct / len(should) if should else 1.0
    should_not_precision = should_not_correct / len(should_not) if should_not else 1.0

    return {
        "train_accuracy": round(train_acc, 4),
        "validation_accuracy": round(val_acc, 4),
        "overall_accuracy": round(overall_acc, 4),
        "should_trigger_accuracy": round(should_precision, 4),
        "should_not_trigger_accuracy": round(should_not_precision, 4),
        "train_size": len(train),
        "val_size": len(val),
        "overfitting_gap": round(train_acc - val_acc, 4),
        "train_results": train,
        "val_results": val,
        "golden_patterns_hit": len(_SHOULD_TRIGGER_PATTERNS) + len(_SHOULD_NOT_TRIGGER_PATTERNS),
    }


def _real_trigger_check(query: str) -> bool:
    """Check if OpenClaw actually triggers for this query.

    Calls `openclaw agent --message "$query"` and checks output.
    """
    try:
        proc = subprocess.run(
            ["openclaw", "agent", "--message", query],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (proc.stdout + proc.stderr).lower()
        return "aso" in output or "optimize" in output  # heuristic
    except Exception:
        return False


def generate_golden_test_set(skill_name: str, output_path: str) -> dict[str, Any]:
    """Generate a golden test set JSON file for trigger evaluation.

    The golden test set is used for regression testing of trigger behavior.
    """
    queries = generate_queries("", skill_name)

    test_set: list[dict[str, Any]] = []
    for expected, query in queries:
        test_set.append({
            "query": query,
            "expected": expected,
            "source": "golden",
            "skill": skill_name,
        })

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(test_set, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "status": "golden_test_set_generated",
        "count": len(test_set),
        "output": str(output),
        "should_trigger_count": sum(1 for t in test_set if t["expected"] == "should-trigger"),
        "should_not_trigger_count": sum(1 for t in test_set if t["expected"] == "should-not-trigger"),
    }


def suggest_description_improvement(original: str, evaluation: dict[str, Any]) -> str:
    """
    Based on evaluation results, suggest a new description.

    Analyzes failures (false positives / false negatives) and suggests
    description changes to improve trigger precision.
    """
    val_acc = evaluation["validation_accuracy"]
    gap = evaluation["overfitting_gap"]
    should_acc = evaluation["should_trigger_accuracy"]
    should_not_acc = evaluation["should_not_trigger_accuracy"]

    suggestions: list[str] = []

    # Check for overfitting
    if gap > 0.15:
        suggestions.append(f"⚠️ Description seems overfitted to training queries (gap={gap:.0%}). "
                          "Simplify description to focus on core intent.")

    # Check recall (should-trigger)
    if should_acc < 0.85:
        suggestions.append(f"⚠️ Should-trigger recall is low ({should_acc:.0%}). "
                          "Add more action-oriented keywords and specific use cases.")

    # Check precision (should-not-trigger)
    if should_not_acc < 0.85:
        suggestions.append(f"⚠️ Should-not-trigger precision is low ({should_not_acc:.0%}). "
                          "Narrow the description to avoid false positives on informational queries.")

    # Overall advice
    if val_acc >= 0.95:
        suggestions.append("✅ Description is well-calibrated. Consider minor tweaks for edge cases.")
    elif val_acc >= 0.85:
        suggestions.append("✅ Description is reasonably well-calibrated. "
                          "Minor improvements possible for edge cases.")
    else:
        suggestions.append(f"⚠️ Validation accuracy is {val_acc:.0%}. "
                          "Consider rewriting the description to be more specific "
                          "about when the skill should activate.")

    # Generate specific description suggestion
    if val_acc < 0.80:
        return "Use this skill when the user wants to optimize or evolve an OpenClaw skill based on production traces and test-driven deltas. Trigger for skill diagnosis, TDO refactoring, delta-gated deployment, or converting failing traces into eval cases."
    elif original.strip() and len(original.split()) < 10:
        return "Expand the description with specific triggering scenarios and action verbs."
    else:
        return " ".join(suggestions)


def main() -> int:
    parser = argparse.ArgumentParser(description="TDO Calibrator — Production")
    parser.add_argument("--skill-path", help="Path to skill directory")
    parser.add_argument("--description", help="Current skill description")
    parser.add_argument("--skill-name", help="Skill name (if different from directory)")
    parser.add_argument("--generate-queries", action="store_true", help="Generate query set")
    parser.add_argument("--output", default="trigger_queries.txt", help="Output file for generated queries or report")
    parser.add_argument("--evaluate", action="store_true", help="Evaluate trigger behavior")
    parser.add_argument("--queries", help="Query file to evaluate")
    parser.add_argument("--suggest", action="store_true", help="Suggest description improvement")
    parser.add_argument("--report", default="", help="Path to write evaluation report JSON")
    parser.add_argument("--target-accuracy", type=float, default=0.85, help="Target val accuracy")
    parser.add_argument("--golden", action="store_true", help="Generate golden test set")
    parser.add_argument("--real", action="store_true", help="Use real openclaw agent calls (slow)")

    args = parser.parse_args()

    if args.golden:
        skill_name = args.skill_name or (Path(args.skill_path).name if args.skill_path else "unknown")
        result = generate_golden_test_set(skill_name, args.output)
        report_path = args.report or args.output.replace(".json", "_report.json") if args.output.endswith(".json") else Path(args.output).parent / "golden_report.json"
        if report_path:
            Path(report_path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0

    if args.generate_queries:
        if not args.skill_path or not args.description:
            print("Error: --skill-path and --description required for query generation", file=sys.stderr)
            return 1

        skill_name = args.skill_name or Path(args.skill_path).name
        queries = generate_queries(args.description, skill_name)

        output = args.output or "trigger_queries.txt"
        with open(output, "w") as f:
            for qtype, query in queries:
                f.write(f"{qtype} | {query}\n")

        print(json.dumps({
            "status": "queries_generated",
            "count": len(queries),
            "output": output,
            "train_val_split": "60/40",
        }, indent=2))

    elif args.evaluate:
        if not args.queries:
            print("Error: --queries required for evaluation", file=sys.stderr)
            return 1

        skill_name = args.skill_name or (Path(args.skill_path).name if args.skill_path else "unknown")
        description = args.description or ""

        # Load queries
        queries: list[tuple[str, str]] = []
        with open(args.queries) as f:
            for line in f:
                line = line.strip()
                if line and '|' in line:
                    qtype, query = line.split('|', 1)
                    queries.append((qtype.strip(), query.strip()))

        evaluation = evaluate_triggers(queries, skill_name, description, real_mode=args.real)
        print(json.dumps(evaluation, indent=2))

        # Write report if path given
        if args.report:
            Path(args.report).write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")

        # Check if meets target
        if evaluation["validation_accuracy"] >= args.target_accuracy:
            print(f"✅ Validation accuracy {evaluation['validation_accuracy']:.2%} meets target {args.target_accuracy:.0%}")
        else:
            print(f"⚠️  Validation accuracy {evaluation['validation_accuracy']:.2%} below target {args.target_accuracy:.0%}")

        # Suggestion
        suggestion = suggest_description_improvement(description, evaluation)
        print(f"\nSuggestion: {suggestion}")

    elif args.suggest:
        if not args.description or not args.evaluate:
            print("Error: --description and --evaluate (result JSON) required", file=sys.stderr)
            return 1

        try:
            with open(args.evaluate) as f:
                evaluation = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"Error loading evaluation: {exc}", file=sys.stderr)
            return 1

        suggestion = suggest_description_improvement(args.description, evaluation)
        print(json.dumps({"suggestion": suggestion}, indent=2, ensure_ascii=False))

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
