"""Minimal SQLite-backed checkpoint store."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path.home() / ".atg" / "checkpoints.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CheckpointStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    work_id TEXT NOT NULL,
                    platform TEXT,
                    status TEXT NOT NULL DEFAULT 'in_progress',
                    data TEXT NOT NULL,
                    meta TEXT,
                    token_snapshot TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_work_id ON checkpoints(work_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_status ON checkpoints(status)"
            )
            conn.commit()

    def save(
        self,
        work_id: str,
        data: dict[str, Any],
        platform: str | None = None,
        meta: dict[str, Any] | None = None,
        token_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            # Keep only one active row per work_id for simplicity (latest wins)
            conn.execute(
                "UPDATE checkpoints SET status = 'superseded', updated_at = ? WHERE work_id = ? AND status = 'in_progress'",
                (now, work_id),
            )
            cur = conn.execute(
                """
                INSERT INTO checkpoints
                    (work_id, platform, status, data, meta, token_snapshot, created_at, updated_at)
                VALUES (?, ?, 'in_progress', ?, ?, ?, ?, ?)
                """,
                (
                    work_id,
                    platform,
                    json.dumps(data),
                    json.dumps(meta) if meta is not None else None,
                    json.dumps(token_snapshot) if token_snapshot is not None else None,
                    now,
                    now,
                ),
            )
            conn.commit()
            checkpoint_id = cur.lastrowid

        return {
            "id": checkpoint_id,
            "work_id": work_id,
            "platform": platform,
            "status": "in_progress",
            "created_at": now,
        }

    def load(self, work_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM checkpoints
                WHERE work_id = ? AND status = 'in_progress'
                ORDER BY id DESC LIMIT 1
                """,
                (work_id,),
            ).fetchone()

        if not row:
            return None

        return {
            "id": row["id"],
            "work_id": row["work_id"],
            "platform": row["platform"],
            "status": row["status"],
            "data": json.loads(row["data"]),
            "meta": json.loads(row["meta"]) if row["meta"] else None,
            "token_snapshot": json.loads(row["token_snapshot"]) if row["token_snapshot"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_incomplete(self, platform: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = """
            SELECT work_id, platform, MAX(updated_at) AS last_updated, COUNT(*) AS versions
            FROM checkpoints
            WHERE status = 'in_progress'
        """
        params: list[Any] = []
        if platform:
            query += " AND platform = ?"
            params.append(platform)
        query += " GROUP BY work_id, platform ORDER BY last_updated DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            {
                "work_id": r["work_id"],
                "platform": r["platform"],
                "last_updated": r["last_updated"],
                "versions": r["versions"],
            }
            for r in rows
        ]

    def mark_done(self, work_id: str) -> bool:
        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE checkpoints SET status = 'done', updated_at = ? WHERE work_id = ? AND status = 'in_progress'",
                (now, work_id),
            )
            conn.commit()
            return cur.rowcount > 0
