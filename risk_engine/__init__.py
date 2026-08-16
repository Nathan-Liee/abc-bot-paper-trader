"""Risk Engine package — System-owned risk evaluation, lot sizing, and gate.

Enforces absolute authority boundary: AI proposes direction; System validates,
calculates risk/lot/SL/exposure, and produces APPROVE/REJECT trade plan.
Zero broker execution.
"""

from __future__ import annotations

from risk_engine.config import RiskConfig
from risk_engine.engine import RiskEngine
from risk_engine.gate import SystemRiskGate
from risk_engine.models import (
    AccountState,
    MarketState,
    RiskDecision,
    RiskEvaluationRecord,
    SymbolSpecification,
)
from risk_engine.reason_codes import ReasonCode

__all__ = [
    "AccountState",
    "MarketState",
    "ReasonCode",
    "RiskConfig",
    "RiskDecision",
    "RiskEngine",
    "RiskEvaluationRecord",
    "SymbolSpecification",
    "SystemRiskGate",
]
