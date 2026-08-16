"""System Risk Gate boundary interface for Future EA / Execution Integration."""

from __future__ import annotations

from typing import Any

from ai_decision.record import DecisionRecord
from risk_engine.engine import RiskEngine
from risk_engine.models import (
    AccountState,
    MarketState,
    RiskDecision,
    RiskEvaluationRecord,
    SymbolSpecification,
)


class SystemRiskGate:
    """Boundary Interface: AI Proposal + System State in -> Risk Decision / Evaluation Record out.

    This class is the public contract used by the orchestrator and future execution engine.
    Zero broker execution occurs here.
    """

    def __init__(self, engine: RiskEngine | None = None) -> None:
        self._engine = engine or RiskEngine()

    @property
    def engine(self) -> RiskEngine:
        return self._engine

    def evaluate_proposal(
        self,
        ai_proposal: DecisionRecord | dict[str, Any],
        account: AccountState,
        market: MarketState,
        spec: SymbolSpecification,
        *,
        correlation_id: str | None = None,
    ) -> RiskDecision:
        """Convenience method returning the simplified JSON-serializable RiskDecision (§11)."""
        record = self._engine.evaluate(
            ai_proposal=ai_proposal,
            account=account,
            market=market,
            spec=spec,
            correlation_id=correlation_id,
        )
        return record.to_decision()

    def evaluate_audit(
        self,
        ai_proposal: DecisionRecord | dict[str, Any],
        account: AccountState,
        market: MarketState,
        spec: SymbolSpecification,
        *,
        correlation_id: str | None = None,
    ) -> RiskEvaluationRecord:
        """Comprehensive audit evaluation method returning full RiskEvaluationRecord (§22)."""
        return self._engine.evaluate(
            ai_proposal=ai_proposal,
            account=account,
            market=market,
            spec=spec,
            correlation_id=correlation_id,
        )
