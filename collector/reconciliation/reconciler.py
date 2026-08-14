"""Reconciliation service.

OBSERVE -> COMPARE -> CLASSIFY -> RECORD -> ESCALATE / ADOPT.

Safety: the service contains no execution capability. It never submits,
modifies, or deletes orders, never closes positions, and never changes
risk or lot parameters. Adoption records observed broker state with
explicit lineage; it never fabricates canonical events for unobserved
history (task sections 16 and 18).

Idempotency: the reconciliation id is a deterministic ``uuid5`` derived
from the outcome signature. Repeated identical snapshots produce the
same outcome and are skipped (no duplicate events, no state churn);
replayed events are absorbed by existing persistence idempotency.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass

from jsonschema import Draft202012Validator, ValidationError

from collector.event_model import (
    EventEnvelope,
    EventType,
    build_event,
    monotonic_ms,
    now_utc_ms,
)
from collector.persistence import PersistenceError, PersistenceRepository
from collector.persistence.reconciling import AdoptionRecord, ReconciliationRunRecord
from collector.reconciliation.broker import (
    BrokerSnapshot,
    BrokerStateProvider,
    BrokerUnavailableError,
)
from collector.reconciliation.classifier import classify
from collector.reconciliation.errors import ReconciliationError
from collector.reconciliation.types import (
    DiffClassification,
    ReconciliationOutcome,
    ReconciliationResult,
    ReconciliationTrigger,
    ShadowState,
)
from collector.settings import PROJECT_ROOT

logger = logging.getLogger("collector.reconciliation")

SCHEMA_PATH = PROJECT_ROOT / "shared" / "schemas" / "canonical-event.schema.json"

_ID_NAMESPACE = uuid.NAMESPACE_URL


@dataclass(frozen=True)
class ReconciliationStats:
    """Observability counters for reconciliation runs (task section 20)."""

    reconciliation_runs: int = 0
    reconciliation_success: int = 0
    reconciliation_adopted: int = 0
    reconciliation_escalated: int = 0
    local_orphans: int = 0
    broker_orphans: int = 0
    state_conflicts: int = 0
    snapshot_available: bool = True
    skipped_identical: int = 0
    reconciliation_latency_ms: int = 0
    last_successful_reconciliation: str | None = None
    last_mismatch_timestamp: str | None = None
    latest_result: str | None = None
    latest_reconciliation_id: str | None = None


class ReconciliationService:
    """Runs one reconciliation at a time against a broker state provider."""

    def __init__(
        self,
        repo: PersistenceRepository,
        provider: BrokerStateProvider,
        *,
        component: str = "collector",
    ) -> None:
        self._repo = repo
        self._provider = provider
        self._component = component
        self._validator: Draft202012Validator | None = None

    @property
    def shadow_state(self) -> ShadowState:
        """Current shadow state: last persisted result, or UNKNOWN."""
        latest = self._repo.get_latest_reconciliation_run()
        if latest is None:
            return ShadowState.UNKNOWN
        return _shadow_state_for(latest.result)

    @property
    def is_synced(self) -> bool:
        return self.shadow_state is ShadowState.SYNCED

    @property
    def is_degraded(self) -> bool:
        return self.shadow_state in (ShadowState.UNKNOWN, ShadowState.ESCALATED)

    def run(self, trigger: ReconciliationTrigger) -> ReconciliationStats:
        """Run one reconciliation and record it (single transaction)."""
        started = monotonic_ms()
        run_ts = now_utc_ms()

        try:
            snapshot = self._provider.snapshot()
        except BrokerUnavailableError as exc:
            return self._snapshot_unavailable(trigger, run_ts, str(exc), started)

        local_positions = self._repo.open_positions()
        local_orders = self._repo.open_orders()
        outcome = classify(local_positions, local_orders, snapshot)
        signature = outcome.signature(trigger)

        latest = self._repo.get_latest_reconciliation_run()
        if (
            latest is not None
            and latest.signature == signature
            and latest.result == outcome.result.value
        ):
            logger.info(
                "reconciliation: %s unchanged (%s); skipping identical run",
                trigger.value,
                outcome.result.value,
            )
            return self._stats_for(
                outcome=outcome,
                started=started,
                run_ts=run_ts,
                runs=1,
                skipped_identical=1,
                latest=latest,
            )

        reconciliation_id = str(uuid.uuid5(_ID_NAMESPACE, f"abc-bot:reconciliation:{signature}"))
        event, run_record = self._build_run(trigger, outcome, reconciliation_id, run_ts)
        adoptions = tuple(
            adoption
            for adoption in self._adoptions_for(outcome, snapshot, reconciliation_id, run_ts)
        )

        try:
            self._repo.save_reconciliation_run(event, run_record, adoptions)
        except PersistenceError as exc:
            logger.error(
                "reconciliation: persistence failed for %s run %s: %s",
                trigger.value,
                reconciliation_id,
                exc,
            )
            raise ReconciliationError(
                f"reconciliation run {reconciliation_id} failed to persist: {exc}", cause=exc
            ) from exc

        stats = self._stats_for(
            outcome=outcome,
            started=started,
            run_ts=run_ts,
            runs=1,
            latest=None,
            reconciliation_id=reconciliation_id,
        )

        if outcome.result is ReconciliationResult.ESCALATED:
            logger.warning(
                "reconciliation: %s -> %s (orphans local=%d broker=%d conflicts=%d); degraded",
                trigger.value,
                outcome.result.value,
                outcome.local_orphans,
                outcome.broker_orphans,
                outcome.state_conflicts,
            )
        elif outcome.result is ReconciliationResult.ADOPTED_BROKER:
            logger.info(
                "reconciliation: %s -> %s (%d broker entities adopted)",
                trigger.value,
                outcome.result.value,
                len(adoptions),
            )
        else:
            logger.info("reconciliation: %s -> %s", trigger.value, outcome.result.value)
        return stats

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _snapshot_unavailable(
        self, trigger: ReconciliationTrigger, run_ts: str, message: str, started: int
    ) -> ReconciliationStats:
        logger.error(
            "reconciliation: broker snapshot unavailable during %s: %s", trigger.value, message
        )
        try:
            self._repo.insert_event(
                build_event(
                    EventType.TIMEOUT,
                    {
                        "timeout_code": "RECONCILIATION_SNAPSHOT_UNAVAILABLE",
                        "component": self._component,
                        "severity": "WARN",
                        "message": f"{trigger.value}: {message}",
                    },
                    ts_event=run_ts,
                )
            )
        except PersistenceError as exc:
            logger.error("reconciliation: failed to record snapshot timeout: %s", exc)
        return ReconciliationStats(
            reconciliation_runs=1,
            reconciliation_latency_ms=max(0, monotonic_ms() - started),
            snapshot_available=False,
            latest_result=None,
            last_mismatch_timestamp=run_ts,
        )

    def _build_run(
        self,
        trigger: ReconciliationTrigger,
        outcome: ReconciliationOutcome,
        reconciliation_id: str,
        run_ts: str,
    ) -> tuple[EventEnvelope, ReconciliationRunRecord]:
        payload: dict[str, object] = {
            "reconciliation_id": reconciliation_id,
            "trigger": trigger.value,
            "local_state": outcome.local_state,
            "broker_state": outcome.broker_state,
            "mismatch": outcome.mismatch,
            "result": outcome.result.value,
            "action": outcome.action,
            "ts": run_ts,
        }
        if outcome.mismatch:
            payload["mismatch_details"] = {
                "diffs": [diff.to_dict() for diff in outcome.diffs],
                "broker_orphans": outcome.broker_orphans,
                "local_orphans": outcome.local_orphans,
                "state_conflicts": outcome.state_conflicts,
            }
        event = build_event(EventType.RECONCILIATION, payload, ts_event=run_ts)
        self._validate_schema(event)
        run_record = ReconciliationRunRecord(
            reconciliation_id=reconciliation_id,
            trigger=trigger.value,
            signature=outcome.signature(trigger),
            result=outcome.result.value,
            action=outcome.action,
            mismatch=outcome.mismatch,
            run_ts=run_ts,
        )
        return event, run_record

    def _adoptions_for(
        self,
        outcome: ReconciliationOutcome,
        snapshot: BrokerSnapshot,
        reconciliation_id: str,
        run_ts: str,
    ) -> list[AdoptionRecord]:
        positions = {p.broker_position_id: p for p in snapshot.positions}
        orders = {o.broker_order_id: o for o in snapshot.orders}
        adoptions: list[AdoptionRecord] = []
        for diff in outcome.diffs:
            if diff.classification is not DiffClassification.RECOVERABLE:
                continue
            if diff.entity_type == "POSITION":
                position = positions.get(diff.broker_id)
                if position is None:
                    continue
                adoptions.append(
                    AdoptionRecord(
                        adoption_id=str(
                            uuid.uuid5(
                                _ID_NAMESPACE,
                                f"abc-bot:adoption:{diff.entity_type}:{diff.broker_id}:{reconciliation_id}",
                            )
                        ),
                        reconciliation_id=reconciliation_id,
                        entity_type="POSITION",
                        broker_id=position.broker_position_id,
                        symbol=position.symbol,
                        direction=position.direction,
                        volume=position.volume,
                        open_price=position.open_price,
                        broker_state=position.broker_state,
                        reason=diff.reason,
                        adopted_ts=run_ts,
                    )
                )
            elif diff.entity_type == "ORDER":
                order = orders.get(diff.broker_id)
                if order is None:
                    continue
                adoptions.append(
                    AdoptionRecord(
                        adoption_id=str(
                            uuid.uuid5(
                                _ID_NAMESPACE,
                                f"abc-bot:adoption:{diff.entity_type}:{diff.broker_id}:{reconciliation_id}",
                            )
                        ),
                        reconciliation_id=reconciliation_id,
                        entity_type="ORDER",
                        broker_id=order.broker_order_id,
                        symbol=order.symbol,
                        direction=None,
                        volume=order.volume,
                        open_price=order.price,
                        broker_state=order.state,
                        reason=diff.reason,
                        adopted_ts=run_ts,
                    )
                )
        adoptions.sort(key=lambda item: (item.entity_type, item.broker_id))
        return adoptions

    def _stats_for(
        self,
        *,
        outcome: ReconciliationOutcome,
        started: int,
        run_ts: str,
        runs: int,
        skipped_identical: int = 0,
        latest: ReconciliationRunRecord | None = None,
        reconciliation_id: str | None = None,
    ) -> ReconciliationStats:
        if latest is not None:
            result = latest.result
            reconciliation_id = latest.reconciliation_id
            run_ts = latest.run_ts
        else:
            result = outcome.result.value
        success = (
            1
            if result
            in (ReconciliationResult.SYNCED.value, ReconciliationResult.ADOPTED_BROKER.value)
            else 0
        )
        return ReconciliationStats(
            reconciliation_runs=runs,
            reconciliation_success=success,
            reconciliation_adopted=1 if result == ReconciliationResult.ADOPTED_BROKER.value else 0,
            reconciliation_escalated=1 if result == ReconciliationResult.ESCALATED.value else 0,
            local_orphans=outcome.local_orphans,
            broker_orphans=outcome.broker_orphans,
            state_conflicts=outcome.state_conflicts,
            skipped_identical=skipped_identical,
            reconciliation_latency_ms=max(0, monotonic_ms() - started),
            last_successful_reconciliation=run_ts if success else None,
            last_mismatch_timestamp=run_ts if outcome.mismatch else None,
            latest_result=result,
            latest_reconciliation_id=reconciliation_id,
        )

    def _validate_schema(self, event: EventEnvelope) -> None:
        if self._validator is None:
            with SCHEMA_PATH.open(encoding="utf-8") as fh:
                self._validator = Draft202012Validator(json.load(fh))
        try:
            self._validator.validate(event.to_dict())
        except ValidationError as exc:
            raise ReconciliationError(
                f"reconciliation event {event.event_id} violates the canonical schema: {exc}"
            ) from exc


def _shadow_state_for(result: str) -> ShadowState:
    for state in (ShadowState.SYNCED, ShadowState.ADOPTED_BROKER, ShadowState.ESCALATED):
        if state.value == result:
            return state
    return ShadowState.UNKNOWN


__all__ = ["ReconciliationService", "ReconciliationStats"]
