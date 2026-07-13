# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Trigger Description Optimizer (TDO Calibrator)

This script helps calibrate a skill's description for optimal trigger precision.
It generates train/validation query sets, tests trigger behavior, and suggests
description improvements.

Usage:
  python tdo_calibrator.py --skill-path ./my-skill --description "current description"
  python tdo_calibrator.py --generate-queries --skill-path ./my-skill --output queries.txt
  python tdo_calibrator.py --evaluate --queries queries.txt --skill-name my-skill
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple

def generate_queries(skill_description: str, skill_name: str) -> List[Tuple[str, str]]:
    """
    Generate 20 trigger test queries (10 should-trigger, 10 should-not-trigger).
    In production, this would call an LLM. Here we provide rule-based templates.
    """
    queries = []

    # Should-trigger: variations around the skill's purpose
    should_templates = [
        "Use {skill} to {action}",
        "I need to {action} using {skill}",
        "Can you {action} with {skill}?",
        "Help me {action} using {skill}",
        "Run {skill} for {action}",
        "Activate {skill} to {action}",
        "I want to {action}, use {skill}",
        "Please {action} via {skill}",
        "Execute {skill} for {action}",
        "Start {skill} to {action}"
    ]

    # Infer action from description (simplified)
    action = "perform the task"  # In production, extract from description via LLM

    for i in range(10):
        template = should_templates[i % len(should_templates)]
        query = template.replace("{skill}", skill_name).replace("{action}", action)
        queries.append(("should-trigger", query))

    # Should-not-trigger: near-miss scenarios
    not_templates = [
        "What is {skill}?",
        "Tell me about {skill}",
        "How does {skill} work?",
        "Explain {skill}",
        "Define {skill}",
        "What can {skill} do?",
        "List features of {skill}",
        "Is {skill} available?",
        "Where is {skill} located?",
        "Who created {skill}?"
    ]

    for i in range(10):
        template = not_templates[i % len(not_templates)]
        query = template.replace("{skill}", skill_name)
        queries.append(("should-not-trigger", query))

    return queries

def evaluate_triggers(queries: List[Tuple[str, str]], skill_name: str) -> dict:
    """
    Test each query against OpenClaw to see if the skill triggers.
    Returns metrics: accuracy, precision, recall, per-query results.
    """
    results = []
    # In production, this would call openclaw agent and check traces
    # Here we simulate based on simple pattern matching (placeholder)
    for expected_type, query in queries:
        # Simulated check: if query contains action words, consider it triggered
        # REAL IMPLEMENTATION: run `openclaw agent --message "$query" --trace` and parse output
        triggered = "perform" in query.lower()  # placeholder logic
        results.append({
            "query": query,
            "expected": expected_type,
            "triggered": triggered,
            "correct": (expected_type == "should-trigger" and triggered) or
                      (expected_type == "should-not-trigger" and not triggered)
        })

    # Split into train/val (60/40)
    split_idx = int(len(results) * 0.6)
    train = results[:split_idx]
    val = results[split_idx:]

    train_acc = sum(r["correct"] for r in train) / len(train) if train else 0
    val_acc = sum(r["correct"] for r in val) / len(val) if val else 0

    return {
        "train_accuracy": train_acc,
        "validation_accuracy": val_acc,
        "train_results": train,
        "val_results": val,
        "overall_accuracy": sum(r["correct"] for r in results) / len(results) if results else 0
    }

def suggest_description_improvement(original: str, evaluation: dict) -> str:
    """
    Based on evaluation results, suggest a new description.
    """
    val_acc = evaluation["validation_accuracy"]
    gap = evaluation["train_accuracy"] - evaluation["validation_accuracy"]

    # Heuristic suggestions (in production, use LLM)
    if val_acc < 0.85:
        if gap > 0.15:
            return "Simplify description to avoid overfitting to training queries. Focus on core intent."
        else:
            return "Add more specific keywords and use cases to improve precision."
    else:
        return "Description is well-calibrated. Consider minor tweaks for edge cases."

def main():
    parser = argparse.ArgumentParser(description="TDO Calibrator")
    parser.add_argument("--skill-path", help="Path to skill directory")
    parser.add_argument("--description", help="Current skill description")
    parser.add_argument("--skill-name", help="Skill name (if different from directory)")
    parser.add_argument("--generate-queries", action="store_true", help="Generate query set")
    parser.add_argument("--output", help="Output file for generated queries")
    parser.add_argument("--evaluate", action="store_true", help="Evaluate trigger behavior")
    parser.add_argument("--queries", help="Query file to evaluate")
    parser.add_argument("--suggest", action="store_true", help="Suggest description improvement")
    parser.add_argument("--target-accuracy", type=float, default=0.85, help="Target val accuracy")

    args = parser.parse_args()

    if args.generate_queries:
        if not args.skill_path or not args.description:
            print("Error: --skill-path and --description required for query generation", file=sys.stderr)
            sys.exit(1)

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
            "train_val_split": "60/40"
        }, indent=2))

    elif args.evaluate:
        if not args.queries:
            print("Error: --queries required for evaluation", file=sys.stderr)
            sys.exit(1)

        # Load queries
        queries = []
        with open(args.queries) as f:
            for line in f:
                line = line.strip()
                if line and '|' in line:
                    qtype, query = line.split('|', 1)
                    queries.append((qtype.strip(), query.strip()))

        evaluation = evaluate_triggers(queries, args.skill_name or "unknown")
        print(json.dumps(evaluation, indent=2))

        # Check if meets target
        if evaluation["validation_accuracy"] >= args.target_accuracy:
            print(f"✅ Validation accuracy {evaluation['validation_accuracy']:.2f} meets target {args.target_accuracy}")
        else:
            print(f"⚠️  Validation accuracy {evaluation['validation_accuracy']:.2f} below target {args.target_accuracy}")

    elif args.suggest:
        if not args.description:
            print("Error: --description required for suggestion", file=sys.stderr)
            sys.exit(1)
        # In full implementation, this would use evaluation results
        print("Suggested improvement: Use 'Use this skill when...' pattern and include specific scenarios.")

    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
