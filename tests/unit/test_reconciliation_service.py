"""Reconciliation service behavior: startup, heartbeat, adoption, escalation,
idempotency, restart, failure handling, and safety boundaries."""

from __future__ import annotations

import inspect
import re
import time
from pathlib import Path

import pytest

from collector.event_model import EventType
from collector.persistence import PersistenceError, PersistenceRepository
from collector.persistence.records import OrderRecord, PositionRecord
from collector.reconciliation.broker import BrokerOrder, BrokerPosition, BrokerSnapshot
from collector.reconciliation.errors import ReconciliationError
from collector.reconciliation.mock import StaticBrokerStateProvider
from collector.reconciliation.reconciler import ReconciliationService
from collector.reconciliation.runner import ReconciliationRunner
from collector.reconciliation.types import ReconciliationResult, ReconciliationTrigger, ShadowState

BROKER_POSITION = "broker-position-001"
BROKER_ORDER = "broker-order-001"


def broker_position(
    *,
    position_id: str = BROKER_POSITION,
    direction: str = "BUY",
    volume: float = 0.1,
    open_price: float = 2000.0,
) -> BrokerPosition:
    return BrokerPosition(
        broker_position_id=position_id,
        symbol="XAUUSDc",
        direction=direction,
        volume=volume,
        open_price=open_price,
        broker_state="OPEN",
    )


def broker_order(*, order_id: str = BROKER_ORDER) -> BrokerOrder:
    return BrokerOrder(broker_order_id=order_id, state="PLACED", volume=0.1, price=2000.0)


def local_position(
    *,
    position_id: str = BROKER_POSITION,
    direction: str = "BUY",
    lot: float = 0.1,
) -> PositionRecord:
    return PositionRecord(
        broker_position_id=position_id,
        direction=direction,
        lot=lot,
        open_price=2000.0,
        open_ts="2026-08-14T09:00:00Z",
        state="OPEN",
    )


def local_order(*, order_id: str = BROKER_ORDER) -> OrderRecord:
    return OrderRecord(
        broker_order_id=order_id,
        requested_lot=0.1,
        requested_price=2000.0,
        order_state="PLACED",
    )


@pytest.fixture
def repo(tmp_path: Path) -> PersistenceRepository:
    return PersistenceRepository(tmp_path / "collector.db")


def reconciliation_events(repo: PersistenceRepository):
    return repo.query_events(event_type=EventType.RECONCILIATION, limit=100)


# ----------------------------------------------------------------------
# Startup
# ----------------------------------------------------------------------


def test_startup_empty_state_synced(repo: PersistenceRepository) -> None:
    with repo:
        svc = ReconciliationService(repo, StaticBrokerStateProvider(BrokerSnapshot()))
        stats = svc.run(ReconciliationTrigger.STARTUP)
        assert stats.latest_result == "SYNCED"
        assert stats.reconciliation_success == 1
        assert stats.reconciliation_escalated == 0
        assert svc.shadow_state is ShadowState.SYNCED
        assert svc.is_synced is True
        assert len(reconciliation_events(repo)) == 1


def test_startup_broker_orphan_adopts(repo: PersistenceRepository) -> None:
    with repo:
        provider = StaticBrokerStateProvider(
            BrokerSnapshot(positions=(broker_position(),), orders=(broker_order(),))
        )
        svc = ReconciliationService(repo, provider)
        stats = svc.run(ReconciliationTrigger.STARTUP)
        assert stats.latest_result == "ADOPTED_BROKER"
        assert stats.broker_orphans == 2
        assert svc.shadow_state is ShadowState.ADOPTED_BROKER
        events = reconciliation_events(repo)
        assert len(events) == 1
        assert events[0].payload["result"] == "ADOPTED_BROKER"
        assert events[0].payload["action"] == "ADOPT_BROKER"
        latest = repo.get_latest_reconciliation_run()
        assert latest is not None and latest.result == "ADOPTED_BROKER"
        adoptions = repo.adoptions_for(events[0].payload["reconciliation_id"])
        assert [item.broker_id for item in adoptions] == [BROKER_ORDER, BROKER_POSITION]


def test_startup_local_orphan_escalates(repo: PersistenceRepository) -> None:
    with repo:
        with repo.transaction():
            repo.upsert_position(local_position())
        svc = ReconciliationService(repo, StaticBrokerStateProvider(BrokerSnapshot()))
        stats = svc.run(ReconciliationTrigger.STARTUP)
        assert stats.latest_result == "ESCALATED"
        assert stats.local_orphans == 1
        assert svc.shadow_state is ShadowState.ESCALATED
        assert svc.is_degraded is True
        assert len(reconciliation_events(repo)) == 1


