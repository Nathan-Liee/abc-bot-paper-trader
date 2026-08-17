"""Execution layer error types.

All execution-layer failures carry a stable machine-readable
``error_code`` (see :mod:`execution.retry`) so upper layers react
deterministically without parsing message text.
"""

from __future__ import annotations

from execution.retry import ErrorCode


class ExecutionError(Exception):
    """Base execution error with a stable classification code."""

    def __init__(self, error_code: ErrorCode | str, message: str) -> None:
        self.error_code: str = (
            error_code.value if isinstance(error_code, ErrorCode) else str(error_code)
        )
        super().__init__(message)


class ExecutionStateError(ExecutionError):
    """Raised on an illegal lifecycle state transition."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INVALID_COMMAND, message)


class DuplicateCommandError(ExecutionError):
    """Raised when a command_id or active trade_id already exists."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.DUPLICATE_COMMAND, message)


class JournalError(ExecutionError):
    """Raised when the durable journal cannot satisfy an operation."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.FAILED, message)


__all__ = ["DuplicateCommandError", "ExecutionError", "ExecutionStateError", "JournalError"]
