"""In-memory broker state provider (mock boundary).

This provider deliberately never connects to MT5/HFM. It exists so the
reconciliation service, tests, and manual verification runs can exercise
the full pipeline without any live broker connectivity (task section 24
and 25).
"""

from __future__ import annotations

from collector.reconciliation.broker import BrokerSnapshot, BrokerUnavailableError


class StaticBrokerStateProvider:
    """Serves a caller-supplied snapshot; may be flagged unavailable.

    Not frozen state machinery: ``snapshot()`` re-reads the current
    assigned value, so callers can simulate broker state changes between
    reconciliation runs.
    """

    def __init__(
        self, snapshot: BrokerSnapshot | None = None, *, unavailable: bool = False
    ) -> None:
        self.set_snapshot(snapshot if snapshot is not None else BrokerSnapshot())
        self._unavailable = unavailable

    def set_snapshot(self, snapshot: BrokerSnapshot) -> None:
        self._snapshot = snapshot

    def set_unavailable(self, unavailable: bool) -> None:
        self._unavailable = unavailable

    def snapshot(self) -> BrokerSnapshot:
        if self._unavailable:
            raise BrokerUnavailableError("mock broker provider is unavailable")
        return self._snapshot


__all__ = ["StaticBrokerStateProvider"]
