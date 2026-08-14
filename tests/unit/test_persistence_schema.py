"""Persistence schema, WAL mode, migration, and append-only trigger tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from collector.event_model import EventType, build_event
from collector.persistence import PersistenceRepository
from collector.persistence.errors import PersistenceError
from collector.persistence.migrations import applied_versions, apply_migrations
from tests.unit.event_factories import TRADE_ID, tick_payload

TABLES = {
    "events",
    "trades",
    "orders",
    "positions",
    "market_snapshots",
    "reconciliation_events",
    "invalid_trades",
    "schema_migrations",
}


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def test_open_creates_db_with_wal_and_fk(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    with PersistenceRepository(db) as repo:
        assert repo.db_path == db
        journal = repo.connection.execute("PRAGMA journal_mode").fetchone()
        assert journal is not None and journal[0] == "wal"
        fk = repo.connection.execute("PRAGMA foreign_keys").fetchone()
        assert fk is not None and fk[0] == 1
        synchronous = repo.connection.execute("PRAGMA synchronous").fetchone()
        assert synchronous is not None and synchronous[0] == 2
        busy = repo.connection.execute("PRAGMA busy_timeout").fetchone()
        assert busy is not None and busy[0] == 5000
        assert _tables(repo.connection) == TABLES


def test_reopen_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    with PersistenceRepository(db) as repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        repo.insert_event(event)
    with PersistenceRepository(db) as repo:
        assert repo.count_events() == 1
        assert repo.get_event(event.event_id) == event


def test_migration_is_recorded_exactly_once(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    with PersistenceRepository(db) as repo:
        rows = repo.connection.execute("SELECT * FROM schema_migrations").fetchall()
        assert len(rows) == 1
        assert rows[0]["version"] == 1
        assert rows[0]["name"] == "initial_schema"
        assert rows[0]["applied_at"] is not None
    with PersistenceRepository(db) as repo:
        assert len(repo.connection.execute("SELECT * FROM schema_migrations").fetchall()) == 1


def test_apply_migrations_returns_only_newly_applied(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    fresh = sqlite3.connect(str(db))
    fresh.row_factory = sqlite3.Row
    try:
        first = apply_migrations(fresh)
        assert first == (1,)
        second = apply_migrations(fresh)
        assert second == ()
        assert applied_versions(fresh) == {1}
    finally:
        fresh.close()
    with PersistenceRepository(db) as repo:
        assert applied_versions(repo.connection) == {1}


def test_events_table_is_append_only(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    with PersistenceRepository(db) as repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        repo.insert_event(event)
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute(
                "UPDATE events SET severity = 'WARN' WHERE event_id = ?", (event.event_id,)
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("DELETE FROM events WHERE event_id = ?", (event.event_id,))


def test_closed_repository_raises_clear_error(tmp_path: Path) -> None:
    repo = PersistenceRepository(tmp_path / "collector.db")
    with pytest.raises(PersistenceError, match="not open"):
        _ = repo.connection
    with pytest.raises(PersistenceError, match="not open"):
        repo.insert_event(build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID))


def test_open_twice_raises(tmp_path: Path) -> None:
    repo = PersistenceRepository(tmp_path / "collector.db")
    repo.open()
    try:
        with pytest.raises(PersistenceError, match="already open"):
            repo.open()
    finally:
        repo.close()
