"""Executor boundary — the only place broker/simulator interaction happens.

The protocol is deliberately tiny: submit market, read position,
attach SL, close, query. No risk/lot/SL computation exists here; values
arrive verbatim from the System-approved command (task §6, §18).
"""

from __future__ import annotations

from typing import Protocol

from execution.models import ExecutionCommand, ExecutionResult, PositionSnapshot
from execution.reconciliation import ReconciliationOutcome


class Executor(Protocol):
    """Contract implemented by the simulated executor now and by the
    EA/broker adapter in a future task."""

    def submit(self, command: ExecutionCommand) -> ExecutionResult: ...

    def get_position(self, command: ExecutionCommand) -> PositionSnapshot | None: ...

    def attach_sl(
        self, command: ExecutionCommand, position_id: str, sl: float
    ) -> ExecutionResult: ...

    def close_position(self, command: ExecutionCommand, position_id: str) -> ExecutionResult: ...

    def query(self, command: ExecutionCommand) -> ReconciliationOutcome: ...


__all__ = ["Executor"]
