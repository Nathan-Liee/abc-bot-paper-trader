"""Reconciliation persistence: run/adoption records, atomicity, queries."""

from __future__ import annotations

from pathlib import Path

import pytest

from collector.event_model import EventEnvelope, EventType, build_event, compute_checksum
from collector.persistence import PersistenceError, PersistenceRepository
from collector.persistence.reconciling import (
    AdoptionRecord,
    ReconciliationRunRecord,
    read_adoptions_for,
)
from collector.persistence.records import OrderRecord
from tests.unit.event_factories import reconciliation_payload


def run_record(
    reconciliation_id: str, *, signature: str = "sig", result: str = "SYNCED"
) -> ReconciliationRunRecord:
    return ReconciliationRunRecord(
        reconciliation_id=reconciliation_id,
        trigger="STARTUP",
        signature=signature,
        result=result,
        action="NONE",
        mismatch=False,
        run_ts="2026-08-14T09:00:00.000Z",
    )


def adoption_record(reconciliation_id: str, broker_id: str) -> AdoptionRecord:
    return AdoptionRecord(
        adoption_id=f"adoption-{broker_id}",
        reconciliation_id=reconciliation_id,
        entity_type="POSITION",
        broker_id=broker_id,
        symbol="XAUUSDc",
        direction="BUY",
        volume=0.1,
        open_price=2000.0,
        broker_state="OPEN",
        reason="broker evidence adopted",
        adopted_ts="2026-08-14T09:00:00.000Z",
    )


def reconciliation_event(reconciliation_id: str) -> EventEnvelope:
    return build_event(
        EventType.RECONCILIATION,
        reconciliation_payload(reconciliation_id=reconciliation_id),
    )


def test_save_run_persists_event_derived_and_run(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    with PersistenceRepository(db) as repo:
        event = reconciliation_event("3f2c9b1e-7d4a-4b8e-9c2f-0d1e2f3a4b5c")
        result = repo.save_reconciliation_run(event, run_record(event.payload["reconciliation_id"]))
        assert result.inserted is True
        assert repo.count_events() == 1
        latest = repo.get_latest_reconciliation_run()
        assert latest is not None
        assert latest.reconciliation_id == "3f2c9b1e-7d4a-4b8e-9c2f-0d1e2f3a4b5c"
        assert latest.result == "SYNCED"
        assert latest.mismatch is False
        derived = repo.connection.execute(
            "SELECT * FROM reconciliation_events WHERE reconciliation_id = ?",
            ("3f2c9b1e-7d4a-4b8e-9c2f-0d1e2f3a4b5c",),
        ).fetchone()
        assert derived is not None
        assert derived["result"] == "SYNCED"


def test_save_run_with_adoptions_is_atomic_and_traceable(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    reconciliation_id = "3f2c9b1e-7d4a-4b8e-9c2f-0d1e2f3a4b5c"
    with PersistenceRepository(db) as repo:
        event = reconciliation_event(reconciliation_id)
        repo.save_reconciliation_run(
            event,
            run_record(reconciliation_id, result="ADOPTED_BROKER", signature="sig2"),
            (adoption_record(reconciliation_id, "broker-position-001"),),
        )
        adoptions = repo.adoptions_for(reconciliation_id)
        assert len(adoptions) == 1
        assert adoptions[0].broker_id == "broker-position-001"
        assert adoptions[0].symbol == "XAUUSDc"
        assert adoptions[0].reconciliation_id == reconciliation_id
        assert repo.get_latest_reconciliation_run() is not None


def test_same_event_replayed_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    with PersistenceRepository(db) as repo:
        event = reconciliation_event("3f2c9b1e-7d4a-4b8e-9c2f-0d1e2f3a4b5c")
        first = repo.save_reconciliation_run(event, run_record(event.payload["reconciliation_id"]))
        second = repo.save_reconciliation_run(event, run_record(event.payload["reconciliation_id"]))
        assert first.inserted is True
        assert second.inserted is False
        assert second.duplicate is True
        assert second.identical is True
        assert repo.count_events() == 1
        assert len(repo.recent_reconciliation_runs()) == 1


def test_conflicting_run_rolls_back_everything(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    reconciliation_id = "3f2c9b1e-7d4a-4b8e-9c2f-0d1e2f3a4b5c"
    with PersistenceRepository(db) as repo:
        event = reconciliation_event(reconciliation_id)
        repo.save_reconciliation_run(
            event,
            run_record(reconciliation_id, result="ADOPTED_BROKER", signature="sig2"),
            (adoption_record(reconciliation_id, "broker-position-001"),),
        )
        before_runs = len(repo.recent_reconciliation_runs())

        conflicting_data = event.to_dict()
        conflicting_data["payload"] = dict(event.payload)
        conflicting_data["payload"]["local_state"] = "open_positions=99"
        conflicting_data["checksum"] = compute_checksum(conflicting_data)
        conflicting = EventEnvelope.from_dict(conflicting_data)
        assert conflicting.event_id == event.event_id

        with pytest.raises(PersistenceError, match="conflicting checksum"):
            repo.save_reconciliation_run(
                conflicting,
                run_record(reconciliation_id, result="ESCALATED", signature="other"),
                (adoption_record(reconciliation_id, "broker-position-999"),),
            )

        assert repo.count_events() == 1
        assert len(repo.recent_reconciliation_runs()) == before_runs
        adoptions = read_adoptions_for(repo.connection, reconciliation_id)
        assert [item.broker_id for item in adoptions] == ["broker-position-001"]


def test_open_orders_excludes_terminal_states(tmp_path: Path) -> None:
    db = tmp_path / "collector.db"
    with PersistenceRepository(db) as repo:
        repo.upsert_order(OrderRecord(broker_order_id="active", order_state="PLACED"))
        repo.upsert_order(OrderRecord(broker_order_id="filled", order_state="FILLED"))
        repo.upsert_order(OrderRecord(broker_order_id="cancelled", order_state="CANCELLED"))
        repo.upsert_order(OrderRecord(broker_order_id="unknown"))
        ids = [order.broker_order_id for order in repo.open_orders()]
        assert ids == ["active", "unknown"]


def test_latest_run_absent_when_empty(tmp_path: Path) -> None:
    with PersistenceRepository(tmp_path / "collector.db") as repo:
        assert repo.get_latest_reconciliation_run() is None
        assert repo.recent_reconciliation_runs() == []
