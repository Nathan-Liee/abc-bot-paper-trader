"""Deterministic canonical JSON and SHA-256 checksum for events.

Canonical form: JSON with sorted keys, compact separators, no whitespace,
UTF-8 encoding, and every ``checksum`` key (envelope level and nested in
payloads) removed before hashing.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping

from shared.constants import CHECKSUM_HEX_LENGTH, CHECKSUM_PREFIX


def strip_checksum_fields(value: object) -> object:
    """Return a copy of *value* with every ``checksum`` key removed."""
    if isinstance(value, dict):
        return {
            key: strip_checksum_fields(item) for key, item in value.items() if key != "checksum"
        }
    if isinstance(value, list):
        return [strip_checksum_fields(item) for item in value]
    return value


def canonical_json_str(event: Mapping[str, object]) -> str:
    """Serialize *event* to canonical JSON (sorted keys, no whitespace)."""
    return json.dumps(
        strip_checksum_fields(dict(event)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def canonical_json_bytes(event: Mapping[str, object]) -> bytes:
    """Serialize *event* to canonical JSON encoded as UTF-8."""
    return canonical_json_str(event).encode("utf-8")


def compute_checksum(event: Mapping[str, object]) -> str:
    """Return the ``sha256:<64 hex>`` checksum of *event*."""
    digest = hashlib.sha256(canonical_json_bytes(event)).hexdigest()
    return f"{CHECKSUM_PREFIX}{digest}"


def verify_checksum(event: Mapping[str, object]) -> bool:
    """True when *event*'s checksum field matches its canonical content."""
    expected = compute_checksum(event)
    current = event.get("checksum")
    if not isinstance(current, str):
        return False
    return hmac.compare_digest(expected, current)


def checksum_hex_length_is_sane() -> bool:
    """Guard against drift between constants and the hashing implementation."""
    return CHECKSUM_HEX_LENGTH == 64


__all__ = [
    "canonical_json_bytes",
    "canonical_json_str",
    "compute_checksum",
    "strip_checksum_fields",
    "verify_checksum",
]
