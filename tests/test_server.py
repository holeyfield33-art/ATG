"""Server entrypoint: check_usage platform default, transport/host gating."""

import os
import tempfile
from pathlib import Path

# atg.server builds a module-level CheckpointStore() on import; point it at a
# throwaway DB instead of the real ~/.atg/checkpoints.db before importing.
# Force the override (not setdefault) — a dev's shell may already export
# ATG_DB_PATH pointing at their real local checkpoints DB, and running the
# test suite must never write there.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="atg-server-test-")
os.environ["ATG_DB_PATH"] = str(Path(_TEST_DB_DIR) / "test-server.db")

import pytest  # noqa: E402

from atg import server  # noqa: E402


def test_check_usage_default_platform_does_not_drop_anthropic_headers():
    # Regression: platform used to default to "openai", so real Anthropic
    # headers were parsed by the wrong parser, came back all-None, and
    # produced a false "proceed" even at zero remaining budget.
    decision = server.check_usage(
        headers={"anthropic-ratelimit-tokens-remaining": "0"},
        estimated_tokens=0,
    )
    assert decision["action"] == "pause"
    assert decision["reason"] == "tokens_exhausted"


def test_check_usage_explicit_platform_still_works():
    decision = server.check_usage(
        platform="openai",
        headers={"x-ratelimit-remaining-tokens": "42000"},
    )
    assert decision["action"] == "proceed"


def test_http_refused_without_allow_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.argv", ["atg", "--transport", "streamable-http"])
    with pytest.raises(SystemExit) as exc:
        server.main()
    assert exc.value.code == 2


def test_http_allowed_binds_loopback_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "sys.argv", ["atg", "--transport", "streamable-http", "--allow-remote-http"]
    )
    calls: dict = {}
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.update(kwargs))
    server.main()
    assert calls == {"transport": "streamable-http", "host": "127.0.0.1", "port": 8765}


def test_http_allowed_with_explicit_non_loopback_host(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "atg",
            "--transport",
            "streamable-http",
            "--host",
            "0.0.0.0",
            "--port",
            "9999",
            "--allow-remote-http",
        ],
    )
    calls: dict = {}
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.update(kwargs))
    server.main()
    assert calls == {"transport": "streamable-http", "host": "0.0.0.0", "port": 9999}


def test_env_var_allow_remote_http_also_binds_loopback_by_default(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ATG_ALLOW_REMOTE_HTTP", "1")
    monkeypatch.setattr("sys.argv", ["atg", "--transport", "streamable-http"])
    calls: dict = {}
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.update(kwargs))
    server.main()
    assert calls["host"] == "127.0.0.1"
