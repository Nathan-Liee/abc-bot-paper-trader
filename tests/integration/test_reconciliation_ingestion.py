"""Integration: JSONL ingestion -> Persistence -> Reconciliation.

Drives the production ingestion path over the committed synthetic
bridge fixture into SQLite, then runs reconciliation against a mock
broker provider (no live MT5/HFM connectivity), and asserts a
contract-valid RECONCILIATION event was persisted.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from collector.adapters.pipeline import IngestionPipeline
from collector.adapters.reader import JsonlFileReader
from collector.event_model import EventType
from collector.persistence import PersistenceRepository
from collector.reconciliation.broker import BrokerPosition, BrokerSnapshot
from collector.reconciliation.mock import StaticBrokerStateProvider
from collector.reconciliation.reconciler import ReconciliationService
from collector.reconciliation.types import ReconciliationTrigger
from collector.settings import PROJECT_ROOT

SCHEMA_PATH = PROJECT_ROOT / "shared" / "schemas" / "canonical-event.schema.json"
FIXTURE = PROJECT_ROOT / "tests" / "replay" / "fixtures" / "bridge_raw_mixed.jsonl"


def ingest_fixture(repo: PersistenceRepository) -> None:
    pipeline = IngestionPipeline(repo, JsonlFileReader(FIXTURE, start_offset=0))
    stats = pipeline.stats()
    while True:
        stats = pipeline.process_once()
        if not stats.lines_read or not pipeline.reader.holds_partial:
            break


def test_ingestion_then_reconciliation_persists_valid_event(tmp_path: Path) -> None:
    repo = PersistenceRepository(tmp_path / "collector.db")
    repo.open()
    try:
        ingest_fixture(repo)
        assert repo.count_events() == 4
        assert repo.get_ingestion_cursor(str(FIXTURE)) is not None

        service = ReconciliationService(repo, StaticBrokerStateProvider(BrokerSnapshot()))
        stats = service.run(ReconciliationTrigger.STARTUP)
        assert stats.latest_result == "SYNCED"

        events = repo.query_events(event_type=EventType.RECONCILIATION, limit=10)
        assert len(events) == 1
        event = events[0]
        assert event.verify_checksum() is True
        assert event.payload["trigger"] == "STARTUP"
        assert event.payload["mismatch"] is False
        assert event.payload["result"] == "SYNCED"

        with SCHEMA_PATH.open(encoding="utf-8") as fh:
            schema = json.load(fh)
        Draft202012Validator(schema).validate(event.to_dict())

        derived = repo.connection.execute(
            "SELECT * FROM reconciliation_events WHERE reconciliation_id = ?",
            (event.payload["reconciliation_id"],),
        ).fetchone()
        assert derived is not None
        assert derived["result"] == "SYNCED"
    finally:
        repo.close()


def test_ingestion_then_broker_orphan_creates_traceable_adoption(tmp_path: Path) -> None:
    repo = PersistenceRepository(tmp_path / "collector.db")
    repo.open()
    try:
        ingest_fixture(repo)
        provider = StaticBrokerStateProvider(
            BrokerSnapshot(
                positions=(
                    BrokerPosition(
                        broker_position_id="broker-position-001",
                        symbol="XAUUSDc",
                        direction="BUY",
                        volume=0.1,
                        open_price=2000.0,
                        broker_state="OPEN",
                    ),
                ),
            )
        )
        service = ReconciliationService(repo, provider)
        stats = service.run(ReconciliationTrigger.HEARTBEAT)
        assert stats.latest_result == "ADOPTED_BROKER"
        assert stats.broker_orphans == 1

        events = repo.query_events(event_type=EventType.RECONCILIATION, limit=10)
        adoption_event = next(e for e in events if e.payload["result"] == "ADOPTED_BROKER")
        assert adoption_event.payload["mismatch"] is True
        adoptions = repo.adoptions_for(adoption_event.payload["reconciliation_id"])
        assert len(adoptions) == 1
        adopted = adoptions[0]
        # broker ids preserved verbatim; lineage recorded
        assert adopted.broker_id == "broker-position-001"
        assert adopted.symbol == "XAUUSDc"
        assert adopted.reason
        assert adopted.reconciliation_id == adoption_event.payload["reconciliation_id"]

        # identical heartbeat is idempotent: no duplicate events
        again = service.run(ReconciliationTrigger.HEARTBEAT)
        assert again.skipped_identical == 1
        assert len(repo.query_events(event_type=EventType.RECONCILIATION, limit=10)) == 1
        assert len(repo.adoptions_for(adoption_event.payload["reconciliation_id"])) == 1
    finally:
        repo.close()
