"""Contract-level lifecycle rules for the canonical event stream.

Source of truth: docs/contracts/canonical-event-contract.md
section 6 (Event Lifecycle) and the validation & correction report
section 5 (Lifecycle). This module encodes ordering and terminality
constraints only; stream-level routing lives in
``collector.event_model.lifecycle``.
"""

from __future__ import annotations

from collections.abc import Mapping

from shared.contracts.errors import ContractValidationError
from shared.contracts.types import EventType

OUT_OF_BAND_EVENTS = frozenset(
    {
        EventType.TICK_RECEIVED,
        EventType.RECONCILIATION,
        EventType.ERROR,
        EventType.TIMEOUT,
    }
)

TRADE_FLOW: tuple[EventType, ...] = (
    EventType.TRIGGER_DETECTED,
    EventType.CONTEXT_BUILT,
    EventType.AI_REQUEST,
    EventType.AI_RESPONSE,
    EventType.RISK_GATE,
    EventType.ORDER_SUBMITTED,
    EventType.ORDER_ACKNOWLEDGED,
    EventType.ORDER_FILLED,
    EventType.POSITION_OPENED,
    EventType.POSITION_UPDATED,
    EventType.NET_PROFIT_POSITIVE,
    EventType.EXIT_SUBMITTED,
    EventType.POSITION_CLOSED,
)

TRADE_FLOW_EVENTS = frozenset(TRADE_FLOW)

TERMINAL_EVENTS = frozenset(
    {
        EventType.POSITION_CLOSED,
        EventType.ERROR,
        EventType.TIMEOUT,
    }
)

NEXT_ALLOWED: dict[EventType, frozenset[EventType]] = {
    EventType.TRIGGER_DETECTED: frozenset({EventType.CONTEXT_BUILT, EventType.RISK_GATE}),
    EventType.CONTEXT_BUILT: frozenset({EventType.AI_REQUEST}),
    EventType.AI_REQUEST: frozenset({EventType.AI_RESPONSE}),
    EventType.AI_RESPONSE: frozenset({EventType.RISK_GATE}),
    EventType.RISK_GATE: frozenset({EventType.ORDER_SUBMITTED}),
    EventType.ORDER_SUBMITTED: frozenset({EventType.ORDER_ACKNOWLEDGED}),
    EventType.ORDER_ACKNOWLEDGED: frozenset({EventType.ORDER_FILLED}),
    EventType.ORDER_FILLED: frozenset({EventType.POSITION_OPENED}),
    EventType.POSITION_OPENED: frozenset(
        {EventType.POSITION_UPDATED, EventType.NET_PROFIT_POSITIVE, EventType.EXIT_SUBMITTED}
    ),
    EventType.POSITION_UPDATED: frozenset(
        {EventType.POSITION_UPDATED, EventType.NET_PROFIT_POSITIVE, EventType.EXIT_SUBMITTED}
    ),
    EventType.NET_PROFIT_POSITIVE: frozenset(
        {EventType.POSITION_UPDATED, EventType.EXIT_SUBMITTED}
    ),
    EventType.EXIT_SUBMITTED: frozenset({EventType.POSITION_CLOSED}),
    EventType.POSITION_CLOSED: frozenset(),
    EventType.ERROR: frozenset(),
    EventType.TIMEOUT: frozenset(),
    EventType.TICK_RECEIVED: frozenset(),
    EventType.RECONCILIATION: frozenset(),
}

_FIRST_TRADE_EVENT_REQUIRED = "the first event of a trade path must be TRIGGER_DETECTED"


def validate_transition(
    previous: EventType,
    next_event: EventType,
    *,
    previous_payload: Mapping[str, object] | None = None,
) -> None:
    """Validate the *previous* -> *next_event* transition.

    Out-of-band events (TICK_RECEIVED, RECONCILIATION, ERROR, TIMEOUT)
    may appear at any point in the stream. Trade-path events must follow
    the ordering defined by NEXT_ALLOWED. A rejected risk gate is a
    terminal condition: no trade-path event may follow it.
    """
    if next_event in OUT_OF_BAND_EVENTS:
        return
    if previous not in TRADE_FLOW_EVENTS:
        raise ContractValidationError(
            f"{previous.value} is not part of the trade flow; {next_event.value} cannot follow it"
        )
    if next_event not in NEXT_ALLOWED[previous]:
        raise ContractValidationError(
            f"Illegal lifecycle transition: {previous.value} -> {next_event.value}"
        )
    if previous is EventType.RISK_GATE:
        payload = previous_payload or {}
        if payload.get("gate_result") == "REJECT":
            raise ContractValidationError(
                "Risk gate rejected the trade; no trade-path event may follow "
                f"(illegal transition RISK_GATE -> {next_event.value})"
            )


class TradeLifecycle:
    """Per-trade lifecycle state machine.

    Not thread-safe and not persistent; holds only in-memory state for a
    single trade identified by *trade_id*.
    """

    def __init__(self, trade_id: str) -> None:
        self._trade_id = trade_id
        self._state: EventType | None = None
        self._last_payload: Mapping[str, object] | None = None
        self._terminal: bool = False
        self._terminal_reason: str | None = None

    @property
    def trade_id(self) -> str:
        return self._trade_id

    @property
    def current_state(self) -> EventType | None:
        return self._state

    @property
    def is_terminal(self) -> bool:
        return self._terminal

    @property
    def terminal_reason(self) -> str | None:
        return self._terminal_reason

    def apply(self, event_type: EventType, payload: Mapping[str, object]) -> None:
        if event_type not in OUT_OF_BAND_EVENTS and self._terminal:
            raise ContractValidationError(
                f"Trade {self._trade_id} is terminal ({self._terminal_reason}); "
                f"cannot apply {event_type.value}"
            )
        if self._state is None:
            if (
                event_type not in OUT_OF_BAND_EVENTS
                and event_type is not EventType.TRIGGER_DETECTED
            ):
                raise ContractValidationError(_FIRST_TRADE_EVENT_REQUIRED)
        elif event_type not in OUT_OF_BAND_EVENTS:
            validate_transition(self._state, event_type, previous_payload=self._last_payload)

        self._apply_special_rules(event_type, payload)
        if event_type not in OUT_OF_BAND_EVENTS or event_type in TERMINAL_EVENTS:
            self._state = event_type
        if event_type in TRADE_FLOW_EVENTS:
            self._last_payload = payload

    def _apply_special_rules(self, event_type: EventType, payload: Mapping[str, object]) -> None:
        if event_type is EventType.RISK_GATE and payload.get("gate_result") == "REJECT":
            self._terminal = True
            self._terminal_reason = "risk gate rejected"
        elif event_type is EventType.RECONCILIATION and self._state in {
            EventType.ORDER_SUBMITTED,
            EventType.ORDER_ACKNOWLEDGED,
        }:
            self._terminal = True
            self._terminal_reason = (
                "reconciliation found an order failure; no position may be opened"
            )
        elif event_type in TERMINAL_EVENTS:
            self._terminal = True
            self._terminal_reason = f"{event_type.value} reached"


__all__ = [
    "NEXT_ALLOWED",
    "OUT_OF_BAND_EVENTS",
    "TERMINAL_EVENTS",
    "TRADE_FLOW",
    "TRADE_FLOW_EVENTS",
    "TradeLifecycle",
    "validate_transition",
]
