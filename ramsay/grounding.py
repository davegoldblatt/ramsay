"""
Grounding Verifier

Extracts concrete claims from AI-generated text and checks each one
against provided source material. Returns a binary pass/fail with
structured claim-level detail.

The verifier catches:
- Contradictions: claims that conflict with source material
- Stale claims: facts that were true but may no longer be current
- Unsupported material: claims with no basis in any provided source
- (Supported claims are fine and reported for transparency)

Design principle: fail closed. If parsing fails or claims can't be
verified, the text fails. One bad claim fails the entire piece.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ramsay.claude import call_claude, load_prompt
from ramsay.config import GROUNDING_MODEL

logger = logging.getLogger(__name__)

# Verdicts that cause a grounding failure
FAILING_VERDICTS = {"contradicted", "stale_or_time_sensitive", "unsupported_material"}


@dataclass
class Claim:
    """A single factual claim extracted from the text."""

    claim_text: str
    claim_category: str
    evidence: Optional[str]
    evidence_source: str
    verdict: str

    @property
    def is_failing(self) -> bool:
        return self.verdict in FAILING_VERDICTS


@dataclass
class GroundingResult:
    """Result of grounding verification."""

    passed: bool
    claims: List[Claim] = field(default_factory=list)
    failure_reasons: List[str] = field(default_factory=list)
    primary_issue: Optional[str] = None
    raw_response: str = ""

    def __bool__(self) -> bool:
        return self.passed

    @property
    def failing_claims(self) -> List[Claim]:
        return [c for c in self.claims if c.is_failing]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pass": self.passed,
            "claims": [
                {
                    "claim_text": c.claim_text,
                    "claim_category": c.claim_category,
                    "evidence": c.evidence,
                    "evidence_source": c.evidence_source,
                    "verdict": c.verdict,
                }
                for c in self.claims
            ],
            "failure_reasons": self.failure_reasons,
            "primary_issue": self.primary_issue,
        }


def verify_grounding(
    text: str,
    source_material: str,
    *,
    model: Optional[str] = None,
    today: Optional[str] = None,
) -> GroundingResult:
    """Verify that all factual claims in text are grounded in source material.

    Args:
        text: The text to verify (any AI-generated writing).
        source_material: Evidence to check claims against. Can be research notes,
            transcripts, conversation history, or any reference material.
        model: Claude model to use. Defaults to config.GROUNDING_MODEL.
        today: Current date as YYYY-MM-DD string. Defaults to today.

    Returns:
        GroundingResult with pass/fail status and claim-level details.
    """
    verifier_prompt = load_prompt("grounding.md")
    effective_model = model or GROUNDING_MODEL
    effective_today = today or datetime.now().strftime("%Y-%m-%d")

    if not source_material.strip():
        logger.warning(
            "Grounding verifier running without source material -- "
            "all factual claims will be unsupported"
        )

    user_message = (
        f"## TEXT TO VERIFY\n\n"
        f"{text}\n\n"
        f"## SOURCE MATERIAL\n\n"
        f"{source_material}\n\n"
        f"## TODAY\n\n"
        f"{effective_today}"
    )

    raw_response = call_claude(
        verifier_prompt,
        user_message,
        max_tokens=2000,
        temperature=0.0,
        model=effective_model,
    )

    try:
        parsed = _parse_json_response(raw_response)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Grounding verifier parse error: %s", e)
        return GroundingResult(
            passed=False,
            failure_reasons=[f"Verifier response parse error: {e}"],
            primary_issue="Verifier response could not be parsed",
            raw_response=raw_response,
        )

    # Build structured claims
    claims = []
    for raw_claim in parsed.get("claims", []):
        claim = Claim(
            claim_text=raw_claim.get("claim_text", ""),
            claim_category=raw_claim.get("claim_category", "unknown"),
            evidence=raw_claim.get("evidence"),
            evidence_source=raw_claim.get("evidence_source", "none"),
            verdict=raw_claim.get("verdict", "unsupported_material"),
        )
        claims.append(claim)

        # Fuzzy sanity check: flag claims the verifier may have hallucinated
        if not _fuzzy_claim_check(claim.claim_text, text):
            logger.warning(
                "Possible verifier hallucination: '%s'",
                claim.claim_text[:80],
            )

    # Extract results
    failure_reasons = parsed.get("failure_reasons", [])
    passed = parsed.get("pass", False)

    # Log summary
    failing = [c for c in claims if c.is_failing]
    logger.info(
        "Grounding: %s | Claims: %d total, %d failing",
        "PASS" if passed else "FAIL",
        len(claims),
        len(failing),
    )

    return GroundingResult(
        passed=passed,
        claims=claims,
        failure_reasons=failure_reasons,
        primary_issue=failure_reasons[0] if failure_reasons else None,
        raw_response=raw_response,
    )


def _parse_json_response(text: str) -> Dict[str, Any]:
    """Extract JSON from a response that may contain markdown fences."""
    # Try markdown-fenced JSON first
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # Fall back to raw JSON
    return json.loads(text.strip())


def _fuzzy_claim_check(claim_text: str, source_text: str) -> bool:
    """Check whether a claim's key words actually appear in the source text.

    Returns True if the claim seems grounded in the text being verified,
    False if the verifier may have hallucinated a claim.
    """
    skip = {
        "that", "this", "with", "from", "they", "their", "were", "have", "been",
        "about", "when", "what", "your", "some", "just", "also", "more", "than",
        "into", "like", "still", "would", "could", "does", "didn",
    }
    words = re.findall(r"[a-zA-Z]{4,}", claim_text.lower())
    significant = [w for w in words if w not in skip]

    if not significant:
        return True

    source_lower = source_text.lower()
    matches = sum(1 for w in significant if w in source_lower)
    return matches >= len(significant) * 0.5
