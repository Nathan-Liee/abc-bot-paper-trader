"""Ingestion cursor persistence tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from collector.event_model import EventEnvelope, EventType, build_event, compute_checksum
from collector.persistence import PersistenceError, PersistenceRepository
from collector.persistence.cursor import IngestionCursor
from tests.unit.event_factories import CORRELATION_ID, TRADE_ID, tick_payload


@pytest.fixture
def repo(tmp_path: Path) -> PersistenceRepository:
    return PersistenceRepository(tmp_path / "collector.db")


def test_initial_cursor_is_none(repo: PersistenceRepository) -> None:
    with repo:
        assert repo.get_ingestion_cursor("data/raw/events.jsonl") is None


def test_save_and_read_cursor(repo: PersistenceRepository) -> None:
    with repo:
        cursor = IngestionCursor.of(
            "data/raw/events.jsonl",
            byte_offset=1024,
            line_number=42,
            last_event_id="3f2c9b1e-7d4a-4b8e-9c2f-0d1e2f3a4b5c",
        )
        repo.save_ingestion_cursor(cursor)
        loaded = repo.get_ingestion_cursor("data/raw/events.jsonl")
        assert loaded is not None
        assert loaded.source_path == cursor.source_path
        assert loaded.byte_offset == 1024
        assert loaded.line_number == 42
        assert loaded.last_event_id == cursor.last_event_id


def test_cursor_upsert_overwrites(repo: PersistenceRepository) -> None:
    with repo:
        repo.save_ingestion_cursor(IngestionCursor.of("src", byte_offset=10, line_number=1))
        repo.save_ingestion_cursor(IngestionCursor.of("src", byte_offset=2048, line_number=5))
        loaded = repo.get_ingestion_cursor("src")
        assert loaded is not None
        assert loaded.byte_offset == 2048
        assert loaded.line_number == 5


def test_insert_event_with_cursor_commits_together(repo: PersistenceRepository) -> None:
    with repo:
        event = build_event(
            EventType.TICK_RECEIVED,
            tick_payload(),
            correlation_id=CORRELATION_ID,
            trade_id=TRADE_ID,
        )
        cursor = IngestionCursor.of("src", byte_offset=500, last_event_id=event.event_id)
        result = repo.insert_event_with_cursor(event, cursor)
        assert result.inserted is True
        assert repo.count_events() == 1
        loaded = repo.get_ingestion_cursor("src")
        assert loaded is not None
        assert loaded.byte_offset == 500
        assert loaded.last_event_id == event.event_id


def test_identical_duplicate_advances_cursor(repo: PersistenceRepository) -> None:
    with repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload())
        first = repo.insert_event_with_cursor(event, IngestionCursor.of("src", byte_offset=100))
        assert first.inserted is True
        second = repo.insert_event_with_cursor(event, IngestionCursor.of("src", byte_offset=200))
        assert second.inserted is False
        assert second.duplicate is True
        assert second.identical is True
        assert repo.count_events() == 1
        loaded = repo.get_ingestion_cursor("src")
        assert loaded is not None
        assert loaded.byte_offset == 200


def test_cursor_update_without_event(repo: PersistenceRepository) -> None:
    with repo:
        repo.save_ingestion_cursor(IngestionCursor.of("src", byte_offset=100))
        loaded = repo.get_ingestion_cursor("src")
        assert loaded is not None
        assert loaded.byte_offset == 100
        assert loaded.last_event_id is None


def test_persistence_failure_does_not_advance_cursor(repo: PersistenceRepository) -> None:
    """A failed persist (conflicting duplicate event_id) leaves the
    cursor untouched: event insert and cursor update share one
    transaction, so both roll back together."""
    with repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload())
        repo.insert_event_with_cursor(
            event, IngestionCursor.of("src", byte_offset=100, last_event_id=event.event_id)
        )

        conflicting_data = event.to_dict()
        conflicting_data["payload"] = tick_payload(bid=2500.0, ask=2500.5)
        conflicting_data["checksum"] = compute_checksum(conflicting_data)
        conflicting = EventEnvelope.from_dict(conflicting_data)
        assert conflicting.event_id == event.event_id
        assert conflicting.checksum != event.checksum

        with pytest.raises(PersistenceError):
            repo.insert_event_with_cursor(conflicting, IngestionCursor.of("src", byte_offset=200))

        loaded = repo.get_ingestion_cursor("src")
        assert loaded is not None
        assert loaded.byte_offset == 100
        assert loaded.last_event_id == event.event_id
        assert repo.count_events() == 1
