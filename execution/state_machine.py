"""Deterministic execution lifecycle state machine (task §7).

``CREATED -> VALIDATED -> SUBMITTED -> PARTIALLY_FILLED -> FILLED ->
MODIFYING -> CLOSED`` with failure states ``REJECTED / FAILED /
EXPIRED / UNKNOWN``. Every non-terminal state may reach UNKNOWN
(timeout / ambiguous response / restart); UNKNOWN is resolved ONLY by
reconciliation (RECONCILED event) adopting broker truth — never by
assumption.
"""

from __future__ import annotations

from enum import StrEnum

from execution.errors import ExecutionStateError
from execution.models import TERMINAL_STATES, CommandState


class ExecutionEvent(StrEnum):
    VALIDATE_OK = "VALIDATE_OK"
    VALIDATE_FAIL = "VALIDATE_FAIL"
    SUBMIT = "SUBMIT"
    PARTIAL_FILL = "PARTIAL_FILL"
    FULL_FILL = "FULL_FILL"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    EXPIRE = "EXPIRE"
    SL_ATTACHING = "SL_ATTACHING"
    SL_ATTACHED = "SL_ATTACHED"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"
    RECONCILED = "RECONCILED"


# States reconciliation may legitimately discover at the broker.
RECONCILABLE_STATES: frozenset[CommandState] = frozenset(
    {
        CommandState.SUBMITTED,
        CommandState.PARTIALLY_FILLED,
        CommandState.FILLED,
        CommandState.MODIFYING,
        CommandState.CLOSED,
        CommandState.REJECTED,
        CommandState.EXPIRED,
        CommandState.FAILED,
    }
)

_TRANSITIONS: dict[CommandState, dict[ExecutionEvent, CommandState]] = {
    CommandState.CREATED: {
        ExecutionEvent.VALIDATE_OK: CommandState.VALIDATED,
        ExecutionEvent.VALIDATE_FAIL: CommandState.FAILED,
        ExecutionEvent.EXPIRE: CommandState.EXPIRED,
    },
    CommandState.VALIDATED: {
        ExecutionEvent.SUBMIT: CommandState.SUBMITTED,
        ExecutionEvent.VALIDATE_FAIL: CommandState.FAILED,
        ExecutionEvent.EXPIRE: CommandState.EXPIRED,
    },
    CommandState.SUBMITTED: {
        ExecutionEvent.PARTIAL_FILL: CommandState.PARTIALLY_FILLED,
        ExecutionEvent.FULL_FILL: CommandState.FILLED,
        ExecutionEvent.REJECTED: CommandState.REJECTED,
        ExecutionEvent.FAILED: CommandState.FAILED,
        ExecutionEvent.EXPIRE: CommandState.EXPIRED,
        ExecutionEvent.UNKNOWN: CommandState.UNKNOWN,
    },
    CommandState.PARTIALLY_FILLED: {
        ExecutionEvent.FULL_FILL: CommandState.FILLED,
        ExecutionEvent.CLOSED: CommandState.CLOSED,
        ExecutionEvent.UNKNOWN: CommandState.UNKNOWN,
        ExecutionEvent.FAILED: CommandState.FAILED,
    },
    CommandState.FILLED: {
        ExecutionEvent.SL_ATTACHING: CommandState.MODIFYING,
        ExecutionEvent.CLOSED: CommandState.CLOSED,
        ExecutionEvent.UNKNOWN: CommandState.UNKNOWN,
        ExecutionEvent.FAILED: CommandState.FAILED,
    },
    CommandState.MODIFYING: {
        ExecutionEvent.SL_ATTACHED: CommandState.FILLED,
        ExecutionEvent.CLOSED: CommandState.CLOSED,
        ExecutionEvent.UNKNOWN: CommandState.UNKNOWN,
        ExecutionEvent.FAILED: CommandState.FAILED,
    },
    CommandState.UNKNOWN: {
        # RECONCILED is special-cased: transition() takes a target.
    },
}

TERMINAL: frozenset[CommandState] = TERMINAL_STATES


def _event_pairs() -> dict[tuple[CommandState, ExecutionEvent], CommandState]:
    table: dict[tuple[CommandState, ExecutionEvent], CommandState] = {}
    for state, events in _TRANSITIONS.items():
        for event, target in events.items():
            table[(state, event)] = target
    for target in RECONCILABLE_STATES:
        table[(CommandState.UNKNOWN, ExecutionEvent.RECONCILED)] = target
    return table


TRANSITION_TABLE: dict[tuple[CommandState, ExecutionEvent], CommandState] = _event_pairs()


def transition(
    current: CommandState,
    event: ExecutionEvent,
    *,
    target: CommandState | None = None,
) -> CommandState:
    """Resolve the next state or raise ``ExecutionStateError``.

    ``target`` is required only for ``RECONCILED`` (the discovered
    broker state) and must be reconciliation-observable.
    """
    if event is ExecutionEvent.RECONCILED:
        if target is None:
            raise ExecutionStateError("RECONCILED requires a discovered target state")
        if current is not CommandState.UNKNOWN:
            raise ExecutionStateError(
                f"reconciliation is only valid from UNKNOWN, not {current.value}"
            )
        if target not in RECONCILABLE_STATES:
            raise ExecutionStateError(f"target {target.value} is not reconciliation-observable")
        return target

    resolved = TRANSITION_TABLE.get((current, event))
    if resolved is None:
        raise ExecutionStateError(f"illegal transition {current.value} --{event.value}--> ?")
    return resolved


class ExecutionStateMachine:
    """Thin state holder; persists nothing (durability lives in journal)."""

    def __init__(self, initial: CommandState = CommandState.CREATED) -> None:
        self._state = initial

    @property
    def state(self) -> CommandState:
        return self._state

    @property
    def is_terminal(self) -> bool:
        return self._state in TERMINAL

    def apply(self, event: ExecutionEvent, *, target: CommandState | None = None) -> CommandState:
        self._state = transition(self._state, event, target=target)
        return self._state


__all__ = [
    "ExecutionEvent",
    "ExecutionStateMachine",
    "RECONCILABLE_STATES",
    "TERMINAL",
    "TRANSITION_TABLE",
    "transition",
]
