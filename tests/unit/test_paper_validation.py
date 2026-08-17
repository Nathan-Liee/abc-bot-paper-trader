"""Unit tests for paper validation harness — deterministic, no broker."""

from __future__ import annotations

from datetime import UTC, datetime

from paper_validation.cost_model import CostMode, CostModel
from paper_validation.execution_simulator import simulate_fill
from paper_validation.market_replay import MarketReplay, MarketTick, ReplayConfig
from paper_validation.models import ExitReason, ScenarioConfig
from paper_validation.scenario_runner import ScenarioRunner
from risk_engine.config import RiskConfig


def _tick(
    bid: float = 4370.0,
    ask: float = 4370.36,
    ts: str | None = None,
) -> MarketTick:
    return MarketTick(
        timestamp_iso=ts or datetime.now(UTC).isoformat(timespec="seconds"),
        bid=bid,
        ask=ask,
        spread=round(ask - bid, 2),
        mid=round((bid + ask) / 2, 2),
        symbol="XAUUSDc",
    )


def _config() -> RiskConfig:
    return RiskConfig()


# --- Market replay determinism ---


def test_replay_determinism() -> None:
    cfg = ReplayConfig(tick_count=20, seed=42)
    replay1 = MarketReplay(cfg)
    replay2 = MarketReplay(cfg)
    ticks1 = replay1.generate_ticks()
    ticks2 = replay2.generate_ticks()
    assert len(ticks1) == 20
    assert len(ticks2) == 20
    for t1, t2 in zip(ticks1, ticks2, strict=True):
        assert t1.bid == t2.bid
        assert t1.ask == t2.ask


def test_replay_different_seed_different() -> None:
    t1 = MarketReplay(ReplayConfig(seed=1, tick_count=10)).generate_ticks()
    t2 = MarketReplay(ReplayConfig(seed=2, tick_count=10)).generate_ticks()
    assert t1[5].bid != t2[5].bid


# --- Cost model ---


def test_cost_model_spread_only() -> None:
    cm = CostModel(mode=CostMode.SPREAD_ONLY)
    result = cm.compute_costs(
        lot=0.01,
        entry_price=4370.0,
        exit_price=4370.5,
        direction="BUY",
        spread_at_entry=0.36,
        spread_at_exit=0.36,
    )
    assert result.commission_cost == 0.0
    assert result.slippage_cost == 0.0
    assert result.spread_cost > 0
    assert result.label == "SIMULATED"


def test_cost_model_full() -> None:
    cm = CostModel(
        mode=CostMode.FULL_COST_MODEL,
        commission_per_lot=5.0,
        swap_per_lot_per_night=1.0,
        slippage_points=2.0,
    )
    result = cm.compute_costs(
        lot=0.01,
        entry_price=4370.0,
        exit_price=4370.5,
        direction="BUY",
        spread_at_entry=0.36,
        spread_at_exit=0.36,
        holding_nights=1,
    )
    assert result.commission_cost == 0.05  # 5.0 * 0.01
    assert result.swap_cost == 0.01  # 1.0 * 0.01 * 1
    assert result.slippage_cost > 0
    assert result.total_cost > result.spread_cost


# --- Position lifecycle: ABC profit close ---


def test_buy_abc_profit_close() -> None:
    cm = CostModel(mode=CostMode.SPREAD_ONLY)
    tick0 = _tick(bid=4370.0, ask=4370.36)
    fill, pos = simulate_fill(
        direction="BUY",
        lot=0.01,
        sl_price=4369.86,  # entry 4370.36 - 50pts × 0.01 = 4369.86
        tick=tick0,
        risk_amount=50.0,
        cost_model=cm,
        trade_id="test-buy-abc",
    )
    # Price goes up → ABC close
    up_tick = _tick(bid=4371.0, ask=4371.36)
    exit_reason = pos.check_exit(up_tick)
    assert exit_reason == ExitReason.ABC_PROFIT_CLOSE


def test_sell_abc_profit_close() -> None:
    cm = CostModel(mode=CostMode.SPREAD_ONLY)
    tick0 = _tick(bid=4370.0, ask=4370.36)
    fill, pos = simulate_fill(
        direction="SELL",
        lot=0.01,
        sl_price=4370.86,  # entry 4370.0 + 50pts × 0.01 = 4370.50; +spread = 4370.86
        tick=tick0,
        risk_amount=50.0,
        cost_model=cm,
        trade_id="test-sell-abc",
    )
    # Price goes down → ABC close
    down_tick = _tick(bid=4369.0, ask=4369.36)
    exit_reason = pos.check_exit(down_tick)
    assert exit_reason == ExitReason.ABC_PROFIT_CLOSE


