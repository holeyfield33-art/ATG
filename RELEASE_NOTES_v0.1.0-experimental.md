# ATG v0.1.0-experimental

**Slim MCP server for token/usage awareness and durable work checkpoints.**

Experimental single-user local sidecar. Not multi-tenant. Not a production enforcement gate.

## Install

```bash
git clone https://github.com/holeyfield33-art/ATG.git
cd ATG
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m atg   # stdio (recommended)
```

## Tools

| Tool | Purpose |
|------|---------|
| `check_usage` | `proceed` / `budget_low` / `pause` from headers or remaining_* |
| `save_checkpoint` | Persist work under `work_id` |
| `load_checkpoint` | Latest in-progress checkpoint |
| `list_checkpoints` | Incomplete work (limit clamped 1–500) |
| `mark_done` | Complete a work item |

Preferred `check_usage` path: pass raw provider `headers` + `platform` (`openai` / `anthropic`). ATG does **not** intercept provider traffic — the host must supply headers or remaining counts. Policy is **advisory**.

## Security posture (read before shipping)

- **stdio** preferred for real MCP hosts.
- **streamable-http** is unauthenticated; requires `--allow-remote-http` or `ATG_ALLOW_REMOTE_HTTP=1`; local-dev only.
- Optional `ATG_INTEGRITY_KEY` HMAC covers `work_id`, `status`, `created_at`, `data`, `meta`, `token_snapshot` (detection, not encryption).
- **Breaking:** the HMAC message format changed to actually cover all six fields listed above (it previously covered only `work_id`, `created_at`, `data`). Checkpoints signed before this change will report `integrity_ok: false` under the new scheme — this is expected, not corruption. Re-save checkpoints you need to keep verifying.
- No encryption at rest. Default DB: `~/.atg/checkpoints.db` (`ATG_DB_PATH` to override).
- `work_id` max 256 chars; charset `[A-Za-z0-9._:/-]`.
- JSON fields capped ~512 KB.
- `mcp[cli]` is pinned to `>=1.0.0,<3.0.0`. The full test suite was run against `mcp==2.1.1`; do not widen this ceiling without re-running the suite against the new version first.

Full notes: [SECURITY.md](https://github.com/holeyfield33-art/ATG/blob/main/SECURITY.md).

## Config

| Env | Meaning |
|-----|---------|
| `ATG_DB_PATH` | SQLite path |
| `ATG_INTEGRITY_KEY` | Optional HMAC key |
| `ATG_ALLOW_REMOTE_HTTP` | Allow unauthenticated HTTP transport |

## Verify

```bash
pytest -q
python examples/agent_loop.py
```

## Honest limits

Single-user, local SQLite, advisory usage policy, no multi-tenant auth, no dashboards. Compose with Horos / Mneme via MCP; do not treat ATG as a platform.

Part of the Aletheia family.
