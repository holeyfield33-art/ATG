"""Policy matrix and header parser tests."""

from atg.usage import decide_action, parse_anthropic_headers, parse_headers, parse_openai_headers


def test_no_limit_data_proceeds():
    d = decide_action()
    assert d["action"] == "proceed"
    assert d["reason"] == "no_limit_data"


def test_hard_pause_insufficient_tokens():
    d = decide_action(remaining_tokens=100, estimated_tokens=500)
    assert d["action"] == "pause"
    assert d["reason"] == "insufficient_tokens_for_estimate"


def test_pause_requests_nearly_exhausted():
    d = decide_action(remaining_tokens=50_000, remaining_requests=1, estimated_tokens=100)
    assert d["action"] == "pause"
    assert d["reason"] == "requests_nearly_exhausted"


def test_absolute_token_floor():
    d = decide_action(remaining_tokens=500, estimated_tokens=0)
    assert d["action"] == "budget_low"
    assert d["reason"] == "tokens_low"


def test_soft_threshold():
    # estimate 5000, threshold 0.2 → soft_limit 25000
    d = decide_action(remaining_tokens=10_000, estimated_tokens=5_000, low_threshold=0.2)
    assert d["action"] == "budget_low"
    assert d["reason"] == "soft_threshold"
    assert d["soft_limit"] == 25_000


def test_proceed_when_comfortable():
    d = decide_action(remaining_tokens=100_000, estimated_tokens=5_000, low_threshold=0.2)
    assert d["action"] == "proceed"
    assert d["reason"] == "ok"


def test_parse_openai_headers():
    h = {
        "x-ratelimit-remaining-tokens": "42000",
        "x-ratelimit-remaining-requests": "8",
        "x-ratelimit-limit-tokens": "90000",
        "x-ratelimit-limit-requests": "10",
    }
    p = parse_openai_headers(h)
    assert p["remaining_tokens"] == 42000
    assert p["remaining_requests"] == 8
    assert p["limit_tokens"] == 90000


def test_parse_openai_headers_case_insensitive():
    h = {"X-RateLimit-Remaining-Tokens": "100"}
    p = parse_openai_headers(h)
    assert p["remaining_tokens"] == 100


def test_parse_anthropic_headers():
    h = {
        "anthropic-ratelimit-tokens-remaining": "12000.0",
        "anthropic-ratelimit-requests-remaining": "3",
    }
    p = parse_anthropic_headers(h)
    assert p["remaining_tokens"] == 12000
    assert p["remaining_requests"] == 3


def test_parse_headers_dispatch():
    h = {"x-ratelimit-remaining-tokens": "9"}
    p = parse_headers("openai", h)
    assert p["remaining_tokens"] == 9

    h2 = {"anthropic-ratelimit-tokens-remaining": "11"}
    p2 = parse_headers("anthropic", h2)
    assert p2["remaining_tokens"] == 11
