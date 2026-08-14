"""Timestamp validation and generation for the canonical event model.

Source of truth: docs/contracts/canonical-event-contract.md section 5
(Timestamps). ``ts_event`` carries the precision the source actually
observed (seconds or milliseconds); ``ts_collected`` is always UTC with
millisecond precision; ``ts_monotonic`` is the process monotonic clock in
milliseconds.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

ISO_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z$")
ISO_UTC_MS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def is_valid_iso_utc(value: object) -> bool:
    """True when *value* is an ISO 8601 UTC timestamp in the contract shape.

    Allowed shapes: ``YYYY-MM-DDTHH:MM:SSZ`` and
    ``YYYY-MM-DDTHH:MM:SS.mmmZ``. Fractional precision other than zero or
    three digits is rejected (no fabricated precision), as are non-UTC
    offsets and impossible calendar dates.
    """
    if not isinstance(value, str):
        return False
    if ISO_UTC_PATTERN.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def is_valid_iso_utc_ms(value: object) -> bool:
    """True when *value* is an ISO 8601 UTC timestamp with milliseconds."""
    if not isinstance(value, str):
        return False
    if ISO_UTC_MS_PATTERN.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def now_utc_ms() -> str:
    """Return the current UTC time as ``YYYY-MM-DDTHH:MM:SS.mmmZ``."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def monotonic_ms() -> int:
    """Return the process monotonic clock in integer milliseconds."""
    import time

    return int(time.monotonic() * 1000)


__all__ = [
    "ISO_UTC_MS_PATTERN",
    "ISO_UTC_PATTERN",
    "is_valid_iso_utc",
    "is_valid_iso_utc_ms",
    "monotonic_ms",
    "now_utc_ms",
]
