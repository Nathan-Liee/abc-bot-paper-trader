"""Unit tests for Risk Engine (PAPER_VALIDATION_V0.1 profile)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_decision.record import DecisionRecord
from risk_engine.calculators import (
    calculate_sl_price,
    calculate_trade_plan,
    round_down_step,
)
from risk_engine.config import RiskConfig
from risk_engine.engine import RiskEngine
from risk_engine.gate import SystemRiskGate
from risk_engine.models import (
    AccountState,
    MarketState,
    ReasonCode,
    RiskDecision,
    RiskEvaluationRecord,
    SymbolSpecification,
)


@pytest.fixture
def base_account() -> AccountState:
    return AccountState(
        balance=10000.0,
        equity=10000.0,
        free_margin=10000.0,
        margin=0.0,
        existing_positions_count=0,
        current_exposure_usd=0.0,
        current_drawdown_pct=0.0,
    )


@pytest.fixture
def base_market() -> MarketState:
    now_iso = datetime.now(UTC).isoformat(timespec="seconds")
    return MarketState(
        bid=2000.00,
        ask=2000.20,
        spread=0.20,  # 20 points, within 45-pt paper threshold
        mid=2000.10,
        symbol="XAUUSDc",
        timestamp_iso=now_iso,
    )


@pytest.fixture
def base_spec() -> SymbolSpecification:
    return SymbolSpecification(
        symbol="XAUUSDc",
        contract_size=1.0,  # Cent mini (matches runtime evidence)
        tick_size=0.01,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=1000.0,
        volume_step=0.01,
        stops_level=0.5,
        freeze_level=8.0,
    )


@pytest.fixture
def base_config() -> RiskConfig:
    return RiskConfig(
        risk_per_trade=0.005,
        max_simultaneous_positions=1,
        max_drawdown=0.05,
        sl_distance_points=50.0,
        max_spread_points=45.0,
        max_exposure_equity_ratio=1.0,
        min_free_margin_equity_ratio=0.10,
        margin_risk_budget_multiplier=1.0,
        leverage_fallback=2000.0,
        compounding_reinvestment_ratio=0.0,
        observed_spread_points=36.0,
        min_ai_confidence=0.5,
    )


def _buy_proposal(record_id: str = "inf-001", confidence: float = 0.85) -> DecisionRecord:
    return DecisionRecord(
        inference_id=record_id,
        model_id="test-model",
        provider="test-provider",
        request_ts="2026-08-17T00:00:00Z",
        latency_ms=100.0,
        context_snapshot_id=None,
        prompt_version="1.0.0",
        direction="BUY",
        confidence=confidence,
        reason="Upward momentum",
        validation_ok=True,
    )


def test_round_down_step() -> None:
    assert round_down_step(0.056, 0.01) == 0.05
    assert round_down_step(0.050, 0.01) == 0.05
    assert round_down_step(0.009, 0.01) == 0.0
    assert round_down_step(1.2345, 0.1) == 1.2
    assert round_down_step(1.0, 0.0) == 0.0


def test_sl_calculation_buy_sell() -> None:
    sl_price, dist, err = calculate_sl_price("BUY", 2000.20, 2.0, stops_level_points=0.5)
    assert err is None
    assert sl_price == 2000.20 - 2.0
    assert dist == 2.0

    sl_price, dist, err = calculate_sl_price("SELL", 2000.00, 2.0, stops_level_points=0.5)
    assert err is None
    assert sl_price == 2000.00 + 2.0
    assert dist == 2.0

    sl_price, dist, err = calculate_sl_price("BUY", 2000.20, 0.2, stops_level_points=0.5)
    assert err is None
    assert dist == 0.5
    assert sl_price == 2000.20 - 0.5


def test_config_paper_profile_metadata() -> None:
    cfg = RiskConfig()
    assert cfg.profile_name == "PAPER_VALIDATION_V0.1"
    assert cfg.is_production is False
    assert cfg.requires_paper_validation is True
    assert cfg.risk_basis == "EQUITY"
    assert cfg.risk_per_trade == 0.005  # 0.5 %
    assert cfg.max_simultaneous_positions == 1
    assert cfg.max_drawdown == 0.05  # 5 %
    assert cfg.sl_distance_points == 50.0
    assert cfg.max_spread_points == 45.0
    assert cfg.max_exposure_equity_ratio == 1.0
    assert cfg.min_free_margin_equity_ratio == 0.10
    assert cfg.margin_risk_budget_multiplier == 1.0
    assert cfg.leverage_fallback == 2000.0
    assert cfg.compounding_reinvestment_ratio == 0.0  # no auto compounding
    assert cfg.validate() == []


def test_config_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ABC_SL_DISTANCE_POINTS", "60")
    monkeypatch.setenv("ABC_MAX_SPREAD_POINTS", "50")
    monkeypatch.setenv("ABC_RISK_PER_TRADE", "0.01")
    cfg = RiskConfig.from_env()
    assert cfg.sl_distance_points == 60.0
    assert cfg.max_spread_points == 50.0
    assert cfg.risk_per_trade == 0.01


def test_config_sl_below_observed_spread_invalid() -> None:
    cfg = RiskConfig(sl_distance_points=30.0)  # 30 < 36 observed
    errors = cfg.validate()
    assert any("below_observed_spread" in e for e in errors)


def test_trade_plan_calculation(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    # Equity 10000, 0.5% risk = 50 budget; SL 50 pts -> loss/lot 5000 -> lot 0.01
    plan = calculate_trade_plan("BUY", base_account, base_market, base_spec, base_config)
    assert plan.ok is True
    assert plan.candidate_lot == 0.01
    assert plan.final_lot == 0.01
    assert plan.risk_amount_usd == 50.0
    assert plan.risk_pct == 0.5
    assert plan.sl_price == round(base_market.ask - 0.50, 2)
    assert plan.exposure_usd == round(0.01 * 1.0 * base_market.ask, 2)


def test_risk_engine_approve_buy(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    engine = RiskEngine(base_config)
    record = engine.evaluate(_buy_proposal(), base_account, base_market, base_spec)
    assert record.decision == "APPROVE"
    assert record.direction == "BUY"
    assert record.lot == 0.01
    assert record.risk_amount == 50.0
    assert record.risk_percent == 0.5
    assert record.sl == round(base_market.ask - 0.50, 2)
    assert record.reason_code == ReasonCode.APPROVED.value


def test_risk_engine_approve_sell(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    engine = RiskEngine(base_config)
    proposal = _buy_proposal("inf-002", 0.90)
    proposal = DecisionRecord(
        inference_id=proposal.inference_id,
        model_id=proposal.model_id,
        provider=proposal.provider,
        request_ts=proposal.request_ts,
        latency_ms=proposal.latency_ms,
        context_snapshot_id=None,
        prompt_version="1.0.0",
        direction="SELL",
        confidence=0.90,
        reason="Resistance rejection",
        validation_ok=True,
    )
    record = engine.evaluate(proposal, base_account, base_market, base_spec)
    assert record.decision == "APPROVE"
    assert record.direction == "SELL"
    assert record.lot == 0.01
    assert record.sl == round(base_market.bid + 0.50, 2)
    assert record.reason_code == ReasonCode.APPROVED.value


def test_risk_engine_ai_no_trade(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    engine = RiskEngine(base_config)
    proposal = _buy_proposal("inf-003", 0.95)
    proposal = DecisionRecord(
        inference_id=proposal.inference_id,
        model_id=proposal.model_id,
        provider=proposal.provider,
        request_ts=proposal.request_ts,
        latency_ms=proposal.latency_ms,
        context_snapshot_id=None,
        prompt_version="1.0.0",
        direction="NO-TRADE",
        confidence=0.95,
        reason="Chop zone",
        validation_ok=True,
    )
    record = engine.evaluate(proposal, base_account, base_market, base_spec)
    assert record.decision == "REJECT"
    assert record.direction == "NO-TRADE"
    assert record.lot == 0.0
    assert record.reason_code == ReasonCode.AI_NO_TRADE.value


def test_risk_engine_ai_validation_failed(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    engine = RiskEngine(base_config)
    proposal = DecisionRecord(
        inference_id="inf-004",
        model_id="test-model",
        provider="test-provider",
        request_ts="2026-08-17T00:00:00Z",
        latency_ms=100.0,
        context_snapshot_id=None,
        prompt_version="1.0.0",
        direction="BUY",
        confidence=0.8,
        reason="",
        validation_ok=False,
        error_class="AUTHORITY_VIOLATION",
    )
    record = engine.evaluate(proposal, base_account, base_market, base_spec)
    assert record.decision == "REJECT"
    assert record.reason_code == ReasonCode.AUTHORITY_VIOLATION.value


def test_risk_engine_spread_too_high(
    base_account: AccountState, base_spec: SymbolSpecification, base_config: RiskConfig
) -> None:
    engine = RiskEngine(base_config)
    bad_market = MarketState(
        bid=2000.0,
        ask=2006.0,  # spread 6.0 = 600 points > 45-pt threshold
        spread=6.0,
        mid=2003.0,
        symbol="XAUUSDc",
        timestamp_iso=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    proposal = {"direction": "BUY", "confidence": 0.8, "validation_ok": True}
    record = engine.evaluate(proposal, base_account, bad_market, base_spec)
    assert record.decision == "REJECT"
    assert record.reason_code == ReasonCode.SPREAD_TOO_HIGH.value


def test_risk_engine_stale_market_context(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    engine = RiskEngine(base_config)
    old_time = datetime.now(UTC) - timedelta(seconds=60)
    stale_market = MarketState(
        bid=base_market.bid,
        ask=base_market.ask,
        spread=base_market.spread,
        mid=base_market.mid,
        symbol=base_market.symbol,
        timestamp_iso=old_time.isoformat(timespec="seconds"),
    )
    proposal = {"direction": "BUY", "confidence": 0.8, "validation_ok": True}
    record = engine.evaluate(proposal, base_account, stale_market, base_spec)
    assert record.decision == "REJECT"
    assert record.reason_code == ReasonCode.STALE_CONTEXT.value


def test_risk_engine_drawdown_limit_exceeded(
    base_market: MarketState, base_spec: SymbolSpecification, base_config: RiskConfig
) -> None:
    engine = RiskEngine(base_config)
    dd_account = AccountState(
        balance=10000.0,
        equity=8500.0,
        free_margin=8500.0,
        margin=0.0,
        existing_positions_count=0,
        current_exposure_usd=0.0,
        current_drawdown_pct=0.15,  # 15 % >= 5 % threshold
    )
    proposal = {"direction": "BUY", "confidence": 0.8, "validation_ok": True}
    record = engine.evaluate(proposal, dd_account, base_market, base_spec)
    assert record.decision == "REJECT"
    assert record.reason_code == ReasonCode.DRAWDOWN_LIMIT.value


def test_risk_engine_exposure_limit_includes_existing(
    base_market: MarketState, base_spec: SymbolSpecification, base_config: RiskConfig
) -> None:
    engine = RiskEngine(base_config)
    existing_exposure_account = AccountState(
        balance=10000.0,
        equity=10000.0,
        free_margin=10000.0,
        margin=0.0,
        existing_positions_count=0,
        current_exposure_usd=9990.0,  # 9990 + 20.002 > 10000 (1.0x equity) -> reject
        current_drawdown_pct=0.0,
    )
    proposal = {"direction": "BUY", "confidence": 0.8, "validation_ok": True}
    record = engine.evaluate(proposal, existing_exposure_account, base_market, base_spec)
    assert record.decision == "REJECT"
    assert record.reason_code == ReasonCode.EXPOSURE_LIMIT.value


def test_risk_engine_insufficient_margin_ratio(
    base_market: MarketState, base_spec: SymbolSpecification, base_config: RiskConfig
) -> None:
    engine = RiskEngine(base_config)
    tight_margin_account = AccountState(
        balance=10000.0,
        equity=10000.0,
        free_margin=1050.0,  # after required margin < 1050 (10% equity + 1x budget)
        margin=0.0,
        existing_positions_count=0,
    )
    proposal = {"direction": "BUY", "confidence": 0.8, "validation_ok": True}
    record = engine.evaluate(proposal, tight_margin_account, base_market, base_spec)
    assert record.decision == "REJECT"
    assert record.reason_code == ReasonCode.INSUFFICIENT_MARGIN.value


def test_risk_engine_positions_cap(
    base_market: MarketState, base_spec: SymbolSpecification, base_config: RiskConfig
) -> None:
    engine = RiskEngine(base_config)
    one_position_account = AccountState(
        balance=10000.0,
        equity=10000.0,
        free_margin=10000.0,
        margin=0.0,
        existing_positions_count=1,  # max_simultaneous_positions = 1 -> reject
        current_exposure_usd=0.0,
        current_drawdown_pct=0.0,
    )
    proposal = {"direction": "BUY", "confidence": 0.8, "validation_ok": True}
    record = engine.evaluate(proposal, one_position_account, base_market, base_spec)
    assert record.decision == "REJECT"
    assert record.reason_code == ReasonCode.EXPOSURE_LIMIT.value


def test_risk_engine_sl_below_observed_spread_config_invalid(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
) -> None:
    bad_config = RiskConfig(
        sl_distance_points=30.0,  # 30 < observed spread 36 -> invalid config
        observed_spread_points=36.0,
        max_spread_points=45.0,
        risk_per_trade=0.005,
        max_drawdown=0.05,
    )
    engine = RiskEngine(bad_config)
    proposal = {"direction": "BUY", "confidence": 0.8, "validation_ok": True}
    record = engine.evaluate(proposal, base_account, base_market, base_spec)
    assert record.decision == "REJECT"
    # config.validate() fails first (fail-closed) -> UNKNOWN_RISK_INPUT
    assert record.reason_code == ReasonCode.UNKNOWN_RISK_INPUT.value


def test_trade_plan_sl_guard_below_observed_spread(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
) -> None:
    bad_config = RiskConfig(
        sl_distance_points=30.0,
        observed_spread_points=36.0,
        max_spread_points=45.0,
        risk_per_trade=0.005,
        max_drawdown=0.05,
    )
    # Direct calculator path (bypasses config.validate()) -> plan guard fires.
    plan = calculate_trade_plan("BUY", base_account, base_market, base_spec, bad_config)
    assert plan.ok is False
    assert plan.error is not None
    assert "sl_distance_not_above_observed_spread" in plan.error


def test_risk_engine_lot_below_min(
    base_market: MarketState, base_spec: SymbolSpecification, base_config: RiskConfig
) -> None:
    engine = RiskEngine(base_config)
    micro_account = AccountState(
        balance=10.0,
        equity=10.0,
        free_margin=10.0,
        margin=0.0,
    )
    proposal = {"direction": "BUY", "confidence": 0.8, "validation_ok": True}
    record = engine.evaluate(proposal, micro_account, base_market, base_spec)
    assert record.decision == "REJECT"
    assert record.reason_code == ReasonCode.LOT_OUT_OF_RANGE.value


def test_risk_engine_nan_infinite_safety(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    engine = RiskEngine(base_config)
    nan_market = MarketState(
        bid=float("nan"),
        ask=2000.0,
        spread=0.2,
        mid=2000.0,
        symbol="XAUUSDc",
        timestamp_iso=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    proposal = {"direction": "BUY", "confidence": 0.8, "validation_ok": True}
    record = engine.evaluate(proposal, base_account, nan_market, base_spec)
    assert record.decision == "REJECT"
    assert record.reason_code == ReasonCode.INVALID_MARKET_CONTEXT.value


def test_risk_engine_rounding_never_exceeds_budget(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    plan = calculate_trade_plan("BUY", base_account, base_market, base_spec, base_config)
    assert plan.ok is True
    budget = base_account.equity * base_config.risk_per_trade
    assert plan.risk_amount_usd <= budget * 1.0001


def test_risk_engine_determinism(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    engine = RiskEngine(base_config)
    proposal = {"direction": "BUY", "confidence": 0.8, "validation_ok": True}
    res1 = engine.evaluate(proposal, base_account, base_market, base_spec)
    res2 = engine.evaluate(proposal, base_account, base_market, base_spec)
    assert res1.decision == res2.decision == "APPROVE"
    assert res1.lot == res2.lot
    assert res1.sl == res2.sl
    assert res1.risk_amount == res2.risk_amount
    assert res1.exposure == res2.exposure


def test_system_risk_gate_interface(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    gate = SystemRiskGate(RiskEngine(base_config))
    proposal = _buy_proposal("inf-gate-01", 0.9)
    decision = gate.evaluate_proposal(proposal, base_account, base_market, base_spec)
    assert isinstance(decision, RiskDecision)
    assert decision.decision == "APPROVE"
    assert decision.direction == "BUY"
    assert decision.lot == 0.01
    assert decision.risk_amount == 50.0

    audit_rec = gate.evaluate_audit(proposal, base_account, base_market, base_spec)
    assert isinstance(audit_rec, RiskEvaluationRecord)
    assert audit_rec.decision == "APPROVE"
    assert audit_rec.inference_id == "inf-gate-01"
