"""Execution layer — contracts + durable lifecycle + deterministic simulator.

Pipeline position (authority unchanged):

    DecisionRecord -> RiskEngine -> TradePlan -> ExecutionCommand ->
    SimulatedExecutor -> reconciliation boundary

This package NEVER: computes direction/lot/risk/SL, attaches TP, calls a
broker or MT5, opens network connections, or performs live trading.
Broker/EA integration is a separate future task.
"""

from __future__ import annotations

from execution.engine import ExecutionConfig, ExecutionEngine, RecoveryItem
from execution.errors import (
    DuplicateCommandError,
    ExecutionError,
    ExecutionStateError,
    JournalError,
)
from execution.executor import Executor
from execution.journal import ExecutionJournal, JournalEvent, StoredCommand
from execution.models import (
    TERMINAL_STATES,
    CommandState,
    Direction,
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
    StaticReconciliation,
)
from execution.retry import (
    RETRY_MATRIX,
    ErrorCode,
    RetryClass,
    RetryPolicy,
    classify_error,
)
from execution.simulated import SimulatedExecutor, SimulatorScenario, SubmitMode
from execution.state_machine import (
    RECONCILABLE_STATES,
    ExecutionEvent,
    ExecutionStateMachine,
    transition,
)
from execution.validation import (
    COMMAND_FIELDS,
    FORBIDDEN_COMMAND_FIELDS,
    PLAN_FIELDS,
    is_expired,
    is_expired_command,
    is_expired_plan,
    validate_command,
    validate_command_dict,
    validate_plan,
    validate_plan_dict,
)

__all__ = [
    "COMMAND_FIELDS",
    "CommandState",
    "Direction",
    "DuplicateCommandError",
    "EntryType",
    "ErrorCode",
    "ExecutionCommand",
    "ExecutionConfig",
    "ExecutionEngine",
    "ExecutionError",
    "ExecutionEvent",
    "ExecutionJournal",
    "ExecutionResult",
    "ExecutionStateError",
    "ExecutionStateMachine",
    "Executor",
    "ExitReason",
    "FORBIDDEN_COMMAND_FIELDS",
    "JournalError",
    "JournalEvent",
    "PLAN_FIELDS",
    "PositionSnapshot",
    "RECONCILABLE_STATES",
    "RETRY_MATRIX",
    "ReconciliationBoundary",
    "ReconciliationOutcome",
    "RecoveryItem",
    "ResultStatus",
    "RetryClass",
    "RetryPolicy",
    "SimulatedExecutor",
    "SimulatorScenario",
    "StaticReconciliation",
    "StoredCommand",
    "SubmitMode",
    "TERMINAL_STATES",
    "TradePlan",
    "classify_error",
    "is_expired",
    "is_expired_command",
    "is_expired_plan",
    "new_command_id",
    "now_iso",
    "transition",
    "validate_command",
    "validate_command_dict",
    "validate_plan",
    "validate_plan_dict",
]
