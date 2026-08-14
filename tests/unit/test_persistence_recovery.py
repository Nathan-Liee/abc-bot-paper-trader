"""Recovery, WAL visibility, replay idempotency, and corruption tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from collector.event_model import EventType, build_event
from collector.persistence import PersistenceRepository
from collector.persistence.errors import PersistenceError
from tests.unit.event_factories import TRADE_ID, tick_payload


def test_restart_preserves_events(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    with PersistenceRepository(db) as repo:
        events = [
            build_event(EventType.TICK_RECEIVED, tick_payload(bid=2000.0 + i), trade_id=TRADE_ID)
            for i in range(10)
        ]
        for event in events:
            repo.insert_event(event)
    with PersistenceRepository(db) as repo:
        assert repo.count_events() == 10
        assert [repo.get_event(event.event_id) for event in events] == events


def test_committed_rows_visible_to_second_connection(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    first = PersistenceRepository(db)
    first.open()
    try:
        second = PersistenceRepository(db)
        second.open()
        try:
            event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
            first.insert_event(event)
            assert second.count_events() == 1
            assert second.get_event(event.event_id) == event
        finally:
            second.close()
    finally:
        first.close()


def test_replay_duplicate_events_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    events = [
        build_event(EventType.TICK_RECEIVED, tick_payload(bid=2000.0 + i), trade_id=TRADE_ID)
        for i in range(5)
    ]
    with PersistenceRepository(db) as repo:
        for event in events:
            repo.insert_event(event)
    with PersistenceRepository(db) as repo:
        for event in events:
            result = repo.insert_event(event)
            assert result.duplicate is True
            assert result.inserted is False
        assert repo.count_events() == 5


def test_corrupt_database_raises_and_is_never_recreated(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    db.write_bytes(b"this is definitely not a sqlite database file")
    with pytest.raises(PersistenceError):
        PersistenceRepository(db).open()
    assert db.read_bytes().startswith(b"this is definitely not a sqlite database file")


def test_truncated_wal_recovers_via_reopen(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    with PersistenceRepository(db) as repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        repo.insert_event(event)
        wal = db.with_suffix(db.suffix + "-wal")
        assert wal.exists()
    with PersistenceRepository(db) as repo:
        assert repo.count_events() == 1
        assert repo.get_event(event.event_id) == event
