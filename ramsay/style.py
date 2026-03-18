"""
Style Evaluator

Evaluates AI-generated text against a configurable quality rubric
defined in YAML. Two stages:

1. Regex precheck — fast, deterministic, no API call
2. LLM evaluation — scores each rubric dimension, returns structured feedback

The gate logic (pass/fail) is enforced in code, not by the LLM.
The LLM scores; code decides.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from ramsay.claude import call_claude, load_prompt
from ramsay.config import STYLE_MODEL, RUBRICS_DIR
from ramsay.precheck import PrecheckResult, run_precheck

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rubric loading
# ---------------------------------------------------------------------------

@dataclass
class Dimension:
    """A single scoring dimension from a rubric."""

    name: str
    description: str
    min_pass: int = 3
    hard_floor: bool = False


@dataclass
class Rubric:
    """A loaded quality rubric."""

    name: str
    description: str
    dimensions: List[Dimension]
    kill_list: List[str] = field(default_factory=list)
    banned_phrases: List[str] = field(default_factory=list)
    subject_banned: List[str] = field(default_factory=list)
    pass_rule: str = "all_hard_floors"
    max_em_dashes: int = 0
    max_subject_words: int = 10

    @property
    def hard_floor_dimensions(self) -> List[Dimension]:
        return [d for d in self.dimensions if d.hard_floor]

    @property
    def advisory_dimensions(self) -> List[Dimension]:
        return [d for d in self.dimensions if not d.hard_floor]


def load_rubric(rubric: Union[str, Path, Dict[str, Any]]) -> Rubric:
    """Load a rubric from a name, file path, or dict.

    Args:
        rubric: One of:
            - A string name of a built-in rubric (e.g., "email")
            - A Path to a YAML file
            - A dict with rubric data already parsed

    Returns:
        A Rubric object ready for evaluation.
    """
    if isinstance(rubric, dict):
        raw = rubric
    elif isinstance(rubric, Path):
        raw = yaml.safe_load(rubric.read_text())
    elif isinstance(rubric, str):
        # Check if it's a file path
        path = Path(rubric)
        if path.exists() and path.suffix in (".yaml", ".yml"):
            raw = yaml.safe_load(path.read_text())
        else:
            # Look for built-in rubric
            builtin_path = RUBRICS_DIR / f"{rubric}.yaml"
            if builtin_path.exists():
                raw = yaml.safe_load(builtin_path.read_text())
            else:
                raise FileNotFoundError(
                    f"Rubric '{rubric}' not found. Looked in: {builtin_path}"
                )
    else:
        raise TypeError(f"Expected str, Path, or dict, got {type(rubric)}")

    dimensions = []
    for dim_data in raw.get("dimensions", []):
        dimensions.append(
            Dimension(
                name=dim_data["name"],
                description=dim_data.get("description", ""),
                min_pass=dim_data.get("min_pass", 3),
                hard_floor=dim_data.get("hard_floor", False),
            )
        )

    return Rubric(
        name=raw.get("name", "custom"),
        description=raw.get("description", ""),
        dimensions=dimensions,
        kill_list=raw.get("kill_list", []),
        banned_phrases=raw.get("banned_phrases", []),
        subject_banned=raw.get("subject_banned", []),
        pass_rule=raw.get("pass_rule", "all_hard_floors"),
        max_em_dashes=raw.get("max_em_dashes", 0),
        max_subject_words=raw.get("max_subject_words", 10),
    )


# ---------------------------------------------------------------------------
# Style evaluation result
# ---------------------------------------------------------------------------

@dataclass
class StyleResult:
    """Result of style evaluation."""

    passed: bool
    precheck: PrecheckResult
    scores: Dict[str, int] = field(default_factory=dict)
    primary_issue: str = ""
    feedback: str = ""
    precheck_failed: bool = False
    raw_response: str = ""

    def __bool__(self) -> bool:
        return self.passed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "precheck_failed": self.precheck_failed,
            "scores": self.scores,
            "primary_issue": self.primary_issue,
            "feedback": self.feedback,
        }


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def evaluate_style(
    text: str,
    rubric: Union[str, Path, Dict[str, Any], Rubric],
    *,
    subject: Optional[str] = None,
    context: str = "",
    model: Optional[str] = None,
) -> StyleResult:
    """Evaluate text against a style rubric.

    Args:
        text: The text to evaluate.
        rubric: Rubric name, path, dict, or Rubric object.
        subject: Optional subject/title line (checked separately).
        context: Optional context about the text (relationship info, etc.)
            that helps the LLM evaluate appropriateness.
        model: Claude model to use. Defaults to config.STYLE_MODEL.

    Returns:
        StyleResult with pass/fail, scores, and feedback.
    """
    # Load rubric if not already loaded
    if not isinstance(rubric, Rubric):
        rubric = load_rubric(rubric)

    effective_model = model or STYLE_MODEL

    # --- Stage 1: Regex precheck (deterministic, no API call) ---
    precheck = run_precheck(
        text,
        banned_phrases=rubric.banned_phrases,
        subject=subject,
        subject_banned=rubric.subject_banned,
        max_subject_words=rubric.max_subject_words,
        max_em_dashes=rubric.max_em_dashes,
    )

    if not precheck.passed:
        logger.info("Precheck FAILED: %s", "; ".join(precheck.failures))
        return StyleResult(
            passed=False,
            precheck=precheck,
            precheck_failed=True,
            primary_issue=precheck.failures[0],
            feedback="; ".join(precheck.failures),
        )

    logger.info("Precheck passed for rubric '%s'", rubric.name)

    # --- Stage 2: LLM evaluation ---
    system_prompt = _build_style_prompt(rubric)

    # Build user message
    parts = []
    if context:
        parts.append(f"CONTEXT:\n{context}\n")
    if subject:
        parts.append(f"TEXT TO EVALUATE:\nTitle/Subject: {subject}\n\n{text}")
    else:
        parts.append(f"TEXT TO EVALUATE:\n{text}")

    user_message = "\n".join(parts)

    raw_response = call_claude(
        system_prompt,
        user_message,
        max_tokens=800,
        temperature=0.0,
        model=effective_model,
    )
    logger.debug("Style LLM raw response: %s", raw_response)

    parsed = _parse_evaluation(raw_response)
    result = _enforce_pass_criteria(parsed, rubric)

    # Build StyleResult
    scores = result.get("scores", {})
    score_summary = ", ".join(f"{k}={v}" for k, v in scores.items()) if scores else "no scores"
    logger.info("Style result: passed=%s [%s]", result.get("passed"), score_summary)

    return StyleResult(
        passed=result.get("passed", False),
        precheck=precheck,
        scores=scores,
        primary_issue=result.get("primary_issue", ""),
        feedback=result.get("feedback", ""),
        raw_response=raw_response,
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_style_prompt(rubric: Rubric) -> str:
    """Build the style evaluation system prompt from template + rubric dimensions.

    Loads prompts/style.md as a template and injects rubric-specific dimensions,
    kill list, and pass criteria.
    """
    template = load_prompt("style.md")

    # Build dimensions section
    dim_lines = []
    for dim in rubric.dimensions:
        floor_note = f" (HARD FLOOR: min {dim.min_pass})" if dim.hard_floor else f" (advisory: min {dim.min_pass})"
        dim_lines.append(f"### {dim.name.upper()}{floor_note}")
        dim_lines.append(dim.description)
        dim_lines.append(f"Score 1-5. Minimum to pass: {dim.min_pass}.")
        dim_lines.append("")
    dimensions_text = "\n".join(dim_lines)

    # Build kill list section
    kill_list_text = ""
    if rubric.kill_list:
        kill_lines = [f"- {item}" for item in rubric.kill_list]
        kill_list_text = "## Kill list\n\nThese are structural anti-patterns. If present, the text fails.\n\n" + "\n".join(kill_lines)

    # Build pass criteria
    pass_criteria_lines = []
    for dim in rubric.hard_floor_dimensions:
        pass_criteria_lines.append(f"- Fail if {dim.name} < {dim.min_pass}")
    for dim in rubric.advisory_dimensions:
        pass_criteria_lines.append(f"- {dim.name} informs feedback but does not drive pass/fail")
    pass_criteria_text = "\n".join(pass_criteria_lines)

    # Build score keys for output format
    score_keys = ", ".join(f'"{d.name}": N' for d in rubric.dimensions)

    # Substitute into template
    prompt = template.replace("{{DIMENSIONS}}", dimensions_text)
    prompt = prompt.replace("{{KILL_LIST}}", kill_list_text)
    prompt = prompt.replace("{{PASS_CRITERIA}}", pass_criteria_text)
    prompt = prompt.replace("{{SCORE_KEYS}}", score_keys)
    prompt = prompt.replace("{{RUBRIC_NAME}}", rubric.name)
    prompt = prompt.replace("{{RUBRIC_DESCRIPTION}}", rubric.description)

    return prompt


# ---------------------------------------------------------------------------
# Response parsing and gate enforcement
# ---------------------------------------------------------------------------

def _parse_evaluation(response: str) -> Dict[str, Any]:
    """Parse the LLM's JSON evaluation response."""
    defaults: Dict[str, Any] = {
        "passed": False,
        "scores": {},
        "primary_issue": "",
        "feedback": "Could not parse evaluation response",
    }
    try:
        # Try to find JSON in the response
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(response[json_start:json_end])
            defaults.update(parsed)
    except (json.JSONDecodeError, KeyError):
        pass
    return defaults


