"""Shared builders and fixtures for execution tests.

Nothing here touches the network or MT5; the SimulatedExecutor is the
only broker stand-in used by the execution test suite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from execution.engine import ExecutionConfig, ExecutionEngine
from execution.journal import ExecutionJournal
from execution.models import (
    EntryType,
    ExecutionCommand,
    TradePlan,
    now_iso,
)
from execution.reconciliation import ReconciliationBoundary, ReconciliationOutcome
from execution.simulated import SimulatedExecutor


def ts_in(seconds: float) -> str:
    """ISO timestamp *seconds* from now (negative -> past)."""
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def make_plan(
    *,
    trade_id: str | None = None,
    direction: str = "BUY",
    lot: float = 0.01,
    entry_reference: float = 4400.0,
    sl: float = 4399.5,
    risk_amount: float = 5.0,
    risk_percent: float = 0.5,
    exposure: float = 44.0,
    symbol: str = "XAUUSDc",
    policy_profile: str = "PAPER_VALIDATION_V0.1",
    ttl_seconds: float = 60.0,
) -> TradePlan:
    """A structurally valid TradePlan (never expired within the test)."""
    return TradePlan(
        trade_id=trade_id or str(uuid4()),
        correlation_id=str(uuid4()),
        inference_id=str(uuid4()),
        risk_evaluation_id=str(uuid4()),
        direction=direction,
        lot=lot,
        entry_reference=entry_reference,
        sl=sl,
        risk_amount=risk_amount,
        risk_percent=risk_percent,
        exposure=exposure,
        symbol=symbol,
        generated_at=ts_in(-1.0),
        expires_at=ts_in(ttl_seconds),
        policy_profile=policy_profile,
    )


def make_command(
    *,
    plan: TradePlan | None = None,
    volume: float | None = None,
    direction: str | None = None,
    sl: float | None = None,
    created_at: str | None = None,
    expires_at: str | None = None,
) -> ExecutionCommand:
    """A structurally valid ExecutionCommand derived from a plan."""
    plan = plan or make_plan()
    return ExecutionCommand(
        command_id=str(uuid4()),
        trade_id=plan.trade_id,
        symbol=plan.symbol,
        direction=direction or plan.direction,
        volume=plan.lot if volume is None else volume,
        entry_type=EntryType.MARKET,
        sl=plan.sl if sl is None else sl,
        created_at=created_at or now_iso(),
        expires_at=expires_at or plan.expires_at,
    )


class SimBrokerReconciliation(ReconciliationBoundary):
    """Reconciliation boundary that answers from the simulator broker book.

    Makes "reconcile before resend" and restart-recovery tests exercise
    the same evidence path a real broker reconciliation would follow.
    """

    def __init__(self, executor: SimulatedExecutor) -> None:
        self._executor = executor

    def reconcile(
        self,
        command: ExecutionCommand,
        hint: object | None = None,
    ) -> ReconciliationOutcome:
        return self._executor.query(command)


def build_engine(
    db_path: str,
    *,
    executor: SimulatedExecutor | None = None,
    reconciliation: ReconciliationBoundary | None = None,
    config: ExecutionConfig | None = None,
) -> tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor, ReconciliationBoundary]:
    """Assemble a wired engine with defaults; returns (engine, journal, executor, rec)."""
    journal = ExecutionJournal(db_path)
    executor = executor or SimulatedExecutor()
    reconciliation = reconciliation or SimBrokerReconciliation(executor)
    engine = ExecutionEngine(journal, executor, reconciliation, config=config)
    return engine, journal, executor, reconciliation