# --- Position lifecycle: SL stop ---


def test_buy_sl_stop() -> None:
    cm = CostModel(mode=CostMode.SPREAD_ONLY)
    tick0 = _tick(bid=4370.0, ask=4370.36)
    fill, pos = simulate_fill(
        direction="BUY",
        lot=0.01,
        sl_price=4369.86,
        tick=tick0,
        risk_amount=50.0,
        cost_model=cm,
        trade_id="test-buy-sl",
    )
    # Price drops below SL → SL_STOP
    sl_tick = _tick(bid=4369.50, ask=4369.86)
    exit_reason = pos.check_exit(sl_tick)
    assert exit_reason == ExitReason.SL_STOP


def test_sell_sl_stop() -> None:
    cm = CostModel(mode=CostMode.SPREAD_ONLY)
    tick0 = _tick(bid=4370.0, ask=4370.36)
    fill, pos = simulate_fill(
        direction="SELL",
        lot=0.01,
        sl_price=4370.86,
        tick=tick0,
        risk_amount=50.0,
        cost_model=cm,
        trade_id="test-sell-sl",
    )
    # Price goes up above SL → SL_STOP
    sl_tick = _tick(bid=4372.0, ask=4372.36)
    exit_reason = pos.check_exit(sl_tick)
    assert exit_reason == ExitReason.SL_STOP


# --- Risk budget invariants ---


def test_risk_budget_not_exceeded_zero_slippage() -> None:
    cm = CostModel(mode=CostMode.SPREAD_ONLY)
    tick0 = _tick(bid=4370.0, ask=4370.36)
    fill, pos = simulate_fill(
        direction="BUY",
        lot=0.01,
        sl_price=4369.86,
        tick=tick0,
        risk_amount=50.0,
        cost_model=cm,
        trade_id="test-budget",
    )
    sl_tick = _tick(bid=4369.50, ask=4369.86)
    exit_reason = pos.check_exit(sl_tick)
    assert exit_reason == ExitReason.SL_STOP
    close_result = pos.close(sl_tick, exit_reason)
    # Realized loss should not exceed theoretical risk (at spread-only cost)
    assert close_result["risk_realized"] <= close_result["risk_theoretical"] * 1.0001


def test_risk_budget_overrun_flagged_with_costs() -> None:
    cm = CostModel(
        mode=CostMode.FULL_COST_MODEL,
        commission_per_lot=10000.0,  # excessive commission to force overrun
        slippage_points=50.0,
    )
    tick0 = _tick(bid=4370.0, ask=4370.36)
    fill, pos = simulate_fill(
        direction="BUY",
        lot=0.01,
        sl_price=4369.86,
        tick=tick0,
        risk_amount=50.0,
        cost_model=cm,
        trade_id="test-overrun",
    )
    sl_tick = _tick(bid=4369.50, ask=4369.86)
    pos.check_exit(sl_tick)
    close_result = pos.close(sl_tick, ExitReason.SL_STOP)
    # With extreme commission, realized loss > theoretical
    assert close_result["risk_realized"] > close_result["risk_theoretical"]


# --- NO-TRADE never produces position ---


def test_no_trade_no_position() -> None:
    runner = ScenarioRunner(RiskConfig())
    scenario = ScenarioConfig(
        scenario_id="no-trade-01",
        description="NO-TRADE test",
        direction="NO-TRADE",
        ticks=[{"bid": 4370.0, "ask": 4370.36}],
    )
    result = runner.run(scenario)
    assert result.approved is False
    assert result.trade_evidence is None


# --- Scenario runner: BUY approve + ABC close ---


def test_scenario_buy_abc_close() -> None:
    runner = ScenarioRunner(RiskConfig())
    ticks = [
        {"bid": 4370.0, "ask": 4370.36, "timestamp_iso": "2026-08-17T09:35:00+00:00"},
        {"bid": 4371.0, "ask": 4371.36, "timestamp_iso": "2026-08-17T09:35:01+00:00"},
    ]
    scenario = ScenarioConfig(
        scenario_id="buy-abc-01",
        description="BUY → ABC profit close",
        direction="BUY",
        confidence=0.85,
        ticks=ticks,
        starting_equity=10000.0,
    )
    result = runner.run(scenario)
    assert result.approved is True
    assert result.exit_reason == "ABC_PROFIT_CLOSE"
    assert result.trade_evidence is not None
    ev = result.trade_evidence
    assert ev["direction"] == "BUY"
    assert ev["lot"] == 0.01
    assert ev["net_pnl"] > 0
    assert ev["risk_config_profile"] == "PAPER_VALIDATION_V0.1"


