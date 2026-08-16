"""Decision record — the auditable output of the AI Decision Engine.

Fields align with the canonical AI_REQUEST / AI_RESPONSE payload contracts
(shared/contracts/payload_specs.py) so records can later be emitted as
events without schema change. Secrets never appear here.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_inference_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class DecisionRecord:
    """Full audit trail for one inference cycle (including fallback)."""

    # request side
    inference_id: str
    model_id: str
    provider: str
    request_ts: str
    latency_ms: float
    context_snapshot_id: str | None
    prompt_version: str
    correlation_id: str | None = None

    # response side
    direction: str = "NO-TRADE"
    confidence: float = 0.0
    reason: str = ""

    # validation / failure
    validation_ok: bool = False
    schema_errors: tuple[str, ...] = field(default_factory=tuple)
    error_class: str | None = None
    error_detail: str | None = None
    repair: str | None = None

    # fallback / retry bookkeeping
    fallback_level: int = 0
    attempts: int = 0
    retried: bool = False
    total_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def fail_closed(
        cls,
        *,
        error_class: str,
        inference_id: str | None = None,
        model_id: str,
        provider: str,
        request_ts: str | None = None,
        context_snapshot_id: str | None = None,
        prompt_version: str,
        correlation_id: str | None = None,
        latency_ms: float = 0.0,
        total_latency_ms: float = 0.0,
        fallback_level: int = 0,
        attempts: int = 0,
        retried: bool = False,
        error_detail: str | None = None,
        schema_errors: tuple[str, ...] = (),
    ) -> DecisionRecord:
        return cls(
            inference_id=inference_id or new_inference_id(),
            model_id=model_id,
            provider=provider,
            request_ts=request_ts or _now_iso(),
            latency_ms=round(latency_ms, 1),
            context_snapshot_id=context_snapshot_id,
            prompt_version=prompt_version,
            correlation_id=correlation_id,
            validation_ok=False,
            schema_errors=schema_errors,
            error_class=error_class,
            error_detail=error_detail,
            fallback_level=fallback_level,
            attempts=attempts,
            retried=retried,
            total_latency_ms=round(total_latency_ms, 1),
        )
