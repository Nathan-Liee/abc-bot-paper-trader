"""Deterministic validation functions for AI outputs.

Five standalone validators, strict by design. NO risk/lot/SL logic lives here —
this module only enforces the AI proposal contract and the authority boundary.
"""

from __future__ import annotations

import math
from typing import Any

VALID_DIRECTIONS = ("BUY", "SELL", "NO-TRADE")

# Fields the AI must never emit — system authority (task item 10).
FORBIDDEN_OUTPUT_KEYS = {
    "lot",
    "lots",
    "position_size",
    "position",
    "risk_percent",
    "risk_amount",
    "risk",
    "sl",
    "stop_loss",
    "stoploss",
    "tp",
    "take_profit",
    "takeprofit",
    "exposure",
    "margin",
    "order",
    "orders",
    "order_type",
    "volume",
    "entry_price",
    "execution",
    "exit",
    "compounding",
    "broker",
    "broker_id",
    "trade_id",
}

FORBIDDEN_REASON_PHRASES = (
    "stop loss",
    "take profit",
    "lot size",
    "position size",
    "margin call",
    "compounding",
    "place order",
    "execute",
    "buy limit",
    "sell stop",
    "entry order",
)

REASON_MAX_LENGTH = 2000


def validate_direction(value: object) -> tuple[str | None, str | None]:
    """Return (direction, error). Direction must be an exact valid token."""
    if not isinstance(value, str):
        return None, "direction_not_string"
    direction = value.strip().upper()
    if direction not in VALID_DIRECTIONS:
        return None, "direction_invalid"
    return direction, None


def validate_confidence(value: object) -> tuple[float | None, str | None]:
    """Return (confidence, error). Must be a finite number in [0, 1]."""
    if isinstance(value, bool):
        return None, "confidence_not_number"
    if not isinstance(value, (int, float)):
        return None, "confidence_not_number"
    if not math.isfinite(value):
        return None, "confidence_not_finite"
    if value < 0.0 or value > 1.0:
        return None, "confidence_out_of_range"
    return round(float(value), 4), None


def validate_reason(value: object) -> tuple[str | None, str | None]:
    """Return (reason, error). Reason must be a string (may be empty)."""
    if not isinstance(value, str):
        return None, "reason_not_string"
    if len(value) > REASON_MAX_LENGTH:
        return None, "reason_too_long"
    return value.strip(), None


def validate_authority_boundary(payload_keys: set[str] | frozenset[str]) -> list[str]:
    """List of AUTHORITY_VIOLATION reasons, empty when boundary is clean."""
    violations: list[str] = []
    bad_keys = FORBIDDEN_OUTPUT_KEYS & {k.lower() for k in payload_keys}
    if bad_keys:
        violations.append("forbidden_output_key:" + ",".join(sorted(bad_keys)))
    return violations


def validate_schema(
    output: dict[str, Any], payload_keys: set[str] | frozenset[str]
) -> tuple[bool, list[str], tuple[str, float, str] | None]:
    """Validate the full contract. Returns (ok, errors, clean output triple).

    Strict: invalid direction, out-of-range/missing confidence, non-string
    reason, forbidden reason phrases, or any authority violation rejects the
    decision (fail-closed).
    """
    errors: list[str] = []

    direction, err = validate_direction(output.get("direction"))
    if err:
        errors.append(err)

    confidence, err = validate_confidence(output.get("confidence"))
    if err:
        errors.append(err)

    reason, err = validate_reason(output.get("reason"))
    if err:
        errors.append(err)

    violations = validate_authority_boundary(payload_keys)
    if violations:
        errors.append("AUTHORITY_VIOLATION:" + ";".join(violations))

    reason_lower = str(output.get("reason") or "").lower()
    for phrase in FORBIDDEN_REASON_PHRASES:
        if phrase in reason_lower:
            errors.append("AUTHORITY_VIOLATION:forbidden_reason_phrase:" + phrase)

    if errors:
        return False, errors, None
    assert direction is not None and confidence is not None and reason is not None
    return True, [], (direction, confidence, reason)
