"""Envelope-level validation tests."""

from __future__ import annotations

import pytest

from collector.event_model import (
    ContractValidationError,
    EventEnvelope,
    build_event,
    compute_checksum,
    validate_payload,
)
from shared.contracts.types import EventType
from tests.unit.event_factories import CORRELATION_ID, TRADE_ID, tick_payload


def test_build_event_creates_valid_envelope() -> None:
    event = build_event(EventType.TICK_RECEIVED, tick_payload())
    assert event.event_type is EventType.TICK_RECEIVED
    assert event.schema_version == "1.0.0"
    assert event.component == "collector"
    assert event.severity == "INFO"
    assert event.checksum.startswith("sha256:")
    assert event.verify_checksum()


def test_build_event_generates_unique_event_ids() -> None:
    first = build_event(EventType.TICK_RECEIVED, tick_payload())
    second = build_event(EventType.TICK_RECEIVED, tick_payload())
    assert first.event_id != second.event_id


def test_build_event_timestamps_and_identifiers() -> None:
    event = build_event(
        EventType.TRIGGER_DETECTED,
        {
            "trigger_source": "TECHNICAL",
            "trigger_category": "x",
            "trigger_metadata": {},
            "context_reference": "c",
        },
        correlation_id=CORRELATION_ID,
        trade_id=TRADE_ID,
    )
    assert event.correlation_id == CORRELATION_ID
    assert event.trade_id == TRADE_ID
    assert event.to_dict()["correlation_id"] == CORRELATION_ID
    assert event.to_dict()["trade_id"] == TRADE_ID


def test_build_event_rejects_unknown_event_type() -> None:
    with pytest.raises(ContractValidationError, match="unknown event type"):
        build_event("NOT_A_TYPE", tick_payload())  # type: ignore[arg-type]


def test_from_dict_roundtrip() -> None:
    event = build_event(EventType.TICK_RECEIVED, tick_payload())
    parsed = EventEnvelope.from_dict(event.to_dict())
    assert parsed == event


def test_from_dict_rejects_missing_required_field() -> None:
    data = build_event(EventType.TICK_RECEIVED, tick_payload()).to_dict()
    del data["ts_collected"]
    with pytest.raises(ContractValidationError, match="missing required envelope field"):
        EventEnvelope.from_dict(data)


def test_from_dict_rejects_null_required_field() -> None:
    data = build_event(EventType.TICK_RECEIVED, tick_payload()).to_dict()
    data["ts_monotonic"] = None  # type: ignore[assignment]
    with pytest.raises(ContractValidationError, match="ts_monotonic"):
        EventEnvelope.from_dict(data)


def test_from_dict_rejects_unknown_envelope_field() -> None:
    data = build_event(EventType.TICK_RECEIVED, tick_payload()).to_dict()
    data["made_up"] = True
    with pytest.raises(ContractValidationError, match="unknown envelope field"):
        EventEnvelope.from_dict(data)


def test_from_dict_rejects_tampered_checksum() -> None:
    data = build_event(EventType.TICK_RECEIVED, tick_payload()).to_dict()
    tampered = compute_checksum({**data, "ts_event": "2026-08-14T10:00:00Z"})
    data["checksum"] = tampered
    with pytest.raises(ContractValidationError, match="checksum mismatch"):
        EventEnvelope.from_dict(data)


def test_optional_envelope_fields_omitted_not_null() -> None:
    event = build_event(EventType.TICK_RECEIVED, tick_payload())
    data = event.to_dict()
    assert "correlation_id" not in data
    assert "trade_id" not in data


def test_trigger_detected_requires_correlation_id() -> None:
    from tests.unit.event_factories import trigger_payload

    with pytest.raises(ContractValidationError, match="correlation_id"):
        build_event(EventType.TRIGGER_DETECTED, trigger_payload())


def test_trade_flow_event_requires_trade_id() -> None:
    from tests.unit.event_factories import ai_request_payload

    with pytest.raises(ContractValidationError, match="trade_id"):
        build_event(EventType.AI_REQUEST, ai_request_payload())


def test_build_event_rejects_supplied_checksum_parameter() -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        build_event(  # type: ignore[call-arg]
            EventType.TICK_RECEIVED,
            tick_payload(),
            checksum="sha256:" + "0" * 64,
        )


def test_validate_payload_rejects_non_dict() -> None:
    with pytest.raises(ContractValidationError, match="payload must be a dict"):
        validate_payload(EventType.TICK_RECEIVED, [1, 2])  # type: ignore[arg-type]
