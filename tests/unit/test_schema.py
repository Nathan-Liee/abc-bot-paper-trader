"""JSON Schema tests: the schema mirrors the contract and validates events."""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from collector.event_model import build_event, to_json
from collector.settings import PROJECT_ROOT
from shared.contracts.types import EventType
from tests.unit.event_factories import CORRELATION_ID, TRADE_ID, tick_payload, valid_payload_for

SCHEMA_PATH = PROJECT_ROOT / "shared" / "schemas" / "canonical-event.schema.json"


@pytest.fixture(scope="module")
def schema() -> dict[str, object]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(event_dict: dict[str, object], schema: dict[str, object]) -> None:
    Draft202012Validator(schema).validate(event_dict)


def _build(event_type: EventType, payload: dict[str, object], **kwargs: object):
    return build_event(
        event_type,
        payload,
        correlation_id=CORRELATION_ID,
        trade_id=TRADE_ID,
        **kwargs,
    )


def test_schema_is_a_valid_json_schema(schema: dict[str, object]) -> None:
    Draft202012Validator.check_schema(schema)


def test_schema_declares_version_1_0_0(schema: dict[str, object]) -> None:
    assert schema["properties"]["schema_version"] == {"const": "1.0.0"}  # type: ignore[index]


@pytest.mark.parametrize("event_type", list(EventType))
def test_all_17_event_types_validate_against_schema(
    event_type: EventType, schema: dict[str, object]
) -> None:
    event = _build(event_type, valid_payload_for(event_type))
    _validate(event.to_dict(), schema)


def test_missing_required_envelope_field_fails(schema: dict[str, object]) -> None:
    data = _build(EventType.TICK_RECEIVED, tick_payload()).to_dict()
    del data["ts_collected"]
    with pytest.raises(Exception, match="ts_collected"):
        _validate(data, schema)


def test_null_required_field_fails(schema: dict[str, object]) -> None:
    from jsonschema.exceptions import ValidationError

    data = _build(EventType.TICK_RECEIVED, tick_payload()).to_dict()
    data["ts_monotonic"] = None  # type: ignore[assignment]
    with pytest.raises(ValidationError):
        _validate(data, schema)


def test_invalid_checksum_format_fails(schema: dict[str, object]) -> None:
    data = _build(EventType.TICK_RECEIVED, tick_payload()).to_dict()
    data["checksum"] = "md5:not-a-checksum"
    with pytest.raises(Exception, match="checksum"):
        _validate(data, schema)


def test_unknown_envelope_field_fails(schema: dict[str, object]) -> None:
    data = _build(EventType.TICK_RECEIVED, tick_payload()).to_dict()
    data["made_up"] = True
    with pytest.raises(Exception, match="made_up"):
        _validate(data, schema)


def test_payload_must_match_its_own_type(schema: dict[str, object]) -> None:
    from tests.unit.event_factories import ai_request_payload

    data = _build(EventType.TICK_RECEIVED, tick_payload()).to_dict()
    data["payload"] = ai_request_payload()
    with pytest.raises(Exception, match="payload"):
        _validate(data, schema)


def test_invalid_payload_enum_fails(schema: dict[str, object]) -> None:
    from tests.unit.event_factories import ai_response_payload

    data = _build(EventType.AI_RESPONSE, ai_response_payload()).to_dict()
    data["payload"]["decision"] = "HOLD"
    with pytest.raises(Exception, match="HOLD"):
        _validate(data, schema)


def test_unknown_payload_field_fails(schema: dict[str, object]) -> None:
    data = _build(EventType.TICK_RECEIVED, tick_payload()).to_dict()
    data["payload"]["bogus"] = 1
    with pytest.raises(Exception, match="bogus"):
        _validate(data, schema)


def test_unknown_extension_dict_is_allowed_by_schema(schema: dict[str, object]) -> None:
    event = _build(EventType.TICK_RECEIVED, tick_payload(_unknown={"vendor": "x"}))
    _validate(event.to_dict(), schema)


def test_trigger_detected_requires_correlation_id(schema: dict[str, object]) -> None:
    from tests.unit.event_factories import trigger_payload

    data = _build(EventType.TRIGGER_DETECTED, trigger_payload()).to_dict()
    del data["correlation_id"]
    with pytest.raises(Exception, match="correlation_id"):
        _validate(data, schema)


def test_risk_gate_reject_requires_rejection_reason(schema: dict[str, object]) -> None:
    from jsonschema.exceptions import ValidationError

    from tests.unit.event_factories import risk_gate_payload

    data = _build(
        EventType.RISK_GATE,
        risk_gate_payload(gate_result="REJECT", rejection_reason="budget exhausted"),
    ).to_dict()
    del data["payload"]["rejection_reason"]
    with pytest.raises(ValidationError):
        _validate(data, schema)


def test_serialized_event_roundtrips_through_schema(schema: dict[str, object]) -> None:
    event = _build(EventType.POSITION_CLOSED, valid_payload_for(EventType.POSITION_CLOSED))
    from collector.event_model import from_json

    _validate(from_json(to_json(event)).to_dict(), schema)
