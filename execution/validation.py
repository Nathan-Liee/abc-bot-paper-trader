"""Validation rules for execution contracts.

Validation is fail-closed: every failure is a stable string tag so
callers can audit and classify without parsing prose.
"""

from __future__ import annotations

from datetime import UTC, datetime

from execution.models import (
    ExecutionCommand,
    TradePlan,
    is_valid_system_id,
    now_iso,
    parse_iso_ts,
)

# Exact contract field sets. Extra keys (e.g. TP, confidence, risk fields)
# are structurally rejected — execution has no authority over them.
PLAN_FIELDS: frozenset[str] = frozenset(
    {
        "trade_id",
        "correlation_id",
        "inference_id",
        "risk_evaluation_id",
        "direction",
        "lot",
        "entry_reference",
        "sl",
        "risk_amount",
        "risk_percent",
        "exposure",
        "symbol",
        "generated_at",
        "expires_at",
        "policy_profile",
    }
)

COMMAND_FIELDS: frozenset[str] = frozenset(
    {
        "command_id",
        "trade_id",
        "symbol",
        "direction",
        "volume",
        "entry_type",
        "sl",
        "created_at",
        "expires_at",
    }
)

# Fields that must never appear on an execution command (authority guard).
FORBIDDEN_COMMAND_FIELDS: frozenset[str] = frozenset(
    {
        "tp",
        "take_profit",
        "confidence",
        "reason",
        "inference_id",
        "risk_amount",
        "risk_percent",
        "exposure",
        "margin",
        "lot",
    }
)


def validate_plan(plan: TradePlan) -> list[str]:
    """Return failure tags for a TradePlan, or an empty list when valid."""
    errors = plan.validate()
    extra_keys = set(plan.to_dict()) - PLAN_FIELDS
    for key in sorted(extra_keys):
        errors.append(f"plan.unknown_field:{key}")
    return errors


def validate_plan_dict(data: dict[str, object]) -> list[str]:
    """Validate a raw mapping BEFORE constructing the plan.

    Rejects unknown keys — including any field an execution caller has
    no business carrying (TP, confidence, reasons). The plan's own
    contract fields (risk_amount, lot, ...) are expected here: they are
    System outputs, not execution inputs.
    """
    errors: list[str] = []
    data_keys = set(data)
    unknown = data_keys - PLAN_FIELDS
    for key in sorted(unknown):
        errors.append(f"plan.unknown_field:{key}")
    missing = PLAN_FIELDS - data_keys
    for key in sorted(missing):
        errors.append(f"plan.missing_field:{key}")
    return errors


def validate_command(command: ExecutionCommand) -> list[str]:
    """Return failure tags for an ExecutionCommand, or an empty list."""
    errors = command.validate()
    extra_keys = set(command.to_dict()) - COMMAND_FIELDS
    for key in sorted(extra_keys):
        errors.append(f"command.unknown_field:{key}")
    for key in FORBIDDEN_COMMAND_FIELDS:
        if key in command.to_dict():
            errors.append(f"command.forbidden_field:{key}")
    return errors


def validate_command_dict(data: dict[str, object]) -> list[str]:
    """Validate a raw command mapping before construction."""
    errors: list[str] = []
    data_keys = set(data)
    unknown = data_keys - COMMAND_FIELDS
    forbidden = data_keys & FORBIDDEN_COMMAND_FIELDS
    for key in sorted(unknown):
        errors.append(f"command.unknown_field:{key}")
    for key in sorted(forbidden):
        errors.append(f"command.forbidden_field:{key}")
    missing = COMMAND_FIELDS - data_keys
    for key in sorted(missing):
        errors.append(f"command.missing_field:{key}")
    if not is_valid_system_id(data.get("command_id")):
        errors.append("command.command_id:invalid_uuid")
    return errors


def is_expired(ts_expires_at: str, now: datetime | None = None) -> bool:
    """True when *now* is strictly after the expires_at timestamp.

    An unparseable timestamp is treated as expired (fail-closed).
    """
    expires = parse_iso_ts(ts_expires_at)
    if expires is None:
        return True
    current = now or datetime.now(UTC)
    return current > expires


def is_expired_plan(plan: TradePlan, now: datetime | None = None) -> bool:
    return is_expired(plan.expires_at, now=now)


def is_expired_command(command: ExecutionCommand, now: datetime | None = None) -> bool:
    return is_expired(command.expires_at, now=now)


def remaining_seconds(ts_expires_at: str, now: datetime | None = None) -> float:
    """Seconds until expiry (negative when expired); unparseable -> -inf."""
    expires = parse_iso_ts(ts_expires_at)
    if expires is None:
        return float("-inf")
    current = now or datetime.now(UTC)
    return (expires - current).total_seconds()


__all__ = [
    "COMMAND_FIELDS",
    "FORBIDDEN_COMMAND_FIELDS",
    "PLAN_FIELDS",
    "is_expired",
    "is_expired_command",
    "is_expired_plan",
    "now_iso",
    "remaining_seconds",
    "validate_command",
    "validate_command_dict",
    "validate_plan",
    "validate_plan_dict",
]
