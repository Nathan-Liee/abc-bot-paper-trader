"""System validation gate — interface boundary only (this task).

The gate consumes an already-validated DecisionRecord and produces a
verdict. It contains NO risk/lot/SL/exposure/margin logic — the full Risk
Engine gate is a separate task. It is the explicit boundary between the AI
proposal layer and system authority: the system decides APPROVE/REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_decision.record import DecisionRecord


@dataclass(frozen=True)
class GateVerdict:
    verdict: str  # "APPROVE" | "REJECT"
    reason: str
    rejection_code: str | None = None


class SystemGate:
    """Boundary interface: DecisionRecord in -> GateVerdict out."""

    def evaluate(self, record: DecisionRecord) -> GateVerdict:
        if not record.validation_ok:
            return GateVerdict(
                verdict="REJECT",
                reason="AI proposal failed validation",
                rejection_code=record.error_class,
            )
        if record.direction == "NO-TRADE":
            return GateVerdict(
                verdict="APPROVE",
                reason="NO-TRADE proposal acknowledged (non-executable, no order path)",
            )
        return GateVerdict(
            verdict="APPROVE",
            reason="structurally valid AI proposal; full risk gate pending (separate task)",
        )
