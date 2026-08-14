"""Non-destructive integrity verification tests."""

from __future__ import annotations

from pathlib import Path

from collector.event_model import EventType, build_event
from collector.persistence import ERROR, PASS, WARNING, PersistenceRepository
from collector.persistence.integrity import run_integrity_checks
from tests.unit.event_factories import TRADE_ID, tick_payload


def _repo(tmp_path: Path) -> PersistenceRepository:
    return PersistenceRepository(tmp_path / "collector.db")


def test_clean_database_reports_all_pass(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        repo.insert_event(event)
        report = run_integrity_checks(repo.connection)
        assert report.status == PASS
        assert all(check.passed for check in report.checks)
        names = {check.name for check in report.checks}
        assert names == {
            "quick_check",
            "event_count",
            "duplicate_event_ids",
            "checksum_verification",
            "orphan_orders",
            "orphan_positions",
            "orphan_reconciliation_events",
            "orphan_market_snapshots",
            "closed_positions_incomplete",
        }
        event_count = next(c for c in report.checks if c.name == "event_count")
        assert "1" in event_count.detail


def test_tampered_checksum_is_reported_as_error(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        event = build_event(EventType.TICK_RECEIVED, tick_payload(), trade_id=TRADE_ID)
        other = build_event(EventType.TICK_RECEIVED, tick_payload(bid=3000.0), trade_id=TRADE_ID)
        repo.insert_event(event)
        row = PersistenceRepository._event_to_row(other)
        row["checksum"] = "sha256:" + "0" * 64
        repo.connection.execute(
            "INSERT INTO events (event_id, event_type, ts_event, ts_collected, "
            "ts_monotonic, correlation_id, trade_id, component, severity, "
            "schema_version, payload_json, checksum) "
            "VALUES (:event_id, :event_type, :ts_event, :ts_collected, :ts_monotonic, "
            ":correlation_id, :trade_id, :component, :severity, :schema_version, "
            ":payload_json, :checksum)",
            row,
        )
        report = run_integrity_checks(repo.connection)
        assert report.status == ERROR
        checksum_check = next(c for c in report.checks if c.name == "checksum_verification")
        assert checksum_check.status == ERROR
        assert other.event_id in checksum_check.detail


def test_orphan_derived_rows_are_warnings(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        repo.connection.execute(
            "INSERT INTO orders (broker_order_id, trade_id, order_state, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("bo-orphan", TRADE_ID, "FILLED", "2026-08-14T09:00:00.000Z"),
        )
        report = run_integrity_checks(repo.connection)
        orphan = next(c for c in report.checks if c.name == "orphan_orders")
        assert orphan.status == WARNING
        assert "1 row(s)" in orphan.detail


def test_closed_position_without_close_data_is_warning(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        repo.connection.execute(
            "INSERT INTO positions (broker_position_id, trade_id, state, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("bp-bad", TRADE_ID, "CLOSED", "2026-08-14T09:00:00.000Z"),
        )
        report = run_integrity_checks(repo.connection)
        bad = next(c for c in report.checks if c.name == "closed_positions_incomplete")
        assert bad.status == WARNING
        assert report.status == WARNING


def test_event_count_check_reports_zero_for_empty_db(tmp_path: Path) -> None:
    with _repo(tmp_path) as repo:
        report = run_integrity_checks(repo.connection)
        assert report.status == PASS
        event_count = next(c for c in report.checks if c.name == "event_count")
        assert "0 event(s)" in event_count.detail
