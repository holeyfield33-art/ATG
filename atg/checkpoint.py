"""Minimal SQLite-backed checkpoint store."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")

DEFAULT_DB = Path.home() / ".atg" / "checkpoints.db"
MAX_JSON_BYTES = 512_000  # ~512 KB per JSON field
DEFAULT_PRUNE_KEEP = 20  # keep last N versions per work_id (including superseded)
WORK_ID_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,256}$")
DEFAULT_CONNECT_RETRIES = 3
DEFAULT_CONNECT_RETRY_BACKOFF = 0.05  # seconds; doubles each retry


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_db_path(db_path: Path | str | None) -> Path:
    if db_path is not None:
        return Path(db_path)
    env = os.environ.get("ATG_DB_PATH")
    if env:
        return Path(env)
    return DEFAULT_DB


def _json_dumps_limited(obj: Any, field_name: str) -> str:
    try:
        raw = json.dumps(obj, separators=(",", ":"))
    except TypeError as exc:
        raise ValueError(f"{field_name} contains a non-JSON-serializable value: {exc}") from exc
    if len(raw.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError(
            f"{field_name} exceeds max size of {MAX_JSON_BYTES} bytes; "
            "store large blobs externally and pass a URI/handle instead"
        )
    return raw


class CheckpointStore:
    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        integrity_key: str | bytes | None = None,
        prune_keep: int = DEFAULT_PRUNE_KEEP,
        connect_retries: int = DEFAULT_CONNECT_RETRIES,
        connect_retry_backoff: float = DEFAULT_CONNECT_RETRY_BACKOFF,
    ) -> None:
        self.db_path = _resolve_db_path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.prune_keep = max(1, prune_keep)
        self._connect_retries = max(0, connect_retries)
        self._connect_retry_backoff = connect_retry_backoff
        key = integrity_key if integrity_key is not None else os.environ.get("ATG_INTEGRITY_KEY")
        self._integrity_key: bytes | None = (
            key.encode("utf-8") if isinstance(key, str) else key
        )
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Open a connection, retrying transient OperationalErrors (e.g. cold-start
        contention creating the db file/directory) with exponential backoff."""
        attempt = 0
        while True:
            try:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute("PRAGMA foreign_keys=ON")
                return conn
            except sqlite3.OperationalError:
                if attempt >= self._connect_retries:
                    raise
                time.sleep(self._connect_retry_backoff * (2**attempt))
                attempt += 1

    def _run_with_retry(self, body: Callable[[sqlite3.Connection], T]) -> T:
        """Run body(conn) under a fresh connection, retrying the whole
        connect+write+commit sequence on a transient OperationalError with
        exponential backoff.

        PRAGMA busy_timeout already covers most lock contention during the
        write itself, but if a write is still blocked when that timeout
        expires, sqlite3 raises OperationalError from execute()/commit() —
        not from connect(). _connect()'s own retry loop only covers errors
        raised by connect() and the PRAGMA setup, so without this wrapper
        that error would propagate unhandled out of save()/mark_done().
        """
        attempt = 0
        while True:
            try:
                with self._connect() as conn:
                    return body(conn)
            except sqlite3.OperationalError:
                if attempt >= self._connect_retries:
                    raise
                time.sleep(self._connect_retry_backoff * (2**attempt))
                attempt += 1

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
                    integrity TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # migrate older DBs that lack integrity column
            cols = {r[1] for r in conn.execute("PRAGMA table_info(checkpoints)").fetchall()}
            if "integrity" not in cols:
                conn.execute("ALTER TABLE checkpoints ADD COLUMN integrity TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_work_id ON checkpoints(work_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_status ON checkpoints(status)"
            )
            conn.commit()

    @staticmethod
    def _sign_message(
        work_id: str,
        platform: str | None,
        status: str,
        created_at: str,
        data_json: str,
        meta_json: str | None,
        token_json: str | None,
    ) -> bytes:
        # Each field is length-prefixed (and tagged N for None) so no combination
        # of field contents can shift a byte across a field boundary.
        parts: list[bytes] = []
        for value in (work_id, platform, status, created_at, data_json, meta_json, token_json):
            if value is None:
                parts.append(b"N")
            else:
                encoded = value.encode("utf-8")
                parts.append(b"S" + str(len(encoded)).encode("ascii") + b":" + encoded)
        return b"|".join(parts)

    def _sign(
        self,
        work_id: str,
        platform: str | None,
        status: str,
        created_at: str,
        data_json: str,
        meta_json: str | None,
        token_json: str | None,
    ) -> str | None:
        if not self._integrity_key:
            return None
        msg = self._sign_message(
            work_id, platform, status, created_at, data_json, meta_json, token_json
        )
        return hmac.new(self._integrity_key, msg, hashlib.sha256).hexdigest()

    def _verify_row(self, row: sqlite3.Row) -> bool | None:
        """Return True/False if key configured, else None (not checked)."""
        if not self._integrity_key:
            return None
        expected = row["integrity"]
        if not expected:
            return False
        msg = self._sign_message(
            row["work_id"],
            row["platform"],
            row["status"],
            row["created_at"],
            row["data"],
            row["meta"],
            row["token_snapshot"],
        )
        actual = hmac.new(self._integrity_key, msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(actual, expected)

    def save(
        self,
        work_id: str,
        data: dict[str, Any],
        platform: str | None = None,
        meta: dict[str, Any] | None = None,
        token_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not work_id or not str(work_id).strip():
            raise ValueError("work_id is required")
        if len(work_id) > 256:
            raise ValueError(f"work_id must be 1-256 characters (got {len(work_id)})")
        if not WORK_ID_RE.fullmatch(work_id):
            raise ValueError(
                "work_id contains disallowed characters; only [A-Za-z0-9._:/-] are permitted"
            )
        if data is None:
            raise ValueError("data is required")

        now = _utc_now()
        data_json = _json_dumps_limited(data, "data")
        meta_json = _json_dumps_limited(meta, "meta") if meta is not None else None
        token_json = (
            _json_dumps_limited(token_snapshot, "token_snapshot")
            if token_snapshot is not None
            else None
        )
        integrity = self._sign(
            work_id, platform, "in_progress", now, data_json, meta_json, token_json
        )

        def _do(conn: sqlite3.Connection) -> int:
            conn.execute(
                "UPDATE checkpoints SET status = 'superseded', updated_at = ? "
                "WHERE work_id = ? AND status = 'in_progress'",
                (now, work_id),
            )
            cur = conn.execute(
                """
                INSERT INTO checkpoints
                    (work_id, platform, status, data, meta, token_snapshot, integrity, created_at, updated_at)
                VALUES (?, ?, 'in_progress', ?, ?, ?, ?, ?, ?)
                """,
                (
                    work_id,
                    platform,
                    data_json,
                    meta_json,
                    token_json,
                    integrity,
                    now,
                    now,
                ),
            )
            new_id = cur.lastrowid
            self._prune(conn, work_id)
            conn.commit()
            return new_id

        checkpoint_id = self._run_with_retry(_do)

        return {
            "id": checkpoint_id,
            "work_id": work_id,
            "platform": platform,
            "status": "in_progress",
            "created_at": now,
            "integrity": bool(integrity),
        }

    def _prune(self, conn: sqlite3.Connection, work_id: str) -> None:
        """Keep only the newest prune_keep rows for this work_id."""
        rows = conn.execute(
            "SELECT id FROM checkpoints WHERE work_id = ? ORDER BY id DESC",
            (work_id,),
        ).fetchall()
        if len(rows) <= self.prune_keep:
            return
        drop_ids = [r["id"] for r in rows[self.prune_keep :]]
        conn.executemany("DELETE FROM checkpoints WHERE id = ?", [(i,) for i in drop_ids])

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

        verified = self._verify_row(row)
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
            "integrity_ok": verified,
        }

    def list_incomplete(
        self, platform: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
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

        def _do(conn: sqlite3.Connection) -> bool:
            cur = conn.execute(
                "UPDATE checkpoints SET status = 'done', updated_at = ? "
                "WHERE work_id = ? AND status = 'in_progress'",
                (now, work_id),
            )
            conn.commit()
            return cur.rowcount > 0

        return self._run_with_retry(_do)
