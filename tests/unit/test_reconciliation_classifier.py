"""Pure comparison-rule tests for the reconciliation classifier."""

from __future__ import annotations

from collector.persistence.records import OrderRecord, PositionRecord
from collector.reconciliation.broker import BrokerOrder, BrokerPosition, BrokerSnapshot
from collector.reconciliation.classifier import classify
from collector.reconciliation.types import (
    DiffClassification,
    ReconciliationResult,
)

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


def local_position(
    *,
    position_id: str = BROKER_POSITION,
    direction: str = "BUY",
    lot: float = 0.1,
    open_price: float = 2000.0,
) -> PositionRecord:
    return PositionRecord(
        broker_position_id=position_id,
        direction=direction,
        lot=lot,
        open_price=open_price,
        open_ts="2026-08-14T09:00:00Z",
        state="OPEN",
    )


def broker_order(
    *,
    order_id: str = BROKER_ORDER,
    volume: float = 0.1,
    price: float = 2000.0,
) -> BrokerOrder:
    return BrokerOrder(
        broker_order_id=order_id,
        symbol="XAUUSDc",
        order_type="MARKET",
        volume=volume,
        price=price,
        state="PLACED",
    )


def local_order(
    *,
    order_id: str = BROKER_ORDER,
    volume: float = 0.1,
    price: float = 2000.0,
) -> OrderRecord:
    return OrderRecord(
        broker_order_id=order_id,
        requested_lot=volume,
        requested_price=price,
        order_state="PLACED",
    )


def _classification(outcome, broker_id: str) -> DiffClassification:
    for diff in outcome.diffs:
        if diff.broker_id == broker_id:
            return diff.classification
    raise AssertionError(f"no diff for {broker_id}")


def test_empty_local_and_broker_synced() -> None:
    outcome = classify([], [], BrokerSnapshot())
    assert outcome.result is ReconciliationResult.SYNCED
    assert outcome.action == "NONE"
    assert outcome.mismatch is False
    assert outcome.diffs == ()


def test_matching_position_and_order_synced() -> None:
    outcome = classify(
        [local_position()],
        [local_order()],
        BrokerSnapshot(positions=(broker_position(),), orders=(broker_order(),)),
    )
    assert outcome.result is ReconciliationResult.SYNCED
    assert outcome.mismatch is False
    assert _classification(outcome, BROKER_POSITION) is DiffClassification.NO_MISMATCH
    assert _classification(outcome, BROKER_ORDER) is DiffClassification.NO_MISMATCH


def test_broker_only_position_is_recoverable() -> None:
    outcome = classify([], [], BrokerSnapshot(positions=(broker_position(),)))
    assert outcome.result is ReconciliationResult.ADOPTED_BROKER
    assert outcome.action == "ADOPT_BROKER"
    assert outcome.mismatch is True
    assert outcome.broker_orphans == 1
    assert _classification(outcome, BROKER_POSITION) is DiffClassification.RECOVERABLE


def test_local_orphan_position_is_escalated() -> None:
    outcome = classify([local_position()], [], BrokerSnapshot())
    assert outcome.result is ReconciliationResult.ESCALATED
    assert outcome.action == "ESCALATE"
    assert outcome.local_orphans == 1
    assert _classification(outcome, BROKER_POSITION) is DiffClassification.MISSING_BROKER


def test_conflicting_direction_is_escalated() -> None:
    outcome = classify(
        [local_position(direction="BUY")],
        [],
        BrokerSnapshot(positions=(broker_position(direction="SELL"),)),
    )
    assert outcome.result is ReconciliationResult.ESCALATED
    assert outcome.state_conflicts == 1
    assert _classification(outcome, BROKER_POSITION) is DiffClassification.CONFLICTING_STATE


def test_conflicting_volume_is_escalated() -> None:
    outcome = classify(
        [local_position(lot=0.1)],
        [],
        BrokerSnapshot(positions=(broker_position(volume=1.0),)),
    )
    assert outcome.result is ReconciliationResult.ESCALATED
    assert _classification(outcome, BROKER_POSITION) is DiffClassification.CONFLICTING_STATE


def test_float_tolerance_absorbed() -> None:
    outcome = classify(
        [local_position(open_price=2000.0)],
        [],
        BrokerSnapshot(positions=(broker_position(open_price=2000.0000001),)),
    )
    assert outcome.result is ReconciliationResult.SYNCED


def test_conflicting_identity_escalates_over_adoption() -> None:
    # broker has position A (adoptable), local has position B (orphan):
    # overall result must be ESCALATED, not ADOPTED_BROKER.
    outcome = classify(
        [local_position(position_id="local-B")],
        [],
        BrokerSnapshot(positions=(broker_position(position_id="broker-A"),)),
    )
    assert outcome.result is ReconciliationResult.ESCALATED
    assert outcome.broker_orphans == 1
    assert outcome.local_orphans == 1


def test_missing_fill_evidence_detected() -> None:
    # Local only knows an open order (no POSITION_OPENED observed);
    # the broker snapshot shows the position: the broker is the actual
    # evidence and the local stream is incomplete -> adoptable.
    outcome = classify(
        [],
        [local_order()],
        BrokerSnapshot(positions=(broker_position(),)),
    )
    assert outcome.result is ReconciliationResult.ADOPTED_BROKER
    assert _classification(outcome, BROKER_POSITION) is DiffClassification.RECOVERABLE


def test_order_state_mismatch_is_not_a_conflict() -> None:
    # order_state is informational on the local side; volume/price are
    # the compared representation. A state label difference alone stays
    # SYNCED.
    outcome = classify(
        [],
        [local_order()],
        BrokerSnapshot(orders=(broker_order(),)),
    )
    assert outcome.result is ReconciliationResult.SYNCED


def test_outcome_signature_is_deterministic() -> None:
    from collector.reconciliation.types import ReconciliationTrigger

    first = classify([], [], BrokerSnapshot(positions=(broker_position(),)))
    second = classify([], [], BrokerSnapshot(positions=(broker_position(),)))
    assert first.signature(ReconciliationTrigger.HEARTBEAT) == second.signature(
        ReconciliationTrigger.HEARTBEAT
    )
    changed = classify([], [], BrokerSnapshot(positions=(broker_position(volume=0.2),)))
    assert first.signature(ReconciliationTrigger.HEARTBEAT) != changed.signature(
        ReconciliationTrigger.HEARTBEAT
    )
    assert first.signature(ReconciliationTrigger.STARTUP) != first.signature(
        ReconciliationTrigger.HEARTBEAT
    )


def test_diffs_ordered_deterministically() -> None:
    outcome = classify(
        [],
        [],
        BrokerSnapshot(
            positions=(broker_position(position_id="p2"), broker_position(position_id="p1"))
        ),
    )
    ids = [diff.broker_id for diff in outcome.diffs]
    assert ids == ["p1", "p2"]
