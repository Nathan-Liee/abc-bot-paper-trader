"""Shared constants for the ABC Bot paper trader stack.

Values mirror `docs/contracts/canonical-event-contract.md` (v1.0.0) and
must stay consistent with that document.
"""

from __future__ import annotations

SCHEMA_VERSION = "1.0.0"

CHECKSUM_PREFIX = "sha256:"
CHECKSUM_HEX_LENGTH = 64

DEFAULT_COMPONENT = "collector"
DEFAULT_SEVERITY = "INFO"

__all__ = [
    "SCHEMA_VERSION",
    "CHECKSUM_PREFIX",
    "CHECKSUM_HEX_LENGTH",
    "DEFAULT_COMPONENT",
    "DEFAULT_SEVERITY",
]
