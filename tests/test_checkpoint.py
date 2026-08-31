"""Checkpoint store: concurrent saves, supersede, mark_done, missing, limits, HMAC."""

import concurrent.futures
import tempfile
from pathlib import Path

import pytest

from atg.checkpoint import MAX_JSON_BYTES, CheckpointStore


@pytest.fixture
def store(tmp_path: Path) -> CheckpointStore:
    return CheckpointStore(db_path=tmp_path / "t.db", integrity_key="test-secret")


def test_save_and_load(store: CheckpointStore):
    store.save("w1", {"step": 1}, platform="openai")
    loaded = store.load("w1")
    assert loaded is not None
    assert loaded["data"]["step"] == 1
    assert loaded["status"] == "in_progress"
    assert loaded["integrity_ok"] is True


def test_load_missing(store: CheckpointStore):
    assert store.load("does-not-exist") is None


def test_supersede_keeps_latest(store: CheckpointStore):
    store.save("w1", {"step": 1})
    store.save("w1", {"step": 2})
    loaded = store.load("w1")
    assert loaded["data"]["step"] == 2


def test_mark_done(store: CheckpointStore):
    store.save("w1", {"step": 1})
    assert store.mark_done("w1") is True
    assert store.load("w1") is None
    assert store.mark_done("w1") is False


def test_list_incomplete(store: CheckpointStore):
    store.save("a", {"x": 1}, platform="openai")
    store.save("b", {"x": 2}, platform="anthropic")
    store.mark_done("a")
    items = store.list_incomplete()
    assert len(items) == 1
    assert items[0]["work_id"] == "b"


def test_size_limit(store: CheckpointStore):
    huge = {"blob": "x" * (MAX_JSON_BYTES + 10)}
    with pytest.raises(ValueError, match="exceeds max size"):
        store.save("w1", huge)


def test_missing_work_id(store: CheckpointStore):
    with pytest.raises(ValueError):
        store.save("", {"a": 1})


def test_concurrent_saves(tmp_path: Path):
    db = tmp_path / "c.db"

    def worker(i: int) -> None:
        s = CheckpointStore(db_path=db)
        s.save("shared", {"n": i}, platform="openai")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(worker, range(20)))

    s = CheckpointStore(db_path=db)
    loaded = s.load("shared")
    assert loaded is not None
    assert "n" in loaded["data"]


def test_integrity_detects_tamper(tmp_path: Path):
    db = tmp_path / "i.db"
    s = CheckpointStore(db_path=db, integrity_key="secret")
    s.save("w1", {"ok": True})
    # tamper directly
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute("UPDATE checkpoints SET data = ? WHERE work_id = ?", ('{"ok": false}', "w1"))
    conn.commit()
    conn.close()

    loaded = s.load("w1")
    assert loaded is not None
    assert loaded["integrity_ok"] is False


def test_env_db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    path = tmp_path / "env.db"
    monkeypatch.setenv("ATG_DB_PATH", str(path))
    s = CheckpointStore()
    assert s.db_path == path
    s.save("w", {"a": 1})
    assert path.exists()
