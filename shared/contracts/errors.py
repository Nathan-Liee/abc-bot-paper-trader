"""Contract-level error type shared by contract and event model layers."""

from __future__ import annotations


class ContractValidationError(ValueError):
    """Raised when an event violates the approved canonical event contract."""
