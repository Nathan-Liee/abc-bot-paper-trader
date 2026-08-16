"""Unit tests for Risk Engine calculators, validation rules, and determinism."""

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
        balance=1000.0,
        equity=1000.0,
        free_margin=1000.0,
        margin=0.0,
        existing_positions_count=0,
        current_exposure_usd=0.0,
        current_drawdown_pct=0.0,
    )


@pytest.fixture
def base_market() -> MarketState:
    now_iso = datetime.now(UTC).isoformat(timespec="seconds")
    return MarketState(
        bid=2000.0,
        ask=2000.20,
        spread=0.20,
        mid=2000.10,
        symbol="XAUUSDc",
        timestamp_iso=now_iso,
    )


@pytest.fixture
def base_spec() -> SymbolSpecification:
    return SymbolSpecification(
        symbol="XAUUSDc",
        contract_size=100.0,  # 100 oz per lot
        tick_size=0.01,
        tick_value=1.0,  # $1 per 0.01 move per lot (100 oz * 0.01 = $1)
        volume_min=0.01,
        volume_max=10.0,
        volume_step=0.01,
        stops_level=0.50,
        freeze_level=0.0,
    )


@pytest.fixture
def base_config() -> RiskConfig:
    return RiskConfig(
        risk_basis="EQUITY",
        risk_pct_per_trade=1.0,  # $10.00 budget on $1000 equity
        max_drawdown_pct=10.0,
        max_exposure_usd=50000.0,
        max_simultaneous_positions=1,
        max_spread=1.0,
        max_stale_seconds=10.0,
        default_sl_points=2.0,  # $2.00 distance = $200 risk per lot
        min_free_margin_usd=50.0,
        min_ai_confidence=0.5,
    )


def test_round_down_step() -> None:
    assert round_down_step(0.056, 0.01) == 0.05
    assert round_down_step(0.050, 0.01) == 0.05
    assert round_down_step(0.009, 0.01) == 0.0
    assert round_down_step(1.2345, 0.1) == 1.2
    assert round_down_step(1.0, 0.0) == 0.0


def test_sl_calculation_buy_sell() -> None:
    # BUY: entry 2000.20, sl_dist 2.0 -> sl 1998.20
    sl_price, dist, err = calculate_sl_price("BUY", 2000.20, 2.0, stops_level_points=0.5)
    assert err is None
    assert sl_price == 2000.20 - 2.0
    assert dist == 2.0

    # SELL: entry 2000.00, sl_dist 2.0 -> sl 2002.00
    sl_price, dist, err = calculate_sl_price("SELL", 2000.00, 2.0, stops_level_points=0.5)
    assert err is None
    assert sl_price == 2000.00 + 2.0
    assert dist == 2.0

    # Stops level clamp: sl_points 0.2 < stops_level 0.5 -> effective dist 0.5
    sl_price, dist, err = calculate_sl_price("BUY", 2000.20, 0.2, stops_level_points=0.5)
    assert err is None
    assert dist == 0.5
    assert sl_price == 2000.20 - 0.5


