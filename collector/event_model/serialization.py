"""Deterministic JSON serialization of canonical events.

Wire format: UTF-8, snake_case keys, deterministic (envelope-defined)
key ordering, no insignificant whitespace, optional fields omitted, and
consistent UTC timestamp strings. This is the format written by the
collector; the checksum canonical form (sorted keys) is separate and
lives in ``collector.event_model.checksum``.
"""

from __future__ import annotations

import json

from collector.event_model.envelope import EventEnvelope
from shared.contracts.errors import ContractValidationError


def to_json(event: EventEnvelope) -> str:
    """Serialize *event* to compact JSON with deterministic key order."""
    return json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"))


def from_json(data: str) -> EventEnvelope:
    """Parse *data* into a validated ``EventEnvelope``."""
    try:
        raw = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ContractValidationError(f"invalid event JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ContractValidationError("event JSON must be a JSON object")
    return EventEnvelope.from_dict(raw)


__all__ = ["from_json", "to_json"]
