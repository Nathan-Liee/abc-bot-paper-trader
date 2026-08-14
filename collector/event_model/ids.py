"""System id generation and validity checks.

System-owned ids are UUIDs generated here; broker-owned ids are opaque
external strings that must never be fabricated (see
``shared.contracts.identity``).
"""

from __future__ import annotations

import uuid


def new_system_id() -> str:
    """Return a fresh system-owned UUID string (lowercase, v4)."""
    return str(uuid.uuid4())


def new_event_id() -> str:
    """Return a fresh event id for an envelope."""
    return new_system_id()


__all__ = ["new_event_id", "new_system_id"]
