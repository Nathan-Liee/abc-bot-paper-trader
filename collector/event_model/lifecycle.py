"""Stream-level lifecycle validation for sequences of canonical events.

This validator enforces contract-level ordering only: it routes trade
path events to a per-trade state machine (``TradeLifecycle``) and
rejects sequences that violate the contract. It is not a trading engine
and holds no business state beyond the in-memory lifecycle of each trade
seen in the validated stream.
"""

from __future__ import annotations

from collections.abc import Iterable

from collector.event_model.envelope import EventEnvelope
from shared.contracts.errors import ContractValidationError
from shared.contracts.lifecycle import TRADE_FLOW_EVENTS, TradeLifecycle
from shared.contracts.types import EventType


def validate_sequence(events: Iterable[EventEnvelope]) -> None:
    """Validate a stream of events; raises on the first contract violation.

    * ``ts_monotonic`` must be non-decreasing across the whole stream.
    * Trade-path events must be tied to a trade id and follow the
      per-trade lifecycle defined by the contract.
    * Out-of-band events (TICK_RECEIVED, RECONCILIATION, ERROR, TIMEOUT)
      without a trade id are valid at any point.
    """
    lifecycles: dict[str, TradeLifecycle] = {}
    last_monotonic: int | None = None

    for event in events:
        if last_monotonic is not None and event.ts_monotonic < last_monotonic:
            raise ContractValidationError(
                "ts_monotonic must be non-decreasing within a stream "
                f"(got {event.ts_monotonic} after {last_monotonic})"
            )
        last_monotonic = event.ts_monotonic

        if event.event_type is EventType.TRIGGER_DETECTED and event.correlation_id is None:
            raise ContractValidationError("TRIGGER_DETECTED requires correlation_id")

        trade_id = event.trade_id
        if event.event_type in TRADE_FLOW_EVENTS and trade_id is None:
            raise ContractValidationError(
                f"{event.event_type.value} requires trade_id within a stream"
            )
        if trade_id is None:
            continue

        lifecycle = lifecycles.get(trade_id)
        if lifecycle is None:
            lifecycle = TradeLifecycle(trade_id)
            lifecycles[trade_id] = lifecycle
        lifecycle.apply(event.event_type, event.payload)


__all__ = ["validate_sequence"]
