"""Durable ingestion cursor state for the JSONL adapter.

The cursor records how much of a source file has been durably consumed:

* ``source_path`` - logical source identifier (as configured)
* ``byte_offset`` - byte position of the next un-consumed line; the
  invariant is that this always points at a line boundary (the start of
  the currently held partial line, or EOF)
* ``line_number`` - informational running line counter (optional)
* ``last_event_id`` - identity of the last successfully persisted event
* ``updated_ts`` - UTC wall clock of the last commit

The cursor is advanced only after an event has been successfully
persisted; the persistence layer commits event + cursor in one
transaction (see ``PersistenceRepository.insert_event_with_cursor``).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from collector.event_model.timestamps import now_utc_ms


@dataclass(frozen=True)
class IngestionCursor:
    """Immutable snapshot of per-source ingestion progress."""

    source_path: str
    byte_offset: int
    line_number: int | None
    last_event_id: str | None
    updated_ts: str

    @classmethod
    def of(
        cls,
        source_path: str,
        byte_offset: int,
        *,
        line_number: int | None = None,
        last_event_id: str | None = None,
    ) -> IngestionCursor:
        """Create a new cursor stamped with the current UTC time."""
        return cls(
            source_path=source_path,
            byte_offset=byte_offset,
            line_number=line_number,
            last_event_id=last_event_id,
            updated_ts=now_utc_ms(),
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> IngestionCursor:
        return cls(
            source_path=row["source_path"],
            byte_offset=int(row["byte_offset"]),
            line_number=row["line_number"],
            last_event_id=row["last_event_id"],
            updated_ts=row["updated_ts"],
        )

    def to_params(self) -> tuple[str, int, int | None, str | None, str]:
        return (
            self.source_path,
            self.byte_offset,
            self.line_number,
            self.last_event_id,
            self.updated_ts,
        )


def read_ingestion_cursor(conn: sqlite3.Connection, source_path: str) -> IngestionCursor | None:
    """Return the persisted cursor for *source_path*, or ``None``."""
    row = conn.execute(
        "SELECT source_path, byte_offset, line_number, last_event_id, updated_ts "
        "FROM ingestion_cursor WHERE source_path = ?",
        (source_path,),
    ).fetchone()
    return IngestionCursor.from_row(row) if row is not None else None


def write_ingestion_cursor(conn: sqlite3.Connection, cursor: IngestionCursor) -> None:
    """Upsert *cursor*; the newest snapshot wins (mutable progress state)."""
    conn.execute(
        "INSERT INTO ingestion_cursor "
        "(source_path, byte_offset, line_number, last_event_id, updated_ts) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(source_path) DO UPDATE SET "
        "byte_offset = excluded.byte_offset, "
        "line_number = excluded.line_number, "
        "last_event_id = excluded.last_event_id, "
        "updated_ts = excluded.updated_ts",
        cursor.to_params(),
    )


__all__ = ["IngestionCursor", "read_ingestion_cursor", "write_ingestion_cursor"]
