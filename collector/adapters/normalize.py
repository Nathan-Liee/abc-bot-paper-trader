"""Normalization of raw bridge lines into canonical event payloads.

The MQL5 bridge emits JSONL lines shaped like::

    {"event_type": "...", "ts_bridge": "...", "payload": {...}}

This module:

* classifies the line: canonical event type, bridge-internal telemetry
  (HEARTBEAT / POSITION_SNAPSHOT / ORDER_SNAPSHOT), or unknown
* validates the raw envelope shape (malformed -> InvalidLineError)
* normalizes the payload to the canonical contract types (numeric
  coercion per the type tokens, ``None`` values dropped - the contract
  forbids nulls, unknown fields preserved verbatim)
* resolves the canonical business timestamp per section 5 defaults of
  the contract (explicit payload field -> ts_bridge -> receipt time)

No new domain fields are invented: symbol names and broker ids are
preserved verbatim (``XAUUSDc`` etc. are never remapped), and timestamps
are never fabricated.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from collector.adapters.errors import InvalidLineError
from shared.contracts.payload_specs import UNKNOWN_FIELD_PLACEHOLDER, get_spec
from shared.contracts.types import EventType

BRIDGE_SOURCE = "mql5"

# Bridge-internal telemetry events: counted but never canonicalized.
_INTERNAL_EVENT_TYPES = frozenset({"HEARTBEAT", "POSITION_SNAPSHOT", "ORDER_SNAPSHOT"})

# Per-event canonical timestamp field (contract section 5 defaults).
_TS_EVENT_FIELD_BY_TYPE: dict[EventType, str | None] = {
    EventType.TICK_RECEIVED: "ts_source",
    EventType.ORDER_ACKNOWLEDGED: "ack_ts",
    EventType.ORDER_FILLED: "fill_ts",
    EventType.POSITION_OPENED: "open_ts",
    EventType.POSITION_CLOSED: "exit_fill_ts",
    EventType.ERROR: None,
    EventType.TIMEOUT: None,
}


class RawLineKind(StrEnum):
    CANONICAL = "canonical"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NormalizedBridgeLine:
    """A raw line classified and normalized for the pipeline."""

    kind: RawLineKind
    event_type: EventType | None = None
    payload: Mapping[str, Any] | None = None
    ts_bridge: str | None = None
    ts_event: str | None = None
    code: str | None = None  # stable machine-readable reason when invalid


def parse_raw_line(text: str) -> Mapping[str, Any]:
    """Parse one JSON line into a mapping, or raise InvalidLineError."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidLineError(f"malformed JSON at line: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise InvalidLineError("line must be a JSON object")
    return parsed


def _coerce_number(token: str, value: Any, field: str) -> Any:
    """Coerce *value* to the canonical type token shape.

    Digits-as-strings and int/float re-typing are accepted; the contract
    type tokens are ``number`` (float) and ``int`` (whole number only).
    """
    if token == "int":
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise InvalidLineError(f"field {field!r} must be an integer") from exc
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidLineError(f"field {field!r} must be numeric") from exc


def normalize_bridge_line(parsed: Mapping[str, Any], *, ts_collected: str) -> NormalizedBridgeLine:
    """Classify and normalize one raw bridge line.

    Raises :class:`InvalidLineError` for malformed envelopes. Unknown
    event types are classified (never raised) so the pipeline can count
    and skip them explicitly.
    """
    event_type_name = parsed.get("event_type")
    if not isinstance(event_type_name, str) or not event_type_name:
        raise InvalidLineError("missing event_type in bridge line")

    ts_bridge = parsed.get("ts_bridge")
    if ts_bridge is not None and not isinstance(ts_bridge, str):
        raise InvalidLineError("ts_bridge must be a string when present")

    payload = parsed.get("payload")
    if not isinstance(payload, dict):
        raise InvalidLineError("payload must be an object")

    if event_type_name in _INTERNAL_EVENT_TYPES:
        return NormalizedBridgeLine(
            kind=RawLineKind.INTERNAL,
            event_type=None,
            payload=None,
            ts_bridge=ts_bridge,
            code="BRIDGE_INTERNAL_EVENT",
        )

    try:
        event_type = EventType(event_type_name)
    except ValueError:
        return NormalizedBridgeLine(
            kind=RawLineKind.UNKNOWN,
            event_type=None,
            payload=payload,
            ts_bridge=ts_bridge,
            code="UNKNOWN_EVENT_TYPE",
        )

    return NormalizedBridgeLine(
        kind=RawLineKind.CANONICAL,
        event_type=event_type,
        payload=_normalize_payload(event_type, payload),
        ts_bridge=ts_bridge,
        ts_event=_resolve_ts_event(event_type, payload, ts_bridge, ts_collected),
    )


def _resolve_ts_event(
    event_type: EventType,
    payload: Mapping[str, Any],
    ts_bridge: str | None,
    ts_collected: str,
) -> str:
    """Resolve the canonical business timestamp (contract section 5).

    Precedence: explicit payload timestamp field -> ``ts_bridge`` ->
    collector receipt time. The value is never fabricated: it is either
    taken from the bridge or from the collector's own receipt clock.
    """
    field = _TS_EVENT_FIELD_BY_TYPE.get(event_type)
    if field is not None:
        value = payload.get(field)
        if isinstance(value, str) and value:
            return value
    if ts_bridge:
        return ts_bridge
    return ts_collected


def _normalize_payload(event_type: EventType, raw: Mapping[str, Any]) -> dict[str, Any]:
    """Coerce raw payload values to canonical types.

    Rules:

    * unknown fields (not in the contract spec) are preserved verbatim
      under the ``UNKNOWN_FIELD_PLACEHOLDER`` key
    * ``None`` values are dropped (contract forbids null)
    * numerics are coerced per the type token
    """
    spec = get_spec(event_type)
    normalized: dict[str, Any] = {}
    unknown: dict[str, Any] = {}
    for field, value in raw.items():
        if value is None:
            continue
        if field in spec.optional or field in spec.required:
            token = spec.types.get(field, "str")
            if token in ("number", "int"):
                normalized[field] = _coerce_number(token, value, field)
            else:
                normalized[field] = value
        else:
            unknown[field] = value
    if unknown:
        normalized[UNKNOWN_FIELD_PLACEHOLDER] = unknown
    return normalized


__all__ = [
    "BRIDGE_SOURCE",
    "NormalizedBridgeLine",
    "RawLineKind",
    "normalize_bridge_line",
    "parse_raw_line",
]
