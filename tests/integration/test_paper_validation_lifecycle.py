"""Integration test: AI fixture → Risk Engine → simulated trade → simulated exit."""

from __future__ import annotations

from paper_validation.models import ScenarioConfig
from paper_validation.scenario_runner import ScenarioRunner
from risk_engine.config import RiskConfig


def test_full_paper_lifecycle_buy_abc() -> None:
    """Full lifecycle: BUY fixture → Risk Engine approves → ABC profit close."""
    runner = ScenarioRunner(RiskConfig())
    ticks = [
        {"bid": 4370.0, "ask": 4370.36, "timestamp_iso": "2026-08-17T09:35:00+00:00"},
        {"bid": 4370.5, "ask": 4370.86, "timestamp_iso": "2026-08-17T09:35:01+00:00"},
        {"bid": 4371.5, "ask": 4371.86, "timestamp_iso": "2026-08-17T09:35:02+00:00"},
    ]
    scenario = ScenarioConfig(
        scenario_id="integration-buy-abc",
        description="Integration: BUY → ABC",
        direction="BUY",
        confidence=0.85,
        ticks=ticks,
        starting_equity=10000.0,
    )
    result = runner.run(scenario)
    assert result.approved is True
    assert result.exit_reason == "ABC_PROFIT_CLOSE"
    ev = result.trade_evidence
    assert ev is not None
    assert ev["direction"] == "BUY"
    assert ev["lot"] == 0.01
    assert ev["risk_config_profile"] == "PAPER_VALIDATION_V0.1"
    assert ev["net_pnl"] > 0
    assert ev["label"] == "SIMULATED"
    # Risk budget integrity (zero slippage, spread-only)
    assert ev["risk_realized"] <= ev["max_risk_theoretical"] * 1.0001


def test_full_paper_lifecycle_sell_sl() -> None:
    """Full lifecycle: SELL fixture → Risk Engine approves → SL stop."""
    runner = ScenarioRunner(RiskConfig())
    ticks = [
        {"bid": 4370.0, "ask": 4370.36, "timestamp_iso": "2026-08-17T09:35:00+00:00"},
        {"bid": 4371.0, "ask": 4371.36, "timestamp_iso": "2026-08-17T09:35:01+00:00"},
        {"bid": 4372.0, "ask": 4372.36, "timestamp_iso": "2026-08-17T09:35:02+00:00"},
    ]
    scenario = ScenarioConfig(
        scenario_id="integration-sell-sl",
        description="Integration: SELL → SL",
        direction="SELL",
        confidence=0.85,
        ticks=ticks,
        starting_equity=10000.0,
    )
    result = runner.run(scenario)
    assert result.approved is True
    assert result.exit_reason == "SL_STOP"
    ev = result.trade_evidence
    assert ev is not None
    assert ev["net_pnl"] < 0


def test_full_paper_lifecycle_reject_no_trade() -> None:
    """Full lifecycle: NO-TRADE → no position."""
    runner = ScenarioRunner(RiskConfig())
    ticks = [
        {"bid": 4370.0, "ask": 4370.36, "timestamp_iso": "2026-08-17T09:35:00+00:00"},
    ]
    scenario = ScenarioConfig(
        scenario_id="integration-no-trade",
        description="Integration: NO-TRADE",
        direction="NO-TRADE",
        ticks=ticks,
    )
    result = runner.run(scenario)
    assert result.approved is False
    assert result.trade_evidence is None
