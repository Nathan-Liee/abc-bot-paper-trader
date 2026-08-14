"""Canonical event contract: pure-data layer shared by all components.

This package is the single source of the event taxonomy, payload shape,
identity rules, and lifecycle constraints. It is deliberately free of
business logic: everything here mirrors
``docs/contracts/canonical-event-contract.md`` (v1.0.0) and the approved
validation & correction report.

The typed runtime representation (envelope, serialization, checksum)
lives in ``collector.event_model``; the machine-readable mirror of this
contract lives in ``shared/schemas/canonical-event.schema.json``.
"""

from shared.contracts.errors import ContractValidationError
from shared.contracts.identity import (
    BROKER_ID_FIELDS,
    BROKER_ID_MAX_LENGTH,
    SYSTEM_ID_FIELDS,
    UUID_PATTERN,
    is_valid_broker_id,
    is_valid_system_id,
)
from shared.contracts.lifecycle import (
    NEXT_ALLOWED,
    OUT_OF_BAND_EVENTS,
    TERMINAL_EVENTS,
    TRADE_FLOW,
    TRADE_FLOW_EVENTS,
    TradeLifecycle,
    validate_transition,
)
from shared.contracts.payload_specs import (
    PAYLOAD_SPECS,
    UNKNOWN_FIELD_PLACEHOLDER,
    ConditionalRule,
    NumericBound,
    PayloadSpec,
    get_spec,
)
from shared.contracts.types import SEVERITY_LEVELS, EventType

__all__ = [
    "BROKER_ID_FIELDS",
    "BROKER_ID_MAX_LENGTH",
    "ConditionalRule",
    "ContractValidationError",
    "EventType",
    "NEXT_ALLOWED",
    "NumericBound",
    "OUT_OF_BAND_EVENTS",
    "PAYLOAD_SPECS",
    "PayloadSpec",
    "SEVERITY_LEVELS",
    "SYSTEM_ID_FIELDS",
    "TERMINAL_EVENTS",
    "TRADE_FLOW",
    "TRADE_FLOW_EVENTS",
    "UNKNOWN_FIELD_PLACEHOLDER",
    "UUID_PATTERN",
    "TradeLifecycle",
    "get_spec",
    "is_valid_broker_id",
    "is_valid_system_id",
    "validate_transition",
]
