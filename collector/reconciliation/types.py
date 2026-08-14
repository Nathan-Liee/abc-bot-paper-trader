"""Internal reconciliation types.

``DiffClassification`` is an *internal* classification vocabulary. It is
deliberately NOT part of the canonical event contract: only the
contract's ``result`` vocabulary (SYNCED / ADOPTED_BROKER / ESCALATED)
leaves this package, inside the canonical ``RECONCILIATION`` payload.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256


class ReconciliationTrigger(StrEnum):
    """Contract triggers for the canonical RECONCILIATION payload."""

    STARTUP = "STARTUP"
    POST_EXECUTION = "POST_EXECUTION"
    HEARTBEAT = "HEARTBEAT"
    MISMATCH = "MISMATCH"


class ReconciliationResult(StrEnum):
    """Contract results; the only vocabulary that reaches the event."""

    SYNCED = "SYNCED"
    ADOPTED_BROKER = "ADOPTED_BROKER"
    ESCALATED = "ESCALATED"


class ShadowState(StrEnum):
    """Reconciliation shadow state machine (task section 17)."""

    UNKNOWN = "UNKNOWN"
    SYNCED = "SYNCED"
    ADOPTED_BROKER = "ADOPTED_BROKER"
    ESCALATED = "ESCALATED"


class DiffClassification(StrEnum):
    """Internal per-entity classification; never emitted as a canonical enum."""

    NO_MISMATCH = "NO_MISMATCH"
    MISSING_LOCAL = "MISSING_LOCAL"
    MISSING_BROKER = "MISSING_BROKER"
    CONFLICTING_STATE = "CONFLICTING_STATE"
    UNKNOWN = "UNKNOWN"
    RECOVERABLE = "RECOVERABLE"
    UNRECOVERABLE = "UNRECOVERABLE"


@dataclass(frozen=True)
class EntityDiff:
    """One deterministic classification for one broker/local entity pairing."""

    entity_type: str
    broker_id: str
    classification: DiffClassification
    reason: str
    local_summary: str
    broker_summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "entity_type": self.entity_type,
            "broker_id": self.broker_id,
            "classification": self.classification.value,
            "reason": self.reason,
            "local_summary": self.local_summary,
            "broker_summary": self.broker_summary,
        }


@dataclass(frozen=True)
class ReconciliationOutcome:
    """Deterministic comparison result for one snapshot."""

    result: ReconciliationResult
    action: str
    mismatch: bool
    local_state: str
    broker_state: str
    diffs: tuple[EntityDiff, ...] = ()
    broker_orphans: int = 0
    local_orphans: int = 0
    state_conflicts: int = 0

    def signature(self, trigger: ReconciliationTrigger) -> str:
        """Stable content hash; identical inputs always hash identically.

        The trigger is part of the signature so each trigger type keeps
        its own audit trail (a POST_EXECUTION run is never skipped just
        because an identical HEARTBEAT run was recorded).
        """
        payload = {
            "trigger": trigger.value,
            "result": self.result.value,
            "action": self.action,
            "mismatch": self.mismatch,
            "local_state": self.local_state,
            "broker_state": self.broker_state,
            "diffs": [diff.to_dict() for diff in self.diffs],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(raw).hexdigest()


__all__ = [
    "DiffClassification",
    "EntityDiff",
    "ReconciliationOutcome",
    "ReconciliationResult",
    "ReconciliationTrigger",
    "ShadowState",
]
