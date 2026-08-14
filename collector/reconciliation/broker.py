"""Broker observed-state abstraction.

This is the external integration boundary for reconciliation. The
protocol defines exactly what the service needs from MT5/HFM. Broker
IDs are preserved verbatim and never generated or transformed here.

The actual live MT5 adapter is out of scope (task section 25): only the
interface and the in-memory mock boundary live in this package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class BrokerUnavailableError(Exception):
    """Raised by a provider when the broker snapshot cannot be collected."""


@dataclass(frozen=True)
class BrokerPosition:
    """Observed broker position; ids preserved verbatim."""

    broker_position_id: str
    symbol: str
    direction: str
    volume: float
    open_price: float
    broker_state: str
    current_price: float | None = None
    timestamps: str | None = None


@dataclass(frozen=True)
class BrokerOrder:
    """Observed broker order; ids preserved verbatim."""

    broker_order_id: str
    state: str
    symbol: str | None = None
    order_type: str | None = None
    volume: float | None = None
    price: float | None = None
    timestamps: str | None = None


@dataclass(frozen=True)
class BrokerSnapshot:
    """One consistent observed view of broker positions and orders."""

    positions: tuple[BrokerPosition, ...] = ()
    orders: tuple[BrokerOrder, ...] = ()


class BrokerStateProvider(Protocol):
    """Collects one consistent broker snapshot.

    Implementations must be safe to call from the single reconciliation
    worker and raise :class:`BrokerUnavailableError` when no snapshot can
    be collected (never return a fabricated or partial snapshot).
    """

    def snapshot(self) -> BrokerSnapshot: ...


__all__ = [
    "BrokerOrder",
    "BrokerPosition",
    "BrokerSnapshot",
    "BrokerStateProvider",
    "BrokerUnavailableError",
]
