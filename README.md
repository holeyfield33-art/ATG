# Aletheia Token Guard (ATG)

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

**ATG does not intercept provider traffic.** The host/agent must supply headers or remaining counts. Policy is advisory.

Policy:

- **pause** — remaining < estimate, or requests ≤ 1
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
# requires explicit opt-in:
python -m atg --transport streamable-http --port 8765 --allow-remote-http
```

### Security: streamable-HTTP

**streamable-HTTP has no authentication.** It is intended for local development only. The server refuses to start HTTP mode unless you pass `--allow-remote-http` or set `ATG_ALLOW_REMOTE_HTTP=1`. Prefer **stdio** for real hosts.

Full notes: [SECURITY.md](SECURITY.md).

---

## Configuration

| Env | Meaning |
|-----|---------|
| `ATG_DB_PATH` | SQLite path (default `~/.atg/checkpoints.db`) |
| `ATG_INTEGRITY_KEY` | Optional HMAC-SHA256 key (covers work_id, status, data, meta, token_snapshot, created_at) |
| `ATG_ALLOW_REMOTE_HTTP` | Set to `1` to allow unauthenticated HTTP transport |

JSON fields (`data`, `meta`, `token_snapshot`) are capped at ~512 KB. Store large blobs externally and pass a URI.

`work_id` max 256 chars; charset `[A-Za-z0-9._:/-]`.

SQLite uses **WAL** + `busy_timeout` with short connect retries on cold start. Old versions per `work_id` are pruned (keep last 20).

---

## Example agent loop

See [`examples/agent_loop.py`](examples/agent_loop.py): extract headers → `check_usage` policy → checkpoint on pause → resume.

```bash
python examples/agent_loop.py
```

---

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

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
