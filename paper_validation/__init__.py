"""Paper validation harness — deterministic simulated trading lifecycle.

No broker execution. No live orders. Uses Risk Engine as source of truth
for all risk/lot/SL calculations. Produces trade-level evidence for RiskConfig
v0.1 revision decisions.
"""

from __future__ import annotations

from paper_validation.cost_model import CostMode, CostModel, CostResult
from paper_validation.evidence import TradeEvidence
from paper_validation.execution_simulator import SimulatedFill
from paper_validation.market_replay import MarketReplay, MarketTick, ReplayConfig
from paper_validation.metrics import MetricsSummary, compute_metrics
from paper_validation.models import (
    ExitReason,
    PaperAccount,
    ScenarioConfig,
    ScenarioResult,
    SimulationConfig,
)
from paper_validation.position_simulator import SimulatedPosition
from paper_validation.scenario_runner import ScenarioRunner

__all__ = [
    "CostMode",
    "CostModel",
    "CostResult",
    "MarketReplay",
    "MarketTick",
    "MetricsSummary",
    "PaperAccount",
    "ReplayConfig",
    "ScenarioConfig",
    "ScenarioResult",
    "ScenarioRunner",
    "SimulatedFill",
    "SimulatedPosition",
    "SimulationConfig",
    "TradeEvidence",
    "ExitReason",
    "compute_metrics",
]
