"""Persistence records for reconciliation service metadata.

One row per reconciliation run and one row per adopted broker entity.
These tables carry *observed* reconciliation state with explicit lineage
(reconciliation_id, reason); they never fabricate canonical events for
unobserved history. All helpers are idempotent (INSERT OR IGNORE).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class ReconciliationRunRecord:
    """Durable metadata of one reconciliation run."""

    reconciliation_id: str
    trigger: str
    signature: str
    result: str
    action: str
    mismatch: bool
    run_ts: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ReconciliationRunRecord:
        return cls(
            reconciliation_id=row["reconciliation_id"],
            trigger=row["trigger"],
            signature=row["signature"],
            result=row["result"],
            action=row["action"],
            mismatch=bool(row["mismatch"]),
            run_ts=row["run_ts"],
        )


@dataclass(frozen=True)
class AdoptionRecord:
    """Traceability of one adopted broker entity (observed state only)."""

    adoption_id: str
    reconciliation_id: str
    entity_type: str
    broker_id: str
    symbol: str | None
    direction: str | None
    volume: float | None
    open_price: float | None
    broker_state: str | None
    reason: str
    adopted_ts: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> AdoptionRecord:
        return cls(
            adoption_id=row["adoption_id"],
            reconciliation_id=row["reconciliation_id"],
            entity_type=row["entity_type"],
            broker_id=row["broker_id"],
            symbol=row["symbol"],
            direction=row["direction"],
            volume=row["volume"],
            open_price=row["open_price"],
            broker_state=row["broker_state"],
            reason=row["reason"],
            adopted_ts=row["adopted_ts"],
        )


def write_reconciliation_run(conn: sqlite3.Connection, run: ReconciliationRunRecord) -> None:
    """Insert *run*; duplicates by reconciliation_id are ignored."""
    conn.execute(
        "INSERT OR IGNORE INTO reconciliation_runs "
        "(reconciliation_id, trigger, signature, result, action, mismatch, run_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            run.reconciliation_id,
            run.trigger,
            run.signature,
            run.result,
            run.action,
            1 if run.mismatch else 0,
            run.run_ts,
        ),
    )


def write_reconciliation_adoption(conn: sqlite3.Connection, adoption: AdoptionRecord) -> None:
    """Insert *adoption*; duplicates by adoption_id are ignored."""
    conn.execute(
        "INSERT OR IGNORE INTO reconciliation_adoptions "
        "(adoption_id, reconciliation_id, entity_type, broker_id, symbol, direction, "
        "volume, open_price, broker_state, reason, adopted_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            adoption.adoption_id,
            adoption.reconciliation_id,
            adoption.entity_type,
            adoption.broker_id,
            adoption.symbol,
            adoption.direction,
            adoption.volume,
            adoption.open_price,
            adoption.broker_state,
            adoption.reason,
            adoption.adopted_ts,
        ),
    )


def read_latest_reconciliation_run(conn: sqlite3.Connection) -> ReconciliationRunRecord | None:
    """Return the most recent run (by run_ts, then id for determinism)."""
    row = conn.execute(
        "SELECT * FROM reconciliation_runs ORDER BY run_ts DESC, reconciliation_id DESC LIMIT 1"
    ).fetchone()
    return ReconciliationRunRecord.from_row(row) if row is not None else None


def read_reconciliation_runs(
    conn: sqlite3.Connection, limit: int = 50
) -> list[ReconciliationRunRecord]:
    rows = conn.execute(
        "SELECT * FROM reconciliation_runs ORDER BY run_ts DESC, reconciliation_id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [ReconciliationRunRecord.from_row(row) for row in rows]


def read_adoptions_for(conn: sqlite3.Connection, reconciliation_id: str) -> list[AdoptionRecord]:
    rows = conn.execute(
        "SELECT * FROM reconciliation_adoptions WHERE reconciliation_id = ? "
        "ORDER BY entity_type, broker_id",
        (reconciliation_id,),
    ).fetchall()
    return [AdoptionRecord.from_row(row) for row in rows]


__all__ = [
    "AdoptionRecord",
    "ReconciliationRunRecord",
    "read_adoptions_for",
    "read_latest_reconciliation_run",
    "read_reconciliation_runs",
    "write_reconciliation_adoption",
    "write_reconciliation_run",
]
