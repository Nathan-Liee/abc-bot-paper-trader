"""Tick semantics tests: append-only, duplicate ts_event allowed, no dedup."""

from __future__ import annotations

import pytest

from collector.event_model import (
    ContractValidationError,
    build_event,
    validate_sequence,
)
from shared.contracts.types import EventType
from tests.unit.event_factories import TS, tick_payload


def _tick(ts_source: str = TS, monotonic: int = 1000, **overrides: object):
    return build_event(
        EventType.TICK_RECEIVED,
        tick_payload(ts_source=ts_source, **overrides),
        ts_event=ts_source,
        ts_collected="2026-08-14T09:00:00.000Z",
        ts_monotonic=monotonic,
    )


def test_duplicate_ts_event_ticks_are_accepted() -> None:
    first = _tick()
    duplicate = _tick()
    assert first.ts_event == duplicate.ts_event
    validate_sequence([first, duplicate])


def test_duplicate_symbol_and_ts_event_are_accepted() -> None:
    validate_sequence(
        [
            _tick(symbol="XAUUSD"),
            _tick(symbol="XAUUSD"),
        ]
    )


def test_tick_without_bid_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="bid"):
        _tick(bid=None)  # type: ignore[arg-type]


def test_tick_id_is_optional() -> None:
    validate_sequence([_tick()])
    validate_sequence([_tick(tick_id="tick-abc")])


def test_tick_sequence_is_append_only_within_stream() -> None:
    with_tick_after_trade = [
        _tick(monotonic=1),
        _tick(monotonic=2),
        _tick(monotonic=3),
    ]
    validate_sequence(with_tick_after_trade)


def test_regression_no_ts_event_checksum_drift() -> None:
    event = _tick()
    assert event.verify_checksum()
