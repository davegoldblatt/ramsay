"""
Fast regex-based precheck filters.

Runs before any LLM call. Catches banned phrases, structural tells,
and mechanical issues that are cheaper to detect with pattern matching
than with an API call.

Each check returns a list of failure reasons (empty = passed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PrecheckResult:
    """Result of running regex prechecks against text."""

    passed: bool
    failures: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.passed


_GREETING_PARAGRAPH_RE = re.compile(
    r"^(?:hi|hey|hello|dear|yo|morning|good morning)\b[^\n]{0,40}$", re.IGNORECASE
)
_SENDER_VOICE_RE = re.compile(
    r"\b(?:we|we're|we've|we'd|our|ours|us|i|i'm|i've|i'd|my|me)\b", re.IGNORECASE
)


def _paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def _sentences(paragraph: str) -> List[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", paragraph.strip()) if s.strip()]


def find_dossier_line(text: str) -> Optional[str]:
    """Return the opening paragraph if it is a standalone "dossier line", else None.

    A dossier line is a single sentence about the recipient (their company, their
    town, what they make) that sits alone as the first paragraph after the greeting
    and does nothing else. Its only job is to show the sender looked them up, and
    because it always lands in the same slot it reads as a template beat:

        Hi Sam,

        Acme's Dayton plant builds hydraulic valves.

        We make ...

    The check is deliberately narrow, so a hit is high-confidence:
    the paragraph is one sentence, has no question, has no sender voice
    (we/our/I/my), and is followed by more body text.
    """
    paragraphs = _paragraphs(text)
    if paragraphs and _GREETING_PARAGRAPH_RE.match(paragraphs[0]):
        paragraphs = paragraphs[1:]
    if len(paragraphs) < 2:
        return None
    opener = paragraphs[0]
    if "?" in opener or len(_sentences(opener)) != 1 or _SENDER_VOICE_RE.search(opener):
        return None
    return opener


def run_precheck(
    text: str,
    *,
    banned_phrases: Optional[List[str]] = None,
    subject: Optional[str] = None,
    subject_banned: Optional[List[str]] = None,
    max_subject_words: int = 10,
    max_em_dashes: int = 0,
    check_been_verbing: bool = True,
    check_dossier_line: bool = False,
) -> PrecheckResult:
    """Run all regex prechecks against a piece of text.

    Args:
        text: The main text body to check.
        banned_phrases: Case-insensitive phrases that cause an automatic fail.
        subject: Optional subject/title line to check separately.
        subject_banned: Subjects that are banned (case-insensitive exact match).
        max_subject_words: Maximum words allowed in subject.
        max_em_dashes: Maximum mid-sentence em dashes allowed (0 = none).
        check_been_verbing: Whether to check for "Been [verb]ing" openers.
        check_dossier_line: Whether to fail a standalone one-sentence fact about
            the recipient as the first body paragraph (see find_dossier_line).

    Returns:
        PrecheckResult with passed status and list of failure reasons.
    """
    failures: List[str] = []

    # Combine subject and text for full-text checks
    full_text = f"{subject}\n{text}" if subject else text
    full_lower = full_text.lower()

    # --- 1. Banned phrase scan ---
    for phrase in (banned_phrases or []):
        phrase_lower = phrase.lower()
        if phrase_lower in full_lower:
            # Find the original-case version for reporting
            idx = full_lower.index(phrase_lower)
            original = full_text[idx : idx + len(phrase)]
            failures.append(f'Banned phrase: "{original}"')

    # --- 1b. "Honestly" as a sentence opener ---
    honestly_re = re.compile(r"(?:^|[.!?]\s+)honestly\b", re.IGNORECASE)
    if honestly_re.search(full_text):
        failures.append('Banned phrase: "Honestly" as sentence opener')

    # --- 2. Em dash count (mid-sentence only) ---
    em_dash_re = re.compile(r"\u2014|--")
    salutation_dash_re = re.compile(r"^\s*(?:\w+[.,]?\s+){0,2}\w+[.,]?\s*(?:\u2014|--)")

    lines = text.split("\n")
    em_dash_count = 0
    for line in lines:
        cleaned = line
        if salutation_dash_re.match(line):
            cleaned = em_dash_re.sub("", line, count=1)
        em_dash_count += len(em_dash_re.findall(cleaned))

    if em_dash_count > max_em_dashes:
        noun = "em dash" if em_dash_count == 1 else "em dashes"
        failures.append(
            f"{em_dash_count} {noun} (max {max_em_dashes} allowed)"
        )

    # --- 3. "Been [verb]ing" opener ---
    if check_been_verbing:
        been_verbing_re = re.compile(r"^been\s+\w+ing\b", re.IGNORECASE)
        body_lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in body_lines:
            # Skip greeting lines
            if re.match(r"^(?:hey|hi|hello|dear|yo)\b", line, re.IGNORECASE):
                continue
            if salutation_dash_re.match(line):
                continue
            # This is the first real content line
            if been_verbing_re.match(line):
                failures.append(f'"Been [verb]ing" opener: "{line[:60]}"')
            break

    # --- 3b. Standalone dossier line ---
    if check_dossier_line:
        dossier = find_dossier_line(text)
        if dossier:
            failures.append(
                f'Dossier line standing alone: "{dossier[:80]}". '
                "Fold the fact into a sentence that does other work, or cut it."
            )

    # --- 4. Subject line checks ---
    if subject is not None:
        subject_stripped = subject.strip()
        subject_lower = subject_stripped.lower()

        # Check against banned subjects
        for bad_subject in (subject_banned or []):
            if subject_lower == bad_subject.lower():
                failures.append(f'Generic subject line: "{subject_stripped}"')
                break

        # Check subject length
        word_count = len(subject_stripped.split())
        if word_count > max_subject_words:
            failures.append(
                f"Subject too long ({word_count} words, max {max_subject_words})"
            )

    return PrecheckResult(
        passed=len(failures) == 0,
        failures=failures,
    )
