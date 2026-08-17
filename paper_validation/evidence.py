"""Trade evidence record for paper validation."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any


def _new_evidence_id() -> str:
    return f"ev-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class TradeEvidence:
    """Complete trade-level evidence record (all SIMULATED)."""

    evidence_id: str
    trade_id: str
    scenario_id: str
    timestamp_open: str
    timestamp_close: str
    direction: str
    proposal_source: str
    confidence: float
    risk_config_profile: str
    equity_before: float
    risk_budget: float
    lot: float
    entry_price: float
    sl_price: float
    max_risk_theoretical: float
    spread_at_entry: float
    exit_price: float
    exit_reason: str
    gross_pnl: float
    spread_cost: float
    commission_cost: float
    swap_cost: float
    slippage_cost: float
    net_pnl: float
    risk_realized: float
    max_adverse_excursion: float
    max_favorable_excursion: float
    holding_duration: int
    risk_decision: str
    reason_code: str
    label: str = "SIMULATED"
    cost_label: str = "SIMULATED"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_close_result(
        cls,
        *,
        trade_id: str,
        scenario_id: str,
        direction: str,
        confidence: float,
        risk_config_profile: str,
        equity_before: float,
        risk_budget: float,
        lot: float,
        entry_price: float,
        sl_price: float,
        max_risk_theoretical: float,
        spread_at_entry: float,
        timestamp_open: str,
        close_result: dict[str, Any],
        risk_decision: str,
        reason_code: str,
        proposal_source: str = "FIXTURE",
        timestamp_close: str = "",
        notes: str = "",
    ) -> TradeEvidence:
        return cls(
            evidence_id=_new_evidence_id(),
            trade_id=trade_id,
            scenario_id=scenario_id,
            timestamp_open=timestamp_open,
            timestamp_close=timestamp_close or close_result.get("exit_ts", ""),
            direction=direction,
            proposal_source=proposal_source,
            confidence=confidence,
            risk_config_profile=risk_config_profile,
            equity_before=equity_before,
            risk_budget=risk_budget,
            lot=lot,
            entry_price=entry_price,
            sl_price=sl_price,
            max_risk_theoretical=max_risk_theoretical,
            spread_at_entry=spread_at_entry,
            exit_price=close_result.get("exit_price", 0.0),
            exit_reason=close_result.get("exit_reason", ""),
            gross_pnl=close_result.get("gross_pnl", 0.0),
            spread_cost=close_result.get("spread_cost", 0.0),
            commission_cost=close_result.get("commission_cost", 0.0),
            swap_cost=close_result.get("swap_cost", 0.0),
            slippage_cost=close_result.get("slippage_cost", 0.0),
            net_pnl=close_result.get("net_pnl", 0.0),
            risk_realized=close_result.get("risk_realized", 0.0),
            max_adverse_excursion=close_result.get("max_adverse_excursion", 0.0),
            max_favorable_excursion=close_result.get("max_favorable_excursion", 0.0),
            holding_duration=close_result.get("holding_steps", 0),
            risk_decision=risk_decision,
            reason_code=reason_code,
            notes=notes,
        )
