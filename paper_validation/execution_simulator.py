"""Simulated execution — fills and position lifecycle (NO broker orders)."""

from __future__ import annotations

from dataclasses import dataclass

from paper_validation.cost_model import CostModel, CostResult
from paper_validation.market_replay import MarketTick
from paper_validation.models import ExitReason


@dataclass(frozen=True)
class SimulatedFill:
    """Simulated order fill (no broker request sent)."""

    fill_price: float
    fill_ts: str
    lot: float
    direction: str
    sl_price: float
    spread_at_fill: float
    label: str = "SIMULATED"


@dataclass
class SimulatedPosition:
    """Open simulated position with lifecycle monitoring."""

    trade_id: str
    direction: str  # "BUY" | "SELL"
    lot: float
    entry_price: float
    sl_price: float
    entry_ts: str
    spread_at_entry: float
    risk_amount_theoretical: float
    cost_model: CostModel
    contract_size: float = 1.0
    tick_value: float = 1.0
    tick_size: float = 0.01
    point: float = 0.01

    # Tracking
    max_adverse_excursion: float = 0.0
    max_favorable_excursion: float = 0.0
    holding_steps: int = 0

    def check_exit(self, tick: MarketTick) -> ExitReason | None:
        """Check if position should close on this tick. ABC: NET_PROFIT > 0 → close."""
        self.holding_steps += 1

        # Calculate current PnL (gross, before costs)
        gross_pnl = self._gross_pnl(tick)

        # Track MAE/MFE
        if gross_pnl < self.max_adverse_excursion:
            self.max_adverse_excursion = gross_pnl
        if gross_pnl > self.max_favorable_excursion:
            self.max_favorable_excursion = gross_pnl

        # SL check (loss-side protection)
        if self.direction == "BUY" and tick.bid <= self.sl_price:
            return ExitReason.SL_STOP
        if self.direction == "SELL" and tick.ask >= self.sl_price:
            return ExitReason.SL_STOP

        # ABC exit: NET_PROFIT > 0 → close
        # Net profit = gross_pnl - costs (spread already in fill prices, so
        # only count commission/swap/slippage as additional cost)
        costs = self._estimate_costs(tick)
        additional_cost = costs.commission_cost + costs.swap_cost + costs.slippage_cost
        net_pnl = gross_pnl - additional_cost
        if net_pnl > 0:
            return ExitReason.ABC_PROFIT_CLOSE

        return None

    def close(self, tick: MarketTick, exit_reason: ExitReason) -> dict[str, object]:
        """Close position and return full trade evidence dict."""
        if self.direction == "BUY":
            exit_price = tick.bid
        else:
            exit_price = tick.ask

        gross_pnl = self._gross_pnl_at_price(exit_price)
        costs = self._estimate_costs(tick)

        # Spread cost = the spread paid at entry + exit (already in gross_pnl
        # via fill prices, but reported separately for transparency)
        net_pnl = gross_pnl - costs.commission_cost - costs.swap_cost - costs.slippage_cost
        risk_realized = abs(min(net_pnl, 0.0))

        return {
            "trade_id": self.trade_id,
            "entry_price": self.entry_price,
            "exit_price": exit_price,
            "exit_reason": exit_reason.value,
            "gross_pnl": round(gross_pnl, 4),
            "spread_cost": costs.spread_cost,
            "commission_cost": costs.commission_cost,
            "swap_cost": costs.swap_cost,
            "slippage_cost": costs.slippage_cost,
            "total_cost": costs.total_cost,
            "net_pnl": round(net_pnl, 4),
            "risk_realized": round(risk_realized, 4),
            "risk_theoretical": self.risk_amount_theoretical,
            "max_adverse_excursion": round(self.max_adverse_excursion, 4),
            "max_favorable_excursion": round(self.max_favorable_excursion, 4),
            "holding_steps": self.holding_steps,
            "label": "SIMULATED",
        }

    def _gross_pnl(self, tick: MarketTick) -> float:
        if self.direction == "BUY":
            return (tick.bid - self.entry_price) * self.lot * self.contract_size
        return (self.entry_price - tick.ask) * self.lot * self.contract_size

    def _gross_pnl_at_price(self, exit_price: float) -> float:
        if self.direction == "BUY":
            return (exit_price - self.entry_price) * self.lot * self.contract_size
        return (self.entry_price - exit_price) * self.lot * self.contract_size

    def _estimate_costs(self, tick: MarketTick) -> CostResult:
        return self.cost_model.compute_costs(
            lot=self.lot,
            entry_price=self.entry_price,
            exit_price=tick.bid if self.direction == "BUY" else tick.ask,
            direction=self.direction,
            spread_at_entry=self.spread_at_entry,
            spread_at_exit=tick.spread,
            contract_size=self.contract_size,
            tick_value=self.tick_value,
            tick_size=self.tick_size,
        )


def simulate_fill(
    direction: str,
    lot: float,
    sl_price: float,
    tick: MarketTick,
    risk_amount: float,
    cost_model: CostModel,
    contract_size: float = 1.0,
    tick_value: float = 1.0,
    tick_size: float = 0.01,
    point: float = 0.01,
    trade_id: str = "",
) -> tuple[SimulatedFill, SimulatedPosition]:
    """Simulate order fill at ask (BUY) or bid (SELL). No broker request."""
    if direction == "BUY":
        fill_price = tick.ask
    else:
        fill_price = tick.bid

    fill = SimulatedFill(
        fill_price=fill_price,
        fill_ts=tick.timestamp_iso,
        lot=lot,
        direction=direction,
        sl_price=sl_price,
        spread_at_fill=tick.spread,
    )

    position = SimulatedPosition(
        trade_id=trade_id,
        direction=direction,
        lot=lot,
        entry_price=fill_price,
        sl_price=sl_price,
        entry_ts=tick.timestamp_iso,
        spread_at_entry=tick.spread,
        risk_amount_theoretical=risk_amount,
        cost_model=cost_model,
        contract_size=contract_size,
        tick_value=tick_value,
        tick_size=tick_size,
        point=point,
    )
    return fill, position
