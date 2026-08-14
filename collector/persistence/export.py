"""Deterministic exports of persisted data to CSV and JSONL.

Exports are read-only: they never mutate the database. Files are
written under ``data/exports`` (configurable via ``ABC_BOT_DATA_DIR``)
with deterministic ordering, so exports are stable and diff-able.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from collector.event_model.serialization import to_json
from collector.persistence.repository import PersistenceRepository

EVENT_CSV_HEADERS = (
    "event_id",
    "event_type",
    "ts_event",
    "ts_collected",
    "ts_monotonic",
    "correlation_id",
    "trade_id",
    "component",
    "severity",
    "schema_version",
    "checksum",
    "payload_json",
)

TRADE_CSV_HEADERS = (
    "trade_id",
    "correlation_id",
    "inference_id",
    "order_id",
    "position_id",
    "direction",
    "lot",
    "entry_price",
    "exit_price",
    "entry_ts",
    "exit_ts",
    "mfe",
    "mae",
    "net_pnl",
    "tx_cost",
    "exit_reason",
    "valid_flag",
    "invalid_reason",
    "updated_at",
)

RECONCILIATION_CSV_HEADERS = (
    "reconciliation_id",
    "ts",
    "trade_id",
    "local_state_json",
    "broker_state_json",
    "result",
    "details",
)


@dataclass(frozen=True)
class ExportResult:
    path: Path
    rows: int


def default_export_dir() -> Path:
    from collector.settings import load_settings

    return load_settings().data_dir / "exports"


def _write_csv(path: Path, headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def export_events_csv(
    repository: PersistenceRepository, directory: Path | None = None
) -> ExportResult:
    conn = repository.connection
    rows = conn.execute("SELECT * FROM events ORDER BY ts_collected, ts_event, event_id").fetchall()
    out = directory / "events.csv" if directory is not None else default_export_dir() / "events.csv"
    _write_csv(
        out,
        EVENT_CSV_HEADERS,
        [tuple(row[header] for header in EVENT_CSV_HEADERS) for row in rows],
    )
    return ExportResult(path=out, rows=len(rows))


def export_trades_csv(
    repository: PersistenceRepository, directory: Path | None = None
) -> ExportResult:
    conn = repository.connection
    rows = conn.execute("SELECT * FROM trades ORDER BY entry_ts, trade_id").fetchall()
    out = directory / "trades.csv" if directory is not None else default_export_dir() / "trades.csv"
    _write_csv(
        out,
        TRADE_CSV_HEADERS,
        [tuple(row[header] for header in TRADE_CSV_HEADERS) for row in rows],
    )
    return ExportResult(path=out, rows=len(rows))


def export_reconciliations_csv(
    repository: PersistenceRepository, directory: Path | None = None
) -> ExportResult:
    conn = repository.connection
    rows = conn.execute(
        "SELECT * FROM reconciliation_events ORDER BY ts, reconciliation_id"
    ).fetchall()
    out = (
        directory / "reconciliations.csv"
        if directory is not None
        else default_export_dir() / "reconciliations.csv"
    )
    _write_csv(
        out,
        RECONCILIATION_CSV_HEADERS,
        [tuple(row[header] for header in RECONCILIATION_CSV_HEADERS) for row in rows],
    )
    return ExportResult(path=out, rows=len(rows))


def export_events_jsonl(
    repository: PersistenceRepository, directory: Path | None = None
) -> ExportResult:
    out = (
        directory / "events.jsonl"
        if directory is not None
        else default_export_dir() / "events.jsonl"
    )
    events = repository.query_events(limit=2**31 - 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(to_json(event))
            handle.write("\n")
    return ExportResult(path=out, rows=len(events))


def export_trades_jsonl(
    repository: PersistenceRepository, directory: Path | None = None
) -> ExportResult:
    out = (
        directory / "trades.jsonl"
        if directory is not None
        else default_export_dir() / "trades.jsonl"
    )
    conn = repository.connection
    rows = conn.execute("SELECT * FROM trades ORDER BY entry_ts, trade_id").fetchall()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    return ExportResult(path=out, rows=len(rows))


def export_reconciliations_jsonl(
    repository: PersistenceRepository, directory: Path | None = None
) -> ExportResult:
    out = (
        directory / "reconciliations.jsonl"
        if directory is not None
        else default_export_dir() / "reconciliations.jsonl"
    )
    conn = repository.connection
    rows = conn.execute(
        "SELECT * FROM reconciliation_events ORDER BY ts, reconciliation_id"
    ).fetchall()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    return ExportResult(path=out, rows=len(rows))


__all__ = [
    "EVENT_CSV_HEADERS",
    "ExportResult",
    "default_export_dir",
    "export_events_csv",
    "export_events_jsonl",
    "export_reconciliations_csv",
    "export_reconciliations_jsonl",
    "export_trades_csv",
    "export_trades_jsonl",
]
