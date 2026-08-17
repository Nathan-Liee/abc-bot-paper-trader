"""Integration test: AI Decision Engine -> System Risk Gate pipeline.

Validates the complete flow without broker execution or MT5 communication.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_decision.client import TransportResult
from ai_decision.config import EngineConfig, ModelConfig, Secrets
from ai_decision.engine import DecisionEngine
from risk_engine.config import RiskConfig
from risk_engine.engine import RiskEngine
from risk_engine.gate import SystemRiskGate
from risk_engine.models import (
    AccountState,
    MarketState,
    ReasonCode,
    RiskDecision,
    SymbolSpecification,
)


@pytest.fixture
def mock_account() -> AccountState:
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
def mock_market() -> MarketState:
    return MarketState(
        bid=2050.0,
        ask=2050.25,
        spread=0.25,
        mid=2050.125,
        symbol="XAUUSDc",
        timestamp_iso=datetime.now(UTC).isoformat(timespec="seconds"),
    )


@pytest.fixture
def mock_spec() -> SymbolSpecification:
    return SymbolSpecification(
        symbol="XAUUSDc",
        contract_size=1.0,  # Cent mini (matches runtime evidence)
        tick_size=0.01,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=1000.0,
        volume_step=0.01,
        stops_level=0.50,
    )


def test_ai_decision_to_risk_gate_pipeline(
    mock_account: AccountState,
    mock_market: MarketState,
    mock_spec: SymbolSpecification,
) -> None:
    # 1. Setup AI Decision Engine with mocked transport returning valid BUY
    ai_config = EngineConfig(
        base_url="http://mock-router/v1",
        primary=ModelConfig(model_id="cf/model-primary", provider="cf"),
        secondary=ModelConfig(model_id="groq/model-secondary", provider="groq"),
        fallback=ModelConfig(model_id="cf/model-fallback", provider="cf"),
        timeout_s=10.0,
        max_attempts=2,
        retry_429_sleep_s=0.1,
        max_tokens=256,
        temperature=0.0,
    )
    secrets = Secrets(api_key="test-key")

    def mock_transport(*args, **kwargs) -> TransportResult:
        payload = '{"direction": "BUY", "confidence": 0.85, "reason": "Support bounce verified"}'
        return TransportResult(status="OK", raw=payload, latency_ms=120.0, error=None)

    ai_engine = DecisionEngine(ai_config, secrets, transport=mock_transport)

    # 2. Setup System Risk Gate (PAPER_VALIDATION_V0.1 profile)
    risk_config = RiskConfig(
        risk_per_trade=0.005,  # 0.5% of 10000 -> 50 USC budget
        sl_distance_points=50.0,  # 50 pts -> loss/lot 5000 -> 0.01 lot
        max_spread_points=45.0,
        max_exposure_equity_ratio=1.0,
        min_free_margin_equity_ratio=0.10,
        margin_risk_budget_multiplier=1.0,
        leverage_fallback=2000.0,
        observed_spread_points=36.0,
    )
    risk_gate = SystemRiskGate(RiskEngine(risk_config))

    # 3. Market context feeding AI
    market_ctx = {
        "symbol": "XAUUSDc",
        "bid": mock_market.bid,
        "ask": mock_market.ask,
        "spread": mock_market.spread,
        "mid": mock_market.mid,
        "atr_m1": 1.5,
        "m1": {"trend": "bullish"},
        "m5": {"trend": "bullish"},
        "context_snapshot_id": "snap-999",
    }

    # Step A: AI produces proposal
    proposal = ai_engine.decide(market_ctx, correlation_id="corr-pipeline-1")
    assert proposal.validation_ok is True
    assert proposal.direction == "BUY"
    assert proposal.confidence == 0.85

    # Step B: Risk Gate evaluates proposal
    decision = risk_gate.evaluate_proposal(
        ai_proposal=proposal,
        account=mock_account,
        market=mock_market,
        spec=mock_spec,
        correlation_id="corr-pipeline-1",
    )

    # Step C: Assert System Gate Approval & Sizing
    assert isinstance(decision, RiskDecision)
    assert decision.decision == "APPROVE", (
        f"Rejection reason: {decision.reason} ({decision.reason_code})"
    )
    assert decision.direction == "BUY"
    assert decision.lot == 0.01
    assert decision.risk_amount == 50.0
    assert decision.risk_percent == 0.5
    assert decision.sl == round(mock_market.ask - 0.5, 2)
    assert decision.reason_code == ReasonCode.APPROVED.value


def test_ai_no_trade_to_risk_gate_pipeline(
    mock_account: AccountState,
    mock_market: MarketState,
    mock_spec: SymbolSpecification,
) -> None:
    # AI returns NO-TRADE
    ai_config = EngineConfig(
        base_url="http://mock-router/v1",
        primary=ModelConfig(model_id="cf/model-primary", provider="cf"),
        secondary=ModelConfig(model_id="groq/model-secondary", provider="groq"),
        fallback=ModelConfig(model_id="cf/model-fallback", provider="cf"),
        timeout_s=10.0,
        max_attempts=2,
        retry_429_sleep_s=0.1,
        max_tokens=256,
        temperature=0.0,
    )
    secrets = Secrets(api_key="test-key")

    def mock_transport(*args, **kwargs) -> TransportResult:
        payload = '{"direction": "NO-TRADE", "confidence": 0.90, "reason": "High volatility"}'
        return TransportResult(status="OK", raw=payload, latency_ms=100.0, error=None)

    ai_engine = DecisionEngine(ai_config, secrets, transport=mock_transport)
    risk_gate = SystemRiskGate()

    market_ctx = {
        "symbol": "XAUUSDc",
        "bid": mock_market.bid,
        "ask": mock_market.ask,
        "spread": mock_market.spread,
        "mid": mock_market.mid,
        "atr_m1": 1.5,
        "m1": {"trend": "neutral"},
        "m5": None,
    }

    proposal = ai_engine.decide(market_ctx)
    assert proposal.direction == "NO-TRADE"

    decision = risk_gate.evaluate_proposal(
        ai_proposal=proposal,
        account=mock_account,
        market=mock_market,
        spec=mock_spec,
    )

    assert decision.decision == "REJECT"
    assert decision.direction == "NO-TRADE"
    assert decision.lot == 0.0
    assert decision.reason_code == ReasonCode.AI_NO_TRADE.value
