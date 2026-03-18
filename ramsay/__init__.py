"""
Ramsay -- quality-controlled text generation.

Define a rubric, provide sources, get text that passes your quality bar.

Three-stage pipeline:

1. **Generate** -- produces text from a task description, source material, and optional voice
2. **Ground** -- verifies every factual claim against your source material
3. **Evaluate** -- scores the text against a configurable quality rubric
4. **Rewrite** -- if either check fails, rewrites with targeted feedback

Quick start:

    from ramsay import generate

    result = generate(
        task="Write a 500-word blog post about distributed caching",
        sources="[your research notes, interview transcripts, etc.]",
        rubric="blog",
    )
    print(result.text)     # the final output
    print(result.passed)   # True if it cleared the quality bar
    print(result.scores)   # dimension scores from the rubric

For evaluating existing text without generation:

    from ramsay import evaluate

    result = evaluate(
        text="Your text here...",
        source_material="Research notes, transcripts, etc...",
        rubric="email",
    )
    print(result.passed, result.feedback)
"""

from __future__ import annotations

__version__ = "0.2.0"

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union

from ramsay.grounding import GroundingResult, verify_grounding
from ramsay.style import StyleResult, evaluate_style, load_rubric, Rubric
from ramsay.pipeline import (
    GenerateResult,
    RewriteResult,
    generate,
    rewrite_until_pass,
    evaluate_and_rewrite,
)


@dataclass
class EvalResult:
    """Combined result from evaluate()."""

    passed: bool
    grounding: GroundingResult
    style: Optional[StyleResult]
    feedback: str = ""

    def __bool__(self) -> bool:
        return self.passed


def evaluate(
    text: str,
    source_material: str = "",
    rubric: Union[str, Path, Dict[str, Any], Rubric] = "email",
    *,
    subject: Optional[str] = None,
    context: str = "",
    model: Optional[str] = None,
    grounding_model: Optional[str] = None,
    style_model: Optional[str] = None,
    skip_grounding: bool = False,
) -> EvalResult:
    """Evaluate a piece of text for quality.

    Runs grounding verification (if source_material provided) and style
    evaluation against the specified rubric. Returns a combined result.

    This is the secondary API for checking existing text without generation.
    For generating new text with quality control, use generate().

    Args:
        text: The text to evaluate.
        source_material: Evidence to verify factual claims against.
            If empty, grounding is skipped.
        rubric: Which rubric to use. Can be:
            - A string name of a built-in rubric (e.g., "email", "essay")
            - A Path to a custom YAML rubric file
            - A dict with rubric data
            - A pre-loaded Rubric object
        subject: Optional subject/title line to evaluate separately.
        context: Optional context (relationship info, etc.) for the evaluator.
        model: Default model for all LLM calls.
        grounding_model: Model for grounding verification.
        style_model: Model for style evaluation.
        skip_grounding: If True, skip grounding verification entirely.

    Returns:
        EvalResult with overall pass/fail, grounding details, style details,
        and combined feedback.
    """
    # Resolve model defaults
    g_model = grounding_model or model
    s_model = style_model or model

    # --- Grounding ---
    grounding_result: Optional[GroundingResult] = None
    grounding_passed = True

    if source_material.strip() and not skip_grounding:
        grounding_result = verify_grounding(
            text, source_material, model=g_model,
        )
        grounding_passed = grounding_result.passed

    # --- Style (only if grounding passes or was skipped) ---
    style_result: Optional[StyleResult] = None
    style_passed = False

    if grounding_passed:
        style_result = evaluate_style(
            text, rubric, subject=subject, context=context, model=s_model,
        )
        style_passed = style_result.passed

    # --- Combine feedback ---
    feedback_parts = []
    if grounding_result and not grounding_result.passed:
        feedback_parts.append(
            "GROUNDING: " + "; ".join(grounding_result.failure_reasons)
        )
    if style_result and not style_result.passed:
        feedback_parts.append("STYLE: " + style_result.feedback)

    overall_passed = grounding_passed and style_passed

    return EvalResult(
        passed=overall_passed,
        grounding=grounding_result or GroundingResult(passed=True),
        style=style_result,
        feedback="\n".join(feedback_parts),
    )


# Re-export key types for convenience
__all__ = [
    "generate",
    "evaluate",
    "rewrite_until_pass",
    "evaluate_and_rewrite",
    "GenerateResult",
    "RewriteResult",
    "EvalResult",
    "GroundingResult",
    "StyleResult",
    "Rubric",
    "load_rubric",
    "verify_grounding",
    "evaluate_style",
]
