"""Persistence repository: the single write path into SQLite WAL.

Responsibilities (task scope):

* immutable, append-only audit stream for canonical events
* idempotent derived-state upserts keyed on contract natural keys
* explicit transaction boundaries (single-writer oriented)
* deterministic connection initialization (WAL, FKs, busy timeout,
  synchronous level)
* queries and integrity utilities (see ``integrity.py`` / ``export.py``)

There is intentionally no ``update_event`` / ``delete_event`` API: the
``events`` table is append-only and protected by SQLite triggers.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from collector.event_model.envelope import EventEnvelope
from collector.event_model.validation import validate_event_dict
from collector.persistence.cursor import (
    IngestionCursor,
    read_ingestion_cursor,
    write_ingestion_cursor,
)
from collector.persistence.errors import PersistenceError
from collector.persistence.migrations import apply_migrations
from collector.persistence.projector import apply_derived_state
from collector.persistence.reconciling import (
    AdoptionRecord,
    ReconciliationRunRecord,
    read_adoptions_for,
    read_latest_reconciliation_run,
    read_reconciliation_runs,
    write_reconciliation_adoption,
    write_reconciliation_run,
)
from collector.persistence.records import (
    InvalidTradeRecord,
    OrderRecord,
    PositionRecord,
    ReconciliationRecord,
    TradeRecord,
    upsert_record,
)
from shared.contracts.types import EventType

logger = logging.getLogger("collector.persistence")

DEFAULT_BUSY_TIMEOUT_MS = 5000
DEFAULT_SYNCHRONOUS = "FULL"


@dataclass(frozen=True)
class InsertResult:
    """Idempotent outcome of an append operation."""

    inserted: bool
    duplicate: bool
    identical: bool


class PersistenceRepository:
    """SQLite WAL-backed repository. Single connection, single writer.

    Not thread-safe: the collector architecture is single-writer
    oriented. Use one repository instance per writer; concurrent reads
    are handled by SQLite WAL itself.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        synchronous: str = DEFAULT_SYNCHRONOUS,
    ) -> None:
        if db_path is None:
            from collector.settings import load_settings

            db_path = load_settings().sqlite_dir / "collector.db"
        self._db_path = db_path
        self._busy_timeout_ms = busy_timeout_ms
        self._synchronous = synchronous.upper()
        self._conn: sqlite3.Connection | None = None
        self._in_transaction = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    @property
    def connection(self) -> sqlite3.Connection:
        """The open connection; raises when the repository is closed."""
        if self._conn is None:
            raise PersistenceError("repository is not open")
        return self._conn

    def open(self) -> None:
        """Open (creating if needed) and deterministically initialize the DB.

        A corrupt or unreadable database raises ``PersistenceError`` with
        a clear message; the file is never silently recreated.
        """
        if self.is_open:
            raise PersistenceError("repository is already open")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(str(self._db_path))
        except sqlite3.Error as exc:
            raise PersistenceError(f"cannot open database {self._db_path}: {exc}") from exc

        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
            conn.execute(f"PRAGMA synchronous={self._synchronous}")
            conn.execute("PRAGMA wal_autocheckpoint=1000")
            quick_check = conn.execute("PRAGMA quick_check").fetchone()
            if quick_check is None or quick_check[0] != "ok":
                raise PersistenceError(f"database integrity check failed for {self._db_path}")
            apply_migrations(conn)
        except sqlite3.DatabaseError as exc:
            conn.close()
            raise PersistenceError(f"cannot initialize database {self._db_path}: {exc}") from exc
        except PersistenceError:
            conn.close()
            raise
        self._conn = conn
        logger.info("opened persistence database %s", self._db_path)

    def close(self) -> None:
        """Close the connection, checkpointing the WAL."""
        if self._conn is not None:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.DatabaseError:
                pass
            self._conn.close()
            self._conn = None
            self._in_transaction = False

    def __enter__(self) -> PersistenceRepository:
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Explicit transaction boundary (``BEGIN IMMEDIATE``).

        Commits on success, rolls back on any exception. Nested
        transactions are rejected: the repository is single-writer.
        """
        if self._in_transaction:
            raise PersistenceError("nested transactions are not supported")
        conn = self.connection
        self._in_transaction = True
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.DatabaseError as exc:
            self._in_transaction = False
            raise PersistenceError(f"cannot begin transaction: {exc}") from exc
        try:
            yield conn
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.DatabaseError:
                pass
            raise
        else:
            try:
                conn.execute("COMMIT")
            except sqlite3.DatabaseError as exc:
                logger.error("commit failed for %s: %s", self._db_path, exc)
                raise
        finally:
            self._in_transaction = False

    # ------------------------------------------------------------------
    # Events: append-only audit stream
    # ------------------------------------------------------------------

    _EVENT_COLUMNS = (
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
        "payload_json",
        "checksum",
    )

    @classmethod
    def _event_to_row(cls, event: EventEnvelope) -> dict[str, object]:
        data = event.to_dict()
        payload = data["payload"]
        assert isinstance(payload, dict)
        return {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "ts_event": event.ts_event,
            "ts_collected": event.ts_collected,
            "ts_monotonic": event.ts_monotonic,
            "correlation_id": event.correlation_id,
            "trade_id": event.trade_id,
            "component": event.component,
            "severity": event.severity,
            "schema_version": event.schema_version,
            "payload_json": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            "checksum": event.checksum,
        }

    @classmethod
    def _row_to_event(cls, row: sqlite3.Row) -> EventEnvelope:
        data: dict[str, object] = {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "ts_event": row["ts_event"],
            "ts_collected": row["ts_collected"],
            "ts_monotonic": row["ts_monotonic"],
            "component": row["component"],
            "severity": row["severity"],
            "schema_version": row["schema_version"],
            "checksum": row["checksum"],
        }
        if row["correlation_id"] is not None:
            data["correlation_id"] = row["correlation_id"]
        if row["trade_id"] is not None:
            data["trade_id"] = row["trade_id"]
        data["payload"] = json.loads(row["payload_json"])
        return EventEnvelope.from_dict(data)

    def insert_event(self, event: EventEnvelope) -> InsertResult:
        """Validate, checksum-verify, and append *event* to the audit stream.

        Idempotent by ``event_id``: a repeated event id does not create a
        duplicate row, and the original row is never modified.
        """
        _ = self.connection
        validate_event_dict(event.to_dict())
        if not event.verify_checksum():
            raise PersistenceError(f"refusing to persist event {event.event_id}: checksum mismatch")
        with self.transaction() as conn:
            return self._insert_event_row(conn, event)

    def append_audit_event(self, event: EventEnvelope) -> InsertResult:
        """Alias of :meth:`insert_event` documenting audit-stream semantics."""
        return self.insert_event(event)

    def _insert_event_row(self, conn: sqlite3.Connection, event: EventEnvelope) -> InsertResult:
        row = self._event_to_row(event)
        columns = ", ".join(self._EVENT_COLUMNS)
        placeholders = ", ".join("?" for _ in self._EVENT_COLUMNS)
        cursor = conn.execute(
            f"INSERT OR IGNORE INTO events ({columns}) VALUES ({placeholders})",
            tuple(row[column] for column in self._EVENT_COLUMNS),
        )
        if cursor.rowcount == 1:
            return InsertResult(inserted=True, duplicate=False, identical=True)

        existing = conn.execute(
            "SELECT checksum FROM events WHERE event_id = ?", (event.event_id,)
        ).fetchone()
        if existing is None:
            raise PersistenceError(
                f"insert did not write event {event.event_id} and no duplicate was found"
            )
        if existing["checksum"] == event.checksum:
            return InsertResult(inserted=False, duplicate=True, identical=True)
        raise PersistenceError(
            f"duplicate event_id {event.event_id} with conflicting checksum; "
            "the original event is preserved untouched"
        )

    def insert_event_with_derived(self, event: EventEnvelope) -> InsertResult:
        """Append *event* and project its derived rows in one transaction.

        If projection fails, the whole transaction rolls back: an event
        is never persisted with half-updated derived state.
        """
        _ = self.connection
        validate_event_dict(event.to_dict())
        if not event.verify_checksum():
            raise PersistenceError(f"refusing to persist event {event.event_id}: checksum mismatch")
        with self.transaction() as conn:
            result = self._insert_event_row(conn, event)
            apply_derived_state(conn, event)
            return result

    # ------------------------------------------------------------------
    # Ingestion cursor: durable per-source byte offsets
    # ------------------------------------------------------------------

    def get_ingestion_cursor(self, source_path: str) -> IngestionCursor | None:
        """Return the persisted ingestion cursor for *source_path*."""
        return read_ingestion_cursor(self.connection, source_path)

    def save_ingestion_cursor(self, cursor: IngestionCursor) -> None:
        """Persist *cursor* in its own transaction (progress-only state)."""
        with self.transaction() as conn:
            write_ingestion_cursor(conn, cursor)

    def insert_event_with_cursor(
        self, event: EventEnvelope, cursor: IngestionCursor
    ) -> InsertResult:
        """Append *event* and advance the ingestion cursor atomically.

        The event row and the cursor update are committed in a single
        transaction: the cursor never moves past an event that was not
        durably persisted, so a restart re-reads uncommitted lines and
        the idempotent event insert absorbs the duplicates.
        """
        _ = self.connection
        validate_event_dict(event.to_dict())
        if not event.verify_checksum():
            raise PersistenceError(f"refusing to persist event {event.event_id}: checksum mismatch")
        with self.transaction() as conn:
            result = self._insert_event_row(conn, event)
            write_ingestion_cursor(conn, cursor)
            return result

    def get_event(self, event_id: str) -> EventEnvelope | None:
        """Fetch one event by id; the stored checksum is re-verified."""
        row = self.connection.execute(
            "SELECT * FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            return self._row_to_event(row)
        except Exception as exc:
            raise PersistenceError(f"stored event {event_id} failed validation: {exc}") from exc

    def query_events(
        self,
        *,
        trade_id: str | None = None,
        correlation_id: str | None = None,
        event_type: object | None = None,
        ts_start: str | None = None,
        ts_end: str | None = None,
        limit: int = 1000,
    ) -> list[EventEnvelope]:
        """Query the audit stream with deterministic ordering.

        ISO-8601 UTC strings sort lexicographically, so range filters on
        ``ts_collected`` are deterministic.
        """
        clauses: list[str] = []
        params: list[object] = []
        if trade_id is not None:
            clauses.append("trade_id = ?")
            params.append(trade_id)
        if correlation_id is not None:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)
        if event_type is not None:
            value = event_type.value if isinstance(event_type, EventType) else str(event_type)
            clauses.append("event_type = ?")
            params.append(value)
        if ts_start is not None:
            clauses.append("ts_collected >= ?")
            params.append(ts_start)
        if ts_end is not None:
            clauses.append("ts_collected <= ?")
            params.append(ts_end)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"SELECT * FROM events{where} ORDER BY ts_collected, ts_event, event_id LIMIT ?"
        params.append(limit)
        rows = self.connection.execute(sql, params).fetchall()
        events: list[EventEnvelope] = []
        for row in rows:
            try:
                events.append(self._row_to_event(row))
            except Exception as exc:
                raise PersistenceError(
                    f"stored event {row['event_id']} failed validation: {exc}"
                ) from exc
        return events

    def count_events(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM events").fetchone()
        assert row is not None
        return int(row[0])

    # ------------------------------------------------------------------
    # Derived state: trades / orders / positions / reconciliation
    # ------------------------------------------------------------------

    def upsert_trade(self, trade: TradeRecord) -> None:
        upsert_record(self.connection, "trades", "trade_id", trade)

    def get_trade(self, trade_id: str) -> TradeRecord | None:
        row = self.connection.execute(
            "SELECT * FROM trades WHERE trade_id = ?", (trade_id,)
        ).fetchone()
        return TradeRecord.from_row(row) if row is not None else None

    def upsert_order(self, order: OrderRecord) -> None:
        upsert_record(self.connection, "orders", "broker_order_id", order)

    def upsert_position(self, position: PositionRecord) -> None:
        upsert_record(self.connection, "positions", "broker_position_id", position)

    def insert_reconciliation(self, record: ReconciliationRecord) -> InsertResult:
        """Insert a reconciliation record; duplicates by id are ignored."""
        with self.transaction() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO reconciliation_events "
                "(reconciliation_id, ts, trade_id, local_state_json, "
                "broker_state_json, result, details) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.reconciliation_id,
                    record.ts,
                    record.trade_id,
                    record.local_state_json,
                    record.broker_state_json,
                    record.result,
                    record.details,
                ),
            )
            inserted = cursor.rowcount == 1
            return InsertResult(inserted=inserted, duplicate=not inserted, identical=True)

    def insert_invalid_trade(self, record: InvalidTradeRecord) -> InsertResult:
        """Record an invalid trade; duplicates by trade id are ignored."""
        with self.transaction() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO invalid_trades "
                "(trade_id, invalid_reason, detected_ts, payload_json) "
                "VALUES (?, ?, ?, ?)",
                (
                    record.trade_id,
                    record.invalid_reason,
                    record.detected_ts,
                    record.payload_json,
                ),
            )
            inserted = cursor.rowcount == 1
            return InsertResult(inserted=inserted, duplicate=not inserted, identical=True)

    def open_positions(self) -> list[PositionRecord]:
        rows = self.connection.execute(
            "SELECT * FROM positions WHERE state = 'OPEN' ORDER BY open_ts, broker_position_id"
        ).fetchall()
        return [PositionRecord.from_row(row) for row in rows]

    def open_orders(self) -> list[OrderRecord]:
        rows = self.connection.execute(
            "SELECT * FROM orders WHERE order_state IS NULL "
            "OR order_state NOT IN ('FILLED', 'CANCELLED', 'REJECTED') "
            "ORDER BY submit_ts, broker_order_id"
        ).fetchall()
        return [OrderRecord.from_row(row) for row in rows]

    def save_reconciliation_run(
        self,
        event: EventEnvelope,
        run: ReconciliationRunRecord,
        adoptions: Sequence[AdoptionRecord] = (),
    ) -> InsertResult:
        """Persist a reconciliation run atomically.

        The canonical ``RECONCILIATION`` event (with its derived
        ``reconciliation_events`` row), the run metadata, and any adopted
        broker entities are committed in a single transaction. Any
        failure rolls the whole run back.
        """
        _ = self.connection
        validate_event_dict(event.to_dict())
        if not event.verify_checksum():
            raise PersistenceError(f"refusing to persist event {event.event_id}: checksum mismatch")
        with self.transaction() as conn:
            result = self._insert_event_row(conn, event)
            apply_derived_state(conn, event)
            write_reconciliation_run(conn, run)
            for adoption in adoptions:
                write_reconciliation_adoption(conn, adoption)
            return result

    def get_latest_reconciliation_run(self) -> ReconciliationRunRecord | None:
        """Return the most recent reconciliation run, or None."""
        return read_latest_reconciliation_run(self.connection)

    def recent_reconciliation_runs(self, limit: int = 50) -> list[ReconciliationRunRecord]:
        return read_reconciliation_runs(self.connection, limit=limit)

    def adoptions_for(self, reconciliation_id: str) -> list[AdoptionRecord]:
        return read_adoptions_for(self.connection, reconciliation_id)

    def recent_reconciliations(self, limit: int = 50) -> list[ReconciliationRecord]:
        rows = self.connection.execute(
            "SELECT * FROM reconciliation_events ORDER BY ts DESC, reconciliation_id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [ReconciliationRecord.from_row(row) for row in rows]


__all__ = [
    "DEFAULT_BUSY_TIMEOUT_MS",
    "DEFAULT_SYNCHRONOUS",
    "InsertResult",
    "PersistenceRepository",
]
