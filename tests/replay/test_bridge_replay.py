"""Deterministic replay of the synthetic raw-bridge fixture.

The fixture contains ONLY synthetic data (fictional symbols, prices,
and broker ids). Replay drives the production ingestion path and
asserts deterministic counts and persisted event types.
"""

from __future__ import annotations

from collector.adapters.replay import replay_source
from collector.persistence import PersistenceRepository
from collector.settings import PROJECT_ROOT

FIXTURE = PROJECT_ROOT / "tests" / "replay" / "fixtures" / "bridge_raw_mixed.jsonl"


def test_replay_deterministic_counts(tmp_path) -> None:
    result = replay_source(FIXTURE, tmp_path / "replay.db")

    assert result.stats.lines_read == 8
    assert result.stats.events_valid == 4
    assert result.stats.events_persisted == 4
    assert result.stats.events_identity_pending == 1
    assert result.stats.internal_event_count == 3
    assert result.stats.unknown_event_count == 0
    assert result.stats.parse_errors == 0
    assert result.stats.persistence_errors == 0
    assert result.stats.events_invalid == 1

    assert result.persisted_event_types == ("TICK_RECEIVED", "TICK_RECEIVED", "ERROR", "TIMEOUT")
    assert result.persisted_count == 4
    assert result.duplicate_count == 0


def test_replay_symbols_preserved_no_remap(tmp_path) -> None:
    replay_source(FIXTURE, tmp_path / "replay.db")
    with PersistenceRepository(tmp_path / "replay.db") as repo:
        ticks = [
            e.payload["symbol"]
            for e in repo.query_events(limit=100)
            if e.event_type.value == "TICK_RECEIVED"
        ]
    assert ticks == ["XAUUSDc", "XAUUSD"]


def test_replay_final_cursor_marks_end_of_file(tmp_path) -> None:
    result = replay_source(FIXTURE, tmp_path / "replay.db")
    assert result.final_cursor is not None
    assert result.final_cursor.byte_offset == FIXTURE.stat().st_size
