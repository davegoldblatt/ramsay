"""
CLI entry point for Ramsay.

Usage:
    ramsay generate --task "Write about X" --sources file.txt --rubric essay
    ramsay evaluate --text "Your text here" --rubric email
    ramsay evaluate --file draft.txt --rubric email --source notes.txt
    ramsay rubrics
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ramsay",
        description="Quality-controlled text generation. Define a rubric, provide sources, get text that passes your quality bar.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- generate (primary command) ---
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate text with quality control. The main command.",
    )
    gen_task_group = gen_parser.add_mutually_exclusive_group(required=True)
    gen_task_group.add_argument("--task", type=str, help="Task description (inline)")
    gen_task_group.add_argument("--task-file", type=str, help="Path to file containing task description")
    gen_parser.add_argument(
        "--sources", type=str, required=True,
        help="Path to source material file",
    )
    gen_parser.add_argument(
        "--rubric", type=str, default="essay",
        help="Rubric name or path to YAML file (default: essay)",
    )
    gen_parser.add_argument(
        "--voice", type=str, default=None,
        help="Voice/style description (e.g., 'Direct, conversational, no hedging.')",
    )
    gen_parser.add_argument(
        "--subject", type=str, default=None,
        help="Subject/title line to evaluate separately",
    )
    gen_parser.add_argument(
        "--context", type=str, default="",
        help="Additional context for evaluation",
    )
    gen_parser.add_argument(
        "--max-rewrites", type=int, default=3,
        help="Maximum rewrite attempts (default: 3)",
    )
    gen_parser.add_argument(
        "--model", type=str, default=None,
        help="Claude model to use",
    )
    gen_parser.add_argument(
        "--json", action="store_true", dest="output_json",
        help="Output results as JSON",
    )

    # --- evaluate ---
    eval_parser = subparsers.add_parser(
        "evaluate",
        help="Evaluate existing text against a quality rubric.",
    )
    eval_group = eval_parser.add_mutually_exclusive_group(required=True)
    eval_group.add_argument("--text", type=str, help="Text to evaluate (inline)")
    eval_group.add_argument("--file", type=str, help="Path to file containing text to evaluate")
    eval_parser.add_argument(
        "--rubric", type=str, default="email",
        help="Rubric name or path to YAML file (default: email)",
    )
    eval_parser.add_argument(
        "--source", type=str, default="",
        help="Path to source material file for grounding verification",
    )
    eval_parser.add_argument(
        "--subject", type=str, default=None,
        help="Subject/title line to evaluate separately",
    )
    eval_parser.add_argument(
        "--context", type=str, default="",
        help="Additional context for the evaluator",
    )
    eval_parser.add_argument(
        "--model", type=str, default=None,
        help="Claude model to use for all evaluations",
    )
    eval_parser.add_argument(
        "--json", action="store_true", dest="output_json",
        help="Output results as JSON",
    )
    eval_parser.add_argument(
        "--skip-grounding", action="store_true",
        help="Skip grounding verification",
    )

    # --- rubrics ---
    rubrics_parser = subparsers.add_parser(
        "rubrics",
        help="List available built-in rubrics.",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "rubrics":
        _cmd_rubrics()
    elif args.command == "evaluate":
        _cmd_evaluate(args)
    elif args.command == "generate":
        _cmd_generate(args)


def _cmd_rubrics() -> None:
    """List available built-in rubrics."""
    from ramsay.config import RUBRICS_DIR
    from ramsay.style import load_rubric

    if not RUBRICS_DIR.exists():
        print("No rubrics directory found.")
        return

    yaml_files = sorted(RUBRICS_DIR.glob("*.yaml"))
    if not yaml_files:
        print("No rubrics found.")
        return

    print("Available rubrics:\n")
    for path in yaml_files:
        try:
            rubric = load_rubric(path)
            dims = ", ".join(d.name for d in rubric.dimensions)
            hard = ", ".join(d.name for d in rubric.hard_floor_dimensions)
            print(f"  {rubric.name}")
            print(f"    {rubric.description}")
            print(f"    Dimensions: {dims}")
            print(f"    Hard floors: {hard}")
            print(f"    Pass rule: {rubric.pass_rule}")
            print()
        except Exception as e:
            print(f"  {path.stem} (error loading: {e})")


def _cmd_evaluate(args: argparse.Namespace) -> None:
    """Evaluate text against a rubric."""
    from ramsay import evaluate

    # Load text
    if args.text:
        text = args.text
    else:
        text = Path(args.file).read_text()

    # Load source material
    source_material = ""
    if args.source:
        source_material = Path(args.source).read_text()

    result = evaluate(
        text=text,
        source_material=source_material,
        rubric=args.rubric,
        subject=args.subject,
        context=args.context,
        model=args.model,
        skip_grounding=args.skip_grounding,
    )

    if args.output_json:
        output = {
            "passed": result.passed,
            "grounding": result.grounding.to_dict() if result.grounding else None,
            "style": result.style.to_dict() if result.style else None,
            "feedback": result.feedback,
        }
        print(json.dumps(output, indent=2))
    else:
        _print_eval_result(result)


def _cmd_generate(args: argparse.Namespace) -> None:
    """Run the generate pipeline."""
    from ramsay import generate

    # Load task
    if args.task_file:
        task = Path(args.task_file).read_text()
    else:
        task = args.task

    # Load sources
    sources = Path(args.sources).read_text()

    result = generate(
        task=task,
        sources=sources,
        rubric=args.rubric,
        voice=args.voice,
        subject=args.subject,
        context=args.context,
        max_rewrites=args.max_rewrites,
        model=args.model,
    )

    if args.output_json:
        output = {
            "passed": result.passed,
            "text": result.text,
            "attempts": len(result.attempts),
            "scores": result.scores,
            "feedback": result.feedback,
        }
        print(json.dumps(output, indent=2))
    else:
        _print_generate_result(result)


def _print_eval_result(result) -> None:
    """Pretty-print an evaluation result."""
    status = "PASSED" if result.passed else "FAILED"
    print(f"\n{'=' * 50}")
    print(f"  Result: {status}")
    print(f"{'=' * 50}\n")

    # Grounding
    g = result.grounding
    if g and g.claims:
        g_status = "PASS" if g.passed else "FAIL"
        print(f"  Grounding: {g_status}")
        print(f"    Claims: {len(g.claims)} total, {len(g.failing_claims)} failing")
        if g.failure_reasons:
            for reason in g.failure_reasons:
                print(f"    - {reason}")
        print()

    # Style
    s = result.style
    if s:
        s_status = "PASS" if s.passed else "FAIL"
        print(f"  Style: {s_status}")
        if s.precheck_failed:
            print(f"    (Failed at precheck stage)")
        if s.scores:
            for name, score in s.scores.items():
                print(f"    {name}: {score}")
        if s.primary_issue:
            print(f"    Primary issue: {s.primary_issue}")
        if s.feedback and not s.passed:
            print(f"    Feedback: {s.feedback}")
        print()

    if result.feedback:
        print(f"  Combined feedback:")
        for line in result.feedback.split("\n"):
            print(f"    {line}")
        print()


def _print_generate_result(result) -> None:
    """Pretty-print a generate pipeline result."""
    status = "PASSED" if result.passed else "FAILED"
    print(f"\n{'=' * 50}")
    print(f"  Result: {status}")
    print(f"  Attempts: {len(result.attempts)}")
    print(f"{'=' * 50}\n")

    if result.scores:
        print("  Final scores:")
        for name, score in result.scores.items():
            print(f"    {name}: {score}")
        print()

    if result.feedback:
        print("  Feedback:")
        for line in result.feedback.split("\n"):
            print(f"    {line}")
        print()

    print("  Final text:")
    print("  " + "-" * 46)
    for line in result.text.split("\n"):
        print(f"  {line}")
    print("  " + "-" * 46)
    print()


if __name__ == "__main__":
    main()
