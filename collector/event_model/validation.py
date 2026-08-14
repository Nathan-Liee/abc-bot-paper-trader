"""Dict-level validation of events against the canonical event contract.

Validators here raise ``shared.contracts.errors.ContractValidationError``
on the first violation and produce plain-dict results. They are the
shared enforcement point for both ``EventEnvelope`` construction and
replay validation.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from collector.event_model.timestamps import is_valid_iso_utc, is_valid_iso_utc_ms
from shared.constants import CHECKSUM_HEX_LENGTH, CHECKSUM_PREFIX, SCHEMA_VERSION
from shared.contracts.errors import ContractValidationError
from shared.contracts.identity import is_valid_broker_id, is_valid_system_id
from shared.contracts.lifecycle import TRADE_FLOW_EVENTS
from shared.contracts.payload_specs import UNKNOWN_FIELD_PLACEHOLDER, get_spec
from shared.contracts.types import SEVERITY_LEVELS, EventType

ENVELOPE_FIELDS = (
    "event_id",
    "event_type",
    "ts_event",
    "ts_collected",
    "ts_monotonic",
    "component",
    "severity",
    "schema_version",
    "payload",
    "checksum",
)

OPTIONAL_ENVELOPE_FIELDS = ("correlation_id", "trade_id")

CHECKSUM_PATTERN = re.compile(f"^{re.escape(CHECKSUM_PREFIX)}[0-9a-f]{{{CHECKSUM_HEX_LENGTH}}}$")

_ENVELOPE_REQUIRED_MESSAGE = "missing required envelope field(s): {missing}"


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_type_token(token: str, value: object, field: str, event_type: str) -> None:
    ok: bool
    if token == "str":
        ok = isinstance(value, str) and bool(value)
    elif token == "number":
        ok = _is_number(value)
    elif token == "int":
        ok = _is_int(value)
    elif token == "bool":
        ok = isinstance(value, bool)
    elif token == "dict":
        ok = isinstance(value, dict)
    elif token == "uuid":
        ok = is_valid_system_id(value)
    elif token == "broker_id":
        ok = is_valid_broker_id(value)
    elif token == "iso_ts":
        ok = is_valid_iso_utc(value)
    else:  # pragma: no cover - guarded by the Literal token type
        raise AssertionError(f"unknown type token {token!r}")
    if not ok:
        raise ContractValidationError(
            f"{event_type}.{field} must be of type {token}, got {type(value).__name__}"
        )


def validate_payload(event_type: EventType, payload: object) -> None:
    """Validate a payload dict for *event_type*; raises on violation."""
    if not isinstance(payload, dict):
        raise ContractValidationError(f"payload must be a dict, got {type(payload).__name__}")
    spec = get_spec(event_type)

    unknown = sorted(set(payload) - spec.allowed_fields)
    if unknown:
        raise ContractValidationError(
            f"unknown field(s) in {event_type.value} payload: {', '.join(unknown)}"
        )

    missing = [field for field in spec.required if field not in payload]
    if missing:
        raise ContractValidationError(
            f"{event_type.value} payload missing required field(s): {', '.join(missing)}"
        )

    for field, value in payload.items():
        if field == UNKNOWN_FIELD_PLACEHOLDER:
            if not isinstance(value, dict):
                raise ContractValidationError(
                    f"{event_type.value}._unknown must be a dict, got {type(value).__name__}"
                )
            continue
        token = spec.types.get(field)
        if token is not None:
            _validate_type_token(token, value, field, event_type.value)
        if field in spec.enums and value not in spec.enums[field]:
            allowed = ", ".join(spec.enums[field])
            raise ContractValidationError(
                f"{event_type.value}.{field} must be one of: {allowed}; got {value!r}"
            )
        if field in spec.const_values and value != spec.const_values[field]:
            raise ContractValidationError(
                f"{event_type.value}.{field} must be {spec.const_values[field]!r}; got {value!r}"
            )

    for rule in spec.conditional_rules:
        if payload.get(rule.trigger_field) == rule.trigger_value:
            for field in rule.requires:
                if field not in payload:
                    raise ContractValidationError(
                        f"{event_type.value}.{field} is required when "
                        f"{rule.trigger_field} == {rule.trigger_value!r}"
                    )
            for field in rule.forbids:
                if field in payload:
                    raise ContractValidationError(
                        f"{event_type.value}.{field} must not be present when "
                        f"{rule.trigger_field} == {rule.trigger_value!r}"
                    )

    for bound in spec.numeric_rules:
        if bound.field in payload:
            value = payload[bound.field]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            if bound.op == "gt" and not value > bound.value:
                raise ContractValidationError(
                    f"{event_type.value}.{bound.field} must be greater than {bound.value}"
                )
            if bound.op == "ge" and not value >= bound.value:
                raise ContractValidationError(
                    f"{event_type.value}.{bound.field} must be at least {bound.value}"
                )
            if bound.op == "lt" and not value < bound.value:
                raise ContractValidationError(
                    f"{event_type.value}.{bound.field} must be less than {bound.value}"
                )
            if bound.op == "le" and not value <= bound.value:
                raise ContractValidationError(
                    f"{event_type.value}.{bound.field} must be at most {bound.value}"
                )


def _require_valid_uuid(value: object, field: str) -> None:
    if not is_valid_system_id(value):
        raise ContractValidationError(f"{field} must be a valid system UUID string, got {value!r}")


def _coerce_event_type(raw: object) -> EventType:
    if isinstance(raw, EventType):
        return raw
    if not isinstance(raw, str):
        raise ContractValidationError(f"event_type must be a string, got {type(raw).__name__}")
    try:
        return EventType(raw)
    except ValueError:
        raise ContractValidationError(f"unknown event type: {raw!r}") from None


def validate_event_dict(event: Mapping[str, object]) -> EventType:
    """Validate an envelope dict; returns the resolved EventType."""
    if not isinstance(event, dict):
        raise ContractValidationError(f"event must be a dict, got {type(event).__name__}")

    missing = [field for field in ENVELOPE_FIELDS if field not in event]
    if missing:
        raise ContractValidationError(_ENVELOPE_REQUIRED_MESSAGE.format(missing=", ".join(missing)))

    allowed = frozenset({*ENVELOPE_FIELDS, *OPTIONAL_ENVELOPE_FIELDS})
    unknown = sorted(set(event) - allowed)
    if unknown:
        raise ContractValidationError(f"unknown envelope field(s): {', '.join(unknown)}")

    _require_valid_uuid(event["event_id"], "event_id")
    event_type = _coerce_event_type(event["event_type"])

    if not is_valid_iso_utc(event["ts_event"]):
        raise ContractValidationError(
            "ts_event must be ISO 8601 UTC (seconds or millisecond precision), "
            f"got {event['ts_event']!r}"
        )
    if not is_valid_iso_utc_ms(event["ts_collected"]):
        raise ContractValidationError(
            f"ts_collected must be ISO 8601 UTC with millisecond precision, "
            f"got {event['ts_collected']!r}"
        )
    if not _is_int(event["ts_monotonic"]) or event["ts_monotonic"] < 0:
        raise ContractValidationError("ts_monotonic must be a non-negative integer")
    if not isinstance(event["component"], str) or not event["component"]:
        raise ContractValidationError("component must be a non-empty string")
    if event["severity"] not in SEVERITY_LEVELS:
        raise ContractValidationError(
            f"severity must be one of: {', '.join(SEVERITY_LEVELS)}; got {event['severity']!r}"
        )
    if event["schema_version"] != SCHEMA_VERSION:
        raise ContractValidationError(
            f"unsupported schema_version {event['schema_version']!r}; expected {SCHEMA_VERSION!r}"
        )
    if (
        not isinstance(event["checksum"], str)
        or CHECKSUM_PATTERN.fullmatch(event["checksum"]) is None
    ):
        raise ContractValidationError(
            f"checksum must match ^sha256:[0-9a-f]{{64}}$; got {event['checksum']!r}"
        )

    if "correlation_id" in event:
        _require_valid_uuid(event["correlation_id"], "correlation_id")
    if "trade_id" in event:
        _require_valid_uuid(event["trade_id"], "trade_id")

    if event_type is EventType.TRIGGER_DETECTED and "correlation_id" not in event:
        raise ContractValidationError("TRIGGER_DETECTED requires correlation_id")
    if event_type in TRADE_FLOW_EVENTS and "trade_id" not in event:
        raise ContractValidationError(f"{event_type.value} requires trade_id")

    validate_payload(event_type, event["payload"])
    return event_type


__all__ = [
    "CHECKSUM_PATTERN",
    "ENVELOPE_FIELDS",
    "OPTIONAL_ENVELOPE_FIELDS",
    "validate_event_dict",
    "validate_payload",
]
