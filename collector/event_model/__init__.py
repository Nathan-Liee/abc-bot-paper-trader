"""Typed event model implementing the canonical event contract.

Public API for building, validating, serializing, checksumming, and
sequence-validating canonical events (docs/contracts/canonical-event-contract.md
v1.0.0). No trading, AI, persistence, or broker integration lives here.
"""

from collector.event_model.checksum import (
    canonical_json_bytes,
    canonical_json_str,
    compute_checksum,
    strip_checksum_fields,
    verify_checksum,
)
from collector.event_model.envelope import EventEnvelope, build_event
from collector.event_model.ids import new_event_id, new_system_id
from collector.event_model.lifecycle import validate_sequence
from collector.event_model.serialization import from_json, to_json
from collector.event_model.timestamps import (
    ISO_UTC_MS_PATTERN,
    ISO_UTC_PATTERN,
    is_valid_iso_utc,
    is_valid_iso_utc_ms,
    monotonic_ms,
    now_utc_ms,
)
from collector.event_model.validation import validate_event_dict, validate_payload
from shared.contracts.errors import ContractValidationError
from shared.contracts.lifecycle import TradeLifecycle, validate_transition
from shared.contracts.types import EventType

__all__ = [
    "ContractValidationError",
    "EventEnvelope",
    "EventType",
    "ISO_UTC_MS_PATTERN",
    "ISO_UTC_PATTERN",
    "TradeLifecycle",
    "build_event",
    "canonical_json_bytes",
    "canonical_json_str",
    "compute_checksum",
    "from_json",
    "is_valid_iso_utc",
    "is_valid_iso_utc_ms",
    "monotonic_ms",
    "new_event_id",
    "new_system_id",
    "now_utc_ms",
    "strip_checksum_fields",
    "to_json",
    "validate_event_dict",
    "validate_payload",
    "validate_sequence",
    "validate_transition",
    "verify_checksum",
]
