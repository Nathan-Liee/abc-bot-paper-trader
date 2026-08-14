"""Typed records for derived persistence tables.

These records mirror the approved schema columns exactly. Optional
fields are ``None`` when unknown; upserts only write non-``None``
fields, so lifecycle updates never clobber earlier data.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, fields

from collector.event_model.timestamps import now_utc_ms

_UPDATED_AT_TABLES = {"trades", "orders", "positions"}


def upsert_record(
    conn: sqlite3.Connection,
    table: str,
    pk_field: str,
    record: object,
) -> None:
    """Insert-or-update *record* into *table*, merging only non-None fields.

    The natural key is *pk_field*. On conflict only the caller-supplied
    (non-``None``) columns are updated, so lifecycle updates never
    clobber previously persisted values. ``updated_at`` is set to the
    current UTC time when not supplied for lifecycle tables.
    """
    values: dict[str, object] = {
        field.name: getattr(record, field.name)
        for field in fields(record)  # type: ignore[arg-type]
        if getattr(record, field.name) is not None
    }
    if table in _UPDATED_AT_TABLES and "updated_at" not in values:
        values["updated_at"] = now_utc_ms()

    columns = list(values)
    if not columns:
        return

    update_columns = [column for column in columns if column != pk_field] or [pk_field]
    placeholders = ", ".join("?" for _ in columns)
    assignments = ", ".join(f"{column}=excluded.{column}" for column in update_columns)
    conn.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT({pk_field}) DO UPDATE SET {assignments}",
        tuple(values[column] for column in columns),
    )


@dataclass(frozen=True)
class TradeRecord:
    trade_id: str
    correlation_id: str | None = None
    inference_id: str | None = None
    order_id: str | None = None
    position_id: str | None = None
    direction: str | None = None
    lot: float | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    entry_ts: str | None = None
    exit_ts: str | None = None
    mfe: float | None = None
    mae: float | None = None
    net_pnl: float | None = None
    tx_cost: float | None = None
    exit_reason: str | None = None
    valid_flag: bool = True
    invalid_reason: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TradeRecord:
        return cls(
            trade_id=row["trade_id"],
            correlation_id=row["correlation_id"],
            inference_id=row["inference_id"],
            order_id=row["order_id"],
            position_id=row["position_id"],
            direction=row["direction"],
            lot=row["lot"],
            entry_price=row["entry_price"],
            exit_price=row["exit_price"],
            entry_ts=row["entry_ts"],
            exit_ts=row["exit_ts"],
            mfe=row["mfe"],
            mae=row["mae"],
            net_pnl=row["net_pnl"],
            tx_cost=row["tx_cost"],
            exit_reason=row["exit_reason"],
            valid_flag=bool(row["valid_flag"]),
            invalid_reason=row["invalid_reason"],
            updated_at=row["updated_at"],
        )


@dataclass(frozen=True)
class OrderRecord:
    broker_order_id: str
    trade_id: str | None = None
    requested_price: float | None = None
    requested_lot: float | None = None
    order_state: str | None = None
    submit_ts: str | None = None
    ack_ts: str | None = None
    done_ts: str | None = None
    broker_response: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> OrderRecord:
        return cls(
            broker_order_id=row["broker_order_id"],
            trade_id=row["trade_id"],
            requested_price=row["requested_price"],
            requested_lot=row["requested_lot"],
            order_state=row["order_state"],
            submit_ts=row["submit_ts"],
            ack_ts=row["ack_ts"],
            done_ts=row["done_ts"],
            broker_response=row["broker_response"],
            updated_at=row["updated_at"],
        )


@dataclass(frozen=True)
class PositionRecord:
    broker_position_id: str
    trade_id: str | None = None
    direction: str | None = None
    lot: float | None = None
    open_price: float | None = None
    close_price: float | None = None
    open_ts: str | None = None
    close_ts: str | None = None
    state: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> PositionRecord:
        return cls(
            broker_position_id=row["broker_position_id"],
            trade_id=row["trade_id"],
            direction=row["direction"],
            lot=row["lot"],
            open_price=row["open_price"],
            close_price=row["close_price"],
            open_ts=row["open_ts"],
            close_ts=row["close_ts"],
            state=row["state"],
            updated_at=row["updated_at"],
        )


@dataclass(frozen=True)
class ReconciliationRecord:
    reconciliation_id: str
    ts: str
    trade_id: str | None = None
    local_state_json: str | None = None
    broker_state_json: str | None = None
    result: str | None = None
    details: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ReconciliationRecord:
        return cls(
            reconciliation_id=row["reconciliation_id"],
            ts=row["ts"],
            trade_id=row["trade_id"],
            local_state_json=row["local_state_json"],
            broker_state_json=row["broker_state_json"],
            result=row["result"],
            details=row["details"],
        )


@dataclass(frozen=True)
class InvalidTradeRecord:
    trade_id: str
    invalid_reason: str
    detected_ts: str
    payload_json: str | None = None


__all__ = [
    "InvalidTradeRecord",
    "OrderRecord",
    "PositionRecord",
    "ReconciliationRecord",
    "TradeRecord",
]
