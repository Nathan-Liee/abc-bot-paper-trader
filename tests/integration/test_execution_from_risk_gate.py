"""Integration: Risk Gate -> TradePlan -> Execution engine -> simulated broker.

Proves the full lineage chain end-to-end without any broker or network:

    DecisionRecord -> RiskEngine evaluate (APPROVE) -> TradePlan
    -> ExecutionCommand (command_id == idempotency key)
    -> SimulatedExecutor FILLED -> SL confirmed -> CLOSED.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ai_decision.record import DecisionRecord
from execution.models import ExecutionCommand, ResultStatus, TradePlan
from risk_engine.engine import RiskEngine
from risk_engine.models import AccountState, MarketState, ReasonCode, SymbolSpecification
from tests.execution.factories import build_engine, ts_in


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _proposal(
    direction: str = "BUY", confidence: float = 0.85, correlation: str | None = None
) -> DecisionRecord:
    return DecisionRecord(
        inference_id=str(uuid4()),
        correlation_id=correlation or str(uuid4()),
        direction=direction,
        confidence=confidence,
        reason="support bounce verified",
        validation_ok=True,
        model_id="cf/model-primary",
        provider="cf",
        request_ts=_now(),
        latency_ms=120.0,
        context_snapshot_id="snap-999",
        prompt_version="v0.1",
    )


def _account() -> AccountState:
    return AccountState(
        balance=20000.0,
        equity=20000.0,
        free_margin=20000.0,
        margin=0.0,
        existing_positions_count=0,
        current_exposure_usd=0.0,
        current_drawdown_pct=0.0,
    )


def _market() -> MarketState:
    return MarketState(
        bid=4399.9,
        ask=4400.1,
        spread=0.2,
        mid=4400.0,
        symbol="XAUUSDc",
        timestamp_iso=_now(),
    )


def _spec() -> SymbolSpecification:
    return SymbolSpecification(
        symbol="XAUUSDc",
        contract_size=1.0,
        tick_size=0.01,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=1.0,
        volume_step=0.01,
        point=0.01,
        stops_level=0.0,
    )


def _evaluate(confidence: float):
    return RiskEngine().evaluate(
        _proposal(confidence=confidence),
        _account(),
        _market(),
        _spec(),
    )


def _plan_from_record(record, market: MarketState) -> TradePlan:
    """Orchestrator projection of an approved record into the execution plan."""
    return TradePlan.from_dict(
        {
            "trade_id": str(uuid4()),
            "correlation_id": record.correlation_id,
            "inference_id": record.inference_id,
            "risk_evaluation_id": record.risk_evaluation_id,
            "direction": record.direction,
            "lot": record.lot,
            "entry_reference": market.ask if record.direction == "BUY" else market.bid,
            "sl": record.sl,
            "risk_amount": record.risk_amount,
            "risk_percent": record.risk_percent,
            "exposure": record.exposure,
            "symbol": "XAUUSDc",
            "generated_at": record.timestamp_iso,
            "expires_at": ts_in(120.0),
            "policy_profile": "PAPER_VALIDATION_V0.1",
        }
    )


def test_execution_consumes_risk_approved_plan(tmp_path: object) -> None:
    market = _market()
    # 1. System Risk Gate approves: 0.5% of 20000 -> 100 USD budget;
    #    SL 50 pts -> loss/lot 5000 => lot 0.02 (within min 0.01/step 0.01)
    record = RiskEngine().evaluate(
        _proposal(direction="BUY", confidence=0.85),
        _account(),
        market,
        _spec(),
    )
    assert record.decision == "APPROVE"
    assert record.reason_code == ReasonCode.APPROVED.value
    assert record.lot > 0 and record.sl > 0

    # 2. Approved record projects into a valid, unexpired TradePlan
    plan = _plan_from_record(record, market)
    assert plan.validate() == []
    assert plan.risk_evaluation_id == record.risk_evaluation_id
    assert plan.inference_id == record.inference_id
    assert plan.direction == record.direction

    # 3. Execution engine: plan -> command -> simulated FILLED
    engine, journal, executor, _ = build_engine(str(tmp_path) + "/flow.db")  # type: ignore[operator]
    command: ExecutionCommand = engine.create_command(plan)
    assert command.idempotency_key == command.command_id
    assert command.trade_id == plan.trade_id
    result = engine.submit(command)
    assert result.status is ResultStatus.FILLED
    assert result.sl_applied is True
    assert result.filled_volume == plan.lot
    position = executor.get_position(command)
    assert position is not None
    assert abs(position.sl - plan.sl) < 1e-9

    # 4. ABC exit: system-owned close reason, idempotent
    closed = engine.close(command, position.position_id)
    assert closed.status is ResultStatus.CLOSED
    assert executor.query(command).discovered_state.value == "CLOSED"
    assert engine.close(command, position.position_id) == closed  # replay, no new calls
    assert len(executor.close_calls) == 1

    # 5. Full lifecycle recorded in the durable journal
    events = [e.event_type for e in journal.events(command.command_id)]
    for expected in ("COMMAND_CREATED", "FULL_FILL", "SL_CONFIRMED", "CLOSED"):
        assert expected in events
    assert journal.get_command(command.command_id).result == closed


def test_risk_reject_never_produces_a_plan(tmp_path: object) -> None:
    """Fail-closed upstream: REJECT carries no trade plan fields to execute."""
    record = _evaluate(confidence=0.30)  # below threshold -> REJECT
    assert record.decision == "REJECT"
    assert record.lot == 0.0
    assert record.sl == 0.0
    engine, journal, _, _ = build_engine(str(tmp_path) + "/flow2.db")  # type: ignore[operator]
    assert journal.command_count() == 0
    assert engine.pending_reconciliation() == []
