"""Reconciliation service errors."""

from __future__ import annotations


class ReconciliationError(Exception):
    """Raised when reconciliation cannot complete safely.

    Wraps persistence failures so the caller can retry with a bounded
    policy; a failed run never marks reconciliation successful and never
    claims SYNCED.
    """

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


__all__ = ["ReconciliationError"]
