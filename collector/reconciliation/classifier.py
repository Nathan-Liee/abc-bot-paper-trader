"""Deterministic local-vs-broker comparison.

Pure function: given derived local state and one broker snapshot it
produces a :class:`ReconciliationOutcome` with per-entity
classifications. No side effects, no persistence, no execution.

Rules (task section 7):

* broker entity without local mapping -> RECOVERABLE (adoptable)
* local entity absent from broker      -> MISSING_BROKER (escalate)
* same id, equal fields                -> NO_MISMATCH
* same id, differing fields            -> CONFLICTING_STATE (escalate)
* unknown/inconsistent evidence        -> UNKNOWN (escalate)

Overall result precedence: ESCALATED > ADOPTED_BROKER > SYNCED.
"""

from __future__ import annotations

import math

from collector.persistence.records import OrderRecord, PositionRecord
from collector.reconciliation.broker import BrokerOrder, BrokerPosition, BrokerSnapshot
from collector.reconciliation.types import (
    DiffClassification,
    EntityDiff,
    ReconciliationOutcome,
    ReconciliationResult,
)

_FLOAT_TOLERANCE = 1e-6


def _is_close(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return True
    return math.isclose(left, right, rel_tol=_FLOAT_TOLERANCE, abs_tol=_FLOAT_TOLERANCE)


def _token(value: str | None) -> str:
    return (value or "").strip().upper()


def _position_summary(position: PositionRecord) -> str:
    return (
        f"direction={_token(position.direction)};lot={position.lot};"
        f"open_price={position.open_price};state={_token(position.state)}"
    )


def _broker_position_summary(position: BrokerPosition) -> str:
    fields = [f"symbol={position.symbol}", f"direction={_token(position.direction)}"]
    fields.append(f"volume={position.volume}")
    fields.append(f"open_price={position.open_price}")
    fields.append(f"state={_token(position.broker_state)}")
    return ";".join(fields)


def _order_summary(order: OrderRecord) -> str:
    fields = [f"state={_token(order.order_state)}"]
    if order.requested_lot is not None:
        fields.append(f"volume={order.requested_lot}")
    if order.requested_price is not None:
        fields.append(f"price={order.requested_price}")
    return ";".join(fields)


def _broker_order_summary(order: BrokerOrder) -> str:
    fields = [f"state={_token(order.state)}"]
    if order.symbol is not None:
        fields.append(f"symbol={order.symbol}")
    if order.order_type is not None:
        fields.append(f"order_type={_token(order.order_type)}")
    if order.volume is not None:
        fields.append(f"volume={order.volume}")
    if order.price is not None:
        fields.append(f"price={order.price}")
    return ";".join(fields)


def _classify_position(local: PositionRecord, broker: BrokerPosition) -> EntityDiff | None:
    if _token(local.direction) != _token(broker.direction):
        return EntityDiff(
            entity_type="POSITION",
            broker_id=broker.broker_position_id,
            classification=DiffClassification.CONFLICTING_STATE,
            reason="direction differs between local and broker",
            local_summary=_position_summary(local),
            broker_summary=_broker_position_summary(broker),
        )
    if not _is_close(local.lot, broker.volume):
        return EntityDiff(
            entity_type="POSITION",
            broker_id=broker.broker_position_id,
            classification=DiffClassification.CONFLICTING_STATE,
            reason="volume differs between local and broker",
            local_summary=_position_summary(local),
            broker_summary=_broker_position_summary(broker),
        )
    if not _is_close(local.open_price, broker.open_price):
        return EntityDiff(
            entity_type="POSITION",
            broker_id=broker.broker_position_id,
            classification=DiffClassification.CONFLICTING_STATE,
            reason="open price differs between local and broker",
            local_summary=_position_summary(local),
            broker_summary=_broker_position_summary(broker),
        )
    return None


def _classify_order(local: OrderRecord, broker: BrokerOrder) -> EntityDiff | None:
    if not _is_close(local.requested_lot, broker.volume):
        return EntityDiff(
            entity_type="ORDER",
            broker_id=broker.broker_order_id,
            classification=DiffClassification.CONFLICTING_STATE,
            reason="volume differs between local and broker",
            local_summary=_order_summary(local),
            broker_summary=_broker_order_summary(broker),
        )
    if not _is_close(local.requested_price, broker.price):
        return EntityDiff(
            entity_type="ORDER",
            broker_id=broker.broker_order_id,
            classification=DiffClassification.CONFLICTING_STATE,
            reason="price differs between local and broker",
            local_summary=_order_summary(local),
            broker_summary=_broker_order_summary(broker),
        )
    return None


def classify(
    local_positions: list[PositionRecord],
    local_orders: list[OrderRecord],
    snapshot: BrokerSnapshot,
) -> ReconciliationOutcome:
    """Compare derived local state against one broker snapshot."""
    local_positions_by_id: dict[str, PositionRecord] = {
        position.broker_position_id: position for position in local_positions
    }
    local_orders_by_id: dict[str, OrderRecord] = {
        order.broker_order_id: order for order in local_orders
    }

    diffs: list[EntityDiff] = []
    broker_orphans = 0
    local_orphans = 0
    state_conflicts = 0

    broker_positions = sorted(snapshot.positions, key=lambda p: p.broker_position_id)
    broker_orders = sorted(snapshot.orders, key=lambda o: o.broker_order_id)

    for bpos in broker_positions:
        local_position = local_positions_by_id.get(bpos.broker_position_id)
        if local_position is None:
            broker_orphans += 1
            diffs.append(
                EntityDiff(
                    entity_type="POSITION",
                    broker_id=bpos.broker_position_id,
                    classification=DiffClassification.RECOVERABLE,
                    reason="broker position has no local mapping; broker evidence adopted",
                    local_summary="",
                    broker_summary=_broker_position_summary(bpos),
                )
            )
            continue
        conflict = _classify_position(local_position, bpos)
        if conflict is not None:
            state_conflicts += 1
            diffs.append(conflict)
        else:
            diffs.append(
                EntityDiff(
                    entity_type="POSITION",
                    broker_id=bpos.broker_position_id,
                    classification=DiffClassification.NO_MISMATCH,
                    reason="local and broker position match",
                    local_summary=_position_summary(local_position),
                    broker_summary=_broker_position_summary(bpos),
                )
            )

    for border in broker_orders:
        local_order = local_orders_by_id.get(border.broker_order_id)
        if local_order is None:
            broker_orphans += 1
            diffs.append(
                EntityDiff(
                    entity_type="ORDER",
                    broker_id=border.broker_order_id,
                    classification=DiffClassification.RECOVERABLE,
                    reason="broker order has no local mapping; broker evidence adopted",
                    local_summary="",
                    broker_summary=_broker_order_summary(border),
                )
            )
            continue
        conflict = _classify_order(local_order, border)
        if conflict is not None:
            state_conflicts += 1
            diffs.append(conflict)
        else:
            diffs.append(
                EntityDiff(
                    entity_type="ORDER",
                    broker_id=border.broker_order_id,
                    classification=DiffClassification.NO_MISMATCH,
                    reason="local and broker order match",
                    local_summary=_order_summary(local_order),
                    broker_summary=_broker_order_summary(border),
                )
            )

    for position_id in local_positions_by_id:
        if position_id not in {p.broker_position_id for p in broker_positions}:
            local_orphans += 1
            diffs.append(
                EntityDiff(
                    entity_type="POSITION",
                    broker_id=position_id,
                    classification=DiffClassification.MISSING_BROKER,
                    reason="local position absent from broker snapshot; not auto-closed",
                    local_summary=_position_summary(local_positions_by_id[position_id]),
                    broker_summary="",
                )
            )

    for order_id in local_orders_by_id:
        if order_id not in {o.broker_order_id for o in broker_orders}:
            local_orphans += 1
            diffs.append(
                EntityDiff(
                    entity_type="ORDER",
                    broker_id=order_id,
                    classification=DiffClassification.MISSING_BROKER,
                    reason="local order absent from broker snapshot; investigated, not modified",
                    local_summary=_order_summary(local_orders_by_id[order_id]),
                    broker_summary="",
                )
            )

    diffs.sort(key=lambda diff: (diff.entity_type, diff.broker_id))
    ordered = tuple(diffs)

    local_position_orphans = sum(
        1
        for diff in ordered
        if diff.entity_type == "POSITION"
        and diff.classification is DiffClassification.MISSING_BROKER
    )
    local_order_orphans = sum(
        1
        for diff in ordered
        if diff.entity_type == "ORDER" and diff.classification is DiffClassification.MISSING_BROKER
    )

    # A local *position* orphan always escalates (investigate, never
    # auto-close). A local *order* orphan only escalates when there is no
    # broker evidence that could explain it: a broker position with no
    # local mapping means the missing fill evidence is actual broker
    # state, so adoption is the correct, deterministic outcome.
    forces_escalation = (
        state_conflicts > 0
        or local_position_orphans > 0
        or (local_order_orphans > 0 and broker_orphans == 0)
    )

    if forces_escalation:
        result = ReconciliationResult.ESCALATED
        action = "ESCALATE"
    elif broker_orphans > 0:
        result = ReconciliationResult.ADOPTED_BROKER
        action = "ADOPT_BROKER"
    else:
        result = ReconciliationResult.SYNCED
        action = "NONE"

    return ReconciliationOutcome(
        result=result,
        action=action,
        mismatch=result is not ReconciliationResult.SYNCED,
        local_state=f"open_positions={len(local_positions_by_id)};open_orders={len(local_orders_by_id)}",
        broker_state=f"positions={len(broker_positions)};orders={len(broker_orders)}",
        diffs=ordered,
        broker_orphans=broker_orphans,
        local_orphans=local_orphans,
        state_conflicts=state_conflicts,
    )


__all__ = ["classify"]
