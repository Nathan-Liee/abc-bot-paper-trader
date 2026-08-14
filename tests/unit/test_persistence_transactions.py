"""Transaction boundary and atomicity tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from collector.event_model import EventType, build_event
from collector.persistence import PersistenceRepository, ReconciliationRecord
from collector.persistence.errors import PersistenceError
from tests.unit.event_factories import TRADE_ID, tick_payload


def _repo(tmp_path: Path) -> PersistenceRepository:
    return PersistenceRepository(tmp_path / "collector.db")


def test_transaction_commits_on_success(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        with repo.transaction() as conn:
            conn.execute(
                "INSERT INTO events (event_id, event_type, ts_event, ts_collected, "
                "ts_monotonic, correlation_id, trade_id, component, severity, "
                "schema_version, payload_json, checksum) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.event_type.value,
                    event.ts_event,
                    event.ts_collected,
                    event.ts_monotonic,
                    event.correlation_id,
                    event.trade_id,
                    event.component,
                    event.severity,
                    event.schema_version,
                    "{}",
                    event.checksum,
                ),
            )
        assert repo.count_events() == 1


def test_transaction_rolls_back_on_exception(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        with pytest.raises(RuntimeError, match="boom"):
            with repo.transaction() as conn:
                conn.execute(
                    "INSERT INTO invalid_trades (trade_id, invalid_reason, detected_ts) "
                    "VALUES (?, ?, ?)",
                    (TRADE_ID, "reason", "2026-08-14T09:00:00.000Z"),
                )
                raise RuntimeError("boom")
        count = repo.connection.execute("SELECT COUNT(*) FROM invalid_trades").fetchone()
        assert count is not None and count[0] == 0


def test_nested_transaction_is_rejected(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        with pytest.raises(PersistenceError, match="nested transactions"):
            with repo.transaction():
                with repo.transaction():
                    pass


def test_insert_event_with_derived_is_atomic(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        opened = build_event(
            EventType.POSITION_OPENED,
            {
                "broker_position_id": "bp-1",
                "direction": "BUY",
                "volume": 0.1,
                "open_price": 2000.3,
                "open_ts": "2026-08-14T09:00:00Z",
                "state": "OPEN",
            },
            trade_id=TRADE_ID,
        )
        result = repo.insert_event_with_derived(opened)
        assert result.inserted is True
        assert repo.count_events() == 1
        trades = repo.connection.execute(
            "SELECT * FROM trades WHERE trade_id = ?", (TRADE_ID,)
        ).fetchall()
        assert len(trades) == 1


def test_manual_rollback_leaves_no_partial_state(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        try:
            with repo.transaction() as conn:
                conn.execute(
                    "INSERT INTO events (event_id, event_type, ts_event, ts_collected, "
                    "ts_monotonic, correlation_id, trade_id, component, severity, "
                    "schema_version, payload_json, checksum) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.event_id,
                        event.event_type.value,
                        event.ts_event,
                        event.ts_collected,
                        event.ts_monotonic,
                        event.correlation_id,
                        event.trade_id,
                        event.component,
                        event.severity,
                        event.schema_version,
                        "{}",
                        event.checksum,
                    ),
                )
                conn.execute(
                    "INSERT INTO trades (trade_id, direction, updated_at) VALUES (?, ?, ?)",
                    (TRADE_ID, "BUY", "2026-08-14T09:00:00.000Z"),
                )
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        assert repo.count_events() == 0
        trades = repo.connection.execute("SELECT COUNT(*) FROM trades").fetchone()
        assert trades is not None and trades[0] == 0


def test_insert_reconciliation_uses_transaction(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        result = repo.insert_reconciliation(
            ReconciliationRecord(
                reconciliation_id="r-1", ts="2026-08-14T09:00:00Z", result="SYNCED"
            )
        )
        assert result.inserted is True
        recent = repo.recent_reconciliations()
        assert len(recent) == 1
        assert recent[0].reconciliation_id == "r-1"
