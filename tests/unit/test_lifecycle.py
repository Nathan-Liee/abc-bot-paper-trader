"""Contract-level lifecycle validation tests."""

from __future__ import annotations

import pytest

from collector.event_model import (
    ContractValidationError,
    EventEnvelope,
    build_event,
    validate_sequence,
    validate_transition,
)
from shared.contracts.lifecycle import NEXT_ALLOWED, TradeLifecycle
from shared.contracts.types import EventType
from tests.unit.event_factories import (
    CORRELATION_ID,
    TRADE_ID,
    ai_request_payload,
    ai_response_payload,
    context_payload,
    error_payload,
    exit_submitted_payload,
    net_profit_positive_payload,
    order_acknowledged_payload,
    order_filled_payload,
    order_submitted_payload,
    position_closed_payload,
    position_opened_payload,
    position_updated_payload,
    reconciliation_payload,
    risk_gate_payload,
    timeout_payload,
    trigger_payload,
)

MONO = 1000


def _trade_event(
    event_type: EventType, payload: dict[str, object], monotonic: int
) -> EventEnvelope:
    return build_event(
        event_type,
        payload,
        correlation_id=CORRELATION_ID,
        trade_id=TRADE_ID,
        ts_event="2026-08-14T09:00:00Z",
        ts_collected="2026-08-14T09:00:00.000Z",
        ts_monotonic=monotonic,
    )


def _full_flow() -> list[EventEnvelope]:
    events: list[tuple[EventType, dict[str, object]]] = [
        (EventType.TRIGGER_DETECTED, trigger_payload()),
        (EventType.CONTEXT_BUILT, context_payload()),
        (EventType.AI_REQUEST, ai_request_payload()),
        (EventType.AI_RESPONSE, ai_response_payload()),
        (EventType.RISK_GATE, risk_gate_payload()),
        (EventType.ORDER_SUBMITTED, order_submitted_payload()),
        (EventType.ORDER_ACKNOWLEDGED, order_acknowledged_payload()),
        (EventType.ORDER_FILLED, order_filled_payload()),
        (EventType.POSITION_OPENED, position_opened_payload()),
        (EventType.POSITION_UPDATED, position_updated_payload()),
        (EventType.NET_PROFIT_POSITIVE, net_profit_positive_payload()),
        (EventType.EXIT_SUBMITTED, exit_submitted_payload()),
        (EventType.POSITION_CLOSED, position_closed_payload()),
    ]
    return [
        _trade_event(event_type, payload, MONO + index)
        for index, (event_type, payload) in enumerate(events)
    ]


def test_full_valid_flow_is_accepted() -> None:
    validate_sequence(_full_flow())


def test_flow_with_oob_events_is_accepted() -> None:
    flow = _full_flow()
    tick = build_event(
        EventType.TICK_RECEIVED,
        {
            "symbol": "XAUUSD",
            "bid": 1.0,
            "ask": 1.1,
            "mid": 1.05,
            "spread": 0.1,
            "ts_source": "2026-08-14T09:00:00Z",
        },
        ts_event="2026-08-14T09:00:00Z",
        ts_collected="2026-08-14T09:00:00.000Z",
        ts_monotonic=500,
    )
    validate_sequence([tick, *flow])


def test_trigger_to_order_submitted_shortcut_is_rejected() -> None:
    events = [
        _trade_event(EventType.TRIGGER_DETECTED, trigger_payload(), MONO),
        _trade_event(EventType.ORDER_SUBMITTED, order_submitted_payload(), MONO + 1),
    ]
    with pytest.raises(ContractValidationError, match="Illegal lifecycle transition"):
        validate_sequence(events)


def test_risk_gate_reject_is_terminal() -> None:
    rejected = risk_gate_payload(
        gate_result="REJECT", final_lot=0.0, rejection_reason="budget exhausted"
    )
    events = [
        _trade_event(EventType.TRIGGER_DETECTED, trigger_payload(), MONO),
        _trade_event(EventType.RISK_GATE, rejected, MONO + 1),
    ]
    validate_sequence(events)
    with pytest.raises(ContractValidationError, match="terminal"):
        validate_sequence(
            [*events, _trade_event(EventType.ORDER_SUBMITTED, order_submitted_payload(), MONO + 2)]
        )


