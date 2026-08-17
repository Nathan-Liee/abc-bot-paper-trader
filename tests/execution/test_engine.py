"""Execution Engine lifecycle: OD-1..OD-10, budgeted retries, reconciliation."""

from __future__ import annotations

from dataclasses import replace

import pytest

from execution.engine import ExecutionConfig, ExecutionEngine, ExecutionError
from execution.errors import ExecutionStateError
from execution.journal import ExecutionJournal
from execution.models import CommandState, ExitReason, ResultStatus
from execution.reconciliation import ReconciliationOutcome, StaticReconciliation
from execution.retry import ErrorCode, RetryPolicy
from execution.simulated import SimulatedExecutor, SimulatorScenario, SubmitMode
from tests.execution.factories import (
    SimBrokerReconciliation,
    make_command,
    make_plan,
    ts_in,
)


@pytest.fixture
def env(tmp_path: object) -> tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]:
    from tests.execution.factories import build_engine

    engine, journal, executor, _ = build_engine(str(tmp_path) + "/engine.db")  # type: ignore[operator]
    return engine, journal, executor


def engine_with_reconciliation(
    env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor],
    outcome: ReconciliationOutcome | None = None,
) -> tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor, StaticReconciliation]:
    """Re-pin the same journal/executor to a static reconciliation boundary."""
    _, journal, executor = env
    rec = StaticReconciliation(outcome=outcome)
    engine = ExecutionEngine(journal, executor, rec)
    return engine, journal, executor, rec