def _enforce_pass_criteria(
    result: Dict[str, Any],
    rubric: Rubric,
) -> Dict[str, Any]:
    """Recompute passed deterministically from scores.

    The LLM scores; code decides the gate. Fail closed on malformed data.
    """
    scores = result.get("scores", {})

    if rubric.pass_rule == "all_hard_floors":
        return _enforce_hard_floors(result, scores, rubric)
    elif rubric.pass_rule == "average":
        return _enforce_average(result, scores, rubric)
    else:
        # Default to hard floors
        return _enforce_hard_floors(result, scores, rubric)


def _enforce_hard_floors(
    result: Dict[str, Any],
    scores: Dict[str, Any],
    rubric: Rubric,
) -> Dict[str, Any]:
    """Pass if all hard-floor dimensions meet their minimums."""
    reasons = []

    for dim in rubric.hard_floor_dimensions:
        val = scores.get(dim.name)
        if not isinstance(val, (int, float)):
            logger.warning(
                "Score key '%s' missing or non-numeric (got %r). Failing closed.",
                dim.name,
                val,
            )
            result["passed"] = False
            if not result.get("primary_issue"):
                result["primary_issue"] = f"Malformed scores: '{dim.name}' missing or non-numeric"
            return result

        if val < dim.min_pass:
            reasons.append(f"{dim.name}={val}<{dim.min_pass}")

    code_passed = len(reasons) == 0
    llm_passed = result.get("passed", False)

    if llm_passed != code_passed:
        logger.info(
            "Style gate override: llm=%s final=%s reasons=%s",
            llm_passed,
            code_passed,
            ",".join(reasons) if reasons else "criteria_met",
        )

    result["passed"] = code_passed
    return result


