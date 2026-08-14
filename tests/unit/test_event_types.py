"""Event type taxonomy tests."""

from __future__ import annotations

import pytest

from collector.event_model import ContractValidationError, build_event, validate_payload
from shared.contracts.payload_specs import get_spec
from shared.contracts.types import EventType
from tests.unit.event_factories import CORRELATION_ID, TRADE_ID, valid_payload_for

ALL_EVENT_TYPES = (
    "TICK_RECEIVED",
    "TRIGGER_DETECTED",
    "CONTEXT_BUILT",
    "AI_REQUEST",
    "AI_RESPONSE",
    "RISK_GATE",
    "ORDER_SUBMITTED",
    "ORDER_ACKNOWLEDGED",
    "ORDER_FILLED",
    "POSITION_OPENED",
    "POSITION_UPDATED",
    "NET_PROFIT_POSITIVE",
    "EXIT_SUBMITTED",
    "POSITION_CLOSED",
    "RECONCILIATION",
    "ERROR",
    "TIMEOUT",
)


def test_exactly_17_event_types() -> None:
    assert len(EventType) == 17


def test_all_17_event_types_exist() -> None:
    assert {member.value for member in EventType} == set(ALL_EVENT_TYPES)


def test_unknown_event_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        EventType("MYSTERY_EVENT")
    with pytest.raises(ContractValidationError, match="Unknown event type"):
        get_spec("MYSTERY_EVENT")


@pytest.mark.parametrize("event_type", [EventType(member) for member in ALL_EVENT_TYPES])
def test_every_event_type_has_a_valid_payload(event_type: EventType) -> None:
    payload = valid_payload_for(event_type)
    validate_payload(event_type, payload)
    event = build_event(
        event_type,
        payload,
        correlation_id=CORRELATION_ID,
        trade_id=TRADE_ID,
    )
    assert event.event_type is event_type
    assert event.verify_checksum()
