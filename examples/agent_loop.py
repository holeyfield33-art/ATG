"""
Minimal agent loop using ATG tools in-process (no MCP host required).

Demonstrates:
  (a) extract rate-limit headers from a provider-like response
  (b) call check_usage (via decide_action + parse_headers)
  (c) checkpoint on pause / budget_low
  (d) resume from checkpoint
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from atg.checkpoint import CheckpointStore
from atg.usage import decide_action, parse_headers


def fake_provider_call(step: int) -> dict:
    """Simulate a provider response that includes rate-limit headers."""
    # Drain tokens as steps progress
    remaining = max(0, 30_000 - step * 8_000)
    return {
        "content": f"result-for-step-{step}",
        "headers": {
            "x-ratelimit-remaining-tokens": str(remaining),
            "x-ratelimit-remaining-requests": "20",
            "x-ratelimit-limit-tokens": "90000",
        },
    }


def run_work(work_id: str, store: CheckpointStore, start_step: int = 0, max_steps: int = 10) -> str:
    step = start_step
    results: list[str] = []

    # Resume prior data if any
    existing = store.load(work_id)
    if existing:
        results = list(existing["data"].get("results", []))
        step = int(existing["data"].get("next_step", start_step))
        print(f"resumed work_id={work_id} at step={step}")

    while step < max_steps:
        estimated = 5_000
        # (a) provider call → headers
        resp = fake_provider_call(step)
        headers = resp["headers"]

        # (b) check_usage path
        parsed = parse_headers("openai", headers)
        decision = decide_action(
            remaining_tokens=parsed["remaining_tokens"],
            remaining_requests=parsed["remaining_requests"],
            estimated_tokens=estimated,
        )
        print(f"step={step} action={decision['action']} reason={decision['reason']} remaining={parsed['remaining_tokens']}")

        if decision["action"] == "pause":
            # (c) checkpoint on pause
            store.save(
                work_id,
                {"results": results, "next_step": step},
                platform="openai",
                token_snapshot=decision,
                meta={"note": "paused by ATG policy"},
            )
            print("paused — checkpoint saved")
            return "paused"

        if decision["action"] == "budget_low":
            # still work, but checkpoint proactively
            store.save(
                work_id,
                {"results": results, "next_step": step},
                platform="openai",
                token_snapshot=decision,
                meta={"note": "budget_low proactive checkpoint"},
            )

        results.append(resp["content"])
        step += 1

        # periodic checkpoint
        if step % 2 == 0:
            store.save(
                work_id,
                {"results": results, "next_step": step},
                platform="openai",
                token_snapshot=decision,
            )

    store.mark_done(work_id)
    print("completed")
    return "completed"


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = CheckpointStore(db_path=Path(td) / "demo.db")
        work_id = "demo-job-1"

        status = run_work(work_id, store)
        assert status in ("paused", "completed")

        if status == "paused":
            # (d) resume
            print("--- resuming ---")
            # bump remaining tokens for the second pass by using a fresh store path
            # and replaying from checkpoint; fake_provider_call still drains,
            # so we only run remaining steps if budget allows.
            status2 = run_work(work_id, store)
            print("final status:", status2)


if __name__ == "__main__":
    main()