def test_startup_conflicting_position_escalates(repo: PersistenceRepository) -> None:
    with repo:
        with repo.transaction():
            repo.upsert_position(local_position(direction="BUY"))
        provider = StaticBrokerStateProvider(
            BrokerSnapshot(positions=(broker_position(direction="SELL"),))
        )
        svc = ReconciliationService(repo, provider)
        stats = svc.run(ReconciliationTrigger.STARTUP)
        assert stats.latest_result == "ESCALATED"
        assert stats.state_conflicts == 1
        assert len(reconciliation_events(repo)) == 1


def test_missing_fill_evidence_detected_and_adopted(repo: PersistenceRepository) -> None:
    with repo:
        with repo.transaction():
            repo.upsert_order(local_order())
        # local stream only observed the order; broker shows the filled position
        provider = StaticBrokerStateProvider(BrokerSnapshot(positions=(broker_position(),)))
        svc = ReconciliationService(repo, provider)
        stats = svc.run(ReconciliationTrigger.STARTUP)
        assert stats.latest_result == "ADOPTED_BROKER"
        events = reconciliation_events(repo)
        assert events[0].payload["mismatch"] is True
        details = events[0].payload["mismatch_details"]
        assert details["broker_orphans"] == 1


# ----------------------------------------------------------------------
# Heartbeat / idempotency
# ----------------------------------------------------------------------


def test_heartbeat_identical_snapshot_is_skipped(repo: PersistenceRepository) -> None:
    with repo:
        svc = ReconciliationService(repo, StaticBrokerStateProvider(BrokerSnapshot()))
        svc.run(ReconciliationTrigger.STARTUP)
        first_heartbeat = svc.run(ReconciliationTrigger.HEARTBEAT)
        assert first_heartbeat.latest_result == "SYNCED"
        assert first_heartbeat.skipped_identical == 0
        second_heartbeat = svc.run(ReconciliationTrigger.HEARTBEAT)
        assert second_heartbeat.skipped_identical == 1
        # startup + first heartbeat recorded; identical heartbeats skipped
        assert len(reconciliation_events(repo)) == 2


def test_heartbeat_detects_new_mismatch(repo: PersistenceRepository) -> None:
    with repo:
        provider = StaticBrokerStateProvider(BrokerSnapshot())
        svc = ReconciliationService(repo, provider)
        svc.run(ReconciliationTrigger.STARTUP)
        provider.set_snapshot(BrokerSnapshot(positions=(broker_position(),)))
        stats = svc.run(ReconciliationTrigger.HEARTBEAT)
        assert stats.latest_result == "ADOPTED_BROKER"
        assert stats.skipped_identical == 0
        assert len(reconciliation_events(repo)) == 2


def test_repeated_snapshot_never_duplicates_events(repo: PersistenceRepository) -> None:
    with repo:
        provider = StaticBrokerStateProvider(BrokerSnapshot())
        svc = ReconciliationService(repo, provider)
        svc.run(ReconciliationTrigger.STARTUP)
        svc.run(ReconciliationTrigger.HEARTBEAT)
        skipped = svc.run(ReconciliationTrigger.HEARTBEAT)
        assert skipped.skipped_identical == 1
        provider.set_snapshot(BrokerSnapshot(positions=(broker_position(),)))
        svc.run(ReconciliationTrigger.HEARTBEAT)
        svc.run(ReconciliationTrigger.HEARTBEAT)
        # startup + 1st heartbeat + adopted heartbeat = 3 events, no duplicates
        assert len(reconciliation_events(repo)) == 3
        assert len(repo.recent_reconciliation_runs()) == 3


def test_runner_heartbeat_interval_honored(repo: PersistenceRepository) -> None:
    runner = ReconciliationRunner(
        repo, StaticBrokerStateProvider(BrokerSnapshot()), interval_seconds=60.0
    )
    runner.start()
    assert runner.startup_stats is not None
    assert runner.startup_stats.latest_result == "SYNCED"
    assert runner.maybe_heartbeat() is None
    runner._last_heartbeat_monotonic = time.monotonic() - 61.0
    stats = runner.maybe_heartbeat()
    assert stats is not None
    assert stats.latest_result == "SYNCED"
    assert stats.skipped_identical == 0
    runner.close()


# ----------------------------------------------------------------------
# Restart safety
# ----------------------------------------------------------------------


def test_restart_retains_shadow_state_and_skips_duplicate_startup(
    repo: PersistenceRepository,
) -> None:
    repo.open()
    svc = ReconciliationService(repo, StaticBrokerStateProvider(BrokerSnapshot()))
    svc.run(ReconciliationTrigger.STARTUP)
    repo.close()

    repo.open()
    restored = ReconciliationService(repo, StaticBrokerStateProvider(BrokerSnapshot()))
    assert restored.shadow_state is ShadowState.SYNCED
    stats = restored.run(ReconciliationTrigger.STARTUP)
    assert stats.skipped_identical == 1
    assert len(reconciliation_events(repo)) == 1
    repo.close()


