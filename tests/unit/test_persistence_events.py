"""Event stream append, idempotency, query, and checksum tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from collector.event_model import EventType, build_event, compute_checksum
from collector.persistence import InsertResult, PersistenceRepository
from collector.persistence.errors import PersistenceError
from tests.unit.event_factories import (
    CORRELATION_ID,
    MONO,
    TRADE_ID,
    tick_payload,
    trigger_payload,
)


def _repo(tmp_path: Path) -> PersistenceRepository:
    return PersistenceRepository(tmp_path / "collector.db")


def test_insert_and_read_roundtrip(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        event = build_event(
            EventType.TICK_RECEIVED,
            tick_payload(),
            trade_id=TRADE_ID,
            ts_monotonic=MONO,
        )
        result = repo.insert_event(event)
        assert result.inserted is True
        assert result.duplicate is False
        assert result.identical is True
        assert repo.count_events() == 1
        assert repo.get_event(event.event_id) == event


def test_append_audit_event_is_alias(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        result = repo.append_audit_event(event)
        assert result.inserted is True
        assert repo.count_events() == 1


def test_replay_same_event_is_idempotent(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        first = repo.insert_event(event)
        second = repo.insert_event(event)
        assert first.inserted is True
        assert second.inserted is False
        assert second.duplicate is True
        assert second.identical is True
        assert repo.count_events() == 1
        assert repo.get_event(event.event_id) == event


def test_duplicate_event_id_with_conflicting_checksum_is_rejected(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        repo.insert_event(event)
        conflicting = replace(event, ts_monotonic=event.ts_monotonic + 1)
        conflicting = replace(conflicting, checksum=compute_checksum(conflicting.to_dict()))
        with pytest.raises(PersistenceError, match="conflicting checksum"):
            repo.insert_event(conflicting)
        assert repo.count_events() == 1
        assert repo.get_event(event.event_id) == event


def test_tampered_checksum_event_is_refused(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        tampered = replace(event, checksum="sha256:" + "0" * 64)
        with pytest.raises(PersistenceError, match="checksum mismatch"):
            repo.insert_event(tampered)
        assert repo.count_events() == 0


def test_query_events_by_trade_id_and_type(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        tick = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        trigger = build_event(
            EventType.TRIGGER_DETECTED,
            trigger_payload(),
            correlation_id=CORRELATION_ID,
            trade_id=TRADE_ID,
        )
        repo.insert_event(tick)
        repo.insert_event(trigger)

        by_trade = repo.query_events(trade_id=TRADE_ID)
        assert {e.event_id for e in by_trade} == {tick.event_id, trigger.event_id}

        by_type = repo.query_events(event_type=EventType.TICK_RECEIVED)
        assert [e.event_id for e in by_type] == [tick.event_id]

        by_correlation = repo.query_events(correlation_id=CORRELATION_ID)
        assert [e.event_id for e in by_correlation] == [trigger.event_id]

        by_type_str = repo.query_events(event_type="TICK_RECEIVED")
        assert [e.event_id for e in by_type_str] == [tick.event_id]


def test_query_events_time_range_and_limit(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        repo.insert_event(event)

        future = repo.query_events(ts_start="2999-01-01T00:00:00.000Z")
        assert future == []

        past = repo.query_events(ts_end="2000-01-01T00:00:00.000Z")
        assert past == []

        all_events = repo.query_events()
        assert all_events == [event]

        none = repo.query_events(limit=0)
        assert none == []


def test_query_events_orders_deterministically(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        events = [
            build_event(EventType.TICK_RECEIVED, tick_payload(bid=2000.0), trade_id=TRADE_ID)
            for _ in range(5)
        ]
        for event in events:
            repo.insert_event(event)
        first = repo.query_events()
        second = repo.query_events()
        assert [e.event_id for e in first] == [e.event_id for e in second]
        assert len(first) == 5


def test_get_event_missing_returns_none(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        assert repo.get_event("missing") is None


def test_insert_result_is_frozen_dataclass() -> None:
    result = InsertResult(inserted=True, duplicate=False, identical=True)
    assert result.inserted is True
    assert result.duplicate is False
