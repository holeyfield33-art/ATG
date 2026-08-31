"""ATG MCP server — usage awareness + durable checkpoints."""

from __future__ import annotations

import os
import sys
import warnings
from typing import Any

from mcp.server import MCPServer

from atg.checkpoint import CheckpointStore
from atg.usage import decide_action, parse_headers

mcp = MCPServer("atg")
store = CheckpointStore()


@mcp.tool()
def check_usage(
    platform: str = "openai",
    estimated_tokens: int = 0,
    remaining_tokens: int | None = None,
    remaining_requests: int | None = None,
    headers: dict[str, str] | None = None,
    low_threshold: float = 0.2,
) -> dict[str, Any]:
    """
    Pre-work / mid-work usage check.

    Preferred path: pass the raw provider response `headers` dict and the
    platform name; ATG will parse rate-limit fields. Alternatively pass
    remaining_tokens / remaining_requests explicitly (host-extracted).

    If neither headers nor remaining_* are provided, returns a neutral
    proceed signal so agents do not block.
    """
    parsed: dict[str, int | None] = {}
    if headers:
        parsed = parse_headers(platform, headers)
        if remaining_tokens is None:
            remaining_tokens = parsed.get("remaining_tokens")
        if remaining_requests is None:
            remaining_requests = parsed.get("remaining_requests")

    decision = decide_action(
        remaining_tokens=remaining_tokens,
        remaining_requests=remaining_requests,
        estimated_tokens=estimated_tokens,
        low_threshold=low_threshold,
    )
    decision["platform"] = platform
    if parsed:
        decision["parsed_limits"] = {
            k: parsed.get(k) for k in ("limit_tokens", "limit_requests")
        }
    return decision


@mcp.tool()
def save_checkpoint(
    work_id: str,
    data: dict[str, Any],
    platform: str | None = None,
    meta: dict[str, Any] | None = None,
    token_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Save a durable checkpoint for work_id.

    `meta` is a free-form bag — useful for Horos receipt_hash or Mneme memory keys.
    JSON fields are capped (~512 KB); store large blobs externally.
    """
    return store.save(
        work_id=work_id,
        data=data,
        platform=platform,
        meta=meta,
        token_snapshot=token_snapshot,
    )


@mcp.tool()
def load_checkpoint(work_id: str) -> dict[str, Any]:
    """Load the latest in-progress checkpoint for work_id."""
    result = store.load(work_id)
    if result is None:
        return {"status": "not_found", "work_id": work_id}
    return {"status": "ok", "checkpoint": result}


@mcp.tool()
def list_checkpoints(
    platform: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List incomplete work items (limit clamped to 1–500)."""
    try:
        limit_i = int(limit)
    except (TypeError, ValueError):
        limit_i = 50
    limit_i = max(1, min(limit_i, 500))
    items = store.list_incomplete(platform=platform, limit=limit_i)
    return {"count": len(items), "items": items, "limit": limit_i}


@mcp.tool()
def mark_done(work_id: str) -> dict[str, Any]:
    """Mark all in-progress checkpoints for work_id as done."""
    updated = store.mark_done(work_id)
    return {"work_id": work_id, "updated": updated}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Aletheia Token Guard MCP server")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "streamable-http"],
        help="MCP transport (default: stdio)",
    )
    parser.add_argument("--port", type=int, default=8765, help="Port for streamable-http")
    parser.add_argument(
        "--allow-remote-http",
        action="store_true",
        help="Override the local-only guard for streamable-http (INSECURE)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run()
        return

    # streamable-HTTP is unauthenticated — local-only by default
    allow = args.allow_remote_http or os.environ.get("ATG_ALLOW_REMOTE_HTTP") == "1"
    if not allow:
        msg = (
            "streamable-http transport is UNAUTHENTICATED and intended for local-only use. "
            "Refusing to bind without --allow-remote-http or ATG_ALLOW_REMOTE_HTTP=1. "
            "Prefer stdio for production hosts."
        )
        print(msg, file=sys.stderr)
        # Still allow bind to localhost only via explicit override path documentation
        warnings.warn(msg, stacklevel=1)
        # Enforce: require the flag
        raise SystemExit(2)

    print(
        "WARNING: streamable-http has no authentication. Bind only on trusted networks.",
        file=sys.stderr,
    )
    mcp.run(transport="streamable-http", port=args.port)


if __name__ == "__main__":
    main()
