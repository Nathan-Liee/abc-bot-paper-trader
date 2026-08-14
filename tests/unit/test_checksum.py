"""Checksum tests: determinism, tamper detection, field exclusion."""

from __future__ import annotations

from collector.event_model import (
    build_event,
    canonical_json_str,
    compute_checksum,
    strip_checksum_fields,
    verify_checksum,
)
from shared.contracts.types import EventType
from tests.unit.event_factories import TRADE_ID, ai_response_payload


def _event_dict(**payload_overrides: object) -> dict[str, object]:
    payload = {
        "symbol": "XAUUSD",
        "bid": 2000.0,
        "ask": 2000.5,
        "mid": 2000.25,
        "spread": 0.5,
        "ts_source": "2026-08-14T09:00:00Z",
        **payload_overrides,
    }
    return build_event(EventType.TICK_RECEIVED, payload).to_dict()


def test_same_event_dict_same_checksum() -> None:
    first = _event_dict()
    assert first["checksum"] == compute_checksum(first)
    assert first["checksum"] == compute_checksum(dict(first))


def test_checksum_format() -> None:
    checksum = _event_dict()["checksum"]
    assert isinstance(checksum, str)
    assert checksum.startswith("sha256:")
    assert len(checksum) == len("sha256:") + 64


def test_different_content_different_checksum() -> None:
    base = _event_dict()
    tampered = {"payload": {**base["payload"], "bid": 2001.0}}
    assert compute_checksum(tampered) != base["checksum"]


def test_checksum_field_excluded_from_hash() -> None:
    base = _event_dict()
    computed = compute_checksum(base)
    assert computed == base["checksum"]


def test_verify_checksum_rejects_tampering() -> None:
    event = _event_dict()
    tampered = dict(event)
    tampered["payload"] = dict(tampered["payload"])
    tampered["payload"]["bid"] = 9999.0
    assert not verify_checksum(tampered)


def test_nested_checksum_field_is_stripped() -> None:
    base = _event_dict()
    with_nested = dict(base)
    with_nested["payload"] = {**with_nested["payload"], "checksum": "sha256:" + "f" * 64}
    assert compute_checksum(with_nested) == base["checksum"]


def test_canonical_json_is_deterministic_regardless_of_key_order() -> None:
    payload = {"a": 1, "b": {"c": 2, "d": 3}}
    left = canonical_json_str({"z": 9, "payload": payload})
    right = canonical_json_str({"payload": dict(reversed(list(payload.items()))), "z": 9})
    assert left == right


def test_strip_checksum_fields_removes_all_levels() -> None:
    data = {"checksum": "x", "payload": {"a": {"checksum": "y", "b": 1}}}
    assert strip_checksum_fields(data) == {"payload": {"a": {"b": 1}}}


def test_checksum_is_utf8_aware() -> None:
    event = build_event(
        EventType.AI_RESPONSE,
        ai_response_payload(reason="momentum terkonfirmasi"),
        trade_id=TRADE_ID,
    )
    assert event.verify_checksum()
    assert event.payload["reason"] == "momentum terkonfirmasi"