class TestCreateCommand:
    def test_valid_plan_creates_created_command(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, _ = env
        plan = make_plan()
        command = engine.create_command(plan)
        assert journal.get_command(command.command_id).state is CommandState.CREATED
        assert command.trade_id == plan.trade_id
        assert command.idempotency_key == command.command_id
        assert command.volume == plan.lot
        assert command.sl == plan.sl
        assert command.entry_type.value == "MARKET"
        assert command.expires_at == plan.expires_at

    def test_invalid_plan_rejected(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, _, _ = env
        with pytest.raises(ExecutionError) as exc:
            engine.create_command(make_plan(lot=0.0))
        assert exc.value.error_code == ErrorCode.INVALID_COMMAND.value

    def test_expired_plan_never_becomes_command(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, _ = env
        stale = replace(
            make_plan(), generated_at=ts_in(-120.0), expires_at=ts_in(-60.0)
        )  # valid ordering, but already past
        with pytest.raises(ExecutionError) as exc:
            engine.create_command(stale)
        assert exc.value.error_code == ErrorCode.EXPIRED.value
        assert journal.command_count() == 0


class TestSubmitLifecycle:
    def test_full_fill_with_sl_confirmed(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, executor = env
        command = engine.create_command(make_plan())
        result = engine.submit(command)
        assert result.status is ResultStatus.FILLED
        assert result.sl_applied is True
        assert result.fill_price == 4400.0
        stored = journal.get_command(command.command_id)
        assert stored.state is CommandState.FILLED
        assert stored.result == result
        assert len(executor.submit_calls) == 1
        assert "SL_CONFIRMED" in [e.event_type for e in journal.events(command.command_id)]

    def test_partial_fill_cancels_remainder_no_second_order(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, executor = env
        command = engine.create_command(make_plan(lot=0.10))
        executor.set_scenario(
            command.command_id, SimulatorScenario(mode=SubmitMode.PARTIAL_FILL, fill_ratio=0.6)
        )
        result = engine.submit(command)
        assert result.status is ResultStatus.FILLED  # promoted after remainder cancel
        assert result.filled_volume == 0.06
        assert result.sl_applied is True
        cancel = next(
            e for e in journal.events(command.command_id) if e.event_type == "CANCEL_REMAINDER"
        )
        assert cancel.payload["cancelled_volume"] == 0.04
        assert cancel.payload["policy"] == "CANCEL_REMAINING"
        assert cancel.payload["second_order"] is False
        assert cancel.payload["requested_volume"] == 0.10
        assert journal.get_command(command.command_id).state is CommandState.FILLED
        assert len(executor.submit_calls) == 1  # never a second order (OD-1)

    def test_rejection_is_terminal_no_retry(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, executor = env
        command = engine.create_command(make_plan())
        executor.set_scenario(command.command_id, SimulatorScenario(mode=SubmitMode.REJECT))
        result = engine.submit(command)
        assert result.status is ResultStatus.REJECTED
        assert result.error_code == ErrorCode.BROKER_REJECT.value
        stored = journal.get_command(command.command_id)
        assert stored.state is CommandState.REJECTED
        assert stored.result == result
        assert len(executor.submit_calls) == 1

    @pytest.mark.parametrize(
        ("mode", "error_code"),
        [
            (SubmitMode.REQUOTE, ErrorCode.REQUOTE_SLIPPAGE),
            (SubmitMode.STALE_FEED, ErrorCode.STALE_FEED),
            (SubmitMode.POSITION_EXISTS, ErrorCode.POSITION_EXISTS),
        ],
    )
    def test_permanent_rejections_no_blind_retry_plan_untouched(
        self,
        env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor],
        mode: SubmitMode,
        error_code: ErrorCode,
    ) -> None:
        engine, journal, executor = env
        plan = make_plan()
        plan_dict = plan.to_dict()
        command = engine.create_command(plan)
        executor.set_scenario(command.command_id, SimulatorScenario(mode=mode))
        result = engine.submit(command)
        assert result.status is ResultStatus.REJECTED
        assert result.error_code == error_code.value
        assert journal.get_command(command.command_id).state is CommandState.REJECTED
        assert len(executor.submit_calls) == 1  # never blind resend (OD-10)
        assert plan.to_dict() == plan_dict  # plan never mutated

    def test_expired_command_never_reaches_executor(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, executor = env
        plan = make_plan()
        command = make_command(
            plan=plan,
            created_at=ts_in(-120.0),
            expires_at=ts_in(-60.0),  # ordering valid, but already past
        )
        journal.create_command(command)
        result = engine.submit(command)
        assert result.status is ResultStatus.EXPIRED
        assert journal.get_command(command.command_id).state is CommandState.EXPIRED
        assert len(executor.submit_calls) == 0  # never submitted (OD-7)
        fresh = engine.create_command(plan)  # terminal trade releases the slot
        assert fresh.trade_id == plan.trade_id

    def test_invalid_command_fails_closed(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, executor = env
        command = make_command(direction="NO-TRADE")
        journal.create_command(command)
        result = engine.submit(command)
        assert result.status is ResultStatus.FAILED
        assert result.error_code == ErrorCode.INVALID_COMMAND.value
        assert journal.get_command(command.command_id).state is CommandState.FAILED
        assert len(executor.submit_calls) == 0

    def test_submit_is_idempotent_replay(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, _, executor = env
        command = engine.create_command(make_plan())
        first = engine.submit(command)
        second = engine.submit(command)
        assert second == first
        assert len(executor.submit_calls) == 1


class TestTimeoutRetries:
    def test_timeout_retries_bounded_after_clean_reconciliation(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, executor = env
        command = engine.create_command(make_plan())
        executor.set_scenario(command.command_id, SimulatorScenario(mode=SubmitMode.TIMEOUT))
        result = engine.submit(command)
        assert result.status is ResultStatus.UNKNOWN
        assert result.error_code == ErrorCode.NETWORK_TIMEOUT.value
        # initial attempt + 2 budgeted retries, each after a clean reconcile
        assert len(executor.submit_calls) == 3
        assert journal.get_command(command.command_id).state is CommandState.UNKNOWN
        reconciles = [
            e
            for e in journal.events(command.command_id)
            if e.event_type == "RECONCILE_AFTER_TIMEOUT"
        ]
        assert len(reconciles) == 2
        assert engine.pending_reconciliation()  # fail-closed entry gate

    def test_retries_stop_when_broker_unreachable(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, _, executor, rec = engine_with_reconciliation(
            env, ReconciliationOutcome(ambiguous=True, evidence={"unreachable": True})
        )
        command = engine.create_command(make_plan())
        executor.set_scenario(command.command_id, SimulatorScenario(mode=SubmitMode.TIMEOUT))
        result = engine.submit(command)
        assert result.status is ResultStatus.UNKNOWN
        assert result.error_code == ErrorCode.AMBIGUOUS_RESPONSE.value
        assert len(executor.submit_calls) == 1  # no retry without proof

    def test_timeout_that_landed_is_resolved_by_broker_evidence(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, executor = env
        command = engine.create_command(make_plan())
        executor.set_scenario(
            command.command_id, SimulatorScenario(mode=SubmitMode.TIMEOUT, timeout_landed=True)
        )
        result = engine.submit(command)
        # evidence found on the first reconcile => adopt broker truth, never
        # resend (OD-10): order landed, so the command is FILLED, not retried
        assert result.status is ResultStatus.FILLED
        assert result.sl_applied is True
        assert result.filled_volume == command.volume
        assert journal.get_command(command.command_id).state is CommandState.FILLED
        assert len(executor.submit_calls) == 1

    def test_reconcile_before_resend(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, _, executor = env
        command = engine.create_command(make_plan())
        executor.set_scenario(command.command_id, SimulatorScenario(mode=SubmitMode.TIMEOUT))
        engine.submit(command)
        calls = len(executor.submit_calls)
        blocked = engine.submit(command)  # UNKNOWN -> refuse, never resend
        assert blocked.status is ResultStatus.UNKNOWN
        assert len(executor.submit_calls) == calls

    def test_audit_rows_never_move_projection_prematurely(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        """EXECUTOR_RESULT / RECONCILE_AFTER_TIMEOUT are audit-only: each row
        carries the pre-transition state and never advances the projection."""
        engine, journal, executor = env
        command = engine.create_command(make_plan())
        executor.set_scenario(command.command_id, SimulatorScenario(mode=SubmitMode.TIMEOUT))
        engine.submit(command)
        assert journal.get_command(command.command_id).state is CommandState.UNKNOWN
        rows = journal.events(command.command_id)
        assert all(event.state is not None for event in rows)
        executor_rows = [event for event in rows if event.event_type == "EXECUTOR_RESULT"]
        assert executor_rows  # audit trail exists
        assert all(event.state is CommandState.SUBMITTED for event in executor_rows)

    def test_submitted_state_never_resends(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, executor = env
        command = engine.create_command(make_plan())
        journal.record(command, "SUBMIT", CommandState.SUBMITTED)
        assert engine.pending_reconciliation()
        result = engine.submit(command)
        assert result.status is ResultStatus.UNKNOWN
        assert len(executor.submit_calls) == 0


class TestReconciliationGate:
    def test_reconcile_requires_unknown(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, _, _ = env
        command = engine.create_command(make_plan())
        engine.submit(command)  # FILLED, not UNKNOWN
        with pytest.raises(ExecutionStateError):
            engine.reconcile(command)

    def test_reconcile_on_unknown_adopts_broker_truth(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, executor = env
        rec = SimBrokerReconciliation(executor)
        stalled = ExecutionEngine(
            journal,
            executor,
            rec,
            config=ExecutionConfig(retry=RetryPolicy(submit_retries=0)),
        )
        command = stalled.create_command(make_plan())
        executor.set_scenario(
            command.command_id, SimulatorScenario(mode=SubmitMode.TIMEOUT, timeout_landed=True)
        )
        result = stalled.submit(command)
        assert result.status is ResultStatus.UNKNOWN  # budget 0 => UNKNOWN immediately
        assert journal.get_command(command.command_id).state is CommandState.UNKNOWN
        reconciled = stalled.reconcile(command)  # broker truth: order landed -> FILLED
        assert reconciled.status is ResultStatus.FILLED
        assert reconciled.sl_applied is True
        assert reconciled.filled_volume == command.volume
        assert journal.get_command(command.command_id).state is CommandState.FILLED
        assert stalled.pending_reconciliation() == []

    def test_reconcile_releases_fail_closed_gate(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        _, journal, executor, rec = engine_with_reconciliation(env)
        engine = ExecutionEngine(journal, executor, rec)
        first = engine.create_command(make_plan())
        executor.set_scenario(first.command_id, SimulatorScenario(mode=SubmitMode.AMBIGUOUS))
        engine.submit(first)
        with pytest.raises(ExecutionError) as exc:
            engine.create_command(make_plan())
        assert exc.value.error_code == ErrorCode.RECONCILIATION_PENDING.value
        rec.set_outcome(ReconciliationOutcome(discovered_state=CommandState.REJECTED, evidence={}))
        engine.reconcile(first)
        second = engine.create_command(make_plan())  # gate released
        assert second.command_id != first.command_id

    def test_reconcile_not_journaled_raises(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, _, _ = env
        with pytest.raises(ExecutionError) as exc:
            engine.reconcile(make_command())
        assert exc.value.error_code == ErrorCode.INVALID_COMMAND.value


class TestSlProtection:
    def test_attach_failure_triggers_emergency_close(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, executor = env
        executor.set_sl_attach_fail(True)
        command = engine.create_command(make_plan())
        result = engine.submit(command)
        assert result.status is ResultStatus.CLOSED
        assert len(executor.attach_calls) == 3  # initial + 2 retries (OD-5 budget)
        assert len(executor.close_calls) == 1  # emergency close (OD-6)
        assert journal.get_command(command.command_id).state is CommandState.CLOSED
        event_types = [e.event_type for e in journal.events(command.command_id)]
        assert "SL_ATTACH_FAILED" in event_types
        assert "EMERGENCY_CLOSE_REQUESTED" in event_types

    def test_emergency_close_failure_goes_unknown(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, executor = env
        executor.set_sl_attach_fail(True)
        executor.set_close_fail(True)
        command = engine.create_command(make_plan())
        result = engine.submit(command)
        assert result.status is ResultStatus.UNKNOWN
        assert result.error_code == ErrorCode.EMERGENCY_CLOSE_FAILED.value
        assert journal.get_command(command.command_id).state is CommandState.UNKNOWN
        assert len(executor.attach_calls) == 3
        assert len(executor.close_calls) == 1
        assert engine.pending_reconciliation()


class TestClose:
    def test_close_happy_path(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, journal, executor = env
        command = engine.create_command(make_plan())
        engine.submit(command)
        position_id = executor.get_position(command).position_id
        result = engine.close(command, position_id, reason=ExitReason.ABC_PROFIT_CLOSE)
        assert result.status is ResultStatus.CLOSED
        assert journal.get_command(command.command_id).state is CommandState.CLOSED
        assert len(executor.close_calls) == 1
        closed = [e for e in journal.events(command.command_id) if e.event_type == "CLOSED"]
        assert closed[-1].payload["reason"] == ExitReason.ABC_PROFIT_CLOSE.value

    def test_close_is_idempotent(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, _, executor = env
        command = engine.create_command(make_plan())
        engine.submit(command)
        position_id = executor.get_position(command).position_id
        first = engine.close(command, position_id)
        second = engine.close(command, position_id)
        assert second == first
        assert len(executor.close_calls) == 1

    def test_close_retry_budget_then_reconcile(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        _, journal, executor, rec = engine_with_reconciliation(env)
        engine = ExecutionEngine(journal, executor, rec)
        command = engine.create_command(make_plan())
        engine.submit(command)
        executor.set_close_fail(True)
        position_id = executor.get_position(command).position_id
        result = engine.close(command, position_id)
        assert result.status is ResultStatus.UNKNOWN
        assert journal.get_command(command.command_id).state is CommandState.UNKNOWN
        assert len(executor.close_calls) == 3  # initial + 2 retries (OD-4 budget)
        rec.set_outcome(ReconciliationOutcome(discovered_state=CommandState.CLOSED, evidence={}))
        reconciled = engine.reconcile(command)
        assert reconciled.status is ResultStatus.CLOSED
        assert journal.get_command(command.command_id).state is CommandState.CLOSED

    def test_sequential_trade_releases_slot_after_close(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        """Terminal CLOSED releases the active-trade slot for the next round."""
        engine, journal, executor = env
        first = engine.create_command(make_plan())
        engine.submit(first)
        position_id = executor.get_position(first).position_id
        engine.close(first, position_id, reason=ExitReason.ABC_PROFIT_CLOSE)
        assert journal.get_command(first.command_id).state is CommandState.CLOSED
        assert engine.pending_reconciliation() == []
        second = engine.create_command(make_plan())
        assert second.command_id != first.command_id
        assert journal.get_command(second.command_id).state is CommandState.CREATED

    def test_close_from_unknown_requires_reconciliation_first(
        self, env: tuple[ExecutionEngine, ExecutionJournal, SimulatedExecutor]
    ) -> None:
        engine, _, executor = env
        command = engine.create_command(make_plan())
        executor.set_scenario(command.command_id, SimulatorScenario(mode=SubmitMode.AMBIGUOUS))
        engine.submit(command)
        with pytest.raises(ExecutionError) as exc:
            engine.close(command, "POS-999999")
        assert exc.value.error_code == ErrorCode.RECONCILIATION_PENDING.value


class TestRecovery:
    def test_created_defaults_to_submit_safe(self, tmp_path: object) -> None:
        from tests.execution.factories import build_engine

        db_path = str(tmp_path) + "/recover.db"  # type: ignore[operator]
        engine_a, journal_a, executor, _ = build_engine(db_path)
        command = engine_a.create_command(make_plan())
        journal_a.close()
        engine_b, journal_b, _, _ = build_engine(db_path)
        items = engine_b.recover()
        assert items[0].command_id == command.command_id
        assert items[0].action == "SUBMIT_SAFE"  # executor was never called
        result = engine_b.submit(command)
        assert result.status is ResultStatus.FILLED
        journal_b.close()

    def test_submitted_requires_reconciliation_first(self, tmp_path: object) -> None:
        from tests.execution.factories import build_engine

        db_path = str(tmp_path) + "/recover2.db"  # type: ignore[operator]
        engine_a, journal_a, _, _ = build_engine(db_path)
        live = engine_a.create_command(make_plan())
        journal_a.record(live, "SUBMIT", CommandState.SUBMITTED)
        journal_a.close()
        engine_b, journal_b, executor_b, _ = build_engine(db_path)
        actions = {item.command_id: item.action for item in engine_b.recover()}
        assert actions[live.command_id] == "RECONCILE"
        assert engine_b.submit(live).status is ResultStatus.UNKNOWN  # never resend
        assert len(executor_b.submit_calls) == 0
        journal_b.close()

    def test_unknown_requires_reconciliation_first(self, tmp_path: object) -> None:
        from tests.execution.factories import build_engine

        db_path = str(tmp_path) + "/recover4.db"  # type: ignore[operator]
        engine_a, journal_a, executor, _ = build_engine(db_path)
        stuck = engine_a.create_command(make_plan())
        executor.set_scenario(stuck.command_id, SimulatorScenario(mode=SubmitMode.TIMEOUT))
        engine_a.submit(stuck)  # UNKNOWN after retry budget
        journal_a.close()
        engine_b, journal_b, executor_b, _ = build_engine(db_path)
        actions = {item.command_id: item.action for item in engine_b.recover()}
        assert actions[stuck.command_id] == "RECONCILE"
        assert engine_b.submit(stuck).status is ResultStatus.UNKNOWN
        assert len(executor_b.submit_calls) == 0
        journal_b.close()

    def test_events_survive_restart(self, tmp_path: object) -> None:
        from tests.execution.factories import build_engine

        db_path = str(tmp_path) + "/recover3.db"  # type: ignore[operator]
        engine_a, journal_a, _, _ = build_engine(db_path)
        command = engine_a.create_command(make_plan())
        engine_a.submit(command)
        expected = [e.event_type for e in journal_a.events(command.command_id)]
        count = journal_a.event_count()
        journal_a.close()
        _, journal_b, _, _ = build_engine(db_path)
        assert journal_b.event_count() == count
        assert [e.event_type for e in journal_b.events(command.command_id)] == expected
        journal_b.close()
