"""Deterministic lifecycle state machine (task §7)."""

from __future__ import annotations

import pytest

from execution.errors import ExecutionStateError
from execution.models import TERMINAL_STATES, CommandState
from execution.state_machine import (
    RECONCILABLE_STATES,
    ExecutionEvent,
    ExecutionStateMachine,
    transition,
)


class TestHappyPath:
    def test_full_lifecycle(self) -> None:
        fsm = ExecutionStateMachine()
        assert fsm.apply(ExecutionEvent.VALIDATE_OK) is CommandState.VALIDATED
        assert fsm.apply(ExecutionEvent.SUBMIT) is CommandState.SUBMITTED
        assert fsm.apply(ExecutionEvent.FULL_FILL) is CommandState.FILLED
        assert fsm.apply(ExecutionEvent.SL_ATTACHING) is CommandState.MODIFYING
        assert fsm.apply(ExecutionEvent.SL_ATTACHED) is CommandState.FILLED
        assert fsm.apply(ExecutionEvent.CLOSED) is CommandState.CLOSED
        assert fsm.is_terminal

    def test_partial_fill_then_cancel_then_close(self) -> None:
        fsm = ExecutionStateMachine()
        fsm.apply(ExecutionEvent.VALIDATE_OK)
        fsm.apply(ExecutionEvent.SUBMIT)
        assert fsm.apply(ExecutionEvent.PARTIAL_FILL) is CommandState.PARTIALLY_FILLED
        assert fsm.apply(ExecutionEvent.CLOSED) is CommandState.CLOSED


class TestRejections:
    @pytest.mark.parametrize(
        ("state", "event"),
        [
            (CommandState.CREATED, ExecutionEvent.CLOSED),
            (CommandState.CREATED, ExecutionEvent.SUBMIT),
            (CommandState.VALIDATED, ExecutionEvent.FULL_FILL),
            (CommandState.SUBMITTED, ExecutionEvent.VALIDATE_OK),
            (CommandState.FILLED, ExecutionEvent.SUBMIT),
            (CommandState.MODIFYING, ExecutionEvent.FULL_FILL),
        ],
    )
    def test_illegal_transitions_raise(self, state: CommandState, event: ExecutionEvent) -> None:
        with pytest.raises(ExecutionStateError):
            transition(state, event)

    @pytest.mark.parametrize("terminal", sorted(TERMINAL_STATES))
    def test_terminal_states_reject_every_event(self, terminal: CommandState) -> None:
        for event in ExecutionEvent:
            with pytest.raises(ExecutionStateError):
                transition(terminal, event)

    def test_unknown_rejects_non_reconciled_events(self) -> None:
        for event in ExecutionEvent:
            if event is ExecutionEvent.RECONCILED:
                continue
            with pytest.raises(ExecutionStateError):
                transition(CommandState.UNKNOWN, event)


class TestReconciliation:
    @pytest.mark.parametrize("target", sorted(RECONCILABLE_STATES))
    def test_unknown_resolves_to_any_reconcilable_state(self, target: CommandState) -> None:
        assert transition(CommandState.UNKNOWN, ExecutionEvent.RECONCILED, target=target) is target

    def test_reconciled_requires_target(self) -> None:
        with pytest.raises(ExecutionStateError):
            transition(CommandState.UNKNOWN, ExecutionEvent.RECONCILED)

    def test_reconciled_only_from_unknown(self) -> None:
        with pytest.raises(ExecutionStateError):
            transition(
                CommandState.SUBMITTED, ExecutionEvent.RECONCILED, target=CommandState.FILLED
            )

    def test_reconciled_target_must_be_observable(self) -> None:
        with pytest.raises(ExecutionStateError):
            transition(CommandState.UNKNOWN, ExecutionEvent.RECONCILED, target=CommandState.CREATED)
        with pytest.raises(ExecutionStateError):
            transition(CommandState.UNKNOWN, ExecutionEvent.RECONCILED, target=CommandState.UNKNOWN)


class TestTableIntegrity:
    def test_reconcilable_states_are_explicit(self) -> None:
        expected = {
            CommandState.SUBMITTED,
            CommandState.PARTIALLY_FILLED,
            CommandState.FILLED,
            CommandState.MODIFYING,
            CommandState.CLOSED,
            CommandState.REJECTED,
            CommandState.EXPIRED,
            CommandState.FAILED,
        }
        assert RECONCILABLE_STATES == frozenset(expected)
