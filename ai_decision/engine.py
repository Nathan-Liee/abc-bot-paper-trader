"""Decision engine orchestrator — proposal-only, bounded, auditable.

Flow: market context -> prompt construction -> inference -> parsing ->
schema validation -> decision validation -> BUY/SELL/NO-TRADE proposal.

The engine NEVER computes lot/risk/SL/exposure/margin/execution/exit and
never touches MT5. System-side approval is a separate gate (interface only
in this task — see ai_decision/gate.py).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ai_decision.client import TransportResult, chat_completion
from ai_decision.config import EngineConfig, Secrets
from ai_decision.parsing import parse_and_normalize
from ai_decision.prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from ai_decision.record import DecisionRecord, new_inference_id
from ai_decision.validation import validate_schema

logger = logging.getLogger("ai_decision")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


Transport = Callable[..., TransportResult]

# Minimal locked market-context shape (project context): symbol, prices,
# spread, M1/M5 contexts, ATR. m5 may be None (insufficient context) but the
# key must exist; derived features are optional and passed through untouched.
REQUIRED_CONTEXT_KEYS = ("symbol", "bid", "ask", "spread", "mid", "atr_m1", "m1", "m5")
NUMERIC_CONTEXT_KEYS = ("bid", "ask", "spread", "mid", "atr_m1")

# Failure classes that justify a bounded retry on the same model. HTTP 400 /
# 401 / 403 are deterministic request/auth problems — retrying would be
# unsafe, so the engine moves to the next fallback level immediately.
RETRYABLE_STATUSES = ("TIMEOUT", "TRANSPORT_ERROR", "HTTP429", "HTTP5XX")


def _classify_http(status: str) -> str:
    if status.startswith("HTTP") and len(status) >= 6:
        code = status[4:7]
        if code.isdigit() and code[0] == "5":
            return "HTTP5XX"
        return status
    return status


class DecisionEngine:
    """Primary/secondary/fallback inference with fail-closed safety."""

    def __init__(
        self,
        config: EngineConfig,
        secrets: Secrets,
        transport: Transport | None = None,
    ) -> None:
        self._config = config
        self._secrets = secrets
        self._transport: Transport = transport or chat_completion

    @property
    def config(self) -> EngineConfig:
        return self._config

    def _call(
        self,
        model_id: str,
        provider: str,
        messages: list[dict[str, str]],
        timeout_s: float,
    ) -> TransportResult:
        return self._transport(
            self._config.base_url,
            self._secrets.api_key,
            model_id,
            messages,
            timeout_s=timeout_s,
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
        )

    def decide(
        self,
        context: dict[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> DecisionRecord:
        t0 = time.monotonic()
        inference_id = new_inference_id()
        request_ts = _now_iso()

        missing = validate_context(context)
        if missing:
            record = DecisionRecord.fail_closed(
                error_class="INVALID_CONTEXT",
                model_id=self._config.primary.model_id,
                provider=self._config.primary.provider,
                context_snapshot_id=_snapshot(context),
                prompt_version=PROMPT_VERSION,
                correlation_id=correlation_id,
                error_detail="missing keys: " + ",".join(sorted(missing)),
            )
            logger.warning("AI decision rejected: %s", record.error_detail)
            return record

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(context)},
        ]
        snapshot = _snapshot(context)
        last_status: str | None = None
        last_detail: str | None = None

        for level, model in enumerate(self._config.chain):
            for attempt in range(self._config.max_attempts):
                result = self._call(
                    model.model_id, model.provider, messages, self._config.timeout_s
                )
                latency = result.latency_ms
                status = _classify_http(result.status)
                last_status = result.status
                last_detail = result.error

                if result.status == "OK":
                    parsed = parse_and_normalize(result.raw)
                    if not parsed.ok:
                        logger.warning(
                            "AI parse failed model=%s level=%s attempt=%s error=%s",
                            model.model_id,
                            level,
                            attempt,
                            parsed.error,
                        )
                        return DecisionRecord.fail_closed(
                            error_class="PARSE_ERROR",
                            model_id=model.model_id,
                            provider=model.provider,
                            request_ts=request_ts,
                            context_snapshot_id=snapshot,
                            prompt_version=PROMPT_VERSION,
                            correlation_id=correlation_id,
                            latency_ms=latency,
                            total_latency_ms=(time.monotonic() - t0) * 1000,
                            fallback_level=level,
                            attempts=attempt + 1,
                            retried=attempt > 0,
                            error_detail=parsed.error,
                        )

                    ok, errors_list, triple = validate_schema(parsed.output, parsed.payload_keys)
                    errors = list(errors_list)
                    if not ok:
                        is_authority = any("AUTHORITY_VIOLATION" in e for e in errors)
                        logger.warning(
                            "AI schema rejected model=%s errors=%s",
                            model.model_id,
                            errors,
                        )
                        return DecisionRecord.fail_closed(
                            error_class="AUTHORITY_VIOLATION" if is_authority else "SCHEMA_ERROR",
                            model_id=model.model_id,
                            provider=model.provider,
                            request_ts=request_ts,
                            context_snapshot_id=snapshot,
                            prompt_version=PROMPT_VERSION,
                            correlation_id=correlation_id,
                            latency_ms=latency,
                            total_latency_ms=(time.monotonic() - t0) * 1000,
                            fallback_level=level,
                            attempts=attempt + 1,
                            retried=attempt > 0,
                            schema_errors=tuple(errors),
                            error_detail=";".join(errors),
                        )

                    assert triple is not None
                    direction, confidence, reason = triple
                    logger.info(
                        "AI decision model=%s level=%s direction=%s confidence=%s latency_ms=%s",
                        model.model_id,
                        level,
                        direction,
                        confidence,
                        round(latency, 1),
                    )
                    return DecisionRecord(
                        inference_id=inference_id,
                        model_id=model.model_id,
                        provider=model.provider,
                        request_ts=request_ts or "",
                        latency_ms=round(latency, 1),
                        context_snapshot_id=snapshot,
                        prompt_version=PROMPT_VERSION,
                        correlation_id=correlation_id,
                        direction=direction,
                        confidence=confidence,
                        reason=reason,
                        validation_ok=True,
                        repair=parsed.repair,
                        fallback_level=level,
                        attempts=attempt + 1,
                        retried=attempt > 0,
                        total_latency_ms=round((time.monotonic() - t0) * 1000, 1),
                    )

                # transport / provider failure path
                retryable = status in RETRYABLE_STATUSES
                if retryable and attempt + 1 < self._config.max_attempts:
                    if result.status == "HTTP429":
                        time.sleep(self._config.retry_429_sleep_s)
                    continue
                # no retries left for this level -> next fallback level
                break

        logger.error(
            "AI provider chain exhausted last_status=%s detail=%s",
            last_status,
            last_detail,
        )
        return DecisionRecord.fail_closed(
            error_class="PROVIDER_FAILURE",
            model_id=self._config.fallback.model_id,
            provider=self._config.fallback.provider,
            request_ts=request_ts,
            context_snapshot_id=snapshot,
            prompt_version=PROMPT_VERSION,
            correlation_id=correlation_id,
            total_latency_ms=(time.monotonic() - t0) * 1000,
            fallback_level=3,
            attempts=self._config.max_attempts,
            retried=True,
            error_detail=f"last_status={last_status} detail={last_detail}",
        )


def validate_context(context: dict[str, Any]) -> list[str]:
    """Return missing/invalid context keys; empty list means the context is usable."""
    missing = [k for k in REQUIRED_CONTEXT_KEYS if k not in context]
    if missing:
        return missing
    bad: list[str] = []
    for key in NUMERIC_CONTEXT_KEYS:
        value = context[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            bad.append(f"{key}:not_number")
        elif not (value == value):  # NaN check
            bad.append(f"{key}:nan")
    if not isinstance(context.get("m1"), dict):
        bad.append("m1:not_dict")
    m5 = context.get("m5")
    if m5 is not None and not isinstance(m5, dict):
        bad.append("m5:not_dict")
    return bad


def _snapshot(context: dict[str, Any]) -> str | None:
    value = context.get("context_snapshot_id")
    return value if isinstance(value, str) and value else None
