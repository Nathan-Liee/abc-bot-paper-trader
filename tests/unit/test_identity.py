"""Identity rules tests: system UUIDs vs broker-owned external strings."""

from __future__ import annotations

from collector.event_model import build_event
from shared.contracts.identity import (
    BROKER_ID_FIELDS,
    BROKER_ID_MAX_LENGTH,
    SYSTEM_ID_FIELDS,
    is_valid_broker_id,
    is_valid_system_id,
)
from shared.contracts.types import EventType
from tests.unit.event_factories import (
    INFERENCE_ID,
    RECONCILIATION_ID,
    TRADE_ID,
    order_filled_payload,
)


def test_system_id_accepts_canonical_lowercase_uuid() -> None:
    assert is_valid_system_id(TRADE_ID)
    assert is_valid_system_id(INFERENCE_ID)
    assert is_valid_system_id(RECONCILIATION_ID)


def test_system_id_rejects_non_uuid_strings() -> None:
    for bad in ("not-a-uuid", "", "123", TRADE_ID.upper(), "x" + TRADE_ID[1:]):
        assert not is_valid_system_id(bad), bad


def test_system_id_rejects_non_strings() -> None:
    assert not is_valid_system_id(123)
    assert not is_valid_system_id(None)


def test_system_id_fields_are_complete() -> None:
    assert SYSTEM_ID_FIELDS == (
        "event_id",
        "trade_id",
        "correlation_id",
        "inference_id",
        "reconciliation_id",
    )


def test_broker_id_accepts_opaque_external_strings() -> None:
    assert is_valid_broker_id("broker-order-001")
    assert is_valid_broker_id("MT5.123456.7")
    assert is_valid_broker_id("a" * BROKER_ID_MAX_LENGTH)


def test_broker_id_rejects_empty_and_too_long() -> None:
    assert not is_valid_broker_id("")
    assert not is_valid_broker_id("a" * (BROKER_ID_MAX_LENGTH + 1))


def test_broker_id_rejects_control_characters() -> None:
    assert not is_valid_broker_id("bad\nid")
    assert not is_valid_broker_id("bad\x00id")


def test_broker_id_rejects_non_strings() -> None:
    assert not is_valid_broker_id(42)
    assert not is_valid_broker_id(None)


def test_broker_id_fields_are_complete() -> None:
    assert BROKER_ID_FIELDS == (
        "broker_order_id",
        "broker_deal_id",
        "broker_position_id",
    )


def test_broker_ids_are_preserved_verbatim() -> None:
    raw = "Broker.ORDER_42..!x"
    event = build_event(
        EventType.ORDER_FILLED,
        order_filled_payload(broker_order_id=raw),
        trade_id=TRADE_ID,
    )
    assert event.payload["broker_order_id"] == raw
    assert event.to_dict()["payload"]["broker_order_id"] == raw


def test_broker_ids_are_never_generated_by_the_model() -> None:
    from tests.unit.event_factories import position_opened_payload

    event = build_event(
        EventType.POSITION_OPENED,
        position_opened_payload(),
        trade_id=TRADE_ID,
    )
    payload = event.to_dict()["payload"]
    assert payload["broker_position_id"] == "broker-position-001"
