"""
Thin wrapper around the Anthropic API.

Keeps all API details in one place so the rest of the library
only deals with strings in / strings out.
"""

from __future__ import annotations

import logging
from pathlib import Path

import anthropic

from ramsay.config import get_api_key, PROMPTS_DIR

logger = logging.getLogger(__name__)

# Reusable client — created lazily on first call
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Return a shared Anthropic client, creating it on first use."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=get_api_key())
    return _client


def call_claude(
    system_prompt: str,
    user_message: str,
    *,
    max_tokens: int = 1000,
    temperature: float = 0.0,
    model: str = "claude-sonnet-4-6",
) -> str:
    """Send a single-turn message to Claude and return the text response.

    Args:
        system_prompt: The system prompt (cached for efficiency).
        user_message: The user message content.
        max_tokens: Maximum tokens in the response.
        temperature: Sampling temperature (0.0 = deterministic).
        model: Which Claude model to use.

    Returns:
        The text content of Claude's response.
    """
    client = _get_client()

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )

    # Log token usage for debugging
    usage = response.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    logger.debug(
        "Token usage: input=%d cache_create=%d cache_read=%d",
        input_tokens,
        cache_create,
        cache_read,
    )

    return response.content[0].text


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts/ directory.

    Args:
        name: Filename within the prompts/ directory (e.g., "grounding.md").

    Returns:
        The prompt text as a string.
    """
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text()
