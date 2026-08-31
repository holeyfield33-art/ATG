# Security notes — Aletheia Token Guard (ATG)

ATG is a **single-user, local sidecar**. It is not multi-tenant and does not encrypt data at rest.

## Transport

| Mode | Auth | Recommendation |
|------|------|----------------|
| **stdio** (default) | Host process boundary | Prefer for real MCP hosts |
| **streamable-http** | **None** | Local development only |

HTTP mode refuses to start unless you pass `--allow-remote-http` or set `ATG_ALLOW_REMOTE_HTTP=1`. When allowed, bind only on trusted networks. Prefer stdio for production hosts.

## Checkpoint integrity

Optional HMAC-SHA256 via `ATG_INTEGRITY_KEY` (or `integrity_key=` constructor arg).

When configured, the MAC covers:

- `work_id`
- `status`
- `created_at`
- `data` (JSON)
- `meta` (JSON)
- `token_snapshot` (JSON)

`load_checkpoint` returns `integrity_ok: true|false|null` (`null` = key not configured).

Integrity is **detection**, not confidentiality. Anyone with filesystem access to the SQLite file can still read checkpoint contents.

## Data at rest

- Default DB path: `~/.atg/checkpoints.db` (override with `ATG_DB_PATH`)
- No encryption at rest
- JSON fields capped at ~512 KB each
- `work_id` limited to 256 chars; charset `[A-Za-z0-9._:/-]`

Do not store long-lived secrets in checkpoint `data` / `meta`. Prefer external handles (URI, key id) and keep secrets in a proper secret store.

## Trust model for usage checks

`check_usage` is a pure function of the arguments the host/agent supplies (headers or `remaining_*`). ATG does **not** intercept provider HTTP traffic. A compromised or buggy agent can pass optimistic numbers and receive `proceed`. Treat the tool as advisory policy, not an enforcement gate in front of the provider API.

## Reporting

This is an early experimental project. Prefer opening a GitHub issue for security-relevant bugs. Do not file public issues that include live secrets or production checkpoint dumps.
