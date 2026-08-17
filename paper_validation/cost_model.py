"""Cost model abstraction for paper validation.

Separates OBSERVED (spread) from NOT_OBSERVED (slippage/commission/swap).
All simulated costs are labeled SIMULATED, never OBSERVED.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CostMode(StrEnum):
    """Cost model modes for paper simulation."""

    SPREAD_ONLY = "SPREAD_ONLY"
    COMMISSION_CONFIGURED = "COMMISSION_CONFIGURED"
    SLIPPAGE_CONFIGURED = "SLIPPAGE_CONFIGURED"
    FULL_COST_MODEL = "FULL_COST_MODEL"


@dataclass(frozen=True)
class CostResult:
    """Breakdown of all costs for a single trade (all SIMULATED)."""

    spread_cost: float = 0.0
    commission_cost: float = 0.0
    swap_cost: float = 0.0
    slippage_cost: float = 0.0
    total_cost: float = 0.0
    label: str = "SIMULATED"


@dataclass(frozen=True)
class CostModel:
    """Cost model for paper validation.

    Modes:
    - SPREAD_ONLY: only spread cost (observed at entry/exit)
    - COMMISSION_CONFIGURED: spread + configured commission
    - SLIPPAGE_CONFIGURED: spread + configured slippage
    - FULL_COST_MODEL: spread + commission + slippage + swap
    """

    mode: CostMode = CostMode.SPREAD_ONLY
    commission_per_lot: float = 0.0
    swap_per_lot_per_night: float = 0.0
    slippage_points: float = 0.0
    point: float = 0.01

    @classmethod
    def from_mode_str(
        cls,
        mode: str,
        *,
        commission_per_lot: float = 0.0,
        swap_per_lot_per_night: float = 0.0,
        slippage_points: float = 0.0,
        point: float = 0.01,
    ) -> CostModel:
        return cls(
            mode=CostMode(mode),
            commission_per_lot=commission_per_lot,
            swap_per_lot_per_night=swap_per_lot_per_night,
            slippage_points=slippage_points,
            point=point,
        )

    def compute_costs(
        self,
        *,
        lot: float,
        entry_price: float,
        exit_price: float,
        direction: str,
        spread_at_entry: float,
        spread_at_exit: float,
        holding_nights: int = 0,
        contract_size: float = 1.0,
        tick_value: float = 1.0,
        tick_size: float = 0.01,
    ) -> CostResult:
        """Compute all costs for a closed trade. All values SIMULATED."""
        spread_cost = 0.0
        commission_cost = 0.0
        swap_cost = 0.0
        slippage_cost = 0.0

        # Spread cost (always computed; this is OBSERVED at entry/exit)
        spread_cost = (spread_at_entry + spread_at_exit) * lot * tick_value / tick_size * 0.5

        if self.mode in (CostMode.COMMISSION_CONFIGURED, CostMode.FULL_COST_MODEL):
            commission_cost = self.commission_per_lot * lot

        if self.mode in (CostMode.SLIPPAGE_CONFIGURED, CostMode.FULL_COST_MODEL):
            slippage_price = self.slippage_points * self.point
            if direction == "BUY":
                slippage_cost = slippage_price * lot * contract_size
            else:
                slippage_cost = slippage_price * lot * contract_size

        if self.mode == CostMode.FULL_COST_MODEL:
            swap_cost = self.swap_per_lot_per_night * lot * holding_nights

        total = spread_cost + commission_cost + swap_cost + slippage_cost
        return CostResult(
            spread_cost=round(spread_cost, 4),
            commission_cost=round(commission_cost, 4),
            swap_cost=round(swap_cost, 4),
            slippage_cost=round(slippage_cost, 4),
            total_cost=round(total, 4),
            label="SIMULATED",
        )
