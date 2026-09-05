# Aletheia Token Guard (ATG)

[![CI](https://github.com/holeyfield33-art/ATG/actions/workflows/ci.yml/badge.svg)](https://github.com/holeyfield33-art/ATG/actions/workflows/ci.yml)
[![Vibe Check Code Scanner](https://img.shields.io/badge/Vibe%20Check-Code%20Scanner-purple?logo=github)](https://github.com/marketplace/actions/vibe-check-code-scanner)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)


**Slim MCP server for token/usage awareness and durable work checkpoints.**

Plugin-ready companion to [Horos](https://github.com/holeyfield33-art/Horos) (context router + signed receipts) and [Mneme](https://github.com/holeyfield33-art/Mneme-) (persistent memory).

**Status:** experimental v0.1 — single-user local sidecar. See [SECURITY.md](SECURITY.md).

---

## Why ATG?

Agents die mid-task when they hit rate limits, spend caps, or context budgets. ATG gives any MCP host a thin side-car that:

1. Answers **"can I keep going?"** (rate-limit headers + simple policy)
2. Lets the agent **save a checkpoint** and resume later
3. Stays out of the way of context selection (Horos) and long-term memory (Mneme)

It is deliberately minimal. No multi-tenant auth, no dashboards, no full connector zoo in v0.

---

## Tools (v0)

| Tool | Purpose |
|------|---------|
| `check_usage` | Rate-limit / budget signal. Returns `proceed` / `budget_low` / `pause` |
| `save_checkpoint` | Persist work progress under a `work_id` |
| `load_checkpoint` | Retrieve the latest checkpoint for a `work_id` |
| `list_checkpoints` | List incomplete / recent work (limit clamped 1–500) |
| `mark_done` | Mark a work item complete |

Optional `meta` on checkpoints can hold a Horos `receipt_hash` or Mneme memory key.

### `check_usage` — header path

Preferred: pass the **raw provider response headers** plus `platform`:

```json
{
  "platform": "openai",
  "estimated_tokens": 5000,
  "headers": {
    "x-ratelimit-remaining-tokens": "42000",
    "x-ratelimit-remaining-requests": "8"
  }
}
```

ATG parses OpenAI / Anthropic header names (case-insensitive). You may also pass `remaining_tokens` / `remaining_requests` directly if the host already extracted them.

Pass the real `platform` name when you pass `headers`. `platform` has no default — if you omit it (or pass something ATG doesn't recognize), ATG merges both the OpenAI and Anthropic parsers rather than guessing OpenAI, so real Anthropic headers are never silently misread as "no limit data" and turned into a false `proceed`.

**ATG does not intercept provider traffic.** The host/agent must supply headers or remaining counts. Policy is advisory.

Policy:

- **pause** — remaining tokens ≤ 0, remaining < estimate, or requests ≤ 1
- **budget_low** — remaining < 1000, or remaining < estimate / `low_threshold` (default 0.2)
- **proceed** — otherwise, or when no limit data is supplied

---

## Quick start

```bash
git clone https://github.com/holeyfield33-art/ATG.git
cd ATG
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# stdio (recommended for MCP hosts)
python -m atg

# streamable-HTTP is UNAUTHENTICATED — local-only
# requires explicit opt-in; binds to 127.0.0.1 by default:
python -m atg --transport streamable-http --port 8765 --allow-remote-http

# to actually expose it beyond this machine, pass --host explicitly too
# (still requires --allow-remote-http):
python -m atg --transport streamable-http --port 8765 --host 0.0.0.0 --allow-remote-http
```

### Security: streamable-HTTP

**streamable-HTTP has no authentication.** It is intended for local development only. The server refuses to start HTTP mode unless you pass `--allow-remote-http` or set `ATG_ALLOW_REMOTE_HTTP=1`. Prefer **stdio** for real hosts.

Full notes: [SECURITY.md](SECURITY.md).

---

## Configuration

| Env | Meaning |
|-----|---------|
| `ATG_DB_PATH` | SQLite path (default `~/.atg/checkpoints.db`) |
| `ATG_INTEGRITY_KEY` | Optional HMAC-SHA256 key (covers work_id, platform, status, data, meta, token_snapshot, created_at) |
| `ATG_ALLOW_REMOTE_HTTP` | Set to `1` to allow unauthenticated HTTP transport |

JSON fields (`data`, `meta`, `token_snapshot`) are capped at ~512 KB. Store large blobs externally and pass a URI.

`work_id` max 256 chars; charset `[A-Za-z0-9._:/-]`.

SQLite uses **WAL** + `busy_timeout=5000` for lock contention, and `_connect()` separately retries (up to 3 attempts, exponential backoff starting at 50ms) on a `sqlite3.OperationalError` raised before a connection is established — e.g. transient contention creating the db file/directory on cold start. Old versions per `work_id` are pruned (keep last 20).

---

## Example agent loop

See [`examples/agent_loop.py`](examples/agent_loop.py): extract headers → `check_usage` policy → checkpoint on pause → resume.

```bash
python examples/agent_loop.py
```

---

## Local development & testing (Codespaces)

Everything below runs the same way in a GitHub Codespace as it does anywhere else —
no extra setup beyond what's already in this repo.

### 1. Get the code and a clean environment

```bash
git clone https://github.com/holeyfield33-art/ATG.git
cd ATG
python -m venv .venv
source .venv/bin/activate        # every new terminal/session needs this re-run
pip install -e ".[dev]"
```
`pip install -e .` is an "editable" install — it links the package to this
checkout instead of copying it, so edits to `atg/*.py` take effect immediately
without reinstalling.

### 2. Run the automated test suite

```bash
pytest -q
```
Expect `46 passed`. `-q` just means quiet output (dots instead of a line per test);
drop it (`pytest`) if you want to see each test name as it runs.

To run one file or one test while you're iterating:
```bash
pytest tests/test_checkpoint.py -v          # one file, verbose
pytest tests/test_checkpoint.py -k tamper   # only tests with "tamper" in the name
```

### 3. Run the server by hand (stdio)

```bash
python -m atg
```
This starts the MCP server on stdio and blocks, waiting for an MCP client to talk
to it over stdin/stdout — it won't print anything on its own. `Ctrl+C` to stop.
This is how a real MCP host (Claude Desktop, an agent framework, etc.) would run it;
there's nothing to click or browse to.

### 4. Run the worked example

```bash
python examples/agent_loop.py
```
This exercises the whole flow in-process — no MCP host needed — so it's the
fastest way to see `check_usage` → `save_checkpoint` → `load_checkpoint` actually
working end to end. Read `examples/agent_loop.py` alongside the output; it's short
and it's the clearest map of how the pieces fit together.

### 5. Verify the security fixes yourself

If you want to see the properties SECURITY.md claims actually hold — rather than
take the docs' word for it — drop this into a scratch file and run it. It tries
the exact three attacks that were open before this round of fixes and confirms
each is now blocked:

```python
# scratch_verify.py — safe to delete after running
import sqlite3, tempfile
from pathlib import Path
from atg.checkpoint import CheckpointStore

with tempfile.TemporaryDirectory() as td:
    db = Path(td) / "verify.db"
    s = CheckpointStore(db_path=db, integrity_key="test-key")
    s.save("job1", {"step": 1}, meta={"receipt_hash": "abc123"},
           token_snapshot={"remaining_tokens": 90000})

    # 1. Tamper with meta/token_snapshot directly in the DB file, bypassing the API
    conn = sqlite3.connect(db)
    conn.execute("UPDATE checkpoints SET meta = ? WHERE work_id = ?",
                 ('{"receipt_hash": "FORGED"}', "job1"))
    conn.execute("UPDATE checkpoints SET token_snapshot = ? WHERE work_id = ?",
                 ('{"remaining_tokens": 1}', "job1"))
    print("tamper detected:", s.load("job1")["integrity_ok"] is False)  # expect True

    # 2. Oversized / malformed work_id
    try:
        s.save("x" * 5000, {"a": 1})
        print("work_id validation: FAILED (accepted bad input)")
    except ValueError:
        print("work_id validation: OK (rejected)")

    # 3. Non-JSON-serializable data
    class Weird:
        pass
    try:
        s.save("w2", {"bad": Weird()})
        print("serialization check: FAILED (silently accepted)")
    except ValueError:
        print("serialization check: OK (rejected)")
```
```bash
python scratch_verify.py
```
All three lines should say the guarantee held. If any of them don't, that's a
regression worth opening an issue over before it ships.

### 6. Sanity-check a fresh dependency install

Because `mcp[cli]` is a range (`>=1.0.0,<3.0.0`), not a single pinned version, it's
worth occasionally confirming what actually gets installed matches what's tested:
```bash
pip show mcp | grep Version   # should currently print 2.1.1
```
If this ever prints something outside the tested range, don't trust the security
posture claims until the test suite has been re-run against that version.

---

## Design principles

- **Side-car, not platform.** Compose with Horos and Mneme via MCP.
- **Headers first.** Prefer live rate-limit headers over Admin APIs.
- **SQLite by default.** Zero ops for personal / consulting use.
- **Loose integration seams.** Checkpoint `meta` can reference Horos / Mneme IDs.
- **Honest limits.** Single-user, local, no encryption at rest, advisory policy only.

---

## License

MIT

---

Part of the Aletheia family — tools that make AI systems inspectable and trustworthy.
