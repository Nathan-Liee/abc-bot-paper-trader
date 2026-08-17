"""Durable execution journal — SQLite WAL, append-only audit + keyed state.

Follows the repository persistence conventions (``collector/persistence``):
WAL mode, idempotent DDL, append-only triggers, keyed projection table on
top of the immutable audit trail.

Two tables:

* ``execution_journal``        append-only audit (no UPDATE/DELETE allowed)
* ``execution_commands``       keyed projection (command_id PK, latest
                               state + latest result) for idempotency lookups

``state`` bookkeeping is write-ahead: a command is journaled as SUBMITTED
BEFORE the executor is invoked, so a crash between journal write and
broker call is always recovered as "reconcile first".

Active-trade uniqueness (one command per live trade) is enforced by a
partial unique index on non-terminal trades.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from execution.errors import DuplicateCommandError, JournalError
from execution.models import (
    CommandState,
    ExecutionCommand,
    ExecutionResult,
    now_iso,
)

_SCHEMA_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS execution_commands (
        command_id TEXT PRIMARY KEY,
        trade_id TEXT NOT NULL,
        state TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_ts TEXT NOT NULL,
        updated_ts TEXT NOT NULL,
        result_json TEXT
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_execution_commands_active_trade
        ON execution_commands(trade_id)
        WHERE state NOT IN ('CLOSED', 'REJECTED', 'FAILED', 'EXPIRED')
    """,
    """
    CREATE TABLE IF NOT EXISTS execution_journal (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        command_id TEXT NOT NULL,
        trade_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        state TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        ts TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_execution_journal_command
        ON execution_journal(command_id, seq)
    """,
    """
    CREATE TRIGGER IF NOT EXISTS execution_journal_no_update
    BEFORE UPDATE ON execution_journal
    BEGIN
        SELECT RAISE(ABORT, 'execution_journal is append-only: UPDATE is forbidden');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS execution_journal_no_delete
    BEFORE DELETE ON execution_journal
    BEGIN
        SELECT RAISE(ABORT, 'execution_journal is append-only: DELETE is forbidden');
    END
    """,
)


@dataclass(frozen=True)
class StoredCommand:
    """Projected current state of one command."""

    command_id: str
    trade_id: str
    state: CommandState
    payload: dict[str, Any]
    created_ts: str
    updated_ts: str
    result: ExecutionResult | None = None


@dataclass(frozen=True)
class JournalEvent:
    """One append-only audit line."""

    seq: int
    command_id: str
    trade_id: str
    event_type: str
    state: CommandState
    payload: dict[str, Any]
    ts: str


