"""Scenario runner — orchestrates paper validation lifecycle per scenario.

AI fixture → Risk Engine → Simulated Entry → Position Lifecycle → ABC/SL Exit → Evidence.
No broker execution. No live orders.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from paper_validation.cost_model import CostModel
from paper_validation.evidence import TradeEvidence
from paper_validation.execution_simulator import simulate_fill
from paper_validation.market_replay import MarketReplay, MarketTick, ReplayConfig
from paper_validation.models import (
    ExitReason,
    PaperAccount,
    ScenarioConfig,
    ScenarioResult,
    SimulationConfig,
    new_trade_id,
)
from risk_engine.config import RiskConfig
from risk_engine.engine import RiskEngine
from risk_engine.models import (
    AccountState,
    MarketState,
    SymbolSpecification,
)
from risk_engine.validators import parse_iso_ts

logger = logging.getLogger("paper_validation")


def _default_xauusdc_spec() -> SymbolSpecification:
    """Symbol spec matching observed HFM Cent XAUUSDc runtime evidence."""
    return SymbolSpecification(
        symbol="XAUUSDc",
        contract_size=1.0,
        tick_size=0.01,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=1000.0,
        volume_step=0.01,
        point=0.01,
        stops_level=0.0,
        freeze_level=8.0,
    )


def _make_account(scenario: ScenarioConfig) -> PaperAccount:
    free_margin = scenario.free_margin_override or scenario.starting_equity
    margin = scenario.margin_override or 0.0
    return PaperAccount(
        balance=scenario.starting_balance,
        equity=scenario.starting_equity,
        free_margin=free_margin,
        margin=margin,
        existing_positions_count=scenario.existing_positions,
        current_exposure_usd=scenario.current_exposure_usd,
        current_drawdown_pct=scenario.current_drawdown_pct,
    )


def _make_market_state(tick: MarketTick) -> MarketState:
    return MarketState(
        bid=tick.bid,
        ask=tick.ask,
        spread=tick.spread,
        mid=tick.mid,
        symbol=tick.symbol,
        timestamp_iso=tick.timestamp_iso,
    )


def _make_account_state(account: PaperAccount) -> AccountState:
    return AccountState(
        balance=account.balance,
        equity=account.equity,
        free_margin=account.free_margin,
        margin=account.margin,
        existing_positions_count=account.existing_positions_count,
        current_exposure_usd=account.current_exposure_usd,
        current_drawdown_pct=account.current_drawdown_pct,
    )


class ScenarioRunner:
    """Runs one scenario: AI fixture → Risk Engine → Sim → Evidence."""

    def __init__(
        self,
        risk_config: RiskConfig | None = None,
        sim_config: SimulationConfig | None = None,
        spec: SymbolSpecification | None = None,
    ) -> None:
        self._risk_config = risk_config or RiskConfig()
        self._risk_engine = RiskEngine(self._risk_config)
        self._sim_config = sim_config or SimulationConfig()
        self._spec = spec or _default_xauusdc_spec()

    @property
    def risk_config(self) -> RiskConfig:
        return self._risk_config

    def run(self, scenario: ScenarioConfig) -> ScenarioResult:
        """Execute one paper validation scenario."""
        sid = scenario.scenario_id
        account = _make_account(scenario)

        # Generate or use fixture ticks
        if scenario.ticks:
            ticks = MarketReplay.from_fixture_ticks(scenario.ticks)
        else:
            replay = MarketReplay(
                ReplayConfig(
                    tick_count=max(self._sim_config.max_steps_per_scenario, 10),
                    seed=self._sim_config.seed,
                )
            )
            ticks = replay.generate_ticks()

        if not ticks:
            return ScenarioResult(
                scenario_id=sid,
                approved=False,
                exit_reason="DATA_INVALID",
                rejection_reason_code="DATA_INVALID",
                rejection_message="No ticks available",
            )

        # Step 1: Risk Engine evaluation at first tick
        first_tick = ticks[0]
        market = _make_market_state(first_tick)
        acc_state = _make_account_state(account)

        # Parse tick timestamp for freshness check (avoid stale-context reject
        # for historical fixture timestamps)
        now_dt = parse_iso_ts(first_tick.timestamp_iso) or datetime.now(UTC)

        ai_proposal: dict[str, Any] = {
            "direction": scenario.direction,
            "confidence": scenario.confidence,
            "reason": scenario.reason,
            "validation_ok": True,
            "inference_id": f"fixture-{sid}",
            "correlation_id": f"scenario-{sid}",
        }

        eval_record = self._risk_engine.evaluate(
            ai_proposal=ai_proposal,
            account=acc_state,
            market=market,
            spec=self._spec,
            correlation_id=f"scenario-{sid}",
            now=now_dt,
        )

        # Handle rejection
        if eval_record.decision == "REJECT":
            return ScenarioResult(
                scenario_id=sid,
                approved=False,
                exit_reason=eval_record.reason_code,
                rejection_reason_code=eval_record.reason_code,
                rejection_message=eval_record.reason,
            )

        # Handle NO-TRADE
        if scenario.direction == "NO-TRADE":
            return ScenarioResult(
                scenario_id=sid,
                approved=False,
                exit_reason=ExitReason.PAPER_SESSION_END.value,
                notes="NO-TRADE proposal; no position opened",
            )

        # Step 2: Simulated fill
        cost_model = CostModel.from_mode_str(
            scenario.cost_mode,
            commission_per_lot=scenario.commission_per_lot,
            swap_per_lot_per_night=scenario.swap_per_lot_per_night,
            slippage_points=scenario.slippage_points,
            point=self._spec.point,
        )

        trade_id = new_trade_id()
        fill, position = simulate_fill(
            direction=eval_record.direction,
            lot=eval_record.lot,
            sl_price=eval_record.sl,
            tick=first_tick,
            risk_amount=eval_record.risk_amount,
            cost_model=cost_model,
            contract_size=self._spec.contract_size,
            tick_value=self._spec.tick_value,
            tick_size=self._spec.tick_size,
            point=self._spec.point,
            trade_id=trade_id,
        )

        # Step 3: Position lifecycle — iterate ticks checking exit conditions
        exit_reason: ExitReason | None = None
        close_tick = first_tick

        for tick in ticks[1:]:
            exit_reason = position.check_exit(tick)
            if exit_reason is not None:
                close_tick = tick
                break

        if exit_reason is None:
            exit_reason = ExitReason.PAPER_SESSION_END

        # Step 4: Close position and generate evidence
        close_result = position.close(close_tick, exit_reason)
        close_result["exit_ts"] = close_tick.timestamp_iso

        # Check risk budget integrity
        risk_overrun = False
        risk_realized_raw = close_result.get("risk_realized", 0)
        risk_realized = (
            float(risk_realized_raw) if isinstance(risk_realized_raw, (int, float)) else 0.0
        )
        if risk_realized > eval_record.risk_amount * 1.0001:
            risk_overrun = True
            exit_str = str(close_result["exit_reason"])
            close_result["exit_reason"] = exit_str + " [RISK_BUDGET_OVERRUN_DUE_TO_SIMULATED_COST]"

        evidence = TradeEvidence.from_close_result(
            trade_id=trade_id,
            scenario_id=sid,
            direction=eval_record.direction,
            confidence=scenario.confidence,
            risk_config_profile=self._risk_config.profile_name,
            equity_before=account.equity,
            risk_budget=account.equity * self._risk_config.risk_per_trade,
            lot=eval_record.lot,
            entry_price=fill.fill_price,
            sl_price=eval_record.sl,
            max_risk_theoretical=eval_record.risk_amount,
            spread_at_entry=fill.spread_at_fill,
            timestamp_open=fill.fill_ts,
            close_result=close_result,
            risk_decision=eval_record.decision,
            reason_code=eval_record.reason_code,
            notes="RISK_BUDGET_OVERRUN" if risk_overrun else "",
        )

        return ScenarioResult(
            scenario_id=sid,
            approved=True,
            exit_reason=exit_reason.value,
            trade_evidence=evidence.to_dict(),
            notes="RISK_BUDGET_OVERRUN_DUE_TO_SIMULATED_COST" if risk_overrun else "",
        )

    def run_batch(self, scenarios: list[ScenarioConfig]) -> list[ScenarioResult]:
        """Run multiple scenarios."""
        return [self.run(s) for s in scenarios]
