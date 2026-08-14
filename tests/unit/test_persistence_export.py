"""Deterministic CSV/JSONL export tests."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from collector.event_model import EventType, build_event, from_json
from collector.persistence import PersistenceRepository
from collector.persistence.export import (
    EVENT_CSV_HEADERS,
    default_export_dir,
    export_events_csv,
    export_events_jsonl,
    export_reconciliations_csv,
    export_reconciliations_jsonl,
    export_trades_csv,
    export_trades_jsonl,
)
from tests.unit.event_factories import (
    MONO,
    RECONCILIATION_ID,
    TRADE_ID,
    position_opened_payload,
    reconciliation_payload,
    tick_payload,
)


@pytest.fixture()
def repo(tmp_path: Path) -> PersistenceRepository:
    return PersistenceRepository(tmp_path / "collector.db")


def test_events_csv_header_and_rows(tmp_path: Path, repo: PersistenceRepository) -> None:
    with repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        repo.insert_event(event)
        result = export_events_csv(repo, directory=tmp_path)
        assert result.rows == 1
        assert result.path == tmp_path / "events.csv"
        with result.path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        assert rows[0] == list(EVENT_CSV_HEADERS)
        assert len(rows) == 2
        assert rows[1][0] == event.event_id
        assert json.loads(rows[1][11]) == event.to_dict()["payload"]


def test_trades_csv_and_jsonl(tmp_path: Path, repo: PersistenceRepository) -> None:
    with repo:
        opened = build_event(
            EventType.POSITION_OPENED,
            position_opened_payload(),
            trade_id=TRADE_ID,
            ts_monotonic=MONO,
        )
        repo.insert_event_with_derived(opened)

        csv_result = export_trades_csv(repo, directory=tmp_path)
        assert csv_result.rows == 1
        with csv_result.path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        assert rows[0][0] == "trade_id"
        assert rows[1][0] == TRADE_ID
        assert rows[1][5] == "BUY"

        jsonl_result = export_trades_jsonl(repo, directory=tmp_path)
        lines = jsonl_result.path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["trade_id"] == TRADE_ID


def test_reconciliations_csv_and_jsonl(tmp_path: Path, repo: PersistenceRepository) -> None:
    with repo:
        record = build_event(
            EventType.RECONCILIATION,
            reconciliation_payload(),
            ts_monotonic=MONO,
        )
        repo.insert_event_with_derived(record)

        csv_result = export_reconciliations_csv(repo, directory=tmp_path)
        assert csv_result.rows == 1
        assert csv_result.path == tmp_path / "reconciliations.csv"

        jsonl_result = export_reconciliations_jsonl(repo, directory=tmp_path)
        lines = jsonl_result.path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["reconciliation_id"] == RECONCILIATION_ID


def test_events_jsonl_roundtrips_through_event_model(
    tmp_path: Path, repo: PersistenceRepository
) -> None:
    with repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        repo.insert_event(event)
        result = export_events_jsonl(repo, directory=tmp_path)
        lines = result.path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert from_json(lines[0]) == event


def test_exports_are_deterministic(tmp_path: Path, repo: PersistenceRepository) -> None:
    with repo:
        events = [
            build_event(EventType.TICK_RECEIVED, tick_payload(bid=2000.0 + i), trade_id=TRADE_ID)
            for i in range(5)
        ]
        for event in events:
            repo.insert_event(event)
        first = export_events_jsonl(repo, directory=tmp_path).path.read_text(encoding="utf-8")
        second = export_events_jsonl(repo, directory=tmp_path).path.read_text(encoding="utf-8")
        assert first == second


def test_default_export_dir_follows_settings(
    tmp_path: Path, repo: PersistenceRepository, monkeypatch: object
) -> None:
    monkeypatch.setenv("ABC_BOT_DATA_DIR", str(tmp_path))  # type: ignore[union-attr]
    assert default_export_dir() == tmp_path / "exports"
    with repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        repo.insert_event(event)
        result = export_events_csv(repo)
        assert result.path == tmp_path / "exports" / "events.csv"
        assert result.path.exists()