class ExecutionJournal:
    """Durable command journal (idempotency + lifecycle persistence)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        try:
            for statement in _SCHEMA_DDL:
                self._conn.execute(statement)
            self._conn.commit()
        except sqlite3.DatabaseError as exc:
            raise JournalError(f"journal schema initialization failed: {exc}") from exc

    def close(self) -> None:
        self._conn.close()

    @property
    def db_path(self) -> str:
        return self._db_path

    # -- writes -----------------------------------------------------------

    def create_command(self, command: ExecutionCommand) -> None:
        """Persist a new command. Refuses duplicate command_id or an
        already-active trade_id (idempotency + one-command-per-trade)."""
        payload = json.dumps(command.to_dict(), sort_keys=True)
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO execution_commands "
                    "(command_id, trade_id, state, payload_json, created_ts, updated_ts) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        command.command_id,
                        command.trade_id,
                        CommandState.CREATED.value,
                        payload,
                        command.created_at,
                        now_iso(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateCommandError(
                f"command or active trade already exists: {command.command_id}"
            ) from exc

    def record(
        self,
        command: ExecutionCommand,
        event_type: str,
        state: CommandState,
        payload: dict[str, Any] | None = None,
    ) -> int:
        """Append an audit line and update the commands projection atomically.

        Returns the append-only journal sequence number.
        """
        payload_json = json.dumps(payload or {}, sort_keys=True)
        ts = now_iso()
        try:
            with self._conn:
                cursor = self._conn.execute(
                    "INSERT INTO execution_journal "
                    "(command_id, trade_id, event_type, state, payload_json, ts) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        command.command_id,
                        command.trade_id,
                        event_type,
                        state.value,
                        payload_json,
                        ts,
                    ),
                )
                self._conn.execute(
                    "UPDATE execution_commands SET state = ?, updated_ts = ? WHERE command_id = ?",
                    (state.value, ts, command.command_id),
                )
        except sqlite3.DatabaseError as exc:
            raise JournalError(f"journal append failed: {exc}") from exc
        seq = cursor.lastrowid
        if seq is None:
            raise JournalError("journal append failed: no sequence returned")
        return int(seq)

    def store_result(self, command: ExecutionCommand, result: ExecutionResult) -> None:
        """Persist the latest result into the projection (audit already
        appended via record())."""
        result_json = json.dumps(result.to_dict(), sort_keys=True)
        try:
            with self._conn:
                self._conn.execute(
                    "UPDATE execution_commands SET result_json = ?, updated_ts = ? "
                    "WHERE command_id = ?",
                    (result_json, now_iso(), command.command_id),
                )
        except sqlite3.DatabaseError as exc:
            raise JournalError(f"journal result store failed: {exc}") from exc

    # -- reads ------------------------------------------------------------

    def get_command(self, command_id: str) -> StoredCommand | None:
        row = self._conn.execute(
            "SELECT * FROM execution_commands WHERE command_id = ?", (command_id,)
        ).fetchone()
        return self._row_to_stored(row) if row is not None else None

    def get_active_for_trade(self, trade_id: str) -> StoredCommand | None:
        row = self._conn.execute(
            "SELECT * FROM execution_commands WHERE trade_id = ? "
            "AND state NOT IN ('CLOSED', 'REJECTED', 'FAILED', 'EXPIRED') "
            "ORDER BY created_ts DESC LIMIT 1",
            (trade_id,),
        ).fetchone()
        return self._row_to_stored(row) if row is not None else None

    def get_result(self, command_id: str) -> ExecutionResult | None:
        stored = self.get_command(command_id)
        return stored.result if stored is not None else None

    def active_commands(self) -> list[StoredCommand]:
        """Every command in a non-terminal state (restart recovery input)."""
        rows = self._conn.execute(
            "SELECT * FROM execution_commands WHERE state NOT IN "
            "('CLOSED', 'REJECTED', 'FAILED', 'EXPIRED') "
            "ORDER BY created_ts",
        ).fetchall()
        return [self._row_to_stored(row) for row in rows]

    def events(self, command_id: str) -> list[JournalEvent]:
        rows = self._conn.execute(
            "SELECT * FROM execution_journal WHERE command_id = ? ORDER BY seq",
            (command_id,),
        ).fetchall()
        return [
            JournalEvent(
                seq=int(row["seq"]),
                command_id=str(row["command_id"]),
                trade_id=str(row["trade_id"]),
                event_type=str(row["event_type"]),
                state=CommandState(str(row["state"])),
                payload=json.loads(str(row["payload_json"])),
                ts=str(row["ts"]),
            )
            for row in rows
        ]

    def event_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM execution_journal").fetchone()
        return int(row["n"]) if row is not None else 0

    def command_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM execution_commands").fetchone()
        return int(row["n"]) if row is not None else 0

    def _row_to_stored(self, row: sqlite3.Row) -> StoredCommand:
        result: ExecutionResult | None = None
        result_json = row["result_json"]
        if result_json:
            result = ExecutionResult.from_dict(json.loads(str(result_json)))
        return StoredCommand(
            command_id=str(row["command_id"]),
            trade_id=str(row["trade_id"]),
            state=CommandState(str(row["state"])),
            payload=json.loads(str(row["payload_json"])),
            created_ts=str(row["created_ts"]),
            updated_ts=str(row["updated_ts"]),
            result=result,
        )


__all__ = ["ExecutionJournal", "JournalEvent", "StoredCommand"]
