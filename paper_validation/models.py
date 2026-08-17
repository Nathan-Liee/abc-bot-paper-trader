"""Data models for paper validation harness."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ExitReason(StrEnum):
    """Exit reason codes for simulated trades."""

    ABC_PROFIT_CLOSE = "ABC_PROFIT_CLOSE"
    SL_STOP = "SL_STOP"
    SPREAD_REJECT = "SPREAD_REJECT"
    RISK_REJECT = "RISK_REJECT"
    MARGIN_REJECT = "MARGIN_REJECT"
    EXPOSURE_REJECT = "EXPOSURE_REJECT"
    DRAWDOWN_REJECT = "DRAWDOWN_REJECT"
    DATA_INVALID = "DATA_INVALID"
    PAPER_SESSION_END = "PAPER_SESSION_END"


@dataclass(frozen=True)
class SimulationConfig:
    """Top-level simulation configuration."""

    starting_equity: float = 10000.0
    starting_balance: float = 10000.0
    leverage: float = 2000.0
    max_steps_per_scenario: int = 500
    seed: int = 42


@dataclass(frozen=True)
class ScenarioConfig:
    """One scenario definition for paper validation."""

    scenario_id: str
    description: str
    direction: str  # "BUY" | "SELL" | "NO-TRADE"
    confidence: float = 0.85
    reason: str = "fixture"
    ticks: list[dict[str, Any]] = field(default_factory=list)
    cost_mode: str = "SPREAD_ONLY"
    slippage_points: float = 0.0
    commission_per_lot: float = 0.0
    swap_per_lot_per_night: float = 0.0
    starting_equity: float = 10000.0
    starting_balance: float = 10000.0
    existing_positions: int = 0
    current_exposure_usd: float = 0.0
    current_drawdown_pct: float = 0.0
    free_margin_override: float | None = None
    margin_override: float | None = None
    force_reject_reason: str | None = None


@dataclass
class PaperAccount:
    """Mutable account state for paper simulation."""

    balance: float
    equity: float
    free_margin: float
    margin: float
    existing_positions_count: int = 0
    current_exposure_usd: float = 0.0
    current_drawdown_pct: float = 0.0

    def to_risk_engine_state(self) -> dict[str, Any]:
        return {
            "balance": self.balance,
            "equity": self.equity,
            "free_margin": self.free_margin,
            "margin": self.margin,
            "existing_positions_count": self.existing_positions_count,
            "current_exposure_usd": self.current_exposure_usd,
            "current_drawdown_pct": self.current_drawdown_pct,
        }


@dataclass(frozen=True)
class ScenarioResult:
    """Result of one scenario execution."""

    scenario_id: str
    approved: bool
    exit_reason: str
    trade_evidence: dict[str, Any] | None = None
    rejection_reason_code: str | None = None
    rejection_message: str | None = None
    notes: str = ""


def new_trade_id() -> str:
    return f"paper-{uuid.uuid4().hex[:12]}"
