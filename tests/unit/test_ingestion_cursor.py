"""Ingestion cursor persistence tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from collector.event_model import EventType, build_event
from collector.persistence import PersistenceRepository
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
