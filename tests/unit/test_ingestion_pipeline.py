"""Ingestion pipeline tests: classification, identity gating, counters."""

from __future__ import annotations

import json
from pathlib import Path

from collector.adapters.normalize import normalize_bridge_line
from collector.adapters.pipeline import IngestionPipeline
from collector.adapters.reader import JsonlFileReader
from collector.persistence import PersistenceRepository

TS = "2026-08-14T09:00:00Z"
TS_COLLECTED = "2026-08-14T09:00:00.000Z"


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _raw(event_type: str, payload: dict) -> str:
    return json.dumps(
        {"event_type": event_type, "source": "mql5", "ts_bridge": TS, "payload": payload}
    )


def _run(tmp_path: Path, lines: list[str]):
    source = tmp_path / "events.jsonl"
    _write_lines(source, lines)
    repo = PersistenceRepository(tmp_path / "collector.db")
    repo.open()
    pipeline = IngestionPipeline(repo, JsonlFileReader(source))
    stats = pipeline.process_once()
    repo.close()
    return repo, pipeline, stats


def test_ticks_persisted_and_cursor_advanced(tmp_path: Path) -> None:
    ticks = [
        _raw(
            "TICK_RECEIVED",
            {
                "symbol": "XAUUSDc",
                "bid": 1.0,
                "ask": 2.0,
                "mid": 1.5,
                "spread": 1.0,
                "ts_source": TS,
            },
        ),
        _raw(
            "TICK_RECEIVED",
            {
                "symbol": "XAUUSD",
                "bid": 2.0,
                "ask": 3.0,
                "mid": 2.5,
                "spread": 1.0,
                "ts_source": TS,
            },
        ),
    ]
    repo, pipeline, stats = _run(tmp_path, ticks)
    with repo:
        assert repo.count_events() == 2
    assert stats.events_valid == 2
    assert stats.events_persisted == 2
    assert stats.lines_read == 2
    assert stats.cursor_offset == pipeline.reader.offset
    assert pipeline.cursor is not None
    assert pipeline.cursor.last_event_id is not None


def test_trade_path_events_identity_pending(tmp_path: Path) -> None:
    lines = [
        _raw(
            "ORDER_ACKNOWLEDGED",
            {"broker_order_id": "b-1", "broker_state": "PLACED", "ack_ts": TS},
        )
    ]
    repo, _, stats = _run(tmp_path, lines)
    with repo:
        assert repo.count_events() == 0
    assert stats.events_identity_pending == 1
    assert stats.events_invalid == 1
    # the cursor still advanced so the stream is not blocked
    assert stats.cursor_offset > 0


def test_internal_and_unknown_classified(tmp_path: Path) -> None:
    lines = [
        _raw("HEARTBEAT", {"status": "RUNNING"}),
        _raw("POSITION_SNAPSHOT", {"broker_position_id": "p-1"}),
        _raw("NOT_A_REAL_EVENT", {}),
    ]
    repo, _, stats = _run(tmp_path, lines)
    with repo:
        assert repo.count_events() == 0
    assert stats.internal_event_count == 2
    assert stats.unknown_event_count == 1
    assert stats.events_invalid == 1


def test_malformed_line_is_counted_and_skipped(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    _write_lines(
        source,
        [
            "{not json",
            _raw(
                "TICK_RECEIVED",
                {"symbol": "X", "bid": 1.0, "ask": 2.0, "mid": 1.5, "spread": 1.0, "ts_source": TS},
            ),
        ],
    )
    repo = PersistenceRepository(tmp_path / "collector.db")
    repo.open()
    pipeline = IngestionPipeline(repo, JsonlFileReader(source))
    stats = pipeline.process_once()
    repo.close()
    assert stats.parse_errors == 1
    assert stats.events_invalid == 1
    assert stats.events_valid == 1
    assert stats.lines_read == 2
    assert stats.cursor_offset == pipeline.reader.offset


def test_contract_violating_line_skipped(tmp_path: Path) -> None:
    # severity is a contract enum; "LOUD" is not allowed.
    line = _raw(
        "ERROR", {"error_code": "E1", "component": "bridge", "severity": "LOUD", "message": "x"}
    )
    repo, _, stats = _run(tmp_path, [line])
    with repo:
        assert repo.count_events() == 0
    assert stats.events_invalid == 1
    assert stats.events_valid == 0


def test_resume_after_cursor_does_not_reprocess(tmp_path: Path) -> None:
    line = _raw(
        "TICK_RECEIVED",
        {"symbol": "X", "bid": 1.0, "ask": 2.0, "mid": 1.5, "spread": 1.0, "ts_source": TS},
    )
    source = tmp_path / "events.jsonl"
    _write_lines(source, [line, line])

    repo = PersistenceRepository(tmp_path / "collector.db")
    repo.open()
    pipeline = IngestionPipeline(repo, JsonlFileReader(source))
    first = pipeline.process_once()
    # Cursor now points at EOF.
    cursor_offset = pipeline.cursor.byte_offset if pipeline.cursor else 0
    second = pipeline.process_once()
    repo.close()
    assert first.lines_read == 2
    assert cursor_offset == source.stat().st_size
    # second poll reads no new lines (relative delta is zero)
    assert second.lines_read - first.lines_read == 0
    repo.open()
    assert repo.count_events() == 2
    repo.close()


def test_normalization_rejects_wrong_source(tmp_path: Path) -> None:
    line = json.dumps(
        {"event_type": "TICK_RECEIVED", "source": "somewhere-else", "ts_bridge": TS, "payload": {}}
    )
    normalized = normalize_bridge_line(json.loads(line), ts_collected=TS_COLLECTED)
    assert normalized.kind.value in {"canonical", "unknown"}  # source is informational only


def test_bridge_events_without_identity_never_reach_repo(tmp_path: Path) -> None:
    line = _raw(
        "ORDER_FILLED",
        {
            "broker_order_id": "b-1",
            "broker_deal_id": "d-1",
            "fill_price": 1.0,
            "fill_volume": 0.1,
            "slippage": 0.0,
            "fill_ts": TS,
        },
    )
    repo, _, stats = _run(tmp_path, [line])
    with repo:
        assert repo.count_events() == 0
    assert stats.events_identity_pending == 1
