"""Deterministic risk, lot, SL, and margin calculators."""

from __future__ import annotations

import math
from dataclasses import dataclass

from risk_engine.config import RiskConfig
from risk_engine.models import AccountState, MarketState, SymbolSpecification


@dataclass(frozen=True)
class LotCalculationResult:
    candidate_lot: float
    final_lot: float
    raw_lot: float
    sl_price: float
    sl_distance_points: float
    risk_amount_usd: float
    risk_pct: float
    exposure_usd: float
    required_margin_usd: float
    ok: bool
    error: str | None = None


def round_down_step(value: float, step: float) -> float:
    """Quantize lot size down to nearest volume_step using exact integer arithmetic."""
    if step <= 0:
        return 0.0
    precision = 8
    inv_step = round(1.0 / step, precision)
    units = math.floor(round(value * inv_step, precision))
    return round(units * step, precision)


def calculate_sl_price(
    direction: str,
    entry_price: float,
    sl_points: float,
    stops_level_points: float = 0.0,
) -> tuple[float, float, str | None]:
    """Calculate Stop-Loss price and distance.

    Returns (sl_price, sl_distance_points, error_str).
    """
    if sl_points <= 0:
        return 0.0, 0.0, "sl_points_non_positive"

    effective_sl_points = (
        max(sl_points, stops_level_points) if stops_level_points > 0 else sl_points
    )

    if direction == "BUY":
        sl_price = entry_price - effective_sl_points
        if sl_price <= 0:
            return 0.0, 0.0, "sl_price_non_positive"
        return round(sl_price, 5), round(effective_sl_points, 5), None

    if direction == "SELL":
        sl_price = entry_price + effective_sl_points
        return round(sl_price, 5), round(effective_sl_points, 5), None

    return 0.0, 0.0, "invalid_direction_for_sl"


def calculate_trade_plan(
    direction: str,
    account: AccountState,
    market: MarketState,
    spec: SymbolSpecification,
    config: RiskConfig,
) -> LotCalculationResult:
    """Deterministic 5-stage trade plan calculator:

    1. Risk Budget -> 2. SL / Risk Distance -> 3. Raw Lot ->
    4. Step/Min/Max Lot -> 5. Margin/Exposure Check.
    """
    if direction not in ("BUY", "SELL"):
        return LotCalculationResult(
            candidate_lot=0.0,
            final_lot=0.0,
            raw_lot=0.0,
            sl_price=0.0,
            sl_distance_points=0.0,
            risk_amount_usd=0.0,
            risk_pct=0.0,
            exposure_usd=0.0,
            required_margin_usd=0.0,
            ok=False,
            error=f"invalid_direction:{direction}",
        )

    # 1. Select capital basis & compute risk budget
    capital_basis = account.equity if config.risk_basis == "EQUITY" else account.balance
    if capital_basis <= 0:
        return LotCalculationResult(
            candidate_lot=0.0,
            final_lot=0.0,
            raw_lot=0.0,
            sl_price=0.0,
            sl_distance_points=0.0,
            risk_amount_usd=0.0,
            risk_pct=0.0,
            exposure_usd=0.0,
            required_margin_usd=0.0,
            ok=False,
            error="capital_basis_non_positive",
        )

    target_risk_usd = capital_basis * (config.risk_pct_per_trade / 100.0)

    # 2. Entry price & SL price
    entry_price = market.ask if direction == "BUY" else market.bid
    sl_price, sl_dist_points, sl_err = calculate_sl_price(
        direction=direction,
        entry_price=entry_price,
        sl_points=config.default_sl_points,
        stops_level_points=spec.stops_level,
    )
    if sl_err:
        return LotCalculationResult(
            candidate_lot=0.0,
            final_lot=0.0,
            raw_lot=0.0,
            sl_price=0.0,
            sl_distance_points=0.0,
            risk_amount_usd=0.0,
            risk_pct=0.0,
            exposure_usd=0.0,
            required_margin_usd=0.0,
            ok=False,
            error=sl_err,
        )

    # 3. Calculate Risk Per Lot (using tick_value and tick_size)
    # Risk per lot = (sl_distance / tick_size) * tick_value
    loss_per_lot_usd = (sl_dist_points / spec.tick_size) * spec.tick_value
    if loss_per_lot_usd <= 0:
        return LotCalculationResult(
            candidate_lot=0.0,
            final_lot=0.0,
            raw_lot=0.0,
            sl_price=sl_price,
            sl_distance_points=sl_dist_points,
            risk_amount_usd=0.0,
            risk_pct=0.0,
            exposure_usd=0.0,
            required_margin_usd=0.0,
            ok=False,
            error="loss_per_lot_non_positive",
        )

    # Raw lot to risk exact budget
    raw_lot = target_risk_usd / loss_per_lot_usd

    # 4. Quantize to candidate lot (step size & volume limits)
    candidate_lot = round_down_step(raw_lot, spec.volume_step)

    if candidate_lot < spec.volume_min:
        return LotCalculationResult(
            candidate_lot=candidate_lot,
            final_lot=0.0,
            raw_lot=raw_lot,
            sl_price=sl_price,
            sl_distance_points=sl_dist_points,
            risk_amount_usd=0.0,
            risk_pct=0.0,
            exposure_usd=0.0,
            required_margin_usd=0.0,
            ok=False,
            error=f"candidate_lot_below_min:{candidate_lot}<{spec.volume_min}",
        )

    final_lot = min(candidate_lot, spec.volume_max)

    # Recalculate actual risk amount & exposure for final_lot
    actual_risk_usd = final_lot * loss_per_lot_usd
    actual_risk_pct = (actual_risk_usd / capital_basis) * 100.0

    # Exposure = final_lot * contract_size * entry_price
    exposure_usd = final_lot * spec.contract_size * entry_price

    # Required margin
    if spec.margin_initial > 0:
        required_margin_usd = final_lot * spec.margin_initial
    else:
        required_margin_usd = exposure_usd / config.leverage

    return LotCalculationResult(
        candidate_lot=candidate_lot,
        final_lot=final_lot,
        raw_lot=raw_lot,
        sl_price=sl_price,
        sl_distance_points=sl_dist_points,
        risk_amount_usd=round(actual_risk_usd, 4),
        risk_pct=round(actual_risk_pct, 4),
        exposure_usd=round(exposure_usd, 2),
        required_margin_usd=round(required_margin_usd, 2),
        ok=True,
    )
