"""Derived-state projection and idempotent upsert tests."""

from __future__ import annotations

import json
from pathlib import Path

from collector.event_model import EventType, build_event
from collector.persistence import (
    OrderRecord,
    PersistenceRepository,
    PositionRecord,
    TradeRecord,
)
from tests.unit.event_factories import (
    BROKER_ORDER_ID,
    BROKER_POSITION_ID,
    MONO,
    RECONCILIATION_ID,
    TRADE_ID,
    context_payload,
    order_acknowledged_payload,
    order_filled_payload,
    order_submitted_payload,
    position_closed_payload,
    position_opened_payload,
    position_updated_payload,
    reconciliation_payload,
    risk_gate_payload,
)


def _repo(tmp_path: Path) -> PersistenceRepository:
    return PersistenceRepository(tmp_path / "collector.db")


def test_full_lifecycle_projects_derived_state(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        opened = build_event(
            EventType.POSITION_OPENED,
            position_opened_payload(),
            trade_id=TRADE_ID,
            ts_monotonic=MONO,
        )
        repo.insert_event_with_derived(opened)

        trade = repo.get_trade(TRADE_ID)
        assert trade is not None
        assert trade.position_id == BROKER_POSITION_ID
        assert trade.direction == "BUY"
        assert trade.lot == 0.1
        assert trade.entry_price == 2000.3
        assert trade.entry_ts == "2026-08-14T09:00:00Z"
        assert trade.valid_flag is True

        positions = repo.open_positions()
        assert len(positions) == 1
        assert positions[0].broker_position_id == BROKER_POSITION_ID
        assert positions[0].state == "OPEN"

        updated = build_event(
            EventType.POSITION_UPDATED,
            position_updated_payload(),
            trade_id=TRADE_ID,
            ts_monotonic=MONO + 1,
        )
        repo.insert_event_with_derived(updated)

        trade = repo.get_trade(TRADE_ID)
        assert trade is not None
        assert trade.mfe == 12.0
        assert trade.mae == -3.0
        assert trade.direction == "BUY"
        assert trade.entry_price == 2000.3

        closed = build_event(
            EventType.POSITION_CLOSED,
            position_closed_payload(),
            trade_id=TRADE_ID,
            ts_monotonic=MONO + 2,
        )
        repo.insert_event_with_derived(closed)

        trade = repo.get_trade(TRADE_ID)
        assert trade is not None
        assert trade.exit_price == 2010.0
        assert trade.exit_ts == "2026-08-14T09:00:00Z"
        assert trade.net_pnl == 8.9
        assert trade.tx_cost == 0.8
        assert trade.exit_reason == "TAKE_PROFIT"

        assert repo.open_positions() == []


def test_order_acknowledged_creates_order_row(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        acknowledged = build_event(
            EventType.ORDER_ACKNOWLEDGED,
            order_acknowledged_payload(),
            trade_id=TRADE_ID,
        )
        repo.insert_event_with_derived(acknowledged)
        rows = repo.connection.execute(
            "SELECT * FROM orders WHERE broker_order_id = ?", (BROKER_ORDER_ID,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["trade_id"] == TRADE_ID
        assert rows[0]["order_state"] == "FILLED"
        assert rows[0]["ack_ts"] == "2026-08-14T09:00:00Z"


def test_order_filled_merges_state_and_response(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        repo.insert_event_with_derived(
            build_event(
                EventType.ORDER_ACKNOWLEDGED, order_acknowledged_payload(), trade_id=TRADE_ID
            )
        )
        filled = build_event(
            EventType.ORDER_FILLED,
            order_filled_payload(),
            trade_id=TRADE_ID,
        )
        repo.insert_event_with_derived(filled)
        rows = repo.connection.execute(
            "SELECT * FROM orders WHERE broker_order_id = ?", (BROKER_ORDER_ID,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["order_state"] == "FILLED"
        assert rows[0]["done_ts"] == "2026-08-14T09:00:00Z"
        response = json.loads(rows[0]["broker_response"])
        assert response == {
            "broker_deal_id": "broker-deal-001",
            "fill_price": 2000.3,
            "fill_volume": 0.1,
            "slippage": 0.05,
        }
        assert rows[0]["ack_ts"] == "2026-08-14T09:00:00Z"


def test_order_submitted_projects_no_order_row(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        submitted = build_event(
            EventType.ORDER_SUBMITTED,
            order_submitted_payload(),
            trade_id=TRADE_ID,
        )
        repo.insert_event_with_derived(submitted)
        count = repo.connection.execute("SELECT COUNT(*) FROM orders").fetchone()
        assert count is not None and count[0] == 0


def test_risk_gate_reject_records_invalid_trade(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        rejected = build_event(
            EventType.RISK_GATE,
            risk_gate_payload(gate_result="REJECT", rejection_reason="budget exceeded"),
            trade_id=TRADE_ID,
        )
        repo.insert_event_with_derived(rejected)
        rows = repo.connection.execute(
            "SELECT * FROM invalid_trades WHERE trade_id = ?", (TRADE_ID,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["invalid_reason"] == "budget exceeded"
        assert rows[0]["detected_ts"] == rejected.ts_collected


def test_risk_gate_allow_projects_nothing(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        allowed = build_event(
            EventType.RISK_GATE,
            risk_gate_payload(gate_result="ALLOW"),
            trade_id=TRADE_ID,
        )
        repo.insert_event_with_derived(allowed)
        count = repo.connection.execute("SELECT COUNT(*) FROM invalid_trades").fetchone()
        assert count is not None and count[0] == 0


def test_reconciliation_insert_is_idempotent(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        record = build_event(
            EventType.RECONCILIATION,
            reconciliation_payload(),
            ts_monotonic=MONO,
        )
        first = repo.insert_event_with_derived(record)
        second = repo.insert_event_with_derived(record)
        assert first.inserted is True
        assert second.duplicate is True
        rows = repo.connection.execute(
            "SELECT * FROM reconciliation_events WHERE reconciliation_id = ?",
            (RECONCILIATION_ID,),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["result"] == "SYNCED"
        assert json.loads(rows[0]["local_state_json"]) == "OPEN"


def test_context_built_projects_market_snapshot(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        built = build_event(
            EventType.CONTEXT_BUILT,
            context_payload(),
            trade_id=TRADE_ID,
        )
        repo.insert_event_with_derived(built)
        rows = repo.connection.execute(
            "SELECT * FROM market_snapshots WHERE snapshot_id = 'snap-1'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["trade_id"] == TRADE_ID
        assert rows[0]["bar_m1"] == "ctx-m1-1"
        assert rows[0]["bar_m5"] == "ctx-m5-1"
        assert rows[0]["atr_m1"] == 1.25
        assert rows[0]["atr_m5"] is None


def test_upsert_trade_partial_update_never_clobbers(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        repo.upsert_trade(TradeRecord(trade_id=TRADE_ID, direction="BUY", entry_price=2000.3))
        repo.upsert_trade(TradeRecord(trade_id=TRADE_ID, mfe=12.0, mae=-3.0))
        trade = repo.get_trade(TRADE_ID)
        assert trade is not None
        assert trade.direction == "BUY"
        assert trade.entry_price == 2000.3
        assert trade.mfe == 12.0
        assert trade.mae == -3.0


def test_upsert_order_and_position_partial_merge(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        repo.upsert_order(OrderRecord(broker_order_id=BROKER_ORDER_ID, trade_id=TRADE_ID))
        repo.upsert_order(OrderRecord(broker_order_id=BROKER_ORDER_ID, order_state="FILLED"))
        rows = repo.connection.execute(
            "SELECT * FROM orders WHERE broker_order_id = ?", (BROKER_ORDER_ID,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["trade_id"] == TRADE_ID
        assert rows[0]["order_state"] == "FILLED"

        repo.upsert_position(
            PositionRecord(broker_position_id=BROKER_POSITION_ID, state="OPEN", open_price=2000.3)
        )
        repo.upsert_position(PositionRecord(broker_position_id=BROKER_POSITION_ID, state="CLOSED"))
        rows = repo.connection.execute(
            "SELECT * FROM positions WHERE broker_position_id = ?", (BROKER_POSITION_ID,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["state"] == "CLOSED"
        assert rows[0]["open_price"] == 2000.3
