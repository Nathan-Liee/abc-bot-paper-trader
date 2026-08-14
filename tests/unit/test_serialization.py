"""Serialization tests: deterministic output, UTF-8, omitted optionals."""

from __future__ import annotations

import json

import pytest

from collector.event_model import ContractValidationError, build_event, from_json, to_json
from shared.contracts.types import EventType
from tests.unit.event_factories import TRADE_ID, ai_response_payload, tick_payload


def test_roundtrip_preserves_event() -> None:
    event = build_event(
        EventType.AI_RESPONSE,
        ai_response_payload(reason="café – momentum"),
        trade_id=TRADE_ID,
    )
    parsed = from_json(to_json(event))
    assert parsed == event
    assert parsed.payload["reason"] == "café – momentum"


def test_wire_format_is_compact_and_utf8() -> None:
    event = build_event(
        EventType.AI_RESPONSE,
        ai_response_payload(reason="café"),
        trade_id=TRADE_ID,
    )
    text = to_json(event)
    assert "\n" not in text
    assert " " not in text
    assert "café" in text


def test_optional_fields_are_omitted() -> None:
    event = build_event(EventType.TICK_RECEIVED, tick_payload())
    text = to_json(event)
    assert "correlation_id" not in text
    assert "trade_id" not in text
    assert "tick_volume" not in text


def test_key_order_is_deterministic() -> None:
    first = to_json(build_event(EventType.TICK_RECEIVED, tick_payload()))
    second = to_json(build_event(EventType.TICK_RECEIVED, tick_payload()))
    first_obj = json.loads(first)
    second_obj = json.loads(second)
    assert list(first_obj) == list(second_obj)
    assert list(first_obj["payload"]) == list(second_obj["payload"])


def test_optional_payload_field_included_when_present() -> None:
    event = build_event(EventType.TICK_RECEIVED, tick_payload(tick_volume=3, tick_id="t-1"))
    parsed = json.loads(to_json(event))
    assert parsed["payload"]["tick_volume"] == 3
    assert parsed["payload"]["tick_id"] == "t-1"


def test_from_json_rejects_invalid_json() -> None:
    with pytest.raises(ContractValidationError, match="invalid event JSON"):
        from_json("{not json")


def test_from_json_rejects_non_object_json() -> None:
    with pytest.raises(ContractValidationError, match="must be a JSON object"):
        from_json("[1, 2]")


def test_timestamps_serialize_consistently() -> None:
    event = build_event(EventType.TICK_RECEIVED, tick_payload())
    parsed = json.loads(to_json(event))
    assert parsed["ts_event"].endswith("Z")
    assert parsed["ts_collected"].endswith("Z")
    assert parsed["ts_monotonic"] == event.ts_monotonic
