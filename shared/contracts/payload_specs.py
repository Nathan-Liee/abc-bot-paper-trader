"""Declarative payload contract for every canonical event type.

Source of truth: docs/contracts/canonical-event-contract.md
section 4 (Payload Contract per Event Type). The registry below is a
pure-data mirror of that document and must not contain business logic.

Field type tokens:
    str       non-empty string
    number    int or float (finite)
    int       integer (bool excluded)
    bool      boolean
    dict      JSON object
    uuid      system-owned UUID string (see identity)
    broker_id broker-owned external string (see identity)
    iso_ts    ISO 8601 UTC timestamp, seconds or millisecond precision
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from shared.contracts.errors import ContractValidationError
from shared.contracts.types import EventType

TypeToken: TypeAlias = Literal[
    "str", "number", "int", "bool", "dict", "uuid", "broker_id", "iso_ts"
]

UNKNOWN_FIELD_PLACEHOLDER = "_unknown"


@dataclass(frozen=True)
class ConditionalRule:
    """Field presence rule triggered by (trigger_field == trigger_value)."""

    trigger_field: str
    trigger_value: object
    requires: tuple[str, ...] = ()
    forbids: tuple[str, ...] = ()


@dataclass(frozen=True)
class NumericBound:
    """Numeric bound rule: field must satisfy <op> <value>."""

    field: str
    op: Literal["gt", "ge", "lt", "le"]
    value: float


@dataclass(frozen=True)
class PayloadSpec:
    event_type: EventType
    required: tuple[str, ...]
    optional: tuple[str, ...]
    types: dict[str, TypeToken]
    enums: dict[str, tuple[str, ...]] = field(default_factory=dict)
    const_values: dict[str, str] = field(default_factory=dict)
    conditional_rules: tuple[ConditionalRule, ...] = ()
    numeric_rules: tuple[NumericBound, ...] = ()

    @property
    def known_fields(self) -> frozenset[str]:
        """Every field this event may carry, conditional fields included."""
        conditional = {
            name for rule in self.conditional_rules for name in (*rule.requires, *rule.forbids)
        }
        return frozenset({*self.required, *self.optional, *self.types, *conditional})

    @property
    def allowed_fields(self) -> frozenset[str]:
        """Every field this event may carry on the wire."""
        return self.known_fields | frozenset({UNKNOWN_FIELD_PLACEHOLDER})


PAYLOAD_SPECS: dict[EventType, PayloadSpec] = {}


def _register(
    event_type: EventType,
    required: tuple[str, ...],
    optional: tuple[str, ...],
    types: dict[str, TypeToken],
    enums: dict[str, tuple[str, ...]] | None = None,
    const_values: dict[str, str] | None = None,
    conditional_rules: tuple[ConditionalRule, ...] | None = None,
    numeric_rules: tuple[NumericBound, ...] | None = None,
) -> None:
    PAYLOAD_SPECS[event_type] = PayloadSpec(
        event_type=event_type,
        required=required,
        optional=optional,
        types=types,
        enums=enums or {},
        const_values=const_values or {},
        conditional_rules=conditional_rules or (),
        numeric_rules=numeric_rules or (),
    )


_register(
    EventType.TICK_RECEIVED,
    required=("symbol", "bid", "ask", "mid", "spread", "ts_source"),
    optional=("tick_volume", "tick_id"),
    types={
        "symbol": "str",
        "bid": "number",
        "ask": "number",
        "mid": "number",
        "spread": "number",
        "ts_source": "iso_ts",
        "tick_volume": "int",
        "tick_id": "str",
    },
)

_register(
    EventType.TRIGGER_DETECTED,
    required=("trigger_source", "trigger_category", "trigger_metadata", "context_reference"),
    optional=(),
    types={
        "trigger_source": "str",
        "trigger_category": "str",
        "trigger_metadata": "dict",
        "context_reference": "str",
    },
    enums={"trigger_source": ("TECHNICAL", "MARKET_EVENT", "SAFETY_FILTER", "HYBRID")},
)

_register(
    EventType.CONTEXT_BUILT,
    required=("symbol", "m1_context_ref", "m5_context_ref", "atr_m1", "context_snapshot_id"),
    optional=("atr_m5", "derived_features"),
    types={
        "symbol": "str",
        "m1_context_ref": "str",
        "m5_context_ref": "str",
        "atr_m1": "number",
        "context_snapshot_id": "str",
        "atr_m5": "number",
        "derived_features": "dict",
    },
)

_register(
    EventType.AI_REQUEST,
    required=("inference_id", "request_ts", "context_snapshot_id"),
    optional=("model_ref",),
    types={
        "inference_id": "uuid",
        "request_ts": "iso_ts",
        "context_snapshot_id": "str",
        "model_ref": "str",
    },
)

_register(
    EventType.AI_RESPONSE,
    required=("inference_id", "decision", "confidence", "reason", "latency_ms", "valid"),
    optional=("error",),
    types={
        "inference_id": "uuid",
        "decision": "str",
        "confidence": "number",
        "reason": "str",
        "latency_ms": "number",
        "valid": "bool",
        "error": "str",
    },
    enums={"decision": ("BUY", "SELL", "NO-TRADE")},
    conditional_rules=(
        ConditionalRule(
            trigger_field="valid",
            trigger_value=False,
            requires=("error",),
        ),
        ConditionalRule(
            trigger_field="valid",
            trigger_value=True,
            forbids=("error",),
        ),
    ),
    numeric_rules=(
        NumericBound(field="confidence", op="ge", value=0.0),
        NumericBound(field="confidence", op="le", value=1.0),
        NumericBound(field="latency_ms", op="ge", value=0.0),
    ),
)

_register(
    EventType.RISK_GATE,
    required=(
        "gate_result",
        "risk_budget_usd",
        "candidate_lot",
        "final_lot",
        "aggregate_risk_usd",
        "aggregate_exposure_usd",
        "free_margin_usd",
    ),
    optional=(),
    types={
        "gate_result": "str",
        "risk_budget_usd": "number",
        "candidate_lot": "number",
        "final_lot": "number",
        "aggregate_risk_usd": "number",
        "aggregate_exposure_usd": "number",
        "free_margin_usd": "number",
        "rejection_reason": "str",
    },
    enums={"gate_result": ("ALLOW", "REJECT")},
    conditional_rules=(
        ConditionalRule(
            trigger_field="gate_result",
            trigger_value="REJECT",
            requires=("rejection_reason",),
        ),
        ConditionalRule(
            trigger_field="gate_result",
            trigger_value="ALLOW",
            forbids=("rejection_reason",),
        ),
    ),
)

_register(
    EventType.ORDER_SUBMITTED,
    required=("requested_price", "requested_volume", "direction", "order_type", "submission_ts"),
    optional=(),
    types={
        "requested_price": "number",
        "requested_volume": "number",
        "direction": "str",
        "order_type": "str",
        "submission_ts": "iso_ts",
    },
)

_register(
    EventType.ORDER_ACKNOWLEDGED,
    required=("broker_order_id", "broker_state", "ack_ts"),
    optional=(),
    types={
        "broker_order_id": "broker_id",
        "broker_state": "str",
        "ack_ts": "iso_ts",
    },
)

_register(
    EventType.ORDER_FILLED,
    required=(
        "broker_order_id",
        "broker_deal_id",
        "fill_price",
        "fill_volume",
        "slippage",
        "fill_ts",
    ),
    optional=(),
    types={
        "broker_order_id": "broker_id",
        "broker_deal_id": "broker_id",
        "fill_price": "number",
        "fill_volume": "number",
        "slippage": "number",
        "fill_ts": "iso_ts",
    },
)

_register(
    EventType.POSITION_OPENED,
    required=("broker_position_id", "direction", "volume", "open_price", "open_ts", "state"),
    optional=(),
    types={
        "broker_position_id": "broker_id",
        "direction": "str",
        "volume": "number",
        "open_price": "number",
        "open_ts": "iso_ts",
        "state": "str",
    },
    const_values={"state": "OPEN"},
)

_register(
    EventType.POSITION_UPDATED,
    required=(
        "broker_position_id",
        "current_price",
        "running_pnl_usd",
        "running_net_pnl_usd",
        "mfe_usd",
        "mae_usd",
        "spread_current",
    ),
    optional=(),
    types={
        "broker_position_id": "broker_id",
        "current_price": "number",
        "running_pnl_usd": "number",
        "running_net_pnl_usd": "number",
        "mfe_usd": "number",
        "mae_usd": "number",
        "spread_current": "number",
    },
)

_register(
    EventType.NET_PROFIT_POSITIVE,
    required=(
        "broker_position_id",
        "trade_id",
        "running_net_pnl_usd",
        "detection_ts",
        "observed_bid",
        "observed_ask",
        "spread_at_detection",
        "reason",
    ),
    optional=(),
    types={
        "broker_position_id": "broker_id",
        "trade_id": "uuid",
        "running_net_pnl_usd": "number",
        "detection_ts": "iso_ts",
        "observed_bid": "number",
        "observed_ask": "number",
        "spread_at_detection": "number",
        "reason": "str",
    },
    const_values={"reason": "NET_PROFIT_THRESHOLD_CROSSED"},
    numeric_rules=(NumericBound(field="running_net_pnl_usd", op="gt", value=0.0),),
)

_register(
    EventType.EXIT_SUBMITTED,
    required=("broker_position_id", "requested_close_price", "close_volume", "submission_ts"),
    optional=(),
    types={
        "broker_position_id": "broker_id",
        "requested_close_price": "number",
        "close_volume": "number",
        "submission_ts": "iso_ts",
    },
)

_register(
    EventType.POSITION_CLOSED,
    required=(
        "broker_position_id",
        "exit_fill_price",
        "exit_fill_volume",
        "exit_fill_ts",
        "realized_pnl_usd",
        "transaction_cost_usd",
        "net_pnl_usd",
        "exit_reason",
        "final_state",
    ),
    optional=(),
    types={
        "broker_position_id": "broker_id",
        "exit_fill_price": "number",
        "exit_fill_volume": "number",
        "exit_fill_ts": "iso_ts",
        "realized_pnl_usd": "number",
        "transaction_cost_usd": "number",
        "net_pnl_usd": "number",
        "exit_reason": "str",
        "final_state": "str",
    },
    const_values={"final_state": "CLOSED"},
)

_register(
    EventType.RECONCILIATION,
    required=(
        "reconciliation_id",
        "trigger",
        "local_state",
        "broker_state",
        "mismatch",
        "result",
        "action",
        "ts",
    ),
    optional=("mismatch_details",),
    types={
        "reconciliation_id": "uuid",
        "trigger": "str",
        "local_state": "str",
        "broker_state": "str",
        "mismatch": "bool",
        "result": "str",
        "action": "str",
        "ts": "iso_ts",
        "mismatch_details": "dict",
    },
    enums={
        "trigger": ("STARTUP", "POST_EXECUTION", "HEARTBEAT", "MISMATCH"),
        "result": ("SYNCED", "ADOPTED_BROKER", "ESCALATED"),
    },
    conditional_rules=(
        ConditionalRule(
            trigger_field="mismatch",
            trigger_value=False,
            forbids=("mismatch_details",),
        ),
    ),
)

_register(
    EventType.ERROR,
    required=("error_code", "component", "severity", "message"),
    optional=("trade_id", "recovery_action"),
    types={
        "error_code": "str",
        "component": "str",
        "severity": "str",
        "message": "str",
        "trade_id": "uuid",
        "recovery_action": "str",
    },
    enums={"severity": ("INFO", "WARN", "ERROR", "CRITICAL")},
)

_register(
    EventType.TIMEOUT,
    required=("timeout_code", "component", "severity", "message"),
    optional=("trade_id", "recovery_action"),
    types={
        "timeout_code": "str",
        "component": "str",
        "severity": "str",
        "message": "str",
        "trade_id": "uuid",
        "recovery_action": "str",
    },
    enums={"severity": ("INFO", "WARN", "ERROR", "CRITICAL")},
)


def get_spec(event_type: EventType | str) -> PayloadSpec:
    """Resolve the payload spec for *event_type* or raise a contract error."""
    if isinstance(event_type, EventType):
        resolved = event_type
    else:
        try:
            resolved = EventType(event_type)
        except ValueError:
            raise ContractValidationError(f"Unknown event type: {event_type!r}") from None
    return PAYLOAD_SPECS[resolved]


__all__ = [
    "ConditionalRule",
    "NumericBound",
    "PAYLOAD_SPECS",
    "PayloadSpec",
    "TypeToken",
    "UNKNOWN_FIELD_PLACEHOLDER",
    "get_spec",
]