def test_trade_plan_calculation(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    # Equity $1000, 1% risk = $10.00 budget
    # SL distance $2.00 -> Loss per lot = (2.0 / 0.01) * 1.0 = $200.00 per lot
    # Raw lot = 10.00 / 200.00 = 0.05 lot
    plan = calculate_trade_plan("BUY", base_account, base_market, base_spec, base_config)
    assert plan.ok is True
    assert plan.candidate_lot == 0.05
    assert plan.final_lot == 0.05
    assert plan.risk_amount_usd == 10.0
    assert plan.risk_pct == 1.0
    assert plan.sl_price == round(base_market.ask - 2.0, 2)
    assert plan.exposure_usd == round(0.05 * 100.0 * base_market.ask, 2)


def test_risk_engine_approve_buy(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    engine = RiskEngine(base_config)
    proposal = DecisionRecord(
        inference_id="inf-001",
        model_id="test-model",
        provider="test-provider",
        request_ts="2026-08-17T00:00:00Z",
        latency_ms=100.0,
        context_snapshot_id=None,
        prompt_version="1.0.0",
        direction="BUY",
        confidence=0.85,
        reason="Upward momentum",
        validation_ok=True,
    )
    record = engine.evaluate(proposal, base_account, base_market, base_spec)
    assert record.decision == "APPROVE"
    assert record.direction == "BUY"
    assert record.lot == 0.05
    assert record.risk_amount == 10.0
    assert record.reason_code == ReasonCode.APPROVED.value


def test_risk_engine_approve_sell(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    engine = RiskEngine(base_config)
    proposal = DecisionRecord(
        inference_id="inf-002",
        model_id="test-model",
        provider="test-provider",
        request_ts="2026-08-17T00:00:00Z",
        latency_ms=100.0,
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
    assert record.lot == 0.05
    assert record.sl == round(base_market.bid + 2.0, 2)
    assert record.reason_code == ReasonCode.APPROVED.value


def test_risk_engine_ai_no_trade(
    base_account: AccountState,
    base_market: MarketState,
    base_spec: SymbolSpecification,
    base_config: RiskConfig,
) -> None:
    engine = RiskEngine(base_config)
    proposal = DecisionRecord(
        inference_id="inf-003",
        model_id="test-model",
        provider="test-provider",
        request_ts="2026-08-17T00:00:00Z",
        latency_ms=100.0,
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
        ask=2006.0,  # spread 6.0 > max 1.0
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
        balance=1000.0,
        equity=850.0,
        free_margin=850.0,
        margin=0.0,
        existing_positions_count=0,
        current_exposure_usd=0.0,
        current_drawdown_pct=15.0,  # 15% >= max 10%
    )
    proposal = {"direction": "BUY", "confidence": 0.8, "validation_ok": True}
    record = engine.evaluate(proposal, dd_account, base_market, base_spec)
    assert record.decision == "REJECT"
    assert record.reason_code == ReasonCode.DRAWDOWN_LIMIT.value


def test_risk_engine_exposure_limit_exceeded(
    base_account: AccountState, base_market: MarketState, base_spec: SymbolSpecification
) -> None:
    tiny_exposure_config = RiskConfig(
        max_exposure_usd=1000.0,  # max $1000 exposure
        risk_pct_per_trade=1.0,
        max_spread=1.0,
    )
    engine = RiskEngine(tiny_exposure_config)
    proposal = {"direction": "BUY", "confidence": 0.8, "validation_ok": True}
    # BUY 0.05 lot @ 2000 ask = 0.05 * 100 * 2000 = $10,000 exposure > $1000
    record = engine.evaluate(proposal, base_account, base_market, base_spec)
    assert record.decision == "REJECT"
    assert record.reason_code == ReasonCode.EXPOSURE_LIMIT.value


def test_risk_engine_insufficient_margin(
    base_market: MarketState, base_spec: SymbolSpecification, base_config: RiskConfig
) -> None:
    engine = RiskEngine(base_config)
    tight_margin_account = AccountState(
        balance=1000.0,
        equity=1000.0,
        free_margin=60.0,  # 60 - required_margin (100) = -40 < min_buffer (50)
        margin=940.0,
        existing_positions_count=0,
    )
    proposal = {"direction": "BUY", "confidence": 0.8, "validation_ok": True}
    record = engine.evaluate(proposal, tight_margin_account, base_market, base_spec)
    assert record.decision == "REJECT"
    assert record.reason_code == ReasonCode.INSUFFICIENT_MARGIN.value


def test_risk_engine_lot_below_min(
    base_market: MarketState, base_spec: SymbolSpecification, base_config: RiskConfig
) -> None:
    engine = RiskEngine(base_config)
    # Tiny equity $10.00 -> 1% risk = $0.10 -> raw lot = 0.10 / 200 = 0.0005 < 0.01 min
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
    proposal = DecisionRecord(
        inference_id="inf-gate-01",
        model_id="model",
        provider="provider",
        request_ts="2026-08-17T00:00:00Z",
        latency_ms=10.0,
        context_snapshot_id=None,
        prompt_version="1.0.0",
        direction="BUY",
        confidence=0.9,
        reason="Valid signal",
        validation_ok=True,
    )
    decision = gate.evaluate_proposal(proposal, base_account, base_market, base_spec)
    assert isinstance(decision, RiskDecision)
    assert decision.decision == "APPROVE"
    assert decision.direction == "BUY"
    assert decision.lot == 0.05
    assert decision.risk_amount == 10.0

    audit_rec = gate.evaluate_audit(proposal, base_account, base_market, base_spec)
    assert isinstance(audit_rec, RiskEvaluationRecord)
    assert audit_rec.decision == "APPROVE"
    assert audit_rec.inference_id == "inf-gate-01"
