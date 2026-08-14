"""Persistence-layer error type."""

from __future__ import annotations


class PersistenceError(Exception):
    """Raised when a persistence operation cannot be completed safely.

    Covers open/init failures, corrupt databases, checksum mismatches on
    the audit stream, conflicting duplicate ids, and transaction errors.
    """