def _enforce_average(
    result: Dict[str, Any],
    scores: Dict[str, Any],
    rubric: Rubric,
) -> Dict[str, Any]:
    """Pass if average of all dimensions meets threshold and hard floors met."""
    reasons = []
    all_values = []

    for dim in rubric.dimensions:
        val = scores.get(dim.name)
        if not isinstance(val, (int, float)):
            logger.warning(
                "Score key '%s' missing or non-numeric (got %r). Failing closed.",
                dim.name,
                val,
            )
            result["passed"] = False
            if not result.get("primary_issue"):
                result["primary_issue"] = f"Malformed scores: '{dim.name}' missing or non-numeric"
            return result

        all_values.append(val)

        # Hard floors still apply
        if dim.hard_floor and val < dim.min_pass:
            reasons.append(f"{dim.name}={val}<{dim.min_pass}")

    # Check average
    if all_values:
        avg = sum(all_values) / len(all_values)
        result["average"] = round(avg, 1)
        if avg < 3.5:
            reasons.append(f"avg={avg:.1f}<3.5")

    # Check all above minimum
    for dim, val in zip(rubric.dimensions, all_values):
        if val < dim.min_pass:
            if f"{dim.name}=" not in " ".join(reasons):
                reasons.append(f"{dim.name}={val}<{dim.min_pass}")

    code_passed = len(reasons) == 0
    result["passed"] = code_passed
    return result
