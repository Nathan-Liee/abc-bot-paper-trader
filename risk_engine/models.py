"""Data models and evaluation record contracts for Risk Engine."""

from __future__ import annotations

import math
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from risk_engine.reason_codes import ReasonCode


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_evaluation_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class AccountState:
    """Current broker account state snapshot."""

    balance: float
    equity: float
    free_margin: float
    margin: float
    existing_positions_count: int = 0
    current_exposure_usd: float = 0.0
    current_drawdown_pct: float = 0.0

    def validate(self) -> list[str]:
        errors: list[str] = []
        for name, val in (
            ("balance", self.balance),
            ("equity", self.equity),
            ("free_margin", self.free_margin),
            ("margin", self.margin),
            ("current_exposure_usd", self.current_exposure_usd),
            ("current_drawdown_pct", self.current_drawdown_pct),
        ):
            if (
                not isinstance(val, (int, float))
                or isinstance(val, bool)
                or math.isnan(val)
                or math.isinf(val)
            ):
                errors.append(f"account.{name}:invalid_number")
        if self.balance < 0:
            errors.append("account.balance:negative")
        if self.equity < 0:
            errors.append("account.equity:negative")
        if self.existing_positions_count < 0:
            errors.append("account.existing_positions_count:negative")
        return errors


@dataclass(frozen=True)
class MarketState:
    """Current market feed snapshot."""

    bid: float
    ask: float
    spread: float
    mid: float
    symbol: str
    timestamp_iso: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        for name, val in (
            ("bid", self.bid),
            ("ask", self.ask),
            ("spread", self.spread),
            ("mid", self.mid),
        ):
            if (
                not isinstance(val, (int, float))
                or isinstance(val, bool)
                or math.isnan(val)
                or math.isinf(val)
            ):
                errors.append(f"market.{name}:invalid_number")
        if self.bid <= 0 or self.ask <= 0 or self.mid <= 0:
            errors.append("market.prices:non_positive")
        if self.ask < self.bid:
            errors.append("market.ask_below_bid")
        if self.spread < 0:
            errors.append("market.spread:negative")
        if not self.symbol or not isinstance(self.symbol, str):
            errors.append("market.symbol:empty")
        if not self.timestamp_iso or not isinstance(self.timestamp_iso, str):
            errors.append("market.timestamp:empty")
        return errors


@dataclass(frozen=True)
class SymbolSpecification:
    """Symbol contract and execution limits from broker."""

    symbol: str
    contract_size: float
    tick_size: float
    tick_value: float
    volume_min: float
    volume_max: float
    volume_step: float
    stops_level: float = 0.0
    freeze_level: float = 0.0
    margin_initial: float = 0.0  # margin per lot if supplied, or 0.0 for leverage-based

    def validate(self) -> list[str]:
        errors: list[str] = []
        for name, val in (
            ("contract_size", self.contract_size),
            ("tick_size", self.tick_size),
            ("tick_value", self.tick_value),
            ("volume_min", self.volume_min),
            ("volume_max", self.volume_max),
            ("volume_step", self.volume_step),
            ("stops_level", self.stops_level),
            ("freeze_level", self.freeze_level),
            ("margin_initial", self.margin_initial),
        ):
            if (
                not isinstance(val, (int, float))
                or isinstance(val, bool)
                or math.isnan(val)
                or math.isinf(val)
            ):
                errors.append(f"symbol_spec.{name}:invalid_number")
        if self.contract_size <= 0:
            errors.append("symbol_spec.contract_size:non_positive")
        if self.tick_size <= 0:
            errors.append("symbol_spec.tick_size:non_positive")
        if self.tick_value <= 0:
            errors.append("symbol_spec.tick_value:non_positive")
        if self.volume_min <= 0:
            errors.append("symbol_spec.volume_min:non_positive")
        if self.volume_max < self.volume_min:
            errors.append("symbol_spec.volume_max_below_min")
        if self.volume_step <= 0:
            errors.append("symbol_spec.volume_step:non_positive")
        return errors


@dataclass(frozen=True)
class RiskDecision:
    """JSON-serializable decision response as required by specification §11."""

    decision: str  # "APPROVE" | "REJECT"
    direction: str  # "BUY" | "SELL" | "NO-TRADE"
    lot: float
    sl: float
    risk_amount: float
    risk_percent: float
    exposure: float
    reason_code: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskEvaluationRecord:
    """Full auditable record for observability and event conversion (§22)."""

    risk_evaluation_id: str
    correlation_id: str | None
    inference_id: str | None
    decision: str
    direction: str
    risk_amount: float
    risk_percent: float
    lot: float
    exposure: float
    sl: float
    reason_code: str
    reason: str
    validation_failures: tuple[str, ...] = field(default_factory=tuple)
    timestamp_iso: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def reject(
        cls,
        *,
        reason_code: ReasonCode | str,
        reason: str,
        correlation_id: str | None = None,
        inference_id: str | None = None,
        direction: str = "NO-TRADE",
        validation_failures: tuple[str, ...] = (),
    ) -> RiskEvaluationRecord:
        code_str = reason_code.value if isinstance(reason_code, ReasonCode) else str(reason_code)
        return cls(
            risk_evaluation_id=new_evaluation_id(),
            correlation_id=correlation_id,
            inference_id=inference_id,
            decision="REJECT",
            direction=direction,
            risk_amount=0.0,
            risk_percent=0.0,
            lot=0.0,
            exposure=0.0,
            sl=0.0,
            reason_code=code_str,
            reason=reason,
            validation_failures=validation_failures,
        )

    def to_decision(self) -> RiskDecision:
        return RiskDecision(
            decision=self.decision,
            direction=self.direction,
            lot=self.lot,
            sl=self.sl,
            risk_amount=self.risk_amount,
            risk_percent=self.risk_percent,
            exposure=self.exposure,
            reason_code=self.reason_code,
            reason=self.reason,
        )
