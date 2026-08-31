# Aletheia Token Guard (ATG)

**Slim MCP server for token/usage awareness and durable work checkpoints.**

Plugin-ready companion to [Horos](https://github.com/holeyfield33-art/Horos) (context router + signed receipts) and [Mneme](https://github.com/holeyfield33-art/Mneme-) (persistent memory).

---

## Why ATG?

Agents die mid-task when they hit rate limits, spend caps, or context budgets. ATG gives any MCP host a thin, reliable side-car that:

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
| `list_checkpoints` | List incomplete / recent work |
| `mark_done` | Mark a work item complete |

Optional meta fields on checkpoints can hold a Horos `receipt_hash` or Mneme memory key for later composition.

---

## Quick start

```bash
git clone https://github.com/holeyfield33-art/ATG.git
cd ATG
python -m venv .venv && source .venv/bin/activate   # or Windows equivalent
pip install -r requirements.txt

# Run over stdio (default for most MCP hosts)
python -m atg

# Or streamable HTTP
python -m atg --transport streamable-http --port 8765
```

Point your MCP host (Claude Code, Cursor, custom agent, etc.) at the server.

---

## Design principles

- **Side-car, not platform.** Compose with Horos and Mneme via MCP; do not re-implement them.
- **Headers first.** Prefer live rate-limit headers. Admin API usage is optional and only used when the key is present.
- **SQLite by default.** Single-file, zero ops for personal / consulting use.
- **Stable tool schemas.** Clear names so hosts can call them reliably.
- **Loose integration seams.** Checkpoint `meta` can reference Horos receipts or Mneme keys without tight coupling.

---

## Status

Early / vibe-coding. Core tools + SQLite checkpoint store. OpenAI + Anthropic header awareness planned first.

---

## License

MIT

---

Part of the Aletheia family — tools that make AI systems inspectable and trustworthy.
