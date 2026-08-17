"""Error classification and retry policy for the execution layer.

Mapping is an explicit contract (task §9). Every error code resolves to
exactly one retry class:

* ``SAFE``     — bounded retry of the SAME command_id, only after
                 reconciliation confirms no broker evidence
* ``UNSAFE``   — blind resend is FORBIDDEN (never used for input, kept
                 as an explicit marker)
* ``RECONCILE``— no action until broker truth is established
* ``PERMANENT``— terminal failure; no retry without owner
* ``EMERGENCY``— protective action required (SL attach failure)
* ``IDEMPOTENT``— replay of an already-stored outcome
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable execution error codes (task §9 matrix)."""

    INVALID_COMMAND = "INVALID_COMMAND"
    AUTHENTICATION = "AUTHENTICATION"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    BROKER_REJECT = "BROKER_REJECT"
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    INVALID_VOLUME_SL = "INVALID_VOLUME_SL"
    MARKET_CLOSED = "MARKET_CLOSED"
    REQUOTE_SLIPPAGE = "REQUOTE_SLIPPAGE"
    DUPLICATE_COMMAND = "DUPLICATE_COMMAND"
    AMBIGUOUS_RESPONSE = "AMBIGUOUS_RESPONSE"
    STALE_FEED = "STALE_FEED"
    POSITION_EXISTS = "POSITION_EXISTS"
    EXPIRED = "EXPIRED"
    SL_ATTACH_FAILED = "SL_ATTACH_FAILED"
    CLOSE_FAILED = "CLOSE_FAILED"
    EMERGENCY_CLOSE_FAILED = "EMERGENCY_CLOSE_FAILED"
    RECONCILIATION_PENDING = "RECONCILIATION_PENDING"
    FAILED = "FAILED"


class RetryClass(StrEnum):
    """Deterministic retry classification."""

    SAFE = "SAFE"
    UNSAFE = "UNSAFE"
    RECONCILE = "RECONCILE"
    PERMANENT = "PERMANENT"
    EMERGENCY = "EMERGENCY"
    IDEMPOTENT = "IDEMPOTENT"


# Explicit matrix — every code appears exactly once.
RETRY_MATRIX: dict[ErrorCode, RetryClass] = {
    ErrorCode.INVALID_COMMAND: RetryClass.PERMANENT,
    ErrorCode.AUTHENTICATION: RetryClass.PERMANENT,
    ErrorCode.NETWORK_TIMEOUT: RetryClass.SAFE,
    ErrorCode.BROKER_REJECT: RetryClass.PERMANENT,
    ErrorCode.INSUFFICIENT_MARGIN: RetryClass.PERMANENT,
    ErrorCode.INVALID_VOLUME_SL: RetryClass.PERMANENT,
    ErrorCode.MARKET_CLOSED: RetryClass.PERMANENT,
    ErrorCode.REQUOTE_SLIPPAGE: RetryClass.PERMANENT,
    ErrorCode.DUPLICATE_COMMAND: RetryClass.IDEMPOTENT,
    ErrorCode.AMBIGUOUS_RESPONSE: RetryClass.RECONCILE,
    ErrorCode.STALE_FEED: RetryClass.PERMANENT,
    ErrorCode.POSITION_EXISTS: RetryClass.PERMANENT,
    ErrorCode.EXPIRED: RetryClass.PERMANENT,
    ErrorCode.SL_ATTACH_FAILED: RetryClass.EMERGENCY,
    ErrorCode.CLOSE_FAILED: RetryClass.SAFE,
    ErrorCode.EMERGENCY_CLOSE_FAILED: RetryClass.RECONCILE,
    ErrorCode.RECONCILIATION_PENDING: RetryClass.RECONCILE,
    ErrorCode.FAILED: RetryClass.UNSAFE,
}

UNCLASSIFIED_ERROR = RetryClass.RECONCILE


def classify_error(error_code: str | None) -> RetryClass:
    """Resolve *error_code* to its retry class.

    An unknown or missing code is treated as RECONCILE (fail-closed:
    do not act, do not retry, establish truth first).
    """
    if error_code is None:
        return UNCLASSIFIED_ERROR
    try:
        return RETRY_MATRIX[ErrorCode(error_code)]
    except ValueError:
        return UNCLASSIFIED_ERROR


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry budgets (owner-approved OD-4/OD-5).

    A budget is the number of RETRIES after the initial attempt, so the
    worst-case attempt count is ``budget + 1``. After the budget is
    exhausted the command transitions to UNKNOWN and reconciliation is
    required. Retries always reuse the SAME command_id/idempotency key.
    """

    close_retries: int = 2
    sl_attach_retries: int = 2
    submit_retries: int = 2

    def validate(self) -> list[str]:
        errors: list[str] = []
        for name, value in (
            ("close_retries", self.close_retries),
            ("sl_attach_retries", self.sl_attach_retries),
            ("submit_retries", self.submit_retries),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"retry_policy.{name}:invalid:{value}")
        return errors


__all__ = [
    "ErrorCode",
    "RETRY_MATRIX",
    "RetryClass",
    "RetryPolicy",
    "classify_error",
]