def test_same_snapshot_after_escalation_stays_escalated(repo: PersistenceRepository) -> None:
    with repo:
        with repo.transaction():
            repo.upsert_position(local_position())
        svc = ReconciliationService(repo, StaticBrokerStateProvider(BrokerSnapshot()))
        svc.run(ReconciliationTrigger.STARTUP)
        stats = svc.run(ReconciliationTrigger.HEARTBEAT)
        assert stats.latest_result == "ESCALATED"
        stats = svc.run(ReconciliationTrigger.HEARTBEAT)
        assert stats.skipped_identical == 1
        assert len(reconciliation_events(repo)) == 2


# ----------------------------------------------------------------------
# Failure handling
# ----------------------------------------------------------------------


def test_broker_unavailable_does_not_claim_synced(repo: PersistenceRepository) -> None:
    with repo:
        provider = StaticBrokerStateProvider(BrokerSnapshot(), unavailable=True)
        svc = ReconciliationService(repo, provider)
        stats = svc.run(ReconciliationTrigger.STARTUP)
        assert stats.snapshot_available is False
        assert stats.latest_result is None
        assert stats.reconciliation_success == 0
        assert len(reconciliation_events(repo)) == 0
        assert svc.shadow_state is ShadowState.UNKNOWN
        timeouts = repo.query_events(event_type=EventType.TIMEOUT, limit=10)
        assert len(timeouts) == 1
        assert timeouts[0].payload["timeout_code"] == "RECONCILIATION_SNAPSHOT_UNAVAILABLE"


def test_persistence_failure_raises_and_keeps_state(
    repo: PersistenceRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    with repo:
        svc = ReconciliationService(repo, StaticBrokerStateProvider(BrokerSnapshot()))
        svc.run(ReconciliationTrigger.STARTUP)

        def failing_save(*args, **kwargs):
            raise PersistenceError("disk full (simulated)")

        monkeypatch.setattr(repo, "save_reconciliation_run", failing_save)
        provider = StaticBrokerStateProvider(BrokerSnapshot(positions=(broker_position(),)))
        failing = ReconciliationService(repo, provider)
        with pytest.raises(ReconciliationError):
            failing.run(ReconciliationTrigger.HEARTBEAT)
        # no duplicate corruption: only the startup SYNCED run exists
        assert len(reconciliation_events(repo)) == 1
        assert len(repo.recent_reconciliation_runs()) == 1


# ----------------------------------------------------------------------
# MISMATCH / POST_EXECUTION triggers
# ----------------------------------------------------------------------


def test_mismatch_and_post_execution_triggers_recorded(repo: PersistenceRepository) -> None:
    with repo:
        provider = StaticBrokerStateProvider(BrokerSnapshot(positions=(broker_position(),)))
        svc = ReconciliationService(repo, provider)
        svc.run(ReconciliationTrigger.MISMATCH)
        svc.run(ReconciliationTrigger.POST_EXECUTION)
        events = reconciliation_events(repo)
        assert {event.payload["trigger"] for event in events} == {"MISMATCH", "POST_EXECUTION"}


def test_runner_post_execution_hook(repo: PersistenceRepository) -> None:
    runner = ReconciliationRunner(repo, StaticBrokerStateProvider(BrokerSnapshot()))
    runner.start()
    stats = runner.reconcile_post_execution()
    assert stats.latest_result == "SYNCED"
    runner.close()


# ----------------------------------------------------------------------
# Safety: no execution capability
# ----------------------------------------------------------------------


def test_reconciliation_never_uses_execution_capability() -> None:
    import collector.reconciliation as package
    from collector.reconciliation import broker, reconciler, runner

    for module in (package, broker, reconciler, runner):
        source = inspect.getsource(module)
        for forbidden in (
            "submit_order(",
            "modify_order(",
            "close_position(",
            "cancel_order(",
            "place_order(",
            "order_management",
            "risk_engine",
            "lot_sizing",
        ):
            assert forbidden not in source, (
                f"{module.__name__} contains forbidden capability {forbidden!r}"
            )
    # the only broker-facing capability is the read-only snapshot
    source = inspect.getsource(broker)
    assert re.search(r"def snapshot\(self\)", source) is not None
    for forbidden in ("def submit", "def modify", "def close", "def delete"):
        assert forbidden not in source


def test_contract_result_vocabulary_never_extended() -> None:
    from collector.reconciliation.types import DiffClassification

    # internal classifications exist but must never leak into events
    assert DiffClassification.RECOVERABLE.value == "RECOVERABLE"
    assert {result.value for result in ReconciliationResult} == {
        "SYNCED",
        "ADOPTED_BROKER",
        "ESCALATED",
    }
