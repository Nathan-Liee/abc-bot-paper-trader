"""Reconciliation runner.

Drives the reconciliation service through its lifecycle:

* ``start()``          -> startup reconciliation (before fully synced)
* ``maybe_heartbeat()``-> heartbeat reconciliation on a bounded interval
* ``reconcile_post_execution()`` / ``reconcile_mismatch()`` -> on-demand

Graceful shutdown is cooperative: ``close()`` closes the repository;
the periodic loop exits between polls via ``stop_check``. The runner
never busy-loops and never retries a failed run harder than the
bounded interval provides.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from collector.persistence import PersistenceRepository
from collector.reconciliation.broker import BrokerStateProvider
from collector.reconciliation.errors import ReconciliationError
from collector.reconciliation.reconciler import ReconciliationService, ReconciliationStats
from collector.reconciliation.types import ReconciliationTrigger

logger = logging.getLogger("collector.reconciliation.runner")


class ReconciliationRunner:
    """Periodic + on-demand reconciliation driver."""

    def __init__(
        self,
        repo: PersistenceRepository,
        provider: BrokerStateProvider,
        *,
        interval_seconds: float = 60.0,
        component: str = "collector",
    ) -> None:
        self._repo = repo
        self._provider = provider
        self._interval_seconds = max(float(interval_seconds), 0.05)
        self._component = component
        self._service: ReconciliationService | None = None
        self._last_heartbeat_monotonic: float | None = None
        self._startup_stats: ReconciliationStats | None = None

    @property
    def service(self) -> ReconciliationService | None:
        return self._service

    @property
    def startup_stats(self) -> ReconciliationStats | None:
        return self._startup_stats

    def start(self) -> ReconciliationStats:
        """Open the repository and run startup reconciliation."""
        self._repo.open()
        self._service = ReconciliationService(self._repo, self._provider, component=self._component)
        self._startup_stats = self._run(ReconciliationTrigger.STARTUP)
        self._last_heartbeat_monotonic = time.monotonic()
        return self._startup_stats

    def reconcile_post_execution(self) -> ReconciliationStats:
        """Reconcile immediately after an observed execution event."""
        return self._run(ReconciliationTrigger.POST_EXECUTION)

    def reconcile_mismatch(self) -> ReconciliationStats:
        """Reconcile because a mismatch was suspected elsewhere."""
        return self._run(ReconciliationTrigger.MISMATCH)

    def maybe_heartbeat(self) -> ReconciliationStats | None:
        """Run heartbeat reconciliation when the interval has elapsed."""
        if self._service is None:
            raise RuntimeError("runner not started; call start() first")
        now = time.monotonic()
        if self._last_heartbeat_monotonic is not None and (
            now - self._last_heartbeat_monotonic < self._interval_seconds
        ):
            return None
        self._last_heartbeat_monotonic = now
        return self._run(ReconciliationTrigger.HEARTBEAT)

    def run(self, stop_check: Callable[[], bool] | None = None) -> ReconciliationStats:
        """Periodic heartbeat loop until *stop_check* returns True."""
        if self._service is None:
            self.start()
        stats = self._startup_stats if self._startup_stats is not None else ReconciliationStats()
        while True:
            if stop_check is not None and stop_check():
                break
            heartbeat = self.maybe_heartbeat()
            if heartbeat is not None:
                stats = heartbeat
            time.sleep(min(self._interval_seconds, 1.0))
        return stats

    def close(self) -> None:
        """Flush state and close resources (cursor/state untouched)."""
        self._repo.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run(self, trigger: ReconciliationTrigger) -> ReconciliationStats:
        assert self._service is not None
        try:
            return self._service.run(trigger)
        except ReconciliationError:
            logger.exception("reconciliation: %s failed; retrying on next cycle", trigger.value)
            return ReconciliationStats(reconciliation_runs=1, snapshot_available=True)


__all__ = ["ReconciliationRunner"]
