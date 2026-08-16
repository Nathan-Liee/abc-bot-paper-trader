"""Validation rules and safety filters for Risk Engine."""

from __future__ import annotations

from datetime import UTC, datetime

from risk_engine.config import RiskConfig
from risk_engine.models import AccountState, MarketState, SymbolSpecification
from risk_engine.reason_codes import ReasonCode


def parse_iso_ts(ts_str: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


def validate_all_inputs(
    ai_direction: str,
    ai_confidence: float,
    account: AccountState,
    market: MarketState,
    spec: SymbolSpecification,
    config: RiskConfig,
    now: datetime | None = None,
) -> tuple[bool, ReasonCode | None, str, list[str]]:
    """Validate all preconditions before trade planning.

    Returns (ok, reason_code, message, error_list).
    """
    failures: list[str] = []

    # 1. AI Proposal Validation
    if ai_direction not in ("BUY", "SELL", "NO-TRADE"):
        failures.append(f"ai.direction:invalid:{ai_direction}")
        return False, ReasonCode.AUTHORITY_VIOLATION, "Invalid AI direction", failures

    if ai_direction == "NO-TRADE":
        return False, ReasonCode.AI_NO_TRADE, "AI proposed NO-TRADE", failures

    if ai_confidence < config.min_ai_confidence:
        failures.append(f"ai.confidence:below_min:{ai_confidence}<{config.min_ai_confidence}")
        return (
            False,
            ReasonCode.AUTHORITY_VIOLATION,
            f"AI confidence {ai_confidence} below minimum {config.min_ai_confidence}",
            failures,
        )

    # 2. Account State
    acc_errors = account.validate()
    if acc_errors:
        failures.extend(acc_errors)
        return (
            False,
            ReasonCode.INVALID_ACCOUNT_STATE,
            "Account state contains invalid fields",
            failures,
        )

    # 3. Market State
    mkt_errors = market.validate()
    if mkt_errors:
        failures.extend(mkt_errors)
        return (
            False,
            ReasonCode.INVALID_MARKET_CONTEXT,
            "Market state contains invalid fields",
            failures,
        )

    # 4. Symbol Specification
    spec_errors = spec.validate()
    if spec_errors:
        failures.extend(spec_errors)
        return (
            False,
            ReasonCode.BROKER_CONSTRAINT,
            "Symbol specification contains invalid fields",
            failures,
        )

    # 5. Config Validation
    cfg_errors = config.validate()
    if cfg_errors:
        failures.extend(cfg_errors)
        return False, ReasonCode.UNKNOWN_RISK_INPUT, "Risk configuration is invalid", failures

    # 6. Freshness / Stale Context Check
    ts_dt = parse_iso_ts(market.timestamp_iso)
    if ts_dt is None:
        failures.append("market.timestamp:unparseable")
        return False, ReasonCode.STALE_CONTEXT, "Unparseable market timestamp", failures

    current_time = now or datetime.now(UTC)
    delta_s = (current_time - ts_dt).total_seconds()
    if delta_s < -5.0 or delta_s > config.max_stale_seconds:
        failures.append(f"market.timestamp:stale_or_future:delta={delta_s:.1f}s")
        return (
            False,
            ReasonCode.STALE_CONTEXT,
            f"Market context is stale ({delta_s:.1f}s old)",
            failures,
        )

    # 7. Spread Check
    if market.spread > config.max_spread:
        failures.append(f"market.spread:exceeds_max:{market.spread}>{config.max_spread}")
        return (
            False,
            ReasonCode.SPREAD_TOO_HIGH,
            f"Market spread {market.spread} exceeds limit {config.max_spread}",
            failures,
        )

    # 8. Drawdown Guard (Circuit Breaker)
    if account.current_drawdown_pct >= config.max_drawdown_pct:
        failures.append(
            f"account.drawdown:exceeds_max:{account.current_drawdown_pct}%>={config.max_drawdown_pct}%"
        )
        return (
            False,
            ReasonCode.DRAWDOWN_LIMIT,
            (
                f"Account drawdown {account.current_drawdown_pct}% "
                f"exceeds max {config.max_drawdown_pct}%"
            ),
            failures,
        )

    # 9. Simultaneous Position Limits
    if account.existing_positions_count >= config.max_simultaneous_positions:
        failures.append(
            f"account.positions:limit_reached:{account.existing_positions_count}>={config.max_simultaneous_positions}"
        )
        return (
            False,
            ReasonCode.EXPOSURE_LIMIT,
            f"Existing positions ({account.existing_positions_count}) at or above limit",
            failures,
        )

    return True, None, "Preconditions OK", []
