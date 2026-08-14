"""Deterministic replay of the synthetic raw-bridge fixture.

The fixture contains ONLY synthetic data (fictional symbols, prices,
and broker ids). Replay drives the production ingestion path and
asserts deterministic counts and persisted event types.
"""

from __future__ import annotations

from collector.adapters.pipeline import IngestionPipeline
from collector.adapters.reader import JsonlFileReader
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


def test_repeated_replay_yields_no_duplicate_events(tmp_path) -> None:
    db_path = tmp_path / "replay.db"
    first = replay_source(FIXTURE, db_path)
    with PersistenceRepository(db_path) as repo:
        cursor = repo.get_ingestion_cursor(str(FIXTURE))
        assert cursor is not None
        assert cursor.byte_offset == FIXTURE.stat().st_size
        pipeline = IngestionPipeline(
            repo, JsonlFileReader(FIXTURE, start_offset=cursor.byte_offset)
        )
        stats = pipeline.process_once()
        assert stats.lines_read == 0
        assert stats.events_parsed == 0
        assert repo.count_events() == first.persisted_count == 4
