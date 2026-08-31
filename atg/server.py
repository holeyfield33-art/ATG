"""ATG MCP server — usage awareness + durable checkpoints."""

from __future__ import annotations

import json
from typing import Any

from mcp.server import MCPServer

from atg.checkpoint import CheckpointStore
from atg.usage import decide_action

mcp = MCPServer("atg")
store = CheckpointStore()


@mcp.tool()
def check_usage(
    platform: str = "openai",
    estimated_tokens: int = 0,
    remaining_tokens: int | None = None,
    remaining_requests: int | None = None,
) -> dict[str, Any]:
    """
    Pre-work / mid-work usage check.

    Prefer supplying remaining_* from the latest provider response headers.
    If omitted, returns a neutral proceed signal so agents do not block.
    """
    decision = decide_action(
        remaining_tokens=remaining_tokens,
        remaining_requests=remaining_requests,
        estimated_tokens=estimated_tokens,
    )
    decision["platform"] = platform
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
    """List incomplete work items."""
    items = store.list_incomplete(platform=platform, limit=limit)
    return {"count": len(items), "items": items}


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
        help="MCP transport",
    )
    parser.add_argument("--port", type=int, default=8765, help="Port for streamable-http")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport="streamable-http", port=args.port)


if __name__ == "__main__":
    main()
