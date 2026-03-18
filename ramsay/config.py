"""
Default configuration for Ramsay.

All values can be overridden at call sites. These are sensible defaults
for most use cases.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------

# Model used for grounding verification (benefits from precision over creativity)
GROUNDING_MODEL = "claude-sonnet-4-6"

# Model used for style evaluation (same reasoning)
STYLE_MODEL = "claude-sonnet-4-6"

# Model used for text generation and rewrites
GENERATION_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Pipeline defaults
# ---------------------------------------------------------------------------

# Maximum rewrite attempts before giving up
MAX_REWRITES = 3

# Maximum regex-only retries (cheap, doesn't count against rewrite budget)
MAX_REGEX_RETRIES = 3

# Consecutive grounding failures before fail-fast bail
GROUNDING_FAIL_FAST = 2

# Temperature for generation calls
GENERATION_TEMPERATURE = 0.7

# Temperature for evaluation calls (deterministic scoring)
EVAL_TEMPERATURE = 0.0

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Package root — used to find bundled rubrics and prompts
PACKAGE_DIR = Path(__file__).parent
PROJECT_DIR = PACKAGE_DIR.parent
RUBRICS_DIR = PROJECT_DIR / "rubrics"
PROMPTS_DIR = PROJECT_DIR / "prompts"

# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------

def get_api_key() -> str:
    """Return the Anthropic API key from the environment.

    Checks ANTHROPIC_API_KEY. Raises ValueError if not set.
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Set it to your Anthropic API key before using Ramsay."
        )
    return key
