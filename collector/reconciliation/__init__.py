"""Reconciliation service: integrity mechanism, not a trading engine.

OBSERVE -> COMPARE -> CLASSIFY -> RECORD -> ESCALATE / ADOPT.

Only observed-state integrity lives here: no order submission, no
position management, no risk or lot changes, no AI (task sections 16
and 22). The broker interface is the external integration boundary; only
the mock provider is implemented in this package.
"""

from collector.reconciliation.broker import (
    BrokerOrder,
    BrokerPosition,
    BrokerSnapshot,
    BrokerStateProvider,
    BrokerUnavailableError,
)
from collector.reconciliation.classifier import classify
from collector.reconciliation.errors import ReconciliationError
from collector.reconciliation.mock import StaticBrokerStateProvider
from collector.reconciliation.reconciler import ReconciliationService, ReconciliationStats
from collector.reconciliation.runner import ReconciliationRunner
from collector.reconciliation.types import (
    DiffClassification,
    EntityDiff,
    ReconciliationOutcome,
    ReconciliationResult,
    ReconciliationTrigger,
    ShadowState,
)

__all__ = [
    "BrokerOrder",
    "BrokerPosition",
    "BrokerSnapshot",
    "BrokerStateProvider",
    "BrokerUnavailableError",
    "DiffClassification",
    "EntityDiff",
    "ReconciliationError",
    "ReconciliationOutcome",
    "ReconciliationResult",
    "ReconciliationRunner",
    "ReconciliationService",
    "ReconciliationStats",
    "ReconciliationTrigger",
    "ShadowState",
    "StaticBrokerStateProvider",
    "classify",
]
