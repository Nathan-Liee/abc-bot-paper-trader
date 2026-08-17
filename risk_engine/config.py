"""Risk Engine policy configuration — PAPER_VALIDATION_V0.1 profile.

This is a PAPER VALIDATION configuration, NOT a production configuration.
All parameters remain configurable via ``from_env()`` and may be revised
once paper-trading evidence is collected.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    """PAPER_VALIDATION_V0.1 risk policy."""

    # --- profile metadata (owner-approved) ---
    profile_name: str = "PAPER_VALIDATION_V0.1"
    is_production: bool = False
    requires_paper_validation: bool = True

    # --- locked project policy (owner) ---
    risk_basis: str = "EQUITY"  # "EQUITY" | "BALANCE"
    risk_per_trade: float = 0.005  # 0.5 % of equity
    max_simultaneous_positions: int = 1
    max_drawdown: float = 0.05  # 5 %

    # --- paper-validation starting parameters (owner-approved) ---
    sl_distance_points: float = 50.0  # paper validation starting SL
    max_spread_points: float = 45.0  # paper validation spread threshold
    max_exposure_equity_ratio: float = 1.0  # exposure <= 100 % equity
    min_free_margin_equity_ratio: float = 0.10  # free margin >= 10 % equity
    margin_risk_budget_multiplier: float = 1.0  # + 1 x next risk budget
    leverage_fallback: float = 2000.0  # observed runtime leverage, fallback only
    compounding_reinvestment_ratio: float = 0.0  # no auto compounding in this profile

    # --- runtime evidence (source: xauusdc-cent-readonly-observation.md) ---
    observed_spread_points: float = 36.0  # median observed spread

    # --- market sanity / AI policy (unchanged) ---
    max_stale_seconds: float = 10.0
    min_ai_confidence: float = 0.5
    confidence_policy_locked: bool = False  # confidence is a filter, never a multiplier

    # --- target identity tracking ---
    target_broker: str = "HFM"
    target_account_type: str = "Cent"
    target_symbol: str = "XAUUSDc"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.risk_basis not in ("EQUITY", "BALANCE"):
            errors.append(f"config.risk_basis:invalid:{self.risk_basis}")
        if not 0 < self.risk_per_trade <= 1:
            errors.append(f"config.risk_per_trade:invalid:{self.risk_per_trade}")
        if self.max_simultaneous_positions < 1:
            errors.append(
                f"config.max_simultaneous_positions:invalid:{self.max_simultaneous_positions}"
            )
        if not 0 < self.max_drawdown < 1:
            errors.append(f"config.max_drawdown:invalid:{self.max_drawdown}")
        if self.sl_distance_points <= 0:
            errors.append(f"config.sl_distance_points:invalid:{self.sl_distance_points}")
        if self.sl_distance_points <= self.observed_spread_points:
            errors.append(
                f"config.sl_distance_points:below_observed_spread:"
                f"{self.sl_distance_points}<={self.observed_spread_points}"
            )
        if self.max_spread_points <= 0:
            errors.append(f"config.max_spread_points:invalid:{self.max_spread_points}")
        if self.max_exposure_equity_ratio <= 0:
            errors.append(
                f"config.max_exposure_equity_ratio:invalid:{self.max_exposure_equity_ratio}"
            )
        if self.min_free_margin_equity_ratio < 0:
            errors.append(
                f"config.min_free_margin_equity_ratio:invalid:{self.min_free_margin_equity_ratio}"
            )
        if self.margin_risk_budget_multiplier < 0:
            errors.append(
                f"config.margin_risk_budget_multiplier:invalid:{self.margin_risk_budget_multiplier}"
            )
        if self.leverage_fallback <= 0:
            errors.append(f"config.leverage_fallback:invalid:{self.leverage_fallback}")
        if not 0 <= self.compounding_reinvestment_ratio <= 1:
            errors.append(
                f"config.compounding_reinvestment_ratio:invalid:{self.compounding_reinvestment_ratio}"
            )
        if self.observed_spread_points < 0:
            errors.append(f"config.observed_spread_points:invalid:{self.observed_spread_points}")
        if self.max_stale_seconds <= 0:
            errors.append(f"config.max_stale_seconds:invalid:{self.max_stale_seconds}")
        return errors

    @classmethod
    def from_env(cls) -> RiskConfig:
        """Construct config from environment variables; defaults = PAPER_VALIDATION_V0.1."""
        return cls(
            profile_name=os.environ.get("ABC_RISK_PROFILE_NAME", "PAPER_VALIDATION_V0.1"),
            is_production=os.environ.get("ABC_RISK_IS_PRODUCTION", "0") == "1",
            requires_paper_validation=(
                os.environ.get("ABC_RISK_REQUIRES_PAPER_VALIDATION", "1") == "1"
            ),
            risk_basis=os.environ.get("ABC_RISK_BASIS", "EQUITY").upper(),
            risk_per_trade=float(os.environ.get("ABC_RISK_PER_TRADE", "0.005")),
            max_simultaneous_positions=int(os.environ.get("ABC_MAX_POSITIONS", "1")),
            max_drawdown=float(os.environ.get("ABC_MAX_DRAWDOWN", "0.05")),
            sl_distance_points=float(os.environ.get("ABC_SL_DISTANCE_POINTS", "50.0")),
            max_spread_points=float(os.environ.get("ABC_MAX_SPREAD_POINTS", "45.0")),
            max_exposure_equity_ratio=float(os.environ.get("ABC_MAX_EXPOSURE_EQUITY_RATIO", "1.0")),
            min_free_margin_equity_ratio=float(
                os.environ.get("ABC_MIN_FREE_MARGIN_EQUITY_RATIO", "0.10")
            ),
            margin_risk_budget_multiplier=float(
                os.environ.get("ABC_MARGIN_RISK_BUDGET_MULTIPLIER", "1.0")
            ),
            leverage_fallback=float(os.environ.get("ABC_LEVERAGE_FALLBACK", "2000.0")),
            compounding_reinvestment_ratio=float(
                os.environ.get("ABC_COMPOUNDING_REINVESTMENT_RATIO", "0.0")
            ),
            observed_spread_points=float(os.environ.get("ABC_OBSERVED_SPREAD_POINTS", "36.0")),
            max_stale_seconds=float(os.environ.get("ABC_MAX_STALE_SECONDS", "10.0")),
            min_ai_confidence=float(os.environ.get("ABC_MIN_AI_CONFIDENCE", "0.5")),
        )
