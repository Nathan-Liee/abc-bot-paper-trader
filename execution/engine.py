"""Execution Engine — Risk-approved TradePlan -> validated command ->
durable lifecycle -> deterministic SimulatedExecutor -> reconciliation.

Authority (locked): the engine translates a System-approved TradePlan
into an ExecutionCommand and manages its lifecycle. It NEVER computes
direction, lot, risk, SL, exposure, or margin; it NEVER submits broker
requests directly (executor boundary only); it NEVER attaches TP.

Design decisions implemented (owner-approved OD-1..OD-10):

* OD-1  partial fill -> CANCEL_REMAINING, no second order, no re-decision
* OD-2  entry type MARKET only; stale plans never become valid commands
* OD-3  ABC exit represented as a close reason; no fixed TP anywhere
* OD-4  close retry budget 2; exhaustion -> UNKNOWN -> reconciliation
* OD-5  SL attach retry budget 2; exhaustion -> SL_ATTACH_FAILED ->
        EMERGENCY_CLOSE
* OD-6  emergency close failure -> UNKNOWN -> reconciliation required;
        new entries fail-closed while reconciliation is pending
* OD-7  TradePlan TTL 5 s default, configurable; now > expires_at -> EXPIRED
* OD-8  durable local journal (SQLite WAL) — no network channel
* OD-9  lineage: inference_id -> risk_evaluation_id -> trade_id ->
        command_id (== idempotency key)
* OD-10 requote/slippage -> reject current command, no blind retry,
        no TradePlan mutation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from execution.errors import DuplicateCommandError, ExecutionError, ExecutionStateError
from execution.executor import Executor
from execution.journal import ExecutionJournal
from execution.models import (
    TERMINAL_STATES,
    CommandState,
    EntryType,
    ExecutionCommand,
    ExecutionResult,
    ExitReason,
    PositionSnapshot,
    ResultStatus,
    TradePlan,
    new_command_id,
    now_iso,
)
from execution.reconciliation import (
    ReconciliationBoundary,
    ReconciliationOutcome,
)
from execution.retry import ErrorCode, RetryClass, RetryPolicy, classify_error
from execution.state_machine import ExecutionEvent, transition
from execution.validation import (
    is_expired_command,
    is_expired_plan,
    validate_command,
    validate_plan,
)

_RECONCILE_ACTIONS = frozenset({CommandState.SUBMITTED, CommandState.UNKNOWN})


@dataclass(frozen=True)
class ExecutionConfig:
    """Execution layer configuration. Nothing here is a risk decision."""

    trade_plan_ttl_seconds: float = 5.0  # OD-7 provisional default (configurable)
    retry: RetryPolicy = field(default_factory=RetryPolicy)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.trade_plan_ttl_seconds, (int, float)) or (
            isinstance(self.trade_plan_ttl_seconds, bool)
        ):
            errors.append("execution_config.trade_plan_ttl_seconds:invalid")
        elif self.trade_plan_ttl_seconds <= 0:
            errors.append("execution_config.trade_plan_ttl_seconds:non_positive")
        errors.extend(self.retry.validate())
        return errors


@dataclass(frozen=True)
class RecoveryItem:
    """Restart-recovery finding for one journaled command."""

    command_id: str
    trade_id: str
    state: CommandState
    action: str  # "RECONCILE" | "SUBMIT_SAFE" | "NONE"


class ExecutionEngine:
    """Orchestrates plan ingestion, submission, SL protection, and close."""

    def __init__(
        self,
        journal: ExecutionJournal,
        executor: Executor,
        reconciliation: ReconciliationBoundary,
        config: ExecutionConfig | None = None,
    ) -> None:
        self._journal = journal
        self._executor = executor
        self._reconciliation = reconciliation
        self._config = config or ExecutionConfig()

    @property
    def journal(self) -> ExecutionJournal:
        return self._journal

    @property
    def config(self) -> ExecutionConfig:
        return self._config

    # ------------------------------------------------------------------
    # plan -> command
    # ------------------------------------------------------------------

    def create_command(self, plan: TradePlan) -> ExecutionCommand:
        """Validate the System TradePlan and persist a new command.

        Raises ``ExecutionError`` on an invalid or expired plan; a plan
        that is stale can never produce a valid command (OD-2/OD-7).
        """
        failures = validate_plan(plan)
        if failures:
            raise ExecutionError(
                ErrorCode.INVALID_COMMAND, f"TradePlan invalid: {', '.join(failures)}"
            )
        if is_expired_plan(plan):
            raise ExecutionError(ErrorCode.EXPIRED, "TradePlan expired; no command created")
        if self._pending_reconciliation_ids():
            raise ExecutionError(
                ErrorCode.RECONCILIATION_PENDING,
                "fail-closed: new entries blocked until reconciliation completes",
            )

        command = ExecutionCommand(
            command_id=new_command_id(),
            trade_id=plan.trade_id,
            symbol=plan.symbol,
            direction=plan.direction,
            volume=plan.lot,
            entry_type=EntryType.MARKET,
            sl=plan.sl,
            created_at=now_iso(),
            expires_at=plan.expires_at,
        )
        try:
            self._journal.create_command(command)
        except DuplicateCommandError:
            raise
        self._journal.record(command, "COMMAND_CREATED", CommandState.CREATED)
        return command

    # ------------------------------------------------------------------
    # submit
    # ------------------------------------------------------------------

    def submit(self, command: ExecutionCommand) -> ExecutionResult:
        """Validate, journal write-ahead, and execute through the executor.

        Idempotent: a command with a stored result returns that result
        (never a second submission, OD-9). A command already in flight
        (SUBMITTED/UNKNOWN) returns UNKNOWN — reconciliation first.
        """
        stored = self._journal.get_command(command.command_id)
        if stored is None:
            raise ExecutionError(
                ErrorCode.INVALID_COMMAND, "command not journaled; create_command first"
            )
        if stored.result is not None:
            return stored.result  # idempotent replay
        if stored.state in TERMINAL_STATES:
            raise ExecutionError(
                ErrorCode.DUPLICATE_COMMAND,
                f"command already terminal ({stored.state.value}) without stored result",
            )
        if stored.state in _RECONCILE_ACTIONS:
            return self._unknown_result(
                command,
                ErrorCode.AMBIGUOUS_RESPONSE,
                f"command is {stored.state.value}; reconciliation required before any action",
            )

        # validation gate (CREATED -> VALIDATED)
        failures = validate_command(command)
        if failures:
            self._record_transition(
                command,
                ExecutionEvent.VALIDATE_FAIL,
                payload={"failures": failures},
            )
            result = ExecutionResult.failed(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=now_iso(),
                error_code=ErrorCode.INVALID_COMMAND.value,
                error_message="; ".join(failures),
            )
            self._store_result(command, result)
            return result

        if stored.state is CommandState.CREATED:
            self._record_transition(command, ExecutionEvent.VALIDATE_OK)

        # expiry gate (VALIDATED -> EXPIRED) — never submitted (OD-7)
        if is_expired_command(command):
            self._record_transition(command, ExecutionEvent.EXPIRE)
            result = ExecutionResult.expired(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=now_iso(),
            )
            self._store_result(command, result)
            return result

        # write-ahead SUBMITTED: crash after this point => recover via
        # reconciliation, never via blind resend
        self._record_transition(command, ExecutionEvent.SUBMIT)

        attempts = 0
        while True:
            result = self._executor.submit(command)
            self._journal.record(
                command,
                "EXECUTOR_RESULT",
                self._current_state(command),
                {"result": result.to_dict(), "attempt": attempts},
            )

            if result.status in (ResultStatus.FILLED, ResultStatus.PARTIALLY_FILLED):
                return self._post_fill(command, result)

            if result.status in (ResultStatus.REJECTED, ResultStatus.FAILED, ResultStatus.EXPIRED):
                event = {
                    ResultStatus.REJECTED: ExecutionEvent.REJECTED,
                    ResultStatus.FAILED: ExecutionEvent.FAILED,
                    ResultStatus.EXPIRED: ExecutionEvent.EXPIRE,
                }[result.status]
                self._record_transition(command, event, payload={"result": result.to_dict()})
                self._store_result(command, result)
                return result

            # UNKNOWN: classify; safe retries only after reconciliation
            # confirms NO broker evidence (never blind resend, OD-10)
            retry_class = classify_error(result.error_code)
            if retry_class is RetryClass.SAFE and attempts < self._config.retry.submit_retries:
                outcome = self._reconciliation.reconcile(command, hint=result)
                self._journal.record(
                    command,
                    "RECONCILE_AFTER_TIMEOUT",
                    self._current_state(command),
                    {"outcome": outcome.evidence},
                )
                if outcome.ambiguous:
                    # broker unreachable: cannot confirm safety -> UNKNOWN
                    self._record_transition(command, ExecutionEvent.UNKNOWN)
                    ambiguous = self._unknown_result(
                        command,
                        ErrorCode.AMBIGUOUS_RESPONSE,
                        "broker unreachable during reconciliation; command state unknown",
                    )
                    self._store_result(command, ambiguous)
                    return ambiguous
                if outcome.discovered_state is None:
                    # no broker evidence: safe to retry the SAME command_id
                    attempts += 1
                    continue
                # broker evidence found: adopt truth, never resend
                self._record_transition(command, ExecutionEvent.UNKNOWN)
                return self._resolve_reconciliation(command, outcome, result)

            self._record_transition(
                command,
                ExecutionEvent.UNKNOWN,
                payload={"retry_class": retry_class.value},
            )
            self._store_result(command, result)
            return result

    # ------------------------------------------------------------------
    # post-fill: SL protection + partial-fill remainder cancel
    # ------------------------------------------------------------------

    def _post_fill(self, command: ExecutionCommand, result: ExecutionResult) -> ExecutionResult:
        if result.status is ResultStatus.PARTIALLY_FILLED:
            self._record_transition(command, ExecutionEvent.PARTIAL_FILL)
            canceled_volume = round(command.volume - result.filled_volume, 8)
            self._journal.record(
                command,
                "CANCEL_REMAINDER",
                CommandState.PARTIALLY_FILLED,
                {
                    "requested_volume": command.volume,
                    "filled_volume": result.filled_volume,
                    "cancelled_volume": canceled_volume,
                    "policy": "CANCEL_REMAINING",
                    "second_order": False,
                },
            )
        else:
            self._record_transition(command, ExecutionEvent.FULL_FILL)
        return self._ensure_sl_protection(command, result)

    def _ensure_sl_protection(
        self, command: ExecutionCommand, result: ExecutionResult
    ) -> ExecutionResult:
        """Verify the System SL is attached; otherwise attach with retry
        budget OD-5, then EMERGENCY_CLOSE on exhaustion (OD-6)."""
        position = self._executor.get_position(command)
        if position is None:
            # no position evidence although broker claimed a fill:
            # treat as ambiguous and require reconciliation
            self._record_transition(command, ExecutionEvent.UNKNOWN)
            unknown = self._unknown_result(
                command,
                ErrorCode.AMBIGUOUS_RESPONSE,
                "fill reported but position not observable",
            )
            self._store_result(command, unknown)
            return unknown

        if position.sl is not None and abs(position.sl - command.sl) < 1e-9:
            self._journal.record(
                command,
                "SL_CONFIRMED",
                CommandState.FILLED,
                {"position_id": position.position_id, "sl": position.sl},
            )
            final = _with_sl_confirmed(result, position)
            self._store_result(command, final)
            return final

        self._record_transition(command, ExecutionEvent.SL_ATTACHING)
        attempts = 0
        attach_result = None
        while attempts <= self._config.retry.sl_attach_retries:
            attach_result = self._executor.attach_sl(command, position.position_id, command.sl)
            self._journal.record(
                command,
                "SL_ATTACH_RESULT",
                CommandState.MODIFYING,
                {"attempt": attempts, "result": attach_result.to_dict()},
            )
            if attach_result.sl_applied:
                self._record_transition(command, ExecutionEvent.SL_ATTACHED)
                final = _with_sl_confirmed(result, position)
                self._store_result(command, final)
                return final
            attempts += 1

        # budget exhausted (OD-5): never leave a position without
        # protective SL
        self._journal.record(
            command,
            "SL_ATTACH_FAILED",
            CommandState.MODIFYING,
            {
                "attempts": attempts,
                "position_id": position.position_id,
                "budget": self._config.retry.sl_attach_retries,
            },
        )
        return self._emergency_close(command, position.position_id)

    def _emergency_close(self, command: ExecutionCommand, position_id: str) -> ExecutionResult:
        self._journal.record(
            command,
            "EMERGENCY_CLOSE_REQUESTED",
            CommandState.MODIFYING,
            {"position_id": position_id, "reason": ExitReason.EMERGENCY_CLOSE.value},
        )
        result = self._executor.close_position(command, position_id)
        self._journal.record(
            command,
            "EMERGENCY_CLOSE_RESULT",
            CommandState.MODIFYING,
            {"result": result.to_dict()},
        )
        if result.status is ResultStatus.CLOSED:
            self._record_transition(
                command, ExecutionEvent.CLOSED, payload={"reason": ExitReason.EMERGENCY_CLOSE.value}
            )
            self._store_result(command, result)
            return result

        self._record_transition(command, ExecutionEvent.UNKNOWN)
        unknown = self._unknown_result(
            command,
            ErrorCode.EMERGENCY_CLOSE_FAILED,
            "emergency close failed; reconciliation required",
        )
        self._store_result(command, unknown)
        return unknown

    # ------------------------------------------------------------------
    # close (ABC exit execution, OD-3/OD-4)
    # ------------------------------------------------------------------

    def close(
        self,
        command: ExecutionCommand,
        position_id: str,
        reason: ExitReason = ExitReason.ABC_PROFIT_CLOSE,
    ) -> ExecutionResult:
        """Execute the System-determined close; bounded retry (OD-4).

        The EXIT CONDITION is System-owned (NET_PROFIT > 0); this method
        only executes an already-decided close with idempotent retries.
        No fixed TP exists in this layer (OD-3).
        """
        stored = self._journal.get_command(command.command_id)
        if stored is None:
            raise ExecutionError(
                ErrorCode.INVALID_COMMAND, "command not journaled; create_command first"
            )
        # idempotent replay ONLY of an already-completed close
        if stored.result is not None and stored.result.status is ResultStatus.CLOSED:
            return stored.result
        if stored.state is CommandState.UNKNOWN:
            raise ExecutionError(
                ErrorCode.RECONCILIATION_PENDING,
                "command state unknown; reconcile before close",
            )

        attempts = 0
        while attempts <= self._config.retry.close_retries:
            result = self._executor.close_position(command, position_id)
            self._journal.record(
                command,
                "CLOSE_RESULT",
                self._current_state(command),
                {"attempt": attempts, "result": result.to_dict(), "reason": reason.value},
            )
            if result.status is ResultStatus.CLOSED:
                self._record_transition(
                    command, ExecutionEvent.CLOSED, payload={"reason": reason.value}
                )
                self._store_result(command, result)
                return result
            attempts += 1

        # budget exhausted (OD-4) -> unknown; reconciliation required
        self._record_transition(command, ExecutionEvent.UNKNOWN, payload={"attempts": attempts})
        unknown = self._unknown_result(
            command,
            ErrorCode.AMBIGUOUS_RESPONSE,
            f"close failed after {attempts} attempts; reconciliation required",
        )
        self._store_result(command, unknown)
        return unknown

    # ------------------------------------------------------------------
    # reconciliation
    # ------------------------------------------------------------------

    def reconcile(self, command: ExecutionCommand) -> ExecutionResult:
        """Resolve an UNKNOWN command against broker truth (task §11).

        Only UNKNOWN commands may be reconciled. On a conclusive outcome
        the lifecycle resumes from the discovered state; on ambiguity the
        command stays UNKNOWN and all new entries remain fail-closed.
        """
        stored = self._journal.get_command(command.command_id)
        if stored is None:
            raise ExecutionError(
                ErrorCode.INVALID_COMMAND, "command not journaled; create_command first"
            )
        if stored.state is not CommandState.UNKNOWN:
            raise ExecutionStateError(f"reconciliation requires UNKNOWN, got {stored.state.value}")

        outcome = self._reconciliation.reconcile(command)
        self._journal.record(
            command,
            "RECONCILIATION_QUERY",
            CommandState.UNKNOWN,
            {"outcome": outcome.evidence, "ambiguous": outcome.ambiguous},
        )
        if outcome.ambiguous or outcome.discovered_state is None:
            self._journal.record(
                command,
                "RECONCILIATION_AMBIGUOUS",
                CommandState.UNKNOWN,
                {"evidence": outcome.evidence},
            )
            fallback = self._unknown_result(
                command,
                ErrorCode.RECONCILIATION_PENDING,
                "reconciliation inconclusive; broker truth unreachable",
            )
            self._store_result(command, fallback)
            return self._journal.get_result(command.command_id) or fallback

        return self._resolve_reconciliation(command, outcome, None)

    def _resolve_reconciliation(
        self,
        command: ExecutionCommand,
        outcome: ReconciliationOutcome,
        hint: ExecutionResult | None,
    ) -> ExecutionResult:
        assert outcome.discovered_state is not None
        self._record_transition(
            command,
            ExecutionEvent.RECONCILED,
            target=outcome.discovered_state,
            payload={"evidence": outcome.evidence},
        )

        if outcome.discovered_state in (CommandState.FILLED, CommandState.PARTIALLY_FILLED):
            if hint is not None and hint.status in (
                ResultStatus.FILLED,
                ResultStatus.PARTIALLY_FILLED,
            ):
                filled = hint
            else:
                # no fill evidence in the hint (e.g. a timeout unknown):
                # adopt only broker-truth values from the reconciliation
                filled = ExecutionResult.filled(
                    command_id=command.command_id,
                    trade_id=command.trade_id,
                    timestamp=now_iso(),
                    filled_volume=float(outcome.evidence.get("filled_volume", 0.0)),
                    fill_price=float(outcome.evidence.get("fill_price", 0.0)),
                )
            return self._ensure_sl_protection(command, filled)

        if outcome.discovered_state is CommandState.SUBMITTED:
            # await the pending order at the broker; do NOT re-submit.
            # The state is already SUBMITTED via the RECONCILED transition.
            self._journal.record(
                command,
                "SUBMITTED_AFTER_RECONCILE",
                CommandState.SUBMITTED,
                {"evidence": outcome.evidence},
            )
            return self._unknown_result(
                command,
                ErrorCode.AMBIGUOUS_RESPONSE,
                "order still pending at broker; continue monitoring",
            )

        result = self._result_for_discovered(command, outcome.discovered_state)
        self._store_result(command, result)
        return result

    def _result_for_discovered(
        self, command: ExecutionCommand, state: CommandState
    ) -> ExecutionResult:
        ts = now_iso()
        if state is CommandState.CLOSED:
            return ExecutionResult.closed(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
            )
        if state is CommandState.REJECTED:
            return ExecutionResult.rejected(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
                error_code=ErrorCode.BROKER_REJECT.value,
                error_message="reconciled to broker rejection",
            )
        if state is CommandState.EXPIRED:
            return ExecutionResult.expired(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
                error_message="reconciled to broker expiry",
            )
        if state is CommandState.FAILED:
            return ExecutionResult.failed(
                command_id=command.command_id,
                trade_id=command.trade_id,
                timestamp=ts,
                error_code=ErrorCode.FAILED.value,
                error_message="reconciled to failure",
            )
        return self._unknown_result(
            command,
            ErrorCode.RECONCILIATION_PENDING,
            f"cannot project discovered state {state.value}",
        )

    # ------------------------------------------------------------------
    # restart recovery
    # ------------------------------------------------------------------

    def recover(self) -> list[RecoveryItem]:
        """Inspect journal state after a restart (task §8, §10 item 12).

        * VALIDATED/CREATED -> safe to submit (executor was never called;
          the write-ahead SUBMITTED record is the evidence of a call)
        * SUBMITTED/UNKNOWN -> reconcile FIRST, never blind resend
        """
        items: list[RecoveryItem] = []
        for stored in self._journal.active_commands():
            if stored.state in _RECONCILE_ACTIONS:
                action = "RECONCILE"
            elif stored.state in (CommandState.CREATED, CommandState.VALIDATED):
                action = "SUBMIT_SAFE"
            else:
                action = "NONE"
            items.append(
                RecoveryItem(
                    command_id=stored.command_id,
                    trade_id=stored.trade_id,
                    state=stored.state,
                    action=action,
                )
            )
        return items

    def pending_reconciliation(self) -> list[RecoveryItem]:
        """Commands currently blocking new entries (fail-closed gate)."""
        return [item for item in self.recover() if item.action == "RECONCILE"]

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _pending_reconciliation_ids(self) -> list[str]:
        return [
            item.command_id
            for item in self.recover()
            if item.action == "RECONCILE" or item.action == "SUBMIT_SAFE"
        ]

    def _record_transition(
        self,
        command: ExecutionCommand,
        event: ExecutionEvent,
        *,
        target: CommandState | None = None,
        payload: dict[str, Any] | None = None,
    ) -> CommandState:
        stored = self._journal.get_command(command.command_id)
        current = stored.state if stored is not None else CommandState.CREATED
        next_state = transition(current, event, target=target)
        self._journal.record(command, event.value, next_state, payload or {})
        return next_state

    def _unknown_result(
        self, command: ExecutionCommand, error_code: ErrorCode, message: str
    ) -> ExecutionResult:
        return ExecutionResult.unknown(
            command_id=command.command_id,
            trade_id=command.trade_id,
            timestamp=now_iso(),
            error_code=error_code.value,
            error_message=message,
        )

    def _current_state(self, command: ExecutionCommand) -> CommandState:
        """Audit-only journal records carry the CURRENT projection state.

        Unlike FSM transitions, these lines must never move the projector
        into an illegal or premature state (e.g. FILLED before the
        FULL_FILL transition is applied).
        """
        stored = self._journal.get_command(command.command_id)
        return stored.state if stored is not None else CommandState.CREATED

    def _store_result(self, command: ExecutionCommand, result: ExecutionResult) -> None:
        self._journal.store_result(command, result)


def _with_sl_confirmed(
    result: ExecutionResult, _position: PositionSnapshot | None
) -> ExecutionResult:
    """Promote a fill result to the final FILLED result with SL confirmed."""
    return ExecutionResult.filled(
        command_id=result.command_id,
        trade_id=result.trade_id,
        timestamp=now_iso(),
        broker_request_id=result.broker_request_id,
        broker_retcode=result.broker_retcode,
        filled_volume=result.filled_volume,
        fill_price=result.fill_price,
        sl_applied=True,
    )


__all__ = ["ExecutionConfig", "ExecutionEngine", "RecoveryItem"]
