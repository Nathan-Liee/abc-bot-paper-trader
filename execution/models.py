"""Execution contracts — TradePlan, ExecutionCommand, ExecutionResult.

Authority (locked, unchanged):

* ``TradePlan`` is a System (Risk Gate) output; execution never mutates it.
* ``ExecutionCommand`` carries NO risk fields, NO TP, NO AI confidence or
  reason; ``command_id`` IS the idempotency key (OD-9).
* ``ExecutionResult`` reports broker-truth values verbatim; broker-owned
  ids are never fabricated by this package.

Lineage (OD-9):

    inference_id -> risk_evaluation_id -> trade_id -> command_id -> result
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from execution.retry import ErrorCode

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class Direction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class EntryType(StrEnum):
    """OD-2: MARKET is the only supported entry type for v0.1."""

    MARKET = "MARKET"


class CommandState(StrEnum):
    """Deterministic execution lifecycle (task §7)."""

    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    MODIFYING = "MODIFYING"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


TERMINAL_STATES: frozenset[CommandState] = frozenset(
    {CommandState.CLOSED, CommandState.REJECTED, CommandState.FAILED, CommandState.EXPIRED}
)


class ResultStatus(StrEnum):
    """Broker-truth surfaces of an execution result."""

    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class ExitReason(StrEnum):
    """System-owned close reasons. No fixed TP exists anywhere."""

    ABC_PROFIT_CLOSE = "ABC_PROFIT_CLOSE"
    SL_STOP = "SL_STOP"
    EMERGENCY_CLOSE = "EMERGENCY_CLOSE"
    SYSTEM_CLOSE = "SYSTEM_CLOSE"


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_command_id() -> str:
    return str(uuid.uuid4())


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and not math.isnan(float(value))
        and not math.isinf(float(value))
    )


@dataclass(frozen=True)
class TradePlan:
    """Immutable System output produced only by an approved risk decision.

    Frozen by construction; execution MUST NOT alter any value.
    """

    trade_id: str
    correlation_id: str
    inference_id: str | None
    risk_evaluation_id: str
    direction: str
    lot: float
    entry_reference: float
    sl: float
    risk_amount: float
    risk_percent: float
    exposure: float
    symbol: str
    generated_at: str
    expires_at: str
    policy_profile: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TradePlan:
        return cls(
            trade_id=str(data["trade_id"]),
            correlation_id=str(data["correlation_id"]),
            inference_id=data.get("inference_id") if "inference_id" in data else None,
            risk_evaluation_id=str(data["risk_evaluation_id"]),
            direction=str(data["direction"]),
            lot=float(data["lot"]),
            entry_reference=float(data["entry_reference"]),
            sl=float(data["sl"]),
            risk_amount=float(data["risk_amount"]),
            risk_percent=float(data["risk_percent"]),
            exposure=float(data["exposure"]),
            symbol=str(data["symbol"]),
            generated_at=str(data["generated_at"]),
            expires_at=str(data["expires_at"]),
            policy_profile=str(data["policy_profile"]),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not is_valid_system_id(self.trade_id):
            errors.append("plan.trade_id:invalid_uuid")
        if not is_valid_system_id(self.correlation_id):
            errors.append("plan.correlation_id:invalid_uuid")
        if self.inference_id is not None and not is_valid_system_id(self.inference_id):
            errors.append("plan.inference_id:invalid_uuid")
        if not is_valid_system_id(self.risk_evaluation_id):
            errors.append("plan.risk_evaluation_id:invalid_uuid")
        if self.direction not in (Direction.BUY.value, Direction.SELL.value):
            errors.append(f"plan.direction:invalid:{self.direction}")
        if not _is_finite_number(self.lot) or self.lot <= 0:
            errors.append("plan.lot:non_positive")
        if not _is_finite_number(self.entry_reference) or self.entry_reference <= 0:
            errors.append("plan.entry_reference:non_positive")
        if not _is_finite_number(self.sl) or self.sl <= 0:
            errors.append("plan.sl:non_positive")
        for name, value in (
            ("risk_amount", self.risk_amount),
            ("risk_percent", self.risk_percent),
            ("exposure", self.exposure),
        ):
            if not _is_finite_number(value) or value < 0:
                errors.append(f"plan.{name}:invalid:{value}")
        if not self.symbol:
            errors.append("plan.symbol:empty")
        if not self.policy_profile:
            errors.append("plan.policy_profile:empty")
        generated = parse_iso_ts(self.generated_at)
        expires = parse_iso_ts(self.expires_at)
        if generated is None:
            errors.append("plan.generated_at:unparseable")
        if expires is None:
            errors.append("plan.expires_at:unparseable")
        if generated is not None and expires is not None and expires <= generated:
            errors.append("plan.expiry_not_after_generated")
        return errors


@dataclass(frozen=True)
class ExecutionCommand:
    """Execution-layer input. Minimal by contract (task §6).

    ``idempotency_key`` is defined as ``command_id`` (OD-9); there is
    deliberately no separate risk/lot/confidence/reason/TP field.
    """

    command_id: str
    trade_id: str
    symbol: str
    direction: str
    volume: float
    entry_type: EntryType
    sl: float
    created_at: str
    expires_at: str

    @property
    def idempotency_key(self) -> str:
        return self.command_id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExecutionCommand:
        return cls(
            command_id=str(data["command_id"]),
            trade_id=str(data["trade_id"]),
            symbol=str(data["symbol"]),
            direction=str(data["direction"]),
            volume=float(data["volume"]),
            entry_type=(
                EntryType(str(data["entry_type"])) if "entry_type" in data else EntryType.MARKET
            ),
            sl=float(data["sl"]),
            created_at=str(data["created_at"]),
            expires_at=str(data["expires_at"]),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not is_valid_system_id(self.command_id):
            errors.append("command.command_id:invalid_uuid")
        if not is_valid_system_id(self.trade_id):
            errors.append("command.trade_id:invalid_uuid")
        if not self.symbol:
            errors.append("command.symbol:empty")
        if self.direction not in (Direction.BUY.value, Direction.SELL.value):
            errors.append(f"command.direction:invalid:{self.direction}")
        if not _is_finite_number(self.volume) or self.volume <= 0:
            errors.append("command.volume:non_positive")
        if self.entry_type is not EntryType.MARKET:
            errors.append(f"command.entry_type:not_market:{self.entry_type}")
        if not _is_finite_number(self.sl) or self.sl <= 0:
            errors.append("command.sl:non_positive")
        created = parse_iso_ts(self.created_at)
        expires = parse_iso_ts(self.expires_at)
        if created is None:
            errors.append("command.created_at:unparseable")
        if expires is None:
            errors.append("command.expires_at:unparseable")
        if created is not None and expires is not None and expires <= created:
            errors.append("command.expiry_not_after_created")
        return errors


@dataclass(frozen=True)
class PositionSnapshot:
    """Broker-truth position read (no execution capability)."""

    position_id: str
    symbol: str
    direction: str
    volume: float
    open_price: float
    sl: float | None
    ts: str


@dataclass(frozen=True)
class ExecutionResult:
    """Execution-layer output; broker values verbatim, never fabricated."""

    command_id: str
    trade_id: str
    status: ResultStatus
    timestamp: str
    broker_request_id: str | None = None
    broker_retcode: int = 0
    filled_volume: float = 0.0
    fill_price: float = 0.0
    sl_applied: bool = False
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExecutionResult:
        return cls(
            command_id=str(data["command_id"]),
            trade_id=str(data["trade_id"]),
            status=ResultStatus(str(data["status"])),
            timestamp=str(data["timestamp"]),
            broker_request_id=data.get("broker_request_id"),
            broker_retcode=int(data.get("broker_retcode", 0)),
            filled_volume=float(data.get("filled_volume", 0.0)),
            fill_price=float(data.get("fill_price", 0.0)),
            sl_applied=bool(data.get("sl_applied", False)),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
        )

    @classmethod
    def filled(
        cls,
        *,
        command_id: str,
        trade_id: str,
        timestamp: str,
        broker_request_id: str | None = None,
        broker_retcode: int = 0,
        filled_volume: float = 0.0,
        fill_price: float = 0.0,
        sl_applied: bool = False,
    ) -> ExecutionResult:
        return cls(
            command_id=command_id,
            trade_id=trade_id,
            status=ResultStatus.FILLED,
            timestamp=timestamp,
            broker_request_id=broker_request_id,
            broker_retcode=broker_retcode,
            filled_volume=filled_volume,
            fill_price=fill_price,
            sl_applied=sl_applied,
        )

    @classmethod
    def partial(
        cls,
        *,
        command_id: str,
        trade_id: str,
        timestamp: str,
        filled_volume: float,
        fill_price: float,
        broker_request_id: str | None = None,
        sl_applied: bool = False,
    ) -> ExecutionResult:
        return cls(
            command_id=command_id,
            trade_id=trade_id,
            status=ResultStatus.PARTIALLY_FILLED,
            timestamp=timestamp,
            broker_request_id=broker_request_id,
            filled_volume=filled_volume,
            fill_price=fill_price,
            sl_applied=sl_applied,
        )

    @classmethod
    def closed(
        cls,
        *,
        command_id: str,
        trade_id: str,
        timestamp: str,
        broker_request_id: str | None = None,
        broker_retcode: int = 0,
    ) -> ExecutionResult:
        return cls(
            command_id=command_id,
            trade_id=trade_id,
            status=ResultStatus.CLOSED,
            timestamp=timestamp,
            broker_request_id=broker_request_id,
            broker_retcode=broker_retcode,
            sl_applied=True,
        )

    @classmethod
    def rejected(
        cls,
        *,
        command_id: str,
        trade_id: str,
        timestamp: str,
        error_code: str,
        error_message: str,
        broker_retcode: int = 0,
        broker_request_id: str | None = None,
    ) -> ExecutionResult:
        return cls(
            command_id=command_id,
            trade_id=trade_id,
            status=ResultStatus.REJECTED,
            timestamp=timestamp,
            broker_request_id=broker_request_id,
            broker_retcode=broker_retcode,
            error_code=error_code,
            error_message=error_message,
        )

    @classmethod
    def failed(
        cls,
        *,
        command_id: str,
        trade_id: str,
        timestamp: str,
        error_code: str,
        error_message: str,
    ) -> ExecutionResult:
        return cls(
            command_id=command_id,
            trade_id=trade_id,
            status=ResultStatus.FAILED,
            timestamp=timestamp,
            error_code=error_code,
            error_message=error_message,
        )

    @classmethod
    def expired(
        cls,
        *,
        command_id: str,
        trade_id: str,
        timestamp: str,
        error_message: str = "command expired",
    ) -> ExecutionResult:
        return cls(
            command_id=command_id,
            trade_id=trade_id,
            status=ResultStatus.EXPIRED,
            timestamp=timestamp,
            error_code=ErrorCode.EXPIRED.value,
            error_message=error_message,
        )

    @classmethod
    def unknown(
        cls,
        *,
        command_id: str,
        trade_id: str,
        timestamp: str,
        error_code: str,
        error_message: str,
    ) -> ExecutionResult:
        return cls(
            command_id=command_id,
            trade_id=trade_id,
            status=ResultStatus.UNKNOWN,
            timestamp=timestamp,
            error_code=error_code,
            error_message=error_message,
        )

    @property
    def is_error(self) -> bool:
        return self.status in (ResultStatus.REJECTED, ResultStatus.FAILED, ResultStatus.UNKNOWN)


def is_valid_system_id(value: object) -> bool:
    """UUID validity for System-owned ids (mirrors shared identity rules)."""
    return isinstance(value, str) and UUID_PATTERN.fullmatch(value) is not None


def parse_iso_ts(ts_str: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        return None


__all__ = [
    "CommandState",
    "Direction",
    "EntryType",
    "ExecutionCommand",
    "ExecutionResult",
    "ExitReason",
    "PositionSnapshot",
    "ResultStatus",
    "TERMINAL_STATES",
    "TradePlan",
    "new_command_id",
    "now_iso",
]
