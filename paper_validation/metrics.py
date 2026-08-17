"""Metrics aggregation for paper validation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricsSummary:
    """Aggregated metrics from paper validation runs."""

    total_scenarios: int = 0
    approved: int = 0
    rejected: int = 0
    trades_closed: int = 0
    abc_closes: int = 0
    sl_stops: int = 0
    session_ends: int = 0

    # Risk metrics
    total_theoretical_risk: float = 0.0
    total_realized_loss: float = 0.0
    max_loss: float = 0.0
    risk_budget_breaches: int = 0
    risk_overrun_due_to_cost: int = 0

    # PnL
    total_net_pnl: float = 0.0
    total_gross_pnl: float = 0.0

    # Costs
    total_spread_cost: float = 0.0
    total_commission_cost: float = 0.0
    total_swap_cost: float = 0.0
    total_slippage_cost: float = 0.0

    # Position
    avg_holding_steps: float = 0.0
    avg_mae: float = 0.0
    avg_mfe: float = 0.0

    # Gate
    approval_rate: float = 0.0
    rejection_rate: float = 0.0
    reason_code_distribution: dict[str, int] = field(default_factory=dict)

    # Labels
    label: str = "SIMULATED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_scenarios": self.total_scenarios,
            "approved": self.approved,
            "rejected": self.rejected,
            "trades_closed": self.trades_closed,
            "abc_closes": self.abc_closes,
            "sl_stops": self.sl_stops,
            "session_ends": self.session_ends,
            "total_theoretical_risk": round(self.total_theoretical_risk, 4),
            "total_realized_loss": round(self.total_realized_loss, 4),
            "max_loss": round(self.max_loss, 4),
            "risk_budget_breaches": self.risk_budget_breaches,
            "risk_overrun_due_to_cost": self.risk_overrun_due_to_cost,
            "total_net_pnl": round(self.total_net_pnl, 4),
            "total_gross_pnl": round(self.total_gross_pnl, 4),
            "total_spread_cost": round(self.total_spread_cost, 4),
            "total_commission_cost": round(self.total_commission_cost, 4),
            "total_swap_cost": round(self.total_swap_cost, 4),
            "total_slippage_cost": round(self.total_slippage_cost, 4),
            "avg_holding_steps": round(self.avg_holding_steps, 1),
            "avg_mae": round(self.avg_mae, 4),
            "avg_mfe": round(self.avg_mfe, 4),
            "approval_rate": round(self.approval_rate, 4),
            "rejection_rate": round(self.rejection_rate, 4),
            "reason_code_distribution": dict(self.reason_code_distribution),
            "label": self.label,
        }


def compute_metrics(
    results: list[Any],
    evidences: list[Any] | None = None,
) -> MetricsSummary:
    """Compute aggregate metrics from scenario results + trade evidences."""
    m = MetricsSummary()
    m.total_scenarios = len(results)

    reason_counts: Counter[str] = Counter()
    holding_steps: list[int] = []
    maes: list[float] = []
    mfes: list[float] = []

    for r in results:
        if getattr(r, "approved", False):
            m.approved += 1
        else:
            m.rejected += 1
            if r.rejection_reason_code:
                reason_counts[r.rejection_reason_code] += 1

        exit_reason = getattr(r, "exit_reason", "")
        if exit_reason == "ABC_PROFIT_CLOSE":
            m.abc_closes += 1
            m.trades_closed += 1
        elif exit_reason == "SL_STOP":
            m.sl_stops += 1
            m.trades_closed += 1
        elif exit_reason == "PAPER_SESSION_END":
            m.session_ends += 1
            m.trades_closed += 1

    if evidences:
        for ev in evidences:
            m.total_theoretical_risk += ev.max_risk_theoretical
            m.total_net_pnl += ev.net_pnl
            m.total_gross_pnl += ev.gross_pnl
            m.total_spread_cost += ev.spread_cost
            m.total_commission_cost += ev.commission_cost
            m.total_swap_cost += ev.swap_cost
            m.total_slippage_cost += ev.slippage_cost

            if ev.net_pnl < 0:
                m.total_realized_loss += abs(ev.net_pnl)
                if abs(ev.net_pnl) > m.max_loss:
                    m.max_loss = abs(ev.net_pnl)

            if ev.risk_realized > ev.max_risk_theoretical * 1.0001:
                m.risk_budget_breaches += 1
                if ev.slippage_cost > 0 or ev.commission_cost > 0:
                    m.risk_overrun_due_to_cost += 1

            holding_steps.append(ev.holding_duration)
            maes.append(ev.max_adverse_excursion)
            mfes.append(ev.max_favorable_excursion)

    if m.total_scenarios > 0:
        m.approval_rate = m.approved / m.total_scenarios
        m.rejection_rate = m.rejected / m.total_scenarios

    if holding_steps:
        m.avg_holding_steps = sum(holding_steps) / len(holding_steps)
    if maes:
        m.avg_mae = sum(maes) / len(maes)
    if mfes:
        m.avg_mfe = sum(mfes) / len(mfes)

    m.reason_code_distribution = dict(reason_counts)
    return m
