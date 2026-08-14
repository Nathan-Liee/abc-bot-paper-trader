"""Typed, immutable envelope for canonical events.

``EventEnvelope`` is the runtime representation of the envelope defined
in docs/contracts/canonical-event-contract.md section 3. It is validated
on construction and carries a computed ``checksum`` that must be verified
when reading events back from disk.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from collector.event_model.checksum import compute_checksum, verify_checksum
from collector.event_model.ids import new_event_id
from collector.event_model.timestamps import monotonic_ms, now_utc_ms
from collector.event_model.validation import validate_event_dict, validate_payload
from shared.constants import DEFAULT_COMPONENT, DEFAULT_SEVERITY, SCHEMA_VERSION
from shared.contracts.errors import ContractValidationError
from shared.contracts.types import EventType


@dataclass(frozen=True)
class EventEnvelope:
    """An immutable canonical event.

    ``payload`` is a read-only mapping; the envelope never mutates after
    construction. Event ids are immutable and broker ids are never
    generated here.
    """

    event_id: str
    event_type: EventType
    ts_event: str
    ts_collected: str
    ts_monotonic: int
    component: str
    severity: str
    schema_version: str
    payload: Mapping[str, object]
    checksum: str
    correlation_id: str | None = None
    trade_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the wire representation (deterministic key order)."""
        data: dict[str, object] = {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "ts_event": self.ts_event,
            "ts_collected": self.ts_collected,
            "ts_monotonic": self.ts_monotonic,
            "component": self.component,
            "severity": self.severity,
            "schema_version": self.schema_version,
            "payload": dict(self.payload),
        }
        if self.correlation_id is not None:
            data["correlation_id"] = self.correlation_id
        if self.trade_id is not None:
            data["trade_id"] = self.trade_id
        data["checksum"] = self.checksum
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> EventEnvelope:
        """Build an envelope from a dict, validating it and its checksum."""
        validate_event_dict(data)
        raw_type = data["event_type"]
        assert isinstance(raw_type, str)
        event_type = EventType(raw_type)
        payload_data = data["payload"]
        assert isinstance(payload_data, dict)
        envelope = cls(
            event_id=data["event_id"],  # type: ignore[arg-type]
            event_type=event_type,
            ts_event=data["ts_event"],  # type: ignore[arg-type]
            ts_collected=data["ts_collected"],  # type: ignore[arg-type]
            ts_monotonic=data["ts_monotonic"],  # type: ignore[arg-type]
            component=data["component"],  # type: ignore[arg-type]
            severity=data["severity"],  # type: ignore[arg-type]
            schema_version=data["schema_version"],  # type: ignore[arg-type]
            payload=MappingProxyType(payload_data),
            checksum=data["checksum"],  # type: ignore[arg-type]
            correlation_id=data.get("correlation_id"),  # type: ignore[arg-type]
            trade_id=data.get("trade_id"),  # type: ignore[arg-type]
        )
        if not verify_checksum(data):
            raise ContractValidationError(
                f"checksum mismatch for event {envelope.event_id} ({event_type.value})"
            )
        return envelope

    def verify_checksum(self) -> bool:
        """Re-verify this envelope's checksum against its own content."""
        return verify_checksum(self.to_dict())


def build_event(
    event_type: EventType | str,
    payload: Mapping[str, object],
    *,
    ts_event: str | None = None,
    ts_collected: str | None = None,
    ts_monotonic: int | None = None,
    component: str = DEFAULT_COMPONENT,
    severity: str = DEFAULT_SEVERITY,
    correlation_id: str | None = None,
    trade_id: str | None = None,
) -> EventEnvelope:
    """Build a validated event with generated ids and a computed checksum.

    ``checksum`` cannot be supplied: it is always computed from the final
    canonical content of the event.
    """
    if isinstance(event_type, str):
        try:
            resolved_type = EventType(event_type)
        except ValueError:
            raise ContractValidationError(f"unknown event type: {event_type!r}") from None
    else:
        resolved_type = event_type

    validate_payload(resolved_type, payload)

    data: dict[str, object] = {
        "event_id": new_event_id(),
        "event_type": resolved_type.value,
        "ts_event": ts_event if ts_event is not None else now_utc_ms(),
        "ts_collected": ts_collected if ts_collected is not None else now_utc_ms(),
        "ts_monotonic": ts_monotonic if ts_monotonic is not None else monotonic_ms(),
        "component": component,
        "severity": severity,
        "schema_version": SCHEMA_VERSION,
        "payload": dict(payload),
    }
    if correlation_id is not None:
        data["correlation_id"] = correlation_id
    if trade_id is not None:
        data["trade_id"] = trade_id
    data["checksum"] = compute_checksum(data)

    return EventEnvelope.from_dict(data)


__all__ = ["EventEnvelope", "build_event"]
