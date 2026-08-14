"""Derived-state projection from canonical events.

Pure field mapping: this module decides *which* derived rows an event
updates, but contains no trading/risk/AI/execution logic. Every write
goes through ``collector.persistence.records.upsert_record`` so partial
lifecycle updates never clobber previously persisted values.

Projection policy (per contract):
* ORDER_ACKNOWLEDGED   -> orders  (state + ack timestamp)
* ORDER_FILLED         -> orders  (FILLED, done_ts, broker_response json)
* POSITION_OPENED      -> positions + trades (entry)
* POSITION_UPDATED     -> trades  (mfe / mae)
* POSITION_CLOSED      -> positions + trades (exit)
* RISK_GATE REJECT     -> invalid_trades
* RECONCILIATION       -> reconciliation_events (insert-only)
* CONTEXT_BUILT        -> market_snapshots
* everything else      -> no derived state
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable

from collector.event_model.envelope import EventEnvelope
from collector.persistence.records import (
    InvalidTradeRecord,
    OrderRecord,
    PositionRecord,
    TradeRecord,
    upsert_record,
)
from shared.contracts.types import EventType

Payload = dict[str, object]


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _apply_order_acknowledged(
    conn: sqlite3.Connection, event: EventEnvelope, payload: Payload
) -> None:
    order_id = payload["broker_order_id"]
    assert isinstance(order_id, str)
    upsert_record(
        conn,
        "orders",
        "broker_order_id",
        OrderRecord(
            broker_order_id=order_id,
            trade_id=event.trade_id,
            order_state=str(payload["broker_state"]),
            ack_ts=str(payload["ack_ts"]),
        ),
    )


def _apply_order_filled(conn: sqlite3.Connection, event: EventEnvelope, payload: Payload) -> None:
    order_id = payload["broker_order_id"]
    assert isinstance(order_id, str)
    upsert_record(
        conn,
        "orders",
        "broker_order_id",
        OrderRecord(
            broker_order_id=order_id,
            order_state="FILLED",
            done_ts=str(payload["fill_ts"]),
            broker_response=_json(
                {
                    "broker_deal_id": payload["broker_deal_id"],
                    "fill_price": payload["fill_price"],
                    "fill_volume": payload["fill_volume"],
                    "slippage": payload["slippage"],
                }
            ),
        ),
    )


def _apply_position_opened(
    conn: sqlite3.Connection, event: EventEnvelope, payload: Payload
) -> None:
    position_id = payload["broker_position_id"]
    assert isinstance(position_id, str)
    lot = payload["volume"]
    assert isinstance(lot, (int, float)) and not isinstance(lot, bool)
    upsert_record(
        conn,
        "positions",
        "broker_position_id",
        PositionRecord(
            broker_position_id=position_id,
            trade_id=event.trade_id,
            direction=str(payload["direction"]),
            lot=lot,
            open_price=payload["open_price"],  # type: ignore[arg-type]
            open_ts=str(payload["open_ts"]),
            state="OPEN",
        ),
    )
    upsert_record(
        conn,
        "trades",
        "trade_id",
        TradeRecord(
            trade_id=event.trade_id or "",
            position_id=position_id,
            direction=str(payload["direction"]),
            lot=lot,
            entry_price=payload["open_price"],  # type: ignore[arg-type]
            entry_ts=str(payload["open_ts"]),
        ),
    )


def _apply_position_updated(
    conn: sqlite3.Connection, event: EventEnvelope, payload: Payload
) -> None:
    mfe = payload["mfe_usd"]
    mae = payload["mae_usd"]
    upsert_record(
        conn,
        "trades",
        "trade_id",
        TradeRecord(
            trade_id=event.trade_id or "",
            mfe=mfe,  # type: ignore[arg-type]
            mae=mae,  # type: ignore[arg-type]
        ),
    )


def _apply_position_closed(
    conn: sqlite3.Connection, event: EventEnvelope, payload: Payload
) -> None:
    position_id = payload["broker_position_id"]
    assert isinstance(position_id, str)
    upsert_record(
        conn,
        "positions",
        "broker_position_id",
        PositionRecord(
            broker_position_id=position_id,
            close_price=payload["exit_fill_price"],  # type: ignore[arg-type]
            close_ts=str(payload["exit_fill_ts"]),
            state="CLOSED",
        ),
    )
    upsert_record(
        conn,
        "trades",
        "trade_id",
        TradeRecord(
            trade_id=event.trade_id or "",
            exit_price=payload["exit_fill_price"],  # type: ignore[arg-type]
            exit_ts=str(payload["exit_fill_ts"]),
            net_pnl=payload["net_pnl_usd"],  # type: ignore[arg-type]
            tx_cost=payload["transaction_cost_usd"],  # type: ignore[arg-type]
            exit_reason=str(payload["exit_reason"]),
        ),
    )


def _apply_risk_gate_reject(
    conn: sqlite3.Connection, event: EventEnvelope, payload: Payload
) -> None:
    upsert_record(
        conn,
        "invalid_trades",
        "trade_id",
        InvalidTradeRecord(
            trade_id=event.trade_id or "",
            invalid_reason=str(payload["rejection_reason"]),
            detected_ts=event.ts_collected,
            payload_json=_json(payload),
        ),
    )


def _apply_reconciliation(conn: sqlite3.Connection, event: EventEnvelope, payload: Payload) -> None:
    reconciliation_id = payload["reconciliation_id"]
    assert isinstance(reconciliation_id, str)
    details: dict[str, object] = {
        "trigger": payload["trigger"],
        "mismatch": payload["mismatch"],
        "action": payload["action"],
    }
    if "mismatch_details" in payload:
        details["mismatch_details"] = payload["mismatch_details"]
    conn.execute(
        "INSERT OR IGNORE INTO reconciliation_events "
        "(reconciliation_id, ts, trade_id, local_state_json, broker_state_json, result, details) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            reconciliation_id,
            str(payload["ts"]),
            event.trade_id,
            _json(payload["local_state"]),
            _json(payload["broker_state"]),
            str(payload["result"]),
            _json(details),
        ),
    )


def _apply_context_built(conn: sqlite3.Connection, event: EventEnvelope, payload: Payload) -> None:
    snapshot_id = payload["context_snapshot_id"]
    assert isinstance(snapshot_id, str)
    features = payload.get("derived_features")
    conn.execute(
        "INSERT OR IGNORE INTO market_snapshots "
        "(snapshot_id, trade_id, ts, bar_m1, bar_m5, atr_m1, atr_m5, features_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            snapshot_id,
            event.trade_id,
            event.ts_event,
            str(payload["m1_context_ref"]),
            str(payload["m5_context_ref"]),
            payload["atr_m1"],
            payload.get("atr_m5"),
            _json(features) if features is not None else None,
        ),
    )


_Handler = Callable[[sqlite3.Connection, EventEnvelope, Payload], None]

_HANDLERS: dict[EventType, _Handler] = {
    EventType.ORDER_ACKNOWLEDGED: _apply_order_acknowledged,
    EventType.ORDER_FILLED: _apply_order_filled,
    EventType.POSITION_OPENED: _apply_position_opened,
    EventType.POSITION_UPDATED: _apply_position_updated,
    EventType.POSITION_CLOSED: _apply_position_closed,
    EventType.RISK_GATE: _apply_risk_gate_reject,
    EventType.RECONCILIATION: _apply_reconciliation,
    EventType.CONTEXT_BUILT: _apply_context_built,
}


def apply_derived_state(conn: sqlite3.Connection, event: EventEnvelope) -> None:
    """Project *event* into its derived tables inside the caller's transaction."""
    handler = _HANDLERS.get(event.event_type)
    if handler is None:
        return
    payload = event.to_dict()["payload"]
    assert isinstance(payload, dict)
    if event.event_type is EventType.RISK_GATE and payload.get("gate_result") != "REJECT":
        return
    handler(conn, event, payload)


__all__ = ["apply_derived_state"]
