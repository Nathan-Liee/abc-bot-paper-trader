"""Deterministic simulated executor for testing only — NO MT5, NO broker.

Driven entirely by configuration (no randomness): the same input
producer + same scenario always yields the same results, so every
required scenario is reproducible in tests (task §10):

1. full fill           7. SL attach failure
2. partial fill        8. close failure
3. rejection           9. successful close
4. timeout            10. duplicate command (broker-side rejection)
5. ambiguous response 11. expired command
6. requote/slippage   12. restart/recovery (query() sees broker book)

The simulator keeps an in-memory broker book (orders + positions) and
answers queries from it, which is what makes restart/recovery and
"reconcile before resend" testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from execution.models import (
    CommandState,
    Direction,
    ExecutionCommand,
    ExecutionResult,
    PositionSnapshot,
    now_iso,
)
from execution.reconciliation import ReconciliationOutcome
from execution.retry import ErrorCode
from execution.state_machine import RECONCILABLE_STATES
from execution.validation import is_expired


class SubmitMode(StrEnum):
    """Per-command behavior override for the simulated broker."""

    FULL_FILL = "FULL_FILL"
    PARTIAL_FILL = "PARTIAL_FILL"
    REJECT = "REJECT"
    TIMEOUT = "TIMEOUT"
    AMBIGUOUS = "AMBIGUOUS"
    REQUOTE = "REQUOTE"
    EXPIRED = "EXPIRED"
    STALE_FEED = "STALE_FEED"
    POSITION_EXISTS = "POSITION_EXISTS"


@dataclass(frozen=True)
class SimulatorScenario:
    """Deterministic scenario knobs."""

    mode: SubmitMode = SubmitMode.FULL_FILL
    fill_ratio: float = 0.6  # used by PARTIAL_FILL (0.10 -> 0.06)
    slippage_points: float = 0.0  # fill price shift in symbol points
    entry_price: float = 4400.0  # ask for BUY / bid for SELL at submit time
    retcode: int = 0
    rejected_reason: str | None = None
    timeout_landed: bool = False  # TIMEOUT: order actually exists at broker


@dataclass
class _SimulatedOrder:
    order_id: str
    command_id: str
    symbol: str
    direction: str
    requested_volume: float
    filled_volume: float
    fill_price: float
    sl: float | None
    state: str  # PLACED | FILLED | PARTIAL | CANCELED | REJECTED


@dataclass
class _SimulatedPosition:
    position_id: str
    command_id: str
    symbol: str
    direction: str
    volume: float
    open_price: float
    sl: float | None
    open_ts: str
    closed: bool = False


class SimulatedExecutor:
    """Deterministic broker stand-in. Never touches MT5 or the network."""

    def __init__(
        self,
        *,
        default: SimulatorScenario | None = None,
        sl_attach_fail: bool = False,
        close_fail: bool = False,
    ) -> None:
        self._default = default or SimulatorScenario()
        self._scenarios: dict[str, SimulatorScenario] = {}
        self._sl_attach_fail = sl_attach_fail
        self._close_fail = close_fail
        self._seq = 0
        self._orders: dict[str, _SimulatedOrder] = {}
        self._positions: dict[str, _SimulatedPosition] = {}
        self._position_by_command: dict[str, str] = {}

        # test observability
        self.submit_calls: list[ExecutionCommand] = []
        self.attach_calls: list[tuple[ExecutionCommand, str, float]] = []
        self.close_calls: list[tuple[ExecutionCommand, str]] = []
        self.query_calls: list[ExecutionCommand] = []

    # -- scenario configuration (deterministic) --------------------------

    def set_scenario(self, command_id: str, scenario: SimulatorScenario) -> None:
        self._scenarios[command_id] = scenario

    def set_sl_attach_fail(self, flag: bool) -> None:
        self._sl_attach_fail = flag

    def set_close_fail(self, flag: bool) -> None:
        self._close_fail = flag

    def scenario(self, command: ExecutionCommand) -> SimulatorScenario:
        return self._scenarios.get(command.command_id, self._default)

    # -- executor contract ------------------------------------------------

    def submit(self, command: ExecutionCommand) -> ExecutionResult:
        self.submit_calls.append(command)
        self._seq += 1
        scenario = self.scenario(command)
        ts = now_iso()

        # broker-side duplicate detection (defensive; engine dedups first)
        if command.command_id in self._orders:
            return ExecutionResult.rejected(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
                error_code=ErrorCode.DUPLICATE_COMMAND.value,
                error_message="broker already holds this command_id",
                broker_request_id=self._orders[command.command_id].order_id,
            )

        # broker-side expiry refusal (OD-7 enforcement at both layers)
        if command.expires_at and self._is_past(command.expires_at):
            return ExecutionResult.expired(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
                error_message="broker refused expired command",
            )

        if scenario.mode is SubmitMode.REJECT:
            return ExecutionResult.rejected(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
                error_code=ErrorCode.BROKER_REJECT.value,
                error_message=scenario.rejected_reason or "broker rejected request",
                broker_retcode=scenario.retcode or 10016,
            )
        if scenario.mode is SubmitMode.REQUOTE:
            return ExecutionResult.rejected(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
                error_code=ErrorCode.REQUOTE_SLIPPAGE.value,
                error_message="requote: price moved beyond tolerance",
                broker_retcode=scenario.retcode or 10022,
            )
        if scenario.mode is SubmitMode.STALE_FEED:
            return ExecutionResult.rejected(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
                error_code=ErrorCode.STALE_FEED.value,
                error_message="market feed is stale",
            )
        if scenario.mode is SubmitMode.POSITION_EXISTS:
            return ExecutionResult.rejected(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
                error_code=ErrorCode.POSITION_EXISTS.value,
                error_message="position already exists for this account",
            )
        if scenario.mode is SubmitMode.EXPIRED:
            return ExecutionResult.expired(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
                error_message="scenario: expired",
            )
        if scenario.mode is SubmitMode.TIMEOUT:
            if scenario.timeout_landed:
                order = self._place_order(command, state="PLACED")
                self._fill_order(order, command, scenario)
            # else: the request never reached the broker -> no order,
            # no evidence (reconciliation finds nothing -> SAFE retry)
            return ExecutionResult.unknown(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
                error_code=ErrorCode.NETWORK_TIMEOUT.value,
                error_message="request timed out; outcome unknown",
            )
        if scenario.mode is SubmitMode.AMBIGUOUS:
            self._place_order(command, state="PLACED")
            return ExecutionResult.unknown(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
                error_code=ErrorCode.AMBIGUOUS_RESPONSE.value,
                error_message="accepted but no deal evidence; outcome ambiguous",
            )

        # FULL_FILL / PARTIAL_FILL
        order = self._place_order(command, state="PLACED")
        partial = scenario.mode is SubmitMode.PARTIAL_FILL
        if partial:
            filled_volume = round(command.volume * scenario.fill_ratio, 2)
            order.state = "PARTIAL"
        else:
            filled_volume = command.volume
        self._fill_order(order, command, scenario, filled_volume=filled_volume)

        if partial:
            # remained volume is canceled at the broker (OD-1)
            order.state = "CANCELED"
            return ExecutionResult.partial(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
                filled_volume=filled_volume,
                fill_price=order.fill_price,
                broker_request_id=order.order_id,
                sl_applied=order.sl is not None,
            )

        return ExecutionResult.filled(
            command_id=command.command_id,
            trade_id=command.trade_id,
            timestamp=ts,
            broker_request_id=order.order_id,
            filled_volume=command.volume,
            fill_price=order.fill_price,
            sl_applied=order.sl is not None,
        )

    def get_position(self, command: ExecutionCommand) -> PositionSnapshot | None:
        position_id = self._position_by_command.get(command.command_id)
        if position_id is None:
            return None
        position = self._positions[position_id]
        return PositionSnapshot(
            position_id=position.position_id,
            symbol=position.symbol,
            direction=position.direction,
            volume=position.volume,
            open_price=position.open_price,
            sl=position.sl,
            ts=now_iso(),
        )

    def attach_sl(self, command: ExecutionCommand, position_id: str, sl: float) -> ExecutionResult:
        self.attach_calls.append((command, position_id, sl))
        position = self._positions.get(position_id)
        if position is None or position.closed:
            return ExecutionResult.failed(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=now_iso(),
                error_code=ErrorCode.SL_ATTACH_FAILED.value,
                error_message="position unavailable for SL attach",
            )
        if self._sl_attach_fail:
            return ExecutionResult.failed(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=now_iso(),
                error_code=ErrorCode.SL_ATTACH_FAILED.value,
                error_message="simulated SL attach failure",
            )
        position.sl = sl
        order = self._orders.get(command.command_id)
        if order is not None:
            order.sl = sl
        return ExecutionResult.filled(
            command_id=command.command_id,
            trade_id=command.trade_id,
            timestamp=now_iso(),
            broker_request_id=position.position_id,
            filled_volume=position.volume,
            fill_price=position.open_price,
            sl_applied=True,
        )

    def close_position(self, command: ExecutionCommand, position_id: str) -> ExecutionResult:
        self.close_calls.append((command, position_id))
        position = self._positions.get(position_id)
        if position is None or position.closed:
            return ExecutionResult.failed(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=now_iso(),
                error_code=ErrorCode.CLOSE_FAILED.value,
                error_message="position already closed or missing",
            )
        if self._close_fail:
            return ExecutionResult.failed(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=now_iso(),
                error_code=ErrorCode.CLOSE_FAILED.value,
                error_message="simulated close failure",
            )
        position.closed = True
        return ExecutionResult.closed(
            command_id=command.command_id,
            trade_id=command.trade_id,
            timestamp=now_iso(),
            broker_request_id=position.position_id,
        )

    def query(self, command: ExecutionCommand) -> ReconciliationOutcome:
        """Broker-truth read used by the reconciliation boundary."""
        self.query_calls.append(command)
        order = self._orders.get(command.command_id)
        if order is None:
            return ReconciliationOutcome(
                discovered_state=None, evidence={"found": False, "command_id": command.command_id}
            )
        position = self._positions.get(self._position_by_command.get(command.command_id, ""))
        evidence = {
            "found": True,
            "broker_order_id": order.order_id,
            "order_state": order.state,
            "filled_volume": order.filled_volume,
            "fill_price": order.fill_price,
        }
        if position is not None:
            evidence["broker_position_id"] = position.position_id
            evidence["position_volume"] = position.volume
            evidence["position_sl"] = position.sl
            evidence["position_closed"] = position.closed
        scenario = self.scenario(command)
        if scenario.mode is SubmitMode.AMBIGUOUS:
            return ReconciliationOutcome(discovered_state=None, ambiguous=True, evidence=evidence)
        state = self._order_to_command_state(order, position)
        return ReconciliationOutcome(discovered_state=state, evidence=evidence)

    # -- internals ----------------------------------------------------------

    def _place_order(self, command: ExecutionCommand, *, state: str) -> _SimulatedOrder:
        order = _SimulatedOrder(
            order_id=f"ORD-{self._seq:06d}",
            command_id=command.command_id,
            symbol=command.symbol,
            direction=command.direction,
            requested_volume=command.volume,
            filled_volume=0.0,
            fill_price=0.0,
            sl=None,
            state=state,
        )
        self._orders[command.command_id] = order
        return order

    def _fill_order(
        self,
        order: _SimulatedOrder,
        command: ExecutionCommand,
        scenario: SimulatorScenario,
        *,
        filled_volume: float | None = None,
    ) -> None:
        slippage = scenario.slippage_points * 0.01
        base = scenario.entry_price
        if command.direction == Direction.BUY.value:
            fill_price = base + slippage
        else:
            fill_price = base - slippage
        fill_price = round(fill_price, 5)
        volume = filled_volume if filled_volume is not None else command.volume
        order.filled_volume = volume
        order.fill_price = fill_price
        order.state = "FILLED"
        if not self._sl_attach_fail:
            order.sl = command.sl
        self._seq += 1
        position = _SimulatedPosition(
            position_id=f"POS-{self._seq:06d}",
            command_id=command.command_id,
            symbol=command.symbol,
            direction=command.direction,
            volume=volume,
            open_price=fill_price,
            sl=order.sl,
            open_ts=now_iso(),
        )
        self._positions[position.position_id] = position
        self._position_by_command[command.command_id] = position.position_id

    def _order_to_command_state(
        self, order: _SimulatedOrder, position: _SimulatedPosition | None
    ) -> CommandState:
        if position is not None and position.closed:
            return CommandState.CLOSED
        if order.state == "FILLED":
            return CommandState.FILLED
        mapping = {
            "PLACED": CommandState.SUBMITTED,
            "PARTIAL": CommandState.PARTIALLY_FILLED,
            "CANCELED": CommandState.REJECTED,
            "REJECTED": CommandState.REJECTED,
        }
        state = mapping.get(order.state, CommandState.UNKNOWN)
        return state if state in RECONCILABLE_STATES else CommandState.UNKNOWN

    def _is_past(self, iso_ts: str) -> bool:
        return is_expired(iso_ts)


__all__ = ["SimulatedExecutor", "SimulatorScenario", "SubmitMode"]