def test_order_failure_never_opens_a_position() -> None:
    failed = [
        _trade_event(EventType.TRIGGER_DETECTED, trigger_payload(), MONO),
        _trade_event(EventType.CONTEXT_BUILT, context_payload(), MONO + 1),
        _trade_event(EventType.AI_REQUEST, ai_request_payload(), MONO + 2),
        _trade_event(EventType.AI_RESPONSE, ai_response_payload(), MONO + 3),
        _trade_event(EventType.RISK_GATE, risk_gate_payload(), MONO + 4),
        _trade_event(EventType.ORDER_SUBMITTED, order_submitted_payload(), MONO + 5),
        _trade_event(
            EventType.RECONCILIATION,
            reconciliation_payload(),
            MONO + 6,
        ),
    ]
    validate_sequence(failed)
    with pytest.raises(ContractValidationError, match="terminal"):
        validate_sequence(
            [*failed, _trade_event(EventType.ORDER_FILLED, order_filled_payload(), MONO + 7)]
        )


def test_first_trade_event_must_be_trigger_detected() -> None:
    events = [_trade_event(EventType.CONTEXT_BUILT, context_payload(), MONO)]
    with pytest.raises(ContractValidationError, match="TRIGGER_DETECTED"):
        validate_sequence(events)


def test_position_closed_is_terminal() -> None:
    flow = _full_flow()
    with pytest.raises(ContractValidationError, match="terminal"):
        validate_sequence(
            [
                *flow,
                _trade_event(EventType.POSITION_UPDATED, position_updated_payload(), MONO + 100),
            ]
        )


def test_error_is_terminal_for_that_trade() -> None:
    events = [
        _trade_event(EventType.TRIGGER_DETECTED, trigger_payload(), MONO),
        _trade_event(EventType.ERROR, error_payload(), MONO + 1),
        _trade_event(EventType.CONTEXT_BUILT, context_payload(), MONO + 2),
    ]
    with pytest.raises(ContractValidationError, match="terminal"):
        validate_sequence(events)


def test_timeout_after_order_submitted_is_terminal() -> None:
    events = [
        _trade_event(EventType.TRIGGER_DETECTED, trigger_payload(), MONO),
        _trade_event(EventType.RISK_GATE, risk_gate_payload(), MONO + 1),
        _trade_event(EventType.ORDER_SUBMITTED, order_submitted_payload(), MONO + 2),
        _trade_event(EventType.TIMEOUT, timeout_payload(), MONO + 3),
        _trade_event(EventType.ORDER_ACKNOWLEDGED, order_acknowledged_payload(), MONO + 4),
    ]
    with pytest.raises(ContractValidationError, match="terminal"):
        validate_sequence(events)


def test_standalone_trade_lifecycle_apply() -> None:
    lifecycle = TradeLifecycle(TRADE_ID)
    assert lifecycle.current_state is None
    lifecycle.apply(EventType.TRIGGER_DETECTED, trigger_payload())
    assert lifecycle.current_state is EventType.TRIGGER_DETECTED
    lifecycle.apply(EventType.RISK_GATE, risk_gate_payload())
    assert lifecycle.current_state is EventType.RISK_GATE
    lifecycle.apply(EventType.ORDER_SUBMITTED, order_submitted_payload())
    assert lifecycle.current_state is EventType.ORDER_SUBMITTED
    assert not lifecycle.is_terminal


def test_validate_transition_pair_rules() -> None:
    validate_transition(EventType.AI_REQUEST, EventType.AI_RESPONSE)
    with pytest.raises(ContractValidationError, match="Illegal lifecycle transition"):
        validate_transition(EventType.CONTEXT_BUILT, EventType.POSITION_CLOSED)
    with pytest.raises(ContractValidationError, match="not part of the trade flow"):
        validate_transition(EventType.TICK_RECEIVED, EventType.ORDER_SUBMITTED)
    with pytest.raises(ContractValidationError, match="Risk gate rejected"):
        validate_transition(
            EventType.RISK_GATE,
            EventType.ORDER_SUBMITTED,
            previous_payload=risk_gate_payload(gate_result="REJECT", rejection_reason="nope"),
        )


def test_trade_lifecycle_requires_trigger_first() -> None:
    lifecycle = TradeLifecycle(TRADE_ID)
    with pytest.raises(ContractValidationError, match="TRIGGER_DETECTED"):
        lifecycle.apply(EventType.CONTEXT_BUILT, context_payload())


def test_trade_lifecycle_reject_is_terminal() -> None:
    lifecycle = TradeLifecycle(TRADE_ID)
    lifecycle.apply(EventType.TRIGGER_DETECTED, trigger_payload())
    lifecycle.apply(
        EventType.RISK_GATE, risk_gate_payload(gate_result="REJECT", rejection_reason="nope")
    )
    assert lifecycle.is_terminal
    with pytest.raises(ContractValidationError, match="terminal"):
        lifecycle.apply(EventType.ORDER_SUBMITTED, order_submitted_payload())


def test_position_closed_removes_next_allowed() -> None:
    assert NEXT_ALLOWED[EventType.POSITION_CLOSED] == frozenset()
