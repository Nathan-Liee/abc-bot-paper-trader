"""Risk Engine orchestrator — evaluates proposals against system authority."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ai_decision.record import DecisionRecord
from risk_engine.calculators import calculate_trade_plan
from risk_engine.config import RiskConfig
from risk_engine.models import (
    AccountState,
    MarketState,
    RiskEvaluationRecord,
    SymbolSpecification,
    new_evaluation_id,
)
from risk_engine.reason_codes import ReasonCode
from risk_engine.validators import validate_all_inputs

logger = logging.getLogger("risk_engine")


class RiskEngine:
    """System-owned Risk Engine."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self._config = config or RiskConfig()

    @property
    def config(self) -> RiskConfig:
        return self._config

    def evaluate(
        self,
        ai_proposal: DecisionRecord | dict[str, Any],
        account: AccountState,
        market: MarketState,
        spec: SymbolSpecification,
        *,
        correlation_id: str | None = None,
        now: datetime | None = None,
    ) -> RiskEvaluationRecord:
        """Main entry point: evaluate an AI proposal against System risk constraints."""
        eval_id = new_evaluation_id()

        # 1. Extract proposal fields safely
        direction: str
        confidence: float
        inference_id: str | None
        corr_id: str | None
        val_ok: bool
        err_class: str | None

        if isinstance(ai_proposal, DecisionRecord):
            direction = ai_proposal.direction
            confidence = ai_proposal.confidence
            inference_id = ai_proposal.inference_id
            val_ok = ai_proposal.validation_ok
            err_class = ai_proposal.error_class
            corr_id = correlation_id or ai_proposal.correlation_id
        elif isinstance(ai_proposal, dict):
            direction = str(ai_proposal.get("direction", "NO-TRADE"))
            try:
                confidence = float(ai_proposal.get("confidence", 0.0))
            except Exception:
                confidence = 0.0
            inference_id = ai_proposal.get("inference_id")
            corr_id = correlation_id or ai_proposal.get("correlation_id")
            val_ok = bool(ai_proposal.get("validation_ok", True))
            err_class = ai_proposal.get("error_class")
        else:
            return RiskEvaluationRecord.reject(
                reason_code=ReasonCode.UNKNOWN_RISK_INPUT,
                reason="Invalid AI proposal object type",
                correlation_id=correlation_id,
                validation_failures=("ai_proposal:invalid_type",),
            )

        # Fail closed if AI proposal already failed validation
        if not val_ok:
            return RiskEvaluationRecord.reject(
                reason_code=ReasonCode.AUTHORITY_VIOLATION,
                reason=f"AI proposal marked invalid: {err_class}",
                correlation_id=corr_id,
                inference_id=inference_id,
                direction=direction,
                validation_failures=(f"ai_proposal.invalid:{err_class}",),
            )

        # 2. Validate all inputs & safety preconditions
        pre_ok, pre_code, pre_msg, pre_failures = validate_all_inputs(
            ai_direction=direction,
            ai_confidence=confidence,
            account=account,
            market=market,
            spec=spec,
            config=self._config,
            now=now,
        )

        if not pre_ok:
            assert pre_code is not None
            logger.info("Risk pre-validation REJECT code=%s reason=%s", pre_code.value, pre_msg)
            return RiskEvaluationRecord.reject(
                reason_code=pre_code,
                reason=pre_msg,
                correlation_id=corr_id,
                inference_id=inference_id,
                direction=direction,
                validation_failures=tuple(pre_failures),
            )

        # 3. Calculate Trade Plan (SL, Lot, Risk Amount, Exposure, Margin)
        plan = calculate_trade_plan(
            direction=direction,
            account=account,
            market=market,
            spec=spec,
            config=self._config,
        )

        if not plan.ok:
            logger.info("Trade plan calculation failed: %s", plan.error)
            err_str = plan.error or "unknown_plan_error"
            if "candidate_lot_below_min" in err_str:
                code = ReasonCode.LOT_OUT_OF_RANGE
            elif "sl" in err_str:
                code = ReasonCode.INVALID_SL
            else:
                code = ReasonCode.BROKER_CONSTRAINT

            return RiskEvaluationRecord.reject(
                reason_code=code,
                reason=f"Trade plan calculation failed: {plan.error}",
                correlation_id=corr_id,
                inference_id=inference_id,
                direction=direction,
                validation_failures=(f"trade_plan.{plan.error}",),
            )

        # 4. Post-calculation validation checks

        # A. Exposure Check
        total_projected_exposure = account.current_exposure_usd + plan.exposure_usd
        if total_projected_exposure > self._config.max_exposure_usd:
            logger.info(
                "Exposure limit exceeded: projected %s > max %s",
                total_projected_exposure,
                self._config.max_exposure_usd,
            )
            return RiskEvaluationRecord.reject(
                reason_code=ReasonCode.EXPOSURE_LIMIT,
                reason=(
                    f"Projected exposure {total_projected_exposure:.2f} "
                    f"exceeds limit {self._config.max_exposure_usd:.2f}"
                ),
                correlation_id=corr_id,
                inference_id=inference_id,
                direction=direction,
                validation_failures=(
                    f"exposure.exceeded:{total_projected_exposure}>{self._config.max_exposure_usd}",
                ),
            )

        # B. Margin & Free Margin Check
        remaining_free_margin = account.free_margin - plan.required_margin_usd
        if remaining_free_margin < self._config.min_free_margin_usd:
            logger.info(
                "Insufficient margin: remaining free margin %s < min buffer %s",
                remaining_free_margin,
                self._config.min_free_margin_usd,
            )
            return RiskEvaluationRecord.reject(
                reason_code=ReasonCode.INSUFFICIENT_MARGIN,
                reason=(
                    f"Free margin after trade ({remaining_free_margin:.2f}) "
                    f"below required buffer ({self._config.min_free_margin_usd:.2f})"
                ),
                correlation_id=corr_id,
                inference_id=inference_id,
                direction=direction,
                validation_failures=(
                    f"margin.insufficient:remaining={remaining_free_margin:.2f}<"
                    f"{self._config.min_free_margin_usd:.2f}",
                ),
            )

        # C. Risk budget check
        capital_basis = account.equity if self._config.risk_basis == "EQUITY" else account.balance
        max_budget = capital_basis * (self._config.risk_pct_per_trade / 100.0)
        if plan.risk_amount_usd > (max_budget * 1.0001):  # allowance for epsilon
            logger.info("Calculated risk %s exceeds budget %s", plan.risk_amount_usd, max_budget)
            return RiskEvaluationRecord.reject(
                reason_code=ReasonCode.RISK_LIMIT,
                reason=(
                    f"Calculated risk {plan.risk_amount_usd:.2f} exceeds budget {max_budget:.2f}"
                ),
                correlation_id=corr_id,
                inference_id=inference_id,
                direction=direction,
                validation_failures=(
                    f"risk.budget_exceeded:{plan.risk_amount_usd:.2f}>{max_budget:.2f}",
                ),
            )

        # 5. APPROVE
        logger.info(
            "Trade proposal APPROVED direction=%s lot=%s sl=%s risk_usd=%s",
            direction,
            plan.final_lot,
            plan.sl_price,
            plan.risk_amount_usd,
        )

        return RiskEvaluationRecord(
            risk_evaluation_id=eval_id,
            correlation_id=corr_id,
            inference_id=inference_id,
            decision="APPROVE",
            direction=direction,
            risk_amount=plan.risk_amount_usd,
            risk_percent=plan.risk_pct,
            lot=plan.final_lot,
            exposure=plan.exposure_usd,
            sl=plan.sl_price,
            reason_code=ReasonCode.APPROVED.value,
            reason="Trade proposal satisfies all system risk criteria",
            validation_failures=(),
        )
