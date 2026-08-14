"""SQLite schema (DDL) for the persistence layer.

Schema derives from the canonical event contract (docs/contracts/), the
bootstrap technical design, and the persistence task specification.
Only fields derivable from approved design are present; no new
domain/business fields are invented here.

Conventions:

* ``events`` is the append-only audit source of truth. It has no
  foreign keys to derived tables, so events can be persisted even when
  derived entities do not exist yet.
* Derived tables (trades/orders/positions/snapshots/reconciliation)
  use natural keys from the contract: ``trade_id``, ``broker_order_id``,
  ``broker_position_id``, ``reconciliation_id``, ``snapshot_id``.
* All DDL is ``IF NOT EXISTS`` so re-running migrations is harmless.
"""

from __future__ import annotations

SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""

_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    ts_event TEXT NOT NULL,
    ts_collected TEXT NOT NULL,
    ts_monotonic INTEGER NOT NULL,
    correlation_id TEXT,
    trade_id TEXT,
    component TEXT NOT NULL,
    severity TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    checksum TEXT NOT NULL
)
"""

_TRADES_DDL = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    correlation_id TEXT,
    inference_id TEXT,
    order_id TEXT,
    position_id TEXT,
    direction TEXT,
    lot REAL,
    entry_price REAL,
    exit_price REAL,
    entry_ts TEXT,
    exit_ts TEXT,
    mfe REAL,
    mae REAL,
    net_pnl REAL,
    tx_cost REAL,
    exit_reason TEXT,
    valid_flag INTEGER NOT NULL DEFAULT 1,
    invalid_reason TEXT,
    updated_at TEXT NOT NULL
)
"""

_ORDERS_DDL = """
CREATE TABLE IF NOT EXISTS orders (
    broker_order_id TEXT PRIMARY KEY,
    trade_id TEXT,
    requested_price REAL,
    requested_lot REAL,
    order_state TEXT,
    submit_ts TEXT,
    ack_ts TEXT,
    done_ts TEXT,
    broker_response TEXT,
    updated_at TEXT NOT NULL
)
"""

_POSITIONS_DDL = """
CREATE TABLE IF NOT EXISTS positions (
    broker_position_id TEXT PRIMARY KEY,
    trade_id TEXT,
    direction TEXT,
    lot REAL,
    open_price REAL,
    close_price REAL,
    open_ts TEXT,
    close_ts TEXT,
    state TEXT,
    updated_at TEXT NOT NULL
)
"""

_MARKET_SNAPSHOTS_DDL = """
CREATE TABLE IF NOT EXISTS market_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    trade_id TEXT,
    ts TEXT NOT NULL,
    bar_m1 TEXT,
    bar_m5 TEXT,
    atr_m1 REAL,
    atr_m5 REAL,
    prices_json TEXT,
    features_json TEXT
)
"""

_RECONCILIATION_DDL = """
CREATE TABLE IF NOT EXISTS reconciliation_events (
    reconciliation_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    trade_id TEXT,
    local_state_json TEXT,
    broker_state_json TEXT,
    result TEXT,
    details TEXT
)
"""

_INVALID_TRADES_DDL = """
CREATE TABLE IF NOT EXISTS invalid_trades (
    trade_id TEXT PRIMARY KEY,
    invalid_reason TEXT NOT NULL,
    detected_ts TEXT NOT NULL,
    payload_json TEXT
)
"""

_INDEXES_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_events_trade_ts ON events(trade_id, ts_event)",
    "CREATE INDEX IF NOT EXISTS idx_events_correlation_ts ON events(correlation_id, ts_event)",
    "CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(event_type, ts_event)",
    "CREATE INDEX IF NOT EXISTS idx_events_checksum ON events(checksum)",
)

_APPEND_ONLY_TRIGGERS_DDL = (
    """
    CREATE TRIGGER IF NOT EXISTS events_no_update
    BEFORE UPDATE ON events
    BEGIN
        SELECT RAISE(ABORT, 'events table is append-only: UPDATE is forbidden');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS events_no_delete
    BEFORE DELETE ON events
    BEGIN
        SELECT RAISE(ABORT, 'events table is append-only: DELETE is forbidden');
    END
    """,
)

# Migration 1: the full initial schema. Every statement is idempotent.
SCHEMA_STATEMENTS: tuple[str, ...] = (
    _EVENTS_DDL,
    *_INDEXES_DDL,
    *_APPEND_ONLY_TRIGGERS_DDL,
    _TRADES_DDL,
    _ORDERS_DDL,
    _POSITIONS_DDL,
    _MARKET_SNAPSHOTS_DDL,
    _RECONCILIATION_DDL,
    _INVALID_TRADES_DDL,
)

__all__ = [
    "SCHEMA_MIGRATIONS_DDL",
    "SCHEMA_STATEMENTS",
]
