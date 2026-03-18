"""
Pipeline -- orchestrates generate -> verify -> evaluate -> rewrite.

The pipeline runs text through the full quality gauntlet:
1. Generate initial text from task + sources + voice
2. Run grounding verification against source material
3. Run style evaluation against a rubric
4. If either fails, rewrite with targeted feedback
5. Repeat until pass or max_rewrites exhausted

Grounding runs first because fabricated facts are worse than style issues.
Grounding fail-fast: 2 consecutive grounding failures = bail (the generator
keeps inventing the same kind of claim; another try won't help).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ramsay.claude import call_claude, load_prompt
from ramsay.config import (
    GENERATION_MODEL,
    GENERATION_TEMPERATURE,
    GROUNDING_FAIL_FAST,
    MAX_REGEX_RETRIES,
    MAX_REWRITES,
)
from ramsay.grounding import GroundingResult, verify_grounding
from ramsay.style import Rubric, StyleResult, evaluate_style, load_rubric

logger = logging.getLogger(__name__)


@dataclass
class Attempt:
    """Record of a single generation/rewrite attempt."""

    attempt: int
    text: str
    grounding: Optional[Dict[str, Any]] = None
    style: Optional[Dict[str, Any]] = None
    failure_type: Optional[str] = None


@dataclass
class GenerateResult:
    """Result of the generate() pipeline."""

    text: str
    passed: bool
    attempts: List[Attempt] = field(default_factory=list)
    scores: Dict[str, int] = field(default_factory=dict)
    feedback: str = ""
    grounding: Optional[GroundingResult] = None
    style: Optional[StyleResult] = None

    def __bool__(self) -> bool:
        return self.passed


# Keep backward compat alias
RewriteResult = GenerateResult


def generate(
    task: str,
    sources: str,
    rubric: Union[str, Path, Dict[str, Any], Rubric],
    *,
    voice: Optional[Union[str, Dict[str, Any]]] = None,
    subject: Optional[str] = None,
    context: str = "",
    max_rewrites: int = MAX_REWRITES,
    model: Optional[str] = None,
    grounding_model: Optional[str] = None,
    style_model: Optional[str] = None,
) -> GenerateResult:
    """Generate quality-controlled text from a task description and sources.

    This is the primary API. Generates text, then runs it through grounding
    verification and style evaluation. If either fails, rewrites with targeted
    feedback until the text passes or max_rewrites is exhausted.

    Args:
        task: What to write. A plain-language description of the desired output.
            E.g., "Write a 1500-word essay explaining CRISPR base editing for
            a technical but non-specialist audience."
        sources: Reference material to ground against. Research notes, transcripts,
            interview excerpts, paper summaries -- any evidence the text can cite.
        rubric: Quality rubric to evaluate against. Can be:
            - A string name of a built-in rubric (e.g., "essay", "email", "blog")
            - A Path to a custom YAML rubric file
            - A dict with rubric data
            - A pre-loaded Rubric object
        voice: Optional style profile. Can be:
            - A string describing the voice ("Direct, conversational, no hedging.")
            - A dict with structured fields (e.g., {"tone": "casual", "sentence_length": "short"})
            - None to use the model's default voice
        subject: Optional subject/title line to evaluate separately.
        context: Optional context for the evaluator (relationship info, etc.).
        max_rewrites: Maximum rewrite attempts before giving up.
        model: Model for generation. Defaults to config.GENERATION_MODEL.
        grounding_model: Model for grounding. Defaults to config.GROUNDING_MODEL.
        style_model: Model for style evaluation. Defaults to config.STYLE_MODEL.

    Returns:
        GenerateResult with final text, pass/fail status, scores, feedback,
        and full trace of all attempts.
    """
    # Load rubric if needed
    if not isinstance(rubric, Rubric):
        rubric = load_rubric(rubric)

    effective_model = model or GENERATION_MODEL

    # Build the generation prompt
    generation_prompt = _build_generation_prompt(task, sources, rubric, voice)

    # --- Generate initial text ---
    logger.info("Generating initial text from task...")
    text = call_claude(
        generation_prompt,
        "Write the text as described. Output only the text itself.",
        max_tokens=4000,
        temperature=GENERATION_TEMPERATURE,
        model=effective_model,
    )

    return _run_quality_pipeline(
        text=text,
        source_material=sources,
        rubric=rubric,
        prompt=generation_prompt,
        subject=subject,
        context=context,
        max_rewrites=max_rewrites,
        model=effective_model,
        grounding_model=grounding_model,
        style_model=style_model,
    )


def rewrite_until_pass(
    prompt: str,
    source_material: str,
    rubric: Union[str, Path, Dict[str, Any], Rubric],
    *,
    subject: Optional[str] = None,
    context: str = "",
    max_rewrites: int = MAX_REWRITES,
    model: Optional[str] = None,
    grounding_model: Optional[str] = None,
    style_model: Optional[str] = None,
) -> GenerateResult:
    """Generate text from a prompt and iterate until it passes quality checks.

    This is the original generation API. For new code, prefer generate() which
    accepts a task description and sources instead of a raw prompt.

    Args:
        prompt: The generation prompt (system prompt for the initial generation).
        source_material: Reference material for grounding verification.
        rubric: Rubric name, path, dict, or Rubric object for style evaluation.
        subject: Optional subject/title to evaluate separately.
        context: Optional context for style evaluation.
        max_rewrites: Maximum rewrite attempts before giving up.
        model: Model for generation. Defaults to config.GENERATION_MODEL.
        grounding_model: Model for grounding. Defaults to config.GROUNDING_MODEL.
        style_model: Model for style evaluation. Defaults to config.STYLE_MODEL.

    Returns:
        GenerateResult with final text, pass status, attempt count, and trace.
    """
    # Load rubric if needed
    if not isinstance(rubric, Rubric):
        rubric = load_rubric(rubric)

    effective_model = model or GENERATION_MODEL

    # --- Generate initial text ---
    logger.info("Generating initial text...")
    text = call_claude(
        prompt,
        "Generate the text as described in the system prompt.",
        max_tokens=2000,
        temperature=GENERATION_TEMPERATURE,
        model=effective_model,
    )

    return _run_quality_pipeline(
        text=text,
        source_material=source_material,
        rubric=rubric,
        prompt=prompt,
        subject=subject,
        context=context,
        max_rewrites=max_rewrites,
        model=effective_model,
        grounding_model=grounding_model,
        style_model=style_model,
    )


def evaluate_and_rewrite(
    text: str,
    source_material: str,
    rubric: Union[str, Path, Dict[str, Any], Rubric],
    *,
    prompt: str = "",
    subject: Optional[str] = None,
    context: str = "",
    max_rewrites: int = MAX_REWRITES,
    model: Optional[str] = None,
    grounding_model: Optional[str] = None,
    style_model: Optional[str] = None,
) -> GenerateResult:
    """Evaluate existing text and rewrite if it fails quality checks.

    Like rewrite_until_pass but starts with existing text instead of
    generating from scratch.

    Args:
        text: The text to evaluate and potentially rewrite.
        source_material: Reference material for grounding verification.
        rubric: Rubric for style evaluation.
        prompt: System prompt to use for rewrites (provides generation context).
        subject: Optional subject/title to evaluate.
        context: Optional context for style evaluation.
        max_rewrites: Maximum rewrite attempts.
        model: Model for rewrites.
        grounding_model: Model for grounding verification.
        style_model: Model for style evaluation.

    Returns:
        GenerateResult with final text, pass status, and trace.
    """
    if not isinstance(rubric, Rubric):
        rubric = load_rubric(rubric)

    effective_model = model or GENERATION_MODEL

    return _run_quality_pipeline(
        text=text,
        source_material=source_material,
        rubric=rubric,
        prompt=prompt,
        subject=subject,
        context=context,
        max_rewrites=max_rewrites,
        model=effective_model,
        grounding_model=grounding_model,
        style_model=style_model,
    )


# ---------------------------------------------------------------------------
# Generation prompt construction
# ---------------------------------------------------------------------------

def _build_generation_prompt(
    task: str,
    sources: str,
    rubric: Rubric,
    voice: Optional[Union[str, Dict[str, Any]]],
) -> str:
    """Build the system prompt for initial generation.

    Loads prompts/generate.md as a template and injects the task, sources,
    rubric dimensions, and voice constraints.
    """
    template = load_prompt("generate.md")

    # Voice block
    voice_block = ""
    if voice is not None:
        if isinstance(voice, dict):
            voice_lines = [f"- **{k}**: {v}" for k, v in voice.items()]
            voice_text = "\n".join(voice_lines)
        else:
            voice_text = str(voice)
        voice_block = f"## Voice and style\n\nMatch this voice:\n\n{voice_text}"

    # Dimensions summary (shorter than the full eval prompt -- just enough to guide)
    dim_lines = []
    for dim in rubric.dimensions:
        floor_tag = " [MUST PASS]" if dim.hard_floor else ""
        dim_lines.append(f"- **{dim.name}**{floor_tag} (min {dim.min_pass}/5): {dim.description.strip()}")
    dimensions_summary = "\n".join(dim_lines)

    # Kill list summary
    kill_list_summary = ""
    if rubric.kill_list:
        kill_lines = [f"- {item}" for item in rubric.kill_list]
        kill_list_summary = "## Anti-patterns (automatic rejection)\n\n" + "\n".join(kill_lines)

    # Banned phrases
    banned_text = ""
    if rubric.banned_phrases:
        banned_text = "\n".join(f'- "{p}"' for p in rubric.banned_phrases)
    else:
        banned_text = "(none)"

    # Substitute into template
    prompt = template.replace("{{TASK}}", task)
    prompt = prompt.replace("{{SOURCES}}", sources if sources.strip() else "(No source material provided.)")
    prompt = prompt.replace("{{VOICE_BLOCK}}", voice_block)
    prompt = prompt.replace("{{DIMENSIONS_SUMMARY}}", dimensions_summary)
    prompt = prompt.replace("{{KILL_LIST_SUMMARY}}", kill_list_summary)
    prompt = prompt.replace("{{BANNED_PHRASES}}", banned_text)

    return prompt


# ---------------------------------------------------------------------------
# Quality pipeline
# ---------------------------------------------------------------------------

def _run_quality_pipeline(
    text: str,
    source_material: str,
    rubric: Rubric,
    prompt: str,
    *,
    subject: Optional[str] = None,
    context: str = "",
    max_rewrites: int = MAX_REWRITES,
    model: str = GENERATION_MODEL,
    grounding_model: Optional[str] = None,
    style_model: Optional[str] = None,
) -> GenerateResult:
    """Internal pipeline: grounding -> style -> rewrite loop.

    Returns GenerateResult with the final text and quality status.
    """
    trace: List[Attempt] = []

    def _record(attempt_num: int, txt: str, g: Optional[GroundingResult],
                s: Optional[StyleResult], failure: Optional[str]) -> None:
        trace.append(Attempt(
            attempt=attempt_num,
            text=txt,
            grounding=g.to_dict() if g else None,
            style=s.to_dict() if s else None,
            failure_type=failure,
        ))

    # --- Initial grounding check ---
    grounding_result = verify_grounding(
        text, source_material, model=grounding_model,
    )
    grounding_passed = grounding_result.passed

    # --- Only run style if grounding passes ---
    style_result: Optional[StyleResult] = None
    style_passed = False
    if grounding_passed:
        style_result = evaluate_style(
            text, rubric, subject=subject, context=context, model=style_model,
        )
        style_passed = style_result.passed

    # Determine initial failure type
    initial_failure = _classify_failure(grounding_passed, style_result)
    _record(0, text, grounding_result, style_result, initial_failure)

    rewrite_count = 0
    regex_retries = 0
    consecutive_grounding_fails = 1 if not grounding_passed else 0

    while not (grounding_passed and style_passed):
        # Determine if this is a regex-only failure (cheap, doesn't count)
        is_regex_only = (
            grounding_passed
            and style_result is not None
            and style_result.precheck_failed
        )

        if is_regex_only:
            regex_retries += 1
            if regex_retries > MAX_REGEX_RETRIES:
                logger.info("Regex retry cap reached (%d)", MAX_REGEX_RETRIES)
                break
        else:
            if rewrite_count >= max_rewrites:
                break
            rewrite_count += 1

        # Build rewrite instruction
        rewrite_block = _build_rewrite_instruction(
            grounding_passed, grounding_result, style_result, is_regex_only, regex_retries,
        )

        logger.info(
            "Rewrite %d/%d (%s failure)",
            rewrite_count, max_rewrites,
            "regex" if is_regex_only else ("grounding" if not grounding_passed else "style"),
        )

        # Rewrite
        rewrite_prompt = prompt or "You are a skilled writer. Rewrite the following text to fix the identified issues while preserving the core message."
        rewrite_message = (
            f"Original text:\n{text}\n\n"
            f"Source material (for factual accuracy):\n{source_material}\n\n"
            f"{rewrite_block}\n\n"
            f"Write only the revised text. No preamble, no explanation."
        )

        text = call_claude(
            rewrite_prompt,
            rewrite_message,
            max_tokens=4000,
            temperature=GENERATION_TEMPERATURE,
            model=model,
        )

        # After rewrite: always run grounding first
        grounding_result = verify_grounding(
            text, source_material, model=grounding_model,
        )
        grounding_passed = grounding_result.passed

        # Only run style if grounding passes
        if grounding_passed:
            consecutive_grounding_fails = 0
            style_result = evaluate_style(
                text, rubric, subject=subject, context=context, model=style_model,
            )
            style_passed = style_result.passed
        else:
            consecutive_grounding_fails += 1
            style_result = None
            style_passed = False

            # Fail-fast: consecutive grounding failures
            if consecutive_grounding_fails >= GROUNDING_FAIL_FAST:
                logger.info(
                    "Grounding fail-fast: %d consecutive failures",
                    consecutive_grounding_fails,
                )
                break

        failure = _classify_failure(grounding_passed, style_result)
        _record(rewrite_count, text, grounding_result, style_result, failure)

    # Build combined feedback
    feedback_parts = []
    if grounding_result and not grounding_result.passed:
        feedback_parts.append(
            "GROUNDING: " + "; ".join(grounding_result.failure_reasons)
        )
    if style_result and not style_result.passed:
        feedback_parts.append("STYLE: " + style_result.feedback)

    return GenerateResult(
        text=text,
        passed=grounding_passed and style_passed,
        attempts=trace,
        scores=style_result.scores if style_result else {},
        feedback="\n".join(feedback_parts),
        grounding=grounding_result,
        style=style_result,
    )


def _classify_failure(
    grounding_passed: bool, style_result: Optional[StyleResult]
) -> Optional[str]:
    """Classify the type of failure for tracing."""
    if not grounding_passed:
        return "grounding"
    if style_result and not style_result.passed:
        if style_result.precheck_failed:
            return "regex"
        return "style"
    return None


def _build_rewrite_instruction(
    grounding_passed: bool,
    grounding_result: GroundingResult,
    style_result: Optional[StyleResult],
    is_regex_only: bool,
    regex_retries: int,
) -> str:
    """Build targeted rewrite instructions based on failure type."""
    if not grounding_passed:
        failure_reasons = grounding_result.failure_reasons
        return (
            "PREVIOUS TEXT REJECTED -- FACTUAL GROUNDING FAILURE.\n"
            + "\n".join(f"- {r}" for r in failure_reasons)
            + "\n\n"
            "Remove or correct the failing claims. Do not invent replacement details. "
            "Only use facts that appear in the source material."
        )

    if is_regex_only and style_result:
        feedback = style_result.feedback
        return (
            f"PREVIOUS TEXT REJECTED -- MECHANICAL ISSUE "
            f"(does not count against rewrite budget).\n"
            f"{feedback}\n\n"
            f"Fix the specific mechanical issues listed above. Do not change "
            f"the content or structure, just remove the offending phrases or punctuation."
        )

    if style_result:
        primary = style_result.primary_issue
        feedback = style_result.feedback
        return (
            f"PREVIOUS TEXT REJECTED -- STYLE ISSUE.\n"
            f"Primary issue: {primary or feedback}\n"
            f"Additional feedback: {feedback}\n\n"
            f"Rewrite to address the primary issue first."
        )

    return "PREVIOUS TEXT REJECTED. Rewrite to improve quality."
