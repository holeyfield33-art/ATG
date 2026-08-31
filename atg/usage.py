"""Slim usage awareness — headers first, simple policy."""

from __future__ import annotations

from typing import Any


def decide_action(
    remaining_tokens: int | None = None,
    remaining_requests: int | None = None,
    estimated_tokens: int = 0,
    low_threshold: float = 0.2,
) -> dict[str, Any]:
    """
    Return a simple proceed / budget_low / pause signal.

    This deliberately does not pretend to know exact remaining budget.
    Prefer live rate-limit headers when available.
    """
    if remaining_tokens is None and remaining_requests is None:
        return {
            "action": "proceed",
            "reason": "no_limit_data",
            "remaining_tokens": None,
            "remaining_requests": None,
            "estimated_tokens": estimated_tokens,
        }

    # Hard pause if we clearly cannot afford the estimate
    if remaining_tokens is not None and estimated_tokens > 0:
        if remaining_tokens < estimated_tokens:
            return {
                "action": "pause",
                "reason": "insufficient_tokens_for_estimate",
                "remaining_tokens": remaining_tokens,
                "remaining_requests": remaining_requests,
                "estimated_tokens": estimated_tokens,
            }

        # Soft warning
        if remaining_tokens < estimated_tokens * (1 / max(low_threshold, 0.01)):
            # e.g. if estimate is 5k and threshold 0.2, warn below 25k
            pass

    if remaining_requests is not None and remaining_requests <= 1:
        return {
            "action": "pause",
            "reason": "requests_nearly_exhausted",
            "remaining_tokens": remaining_tokens,
            "remaining_requests": remaining_requests,
            "estimated_tokens": estimated_tokens,
        }

    if remaining_tokens is not None and remaining_tokens < 1000:
        return {
            "action": "budget_low",
            "reason": "tokens_low",
            "remaining_tokens": remaining_tokens,
            "remaining_requests": remaining_requests,
            "estimated_tokens": estimated_tokens,
        }

    return {
        "action": "proceed",
        "reason": "ok",
        "remaining_tokens": remaining_tokens,
        "remaining_requests": remaining_requests,
        "estimated_tokens": estimated_tokens,
    }


def parse_openai_headers(headers: dict[str, str]) -> dict[str, int | None]:
    """Extract useful rate-limit fields from OpenAI response headers."""
    def _int(key: str) -> int | None:
        val = headers.get(key) or headers.get(key.lower())
        if val is None:
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    return {
        "remaining_tokens": _int("x-ratelimit-remaining-tokens"),
        "remaining_requests": _int("x-ratelimit-remaining-requests"),
        "limit_tokens": _int("x-ratelimit-limit-tokens"),
        "limit_requests": _int("x-ratelimit-limit-requests"),
    }


def parse_anthropic_headers(headers: dict[str, str]) -> dict[str, int | None]:
    """Extract useful rate-limit fields from Anthropic response headers."""
    def _int(key: str) -> int | None:
        val = headers.get(key) or headers.get(key.lower())
        if val is None:
            return None
        try:
            # Anthropic sometimes rounds remaining tokens
            return int(float(val))
        except (TypeError, ValueError):
            return None

    return {
        "remaining_tokens": _int("anthropic-ratelimit-tokens-remaining"),
        "remaining_requests": _int("anthropic-ratelimit-requests-remaining"),
        "limit_tokens": _int("anthropic-ratelimit-tokens-limit"),
        "limit_requests": _int("anthropic-ratelimit-requests-limit"),
    }
