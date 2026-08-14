"""Non-destructive integrity verification for the persistence layer.

Reports PASS / WARNING / ERROR per check and a single aggregated
status. Nothing here repairs data; detection only.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from collector.event_model.envelope import EventEnvelope
from collector.event_model.validation import validate_event_dict

PASS = "PASS"
WARNING = "WARNING"
ERROR = "ERROR"
STATUSES = (PASS, WARNING, ERROR)


@dataclass(frozen=True)
class IntegrityCheck:
    name: str
    status: str = PASS
    detail: str = "ok"

    @property
    def passed(self) -> bool:
        return self.status == PASS


@dataclass
class IntegrityReport:
    checks: list[IntegrityCheck] = field(default_factory=list)

    @property
    def status(self) -> str:
        for candidate in (ERROR, WARNING, PASS):
            if any(check.status == candidate for check in self.checks):
                return candidate
        return PASS

    def add(self, name: str, status: str, detail: str) -> None:
        assert status in STATUSES
        self.checks.append(IntegrityCheck(name=name, status=status, detail=detail))


def run_integrity_checks(conn: sqlite3.Connection) -> IntegrityReport:
    """Run the standard battery of integrity checks on *conn* (read-only)."""
    report = IntegrityReport()

    quick = conn.execute("PRAGMA quick_check").fetchone()
    if quick is None or quick[0] != "ok":
        report.add("quick_check", ERROR, f"quick_check returned {quick!r}")
    else:
        report.add("quick_check", PASS, "ok")

    count_row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
    count = int(count_row[0]) if count_row is not None else 0
    report.add("event_count", PASS, f"{count} event(s)")

    duplicates = conn.execute(
        "SELECT event_id, COUNT(*) AS n FROM events GROUP BY event_id HAVING COUNT(*) > 1"
    ).fetchall()
    if duplicates:
        detail = ", ".join(f"{row['event_id']}x{row['n']}" for row in duplicates)
        report.add("duplicate_event_ids", ERROR, detail)
    else:
        report.add("duplicate_event_ids", PASS, "ok")

    _verify_checksums(conn, report)

    for table in ("orders", "positions", "reconciliation_events", "market_snapshots"):
        orphans = conn.execute(
            f"SELECT COUNT(*) FROM {table} t WHERE t.trade_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM events e WHERE e.trade_id = t.trade_id)"
        ).fetchone()
        n = int(orphans[0]) if orphans is not None else 0
        if n:
            report.add(
                f"orphan_{table}",
                WARNING,
                f"{n} row(s) reference trade_id(s) absent from the event stream",
            )
        else:
            report.add(f"orphan_{table}", PASS, "ok")

    bad_positions = conn.execute(
        "SELECT COUNT(*) FROM positions p WHERE p.state = 'CLOSED' "
        "AND (p.close_price IS NULL OR p.close_ts IS NULL)"
    ).fetchone()
    n = int(bad_positions[0]) if bad_positions is not None else 0
    if n:
        detail = f"{n} closed position(s) lack close data"
        report.add("closed_positions_incomplete", WARNING, detail)
    else:
        report.add("closed_positions_incomplete", PASS, "ok")

    return report


def _verify_checksums(conn: sqlite3.Connection, report: IntegrityReport) -> None:
    rows = conn.execute(
        "SELECT event_id, event_type, ts_event, ts_collected, ts_monotonic, "
        "correlation_id, trade_id, component, severity, schema_version, "
        "payload_json, checksum FROM events"
    ).fetchall()
    mismatches: list[str] = []
    for row in rows:
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
        try:
            data["payload"] = json.loads(row["payload_json"])
            validate_event_dict(data)
            envelope = EventEnvelope.from_dict(data)
            if not envelope.verify_checksum():
                mismatches.append(row["event_id"])
        except Exception:
            mismatches.append(f"{row['event_id']}(invalid)")
    if mismatches:
        report.add("checksum_verification", ERROR, f"mismatch(es): {', '.join(mismatches)}")
    else:
        report.add("checksum_verification", PASS, "ok")


__all__ = ["ERROR", "PASS", "WARNING", "IntegrityCheck", "IntegrityReport", "run_integrity_checks"]