# --- Scenario runner: SELL approve + SL stop ---


def test_scenario_sell_sl_stop() -> None:
    runner = ScenarioRunner(RiskConfig())
    ticks = [
        {"bid": 4370.0, "ask": 4370.36, "timestamp_iso": "2026-08-17T09:35:00+00:00"},
        {"bid": 4372.0, "ask": 4372.36, "timestamp_iso": "2026-08-17T09:35:01+00:00"},
    ]
    scenario = ScenarioConfig(
        scenario_id="sell-sl-01",
        description="SELL → SL stop",
        direction="SELL",
        confidence=0.85,
        ticks=ticks,
        starting_equity=10000.0,
    )
    result = runner.run(scenario)
    assert result.approved is True
    assert result.exit_reason == "SL_STOP"
    assert result.trade_evidence is not None
    assert result.trade_evidence["net_pnl"] < 0


# --- Scenario runner: spread reject ---


def test_scenario_spread_reject() -> None:
    runner = ScenarioRunner(RiskConfig())
    # spread 6.0 = 600 points > 45
    ticks = [
        {"bid": 4370.0, "ask": 4376.0, "timestamp_iso": "2026-08-17T09:35:00+00:00"},
    ]
    scenario = ScenarioConfig(
        scenario_id="spread-reject-01",
        description="Spread above threshold",
        direction="BUY",
        ticks=ticks,
    )
    result = runner.run(scenario)
    assert result.approved is False
    assert "SPREAD" in result.rejection_reason_code


# --- Scenario runner: existing position blocks entry ---


def test_scenario_existing_position_blocks() -> None:
    runner = ScenarioRunner(RiskConfig())
    ticks = [
        {"bid": 4370.0, "ask": 4370.36, "timestamp_iso": "2026-08-17T09:35:00+00:00"},
    ]
    scenario = ScenarioConfig(
        scenario_id="pos-cap-01",
        description="Existing position blocks entry",
        direction="BUY",
        ticks=ticks,
        existing_positions=1,
    )
    result = runner.run(scenario)
    assert result.approved is False
    assert "EXPOSURE" in result.rejection_reason_code


# --- Scenario runner: drawdown reject ---


def test_scenario_drawdown_reject() -> None:
    runner = ScenarioRunner(RiskConfig())
    ticks = [
        {"bid": 4370.0, "ask": 4370.36, "timestamp_iso": "2026-08-17T09:35:00+00:00"},
    ]
    scenario = ScenarioConfig(
        scenario_id="dd-reject-01",
        description="Drawdown exceeds 5%",
        direction="BUY",
        ticks=ticks,
        current_drawdown_pct=0.10,
    )
    result = runner.run(scenario)
    assert result.approved is False
    assert "DRAWDOWN" in result.rejection_reason_code


# --- Scenario runner: insufficient margin ---


def test_scenario_insufficient_margin() -> None:
    runner = ScenarioRunner(RiskConfig())
    ticks = [
        {"bid": 4370.0, "ask": 4370.36, "timestamp_iso": "2026-08-17T09:35:00+00:00"},
    ]
    scenario = ScenarioConfig(
        scenario_id="margin-reject-01",
        description="Insufficient free margin",
        direction="BUY",
        ticks=ticks,
        starting_equity=10000.0,
        free_margin_override=50.0,
    )
    result = runner.run(scenario)
    assert result.approved is False
    assert "MARGIN" in result.rejection_reason_code


# --- Determinism: same inputs → same outputs ---


def test_scenario_determinism() -> None:
    runner = ScenarioRunner(RiskConfig())
    ticks = [
        {"bid": 4370.0, "ask": 4370.36, "timestamp_iso": "2026-08-17T09:35:00+00:00"},
        {"bid": 4371.0, "ask": 4371.36, "timestamp_iso": "2026-08-17T09:35:01+00:00"},
    ]
    scenario = ScenarioConfig(
        scenario_id="det-01",
        description="Determinism test",
        direction="BUY",
        ticks=ticks,
        starting_equity=10000.0,
    )
    r1 = runner.run(scenario)
    r2 = runner.run(scenario)
    assert r1.exit_reason == r2.exit_reason
    assert r1.trade_evidence["lot"] == r2.trade_evidence["lot"]
    assert r1.trade_evidence["net_pnl"] == r2.trade_evidence["net_pnl"]
