"""Event type taxonomy and severity levels.

Source of truth: docs/contracts/canonical-event-contract.md
sections 2 and 3 (envelope severity enum and event type catalog).
"""

from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
    TICK_RECEIVED = "TICK_RECEIVED"
    TRIGGER_DETECTED = "TRIGGER_DETECTED"
    CONTEXT_BUILT = "CONTEXT_BUILT"
    AI_REQUEST = "AI_REQUEST"
    AI_RESPONSE = "AI_RESPONSE"
    RISK_GATE = "RISK_GATE"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_ACKNOWLEDGED = "ORDER_ACKNOWLEDGED"
    ORDER_FILLED = "ORDER_FILLED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_UPDATED = "POSITION_UPDATED"
    NET_PROFIT_POSITIVE = "NET_PROFIT_POSITIVE"
    EXIT_SUBMITTED = "EXIT_SUBMITTED"
    POSITION_CLOSED = "POSITION_CLOSED"
    RECONCILIATION = "RECONCILIATION"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


SEVERITY_LEVELS = ("INFO", "WARN", "ERROR", "CRITICAL")
