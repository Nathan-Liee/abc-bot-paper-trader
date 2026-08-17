"""Reconciliation boundary — interface only, no broker implementation.

The Execution Engine never treats UNKNOWN as success or failure; an
UNKNOWN command is paused until the reconciliation boundary reports
broker truth (task §11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from execution.models import CommandState, ExecutionCommand, ExecutionResult, now_iso


@dataclass(frozen=True)
class ReconciliationOutcome:
    """Broker-truth evidence produced by a reconciliation attempt.

    * ``discovered_state`` — the actual command-relevant state when the
      broker reply is conclusive (None when no order/position exists or
      when the evidence is inconclusive)
    * ``ambiguous``        — True when the broker was not reachable or
      the response does not allow a conclusion (fail-closed)
    * ``evidence``         — verbatim observed facts (order/position ids,
      volumes, prices, states); never fabricated
    """

    discovered_state: CommandState | None = None
    ambiguous: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=now_iso)


class ReconciliationBoundary(Protocol):
    """Contract the engine relies on for UNKNOWN resolution."""

    def reconcile(
        self,
        command: ExecutionCommand,
        hint: ExecutionResult | None = None,
    ) -> ReconciliationOutcome:
        """Query broker truth for *command* (or a past ambiguous result).

        Implementation lives in a future EA/broker-reconciliation task;
        this task provides mocks only.
        """
        ...


class StaticReconciliation:
    """Mock boundary for tests/paper mode: returns a configured outcome."""

    def __init__(self, outcome: ReconciliationOutcome | None = None) -> None:
        self._outcome = outcome
        self.calls: list[ExecutionCommand] = []

    def set_outcome(self, outcome: ReconciliationOutcome | None) -> None:
        self._outcome = outcome

    def reconcile(
        self,
        command: ExecutionCommand,
        hint: ExecutionResult | None = None,
    ) -> ReconciliationOutcome:
        self.calls.append(command)
        if self._outcome is None:
            return ReconciliationOutcome(ambiguous=True, evidence={"hint": hint})
        return self._outcome


__all__ = ["ReconciliationBoundary", "ReconciliationOutcome", "StaticReconciliation"]
