"""Risk Engine policy configuration with explicit pending flags."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    """Configurable risk policy parameters.

    All numeric thresholds marked with pending flags when default values are
    provisional / safety-baseline defaults, as mandated by prompt instructions
    and Obsidian specs.
    """

    # Risk basis & budget (% per trade)
    risk_basis: str = "EQUITY"  # "EQUITY" | "BALANCE"
    risk_pct_per_trade: float = 1.0  # 1% default safe baseline
    risk_pct_locked: bool = False  # PENDING CONFIGURATION (§10)

    # Exposure & Drawdown limits
    max_drawdown_pct: float = 10.0  # 10% maximum equity drawdown guard
    max_exposure_usd: float = 5000.0  # Total open position exposure cap
    max_simultaneous_positions: int = 1

    # Market sanity filters
    max_spread: float = 5.0  # Maximum spread filter (in price points / USD)
    max_stale_seconds: float = 10.0  # Timestamp freshness limit

    # SL / Distance settings
    default_sl_points: float = 2.0  # $2.00 (200 pips) default XAUUSD protection distance
    sl_distance_locked: bool = False  # PENDING CONFIGURATION (§16)

    # Margin buffer
    min_free_margin_usd: float = 50.0  # Free margin buffer minimum
    leverage: float = 100.0  # Account leverage assumption if broker initial margin not provided

    # AI Confidence policy
    min_ai_confidence: float = 0.5  # Filter out low-confidence proposals
    confidence_policy_locked: bool = False  # PENDING CONFIGURATION (§18)

    # Target identity tracking
    target_broker: str = "HFM"
    target_account_type: str = "Cent"
    target_symbol: str = "XAUUSDc"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.risk_basis not in ("EQUITY", "BALANCE"):
            errors.append(f"config.risk_basis:invalid:{self.risk_basis}")
        if self.risk_pct_per_trade <= 0 or self.risk_pct_per_trade > 100:
            errors.append(f"config.risk_pct_per_trade:invalid:{self.risk_pct_per_trade}")
        if self.max_drawdown_pct <= 0 or self.max_drawdown_pct > 100:
            errors.append(f"config.max_drawdown_pct:invalid:{self.max_drawdown_pct}")
        if self.max_exposure_usd <= 0:
            errors.append(f"config.max_exposure_usd:invalid:{self.max_exposure_usd}")
        if self.max_spread <= 0:
            errors.append(f"config.max_spread:invalid:{self.max_spread}")
        if self.max_stale_seconds <= 0:
            errors.append(f"config.max_stale_seconds:invalid:{self.max_stale_seconds}")
        if self.default_sl_points <= 0:
            errors.append(f"config.default_sl_points:invalid:{self.default_sl_points}")
        return errors

    @classmethod
    def from_env(cls) -> RiskConfig:
        """Construct config from environment variables with safe defaults."""
        return cls(
            risk_basis=os.environ.get("ABC_RISK_BASIS", "EQUITY").upper(),
            risk_pct_per_trade=float(os.environ.get("ABC_RISK_PCT_PER_TRADE", "1.0")),
            max_drawdown_pct=float(os.environ.get("ABC_MAX_DRAWDOWN_PCT", "10.0")),
            max_exposure_usd=float(os.environ.get("ABC_MAX_EXPOSURE_USD", "5000.0")),
            max_spread=float(os.environ.get("ABC_MAX_SPREAD", "5.0")),
            max_stale_seconds=float(os.environ.get("ABC_MAX_STALE_SECONDS", "10.0")),
            default_sl_points=float(os.environ.get("ABC_DEFAULT_SL_POINTS", "2.0")),
            min_free_margin_usd=float(os.environ.get("ABC_MIN_FREE_MARGIN_USD", "50.0")),
        )
