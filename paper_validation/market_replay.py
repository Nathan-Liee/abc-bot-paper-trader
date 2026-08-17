"""Market replay — deterministic tick feed for paper validation."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class MarketTick:
    """Single market tick for replay."""

    timestamp_iso: str
    bid: float
    ask: float
    spread: float
    mid: float
    symbol: str = "XAUUSDc"

    def to_market_state_dict(self) -> dict[str, Any]:
        return {
            "bid": self.bid,
            "ask": self.ask,
            "spread": self.spread,
            "mid": self.mid,
            "symbol": self.symbol,
            "timestamp_iso": self.timestamp_iso,
        }


@dataclass
class ReplayConfig:
    """Configuration for deterministic market replay."""

    symbol: str = "XAUUSDc"
    base_price: float = 4370.0
    point: float = 0.01
    spread_points: float = 36.0
    volatility_points: float = 20.0
    tick_count: int = 100
    start_time: datetime = field(
        default_factory=lambda: datetime(2026, 8, 17, 9, 35, 0, tzinfo=UTC)
    )
    tick_interval_s: int = 1
    seed: int = 42


class MarketReplay:
    """Deterministic market tick generator.

    Same seed/config → same ticks. No live data access.
    """

    def __init__(self, config: ReplayConfig) -> None:
        self._config = config
        self._rng = random.Random(config.seed)

    def generate_ticks(self) -> list[MarketTick]:
        """Generate deterministic tick series."""
        cfg = self._config
        ticks: list[MarketTick] = []
        current_price = cfg.base_price
        spread_price = cfg.spread_points * cfg.point

        for i in range(cfg.tick_count):
            ts = cfg.start_time + timedelta(seconds=cfg.tick_interval_s * i)

            # Random walk in points
            move_points = self._rng.uniform(-cfg.volatility_points, cfg.volatility_points)
            move_price = move_points * cfg.point
            current_price = round(current_price + move_price, 2)
            if current_price <= spread_price:
                current_price = round(spread_price + 1.0, 2)

            bid = round(current_price, 2)
            ask = round(current_price + spread_price, 2)
            mid = round((bid + ask) / 2, 2)
            spread = round(ask - bid, 2)

            ticks.append(
                MarketTick(
                    timestamp_iso=ts.isoformat(timespec="seconds"),
                    bid=bid,
                    ask=ask,
                    spread=spread,
                    mid=mid,
                    symbol=cfg.symbol,
                )
            )
        return ticks

    @staticmethod
    def from_fixture_ticks(
        ticks_data: list[dict[str, Any]],
        symbol: str = "XAUUSDc",
    ) -> list[MarketTick]:
        """Build MarketTick list from raw fixture dicts."""
        result: list[MarketTick] = []
        for t in ticks_data:
            bid = float(t["bid"])
            ask = float(t["ask"])
            result.append(
                MarketTick(
                    timestamp_iso=str(t.get("timestamp_iso", "")),
                    bid=bid,
                    ask=ask,
                    spread=round(ask - bid, 2),
                    mid=round((bid + ask) / 2, 2),
                    symbol=symbol,
                )
            )
        return result
