"""Deterministic, transactional schema migrations.

Migrations are plain ordered SQL batches recorded in
``schema_migrations``. Each migration runs inside its own transaction;
already-applied versions are skipped, so re-running migrations never
damages the database. No external migration framework is used.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from collector.event_model.timestamps import now_utc_ms
from collector.persistence.errors import PersistenceError
from collector.persistence.schema import SCHEMA_MIGRATIONS_DDL, SCHEMA_STATEMENTS


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(version=1, name="initial_schema", statements=SCHEMA_STATEMENTS),
)


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Return the set of migration versions already applied to *conn*."""
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {int(row[0]) for row in rows}


def apply_migrations(conn: sqlite3.Connection) -> tuple[int, ...]:
    """Apply pending migrations in order; returns newly applied versions.

    The ``schema_migrations`` table is created first (idempotently), then
    each pending migration runs inside ``BEGIN IMMEDIATE``/``COMMIT`` with
    full rollback on failure.
    """
    conn.execute(SCHEMA_MIGRATIONS_DDL)
    applied = applied_versions(conn)
    newly_applied: list[int] = []

    for migration in MIGRATIONS:
        if migration.version in applied:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in migration.statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (migration.version, migration.name, now_utc_ms()),
            )
            conn.execute("COMMIT")
        except sqlite3.DatabaseError as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.DatabaseError:
                pass
            raise PersistenceError(
                f"migration {migration.version} ({migration.name}) failed: {exc}"
            ) from exc
        newly_applied.append(migration.version)

    return tuple(newly_applied)


__all__ = ["MIGRATIONS", "Migration", "applied_versions", "apply_migrations"]
