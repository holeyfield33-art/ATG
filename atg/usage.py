"""Slim usage awareness — headers first, simple policy."""

from __future__ import annotations

from typing import Any

# Soft-low multiplier: if remaining < estimated / low_threshold, surface budget_low.
# e.g. threshold 0.2 and estimate 5000 → warn when remaining < 25000.
DEFAULT_LOW_THRESHOLD = 0.2
ABSOLUTE_TOKEN_FLOOR = 1000


def parse_openai_headers(headers: dict[str, str]) -> dict[str, int | None]:
    """Extract useful rate-limit fields from OpenAI response headers."""

    def _int(key: str) -> int | None:
        val = headers.get(key)
        if val is None:
            for k, v in headers.items():
                if k.lower() == key.lower():
                    val = v
                    break
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
        val = headers.get(key)
        if val is None:
            for k, v in headers.items():
                if k.lower() == key.lower():
                    val = v
                    break
        if val is None:
            return None
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return None

    return {
        "remaining_tokens": _int("anthropic-ratelimit-tokens-remaining"),
        "remaining_requests": _int("anthropic-ratelimit-requests-remaining"),
        "limit_tokens": _int("anthropic-ratelimit-tokens-limit"),
        "limit_requests": _int("anthropic-ratelimit-requests-limit"),
    }


def parse_headers(platform: str | None, headers: dict[str, str]) -> dict[str, int | None]:
    """Dispatch to the correct header parser for the platform.

    An unset/unrecognized platform merges both parsers rather than guessing —
    guessing OpenAI for headers that are actually Anthropic's (or vice versa)
    would silently return all-None and let decide_action report a false
    "proceed" on an exhausted budget. A non-string platform (a caller passing
    a stray int/dict through a loosely-typed MCP call) is treated the same as
    unset rather than raising, for the same reason.
    """
    platform = platform.lower().strip() if isinstance(platform, str) else ""
    if platform in ("openai", "azure", "azure_openai"):
        return parse_openai_headers(headers)
    if platform in ("anthropic", "claude"):
        return parse_anthropic_headers(headers)
    oa = parse_openai_headers(headers)
    an = parse_anthropic_headers(headers)
    return {
        "remaining_tokens": oa["remaining_tokens"] if oa["remaining_tokens"] is not None else an["remaining_tokens"],
        "remaining_requests": oa["remaining_requests"] if oa["remaining_requests"] is not None else an["remaining_requests"],
        "limit_tokens": oa["limit_tokens"] if oa["limit_tokens"] is not None else an["limit_tokens"],
        "limit_requests": oa["limit_requests"] if oa["limit_requests"] is not None else an["limit_requests"],
    }


def decide_action(
    remaining_tokens: int | None = None,
    remaining_requests: int | None = None,
    estimated_tokens: int = 0,
    low_threshold: float = DEFAULT_LOW_THRESHOLD,
) -> dict[str, Any]:
    """
    Return a simple proceed / budget_low / pause signal.

    Soft threshold: when remaining_tokens < estimated_tokens / low_threshold
    (and still above the hard estimate), return budget_low so the agent can
    checkpoint early.
    """
    if remaining_tokens is None and remaining_requests is None:
        return {
            "action": "proceed",
            "reason": "no_limit_data",
            "remaining_tokens": None,
            "remaining_requests": None,
            "estimated_tokens": estimated_tokens,
        }

    if remaining_tokens is not None and estimated_tokens > 0:
        if remaining_tokens < estimated_tokens:
            return {
                "action": "pause",
                "reason": "insufficient_tokens_for_estimate",
                "remaining_tokens": remaining_tokens,
                "remaining_requests": remaining_requests,
                "estimated_tokens": estimated_tokens,
            }

    # Hard stop on a truly exhausted token budget even when the caller didn't
    # supply estimated_tokens — without this, a 0-budget caller that omits the
    # estimate only ever gets the advisory "budget_low", never "pause".
    if remaining_tokens is not None and remaining_tokens <= 0:
        return {
            "action": "pause",
            "reason": "tokens_exhausted",
            "remaining_tokens": remaining_tokens,
            "remaining_requests": remaining_requests,
            "estimated_tokens": estimated_tokens,
        }

    if remaining_requests is not None and remaining_requests <= 1:
        return {
            "action": "pause",
            "reason": "requests_nearly_exhausted",
            "remaining_tokens": remaining_tokens,
            "remaining_requests": remaining_requests,
            "estimated_tokens": estimated_tokens,
        }

    if remaining_tokens is not None and remaining_tokens < ABSOLUTE_TOKEN_FLOOR:
        return {
            "action": "budget_low",
            "reason": "tokens_low",
            "remaining_tokens": remaining_tokens,
            "remaining_requests": remaining_requests,
            "estimated_tokens": estimated_tokens,
        }

    if remaining_tokens is not None and estimated_tokens > 0:
        thresh = max(float(low_threshold), 0.01)
        soft_limit = estimated_tokens / thresh
        if remaining_tokens < soft_limit:
            return {
                "action": "budget_low",
                "reason": "soft_threshold",
                "remaining_tokens": remaining_tokens,
                "remaining_requests": remaining_requests,
                "estimated_tokens": estimated_tokens,
                "soft_limit": int(soft_limit),
            }

    return {
        "action": "proceed",
        "reason": "ok",
        "remaining_tokens": remaining_tokens,
        "remaining_requests": remaining_requests,
        "estimated_tokens": estimated_tokens,
    }
