"""Timestamp validation tests."""

from __future__ import annotations

from collector.event_model import (
    is_valid_iso_utc,
    is_valid_iso_utc_ms,
    monotonic_ms,
    now_utc_ms,
)


def test_valid_second_precision_timestamp() -> None:
    assert is_valid_iso_utc("2026-08-14T09:00:00Z")


def test_valid_millisecond_precision_timestamp() -> None:
    assert is_valid_iso_utc("2026-08-14T09:00:00.123Z")
    assert is_valid_iso_utc_ms("2026-08-14T09:00:00.123Z")


def test_millisecond_precision_required_for_ms_variant() -> None:
    assert not is_valid_iso_utc_ms("2026-08-14T09:00:00Z")


def test_fabricated_precision_is_rejected() -> None:
    assert not is_valid_iso_utc("2026-08-14T09:00:00.1Z")
    assert not is_valid_iso_utc("2026-08-14T09:00:00.12Z")
    assert not is_valid_iso_utc("2026-08-14T09:00:00.1234Z")


def test_non_utc_offsets_are_rejected() -> None:
    assert not is_valid_iso_utc("2026-08-14T09:00:00+07:00")
    assert not is_valid_iso_utc("2026-08-14T09:00:00+0000")


def test_impossible_dates_are_rejected() -> None:
    assert not is_valid_iso_utc("2026-02-30T09:00:00Z")
    assert not is_valid_iso_utc("2026-13-01T09:00:00Z")


def test_non_strings_are_rejected() -> None:
    assert not is_valid_iso_utc(None)
    assert not is_valid_iso_utc(20260814)
    assert not is_valid_iso_utc(["2026-08-14T09:00:00Z"])


def test_lowercase_z_is_rejected() -> None:
    assert not is_valid_iso_utc("2026-08-14T09:00:00z")


def test_generated_now_is_valid_utc_ms() -> None:
    assert is_valid_iso_utc_ms(now_utc_ms())
    assert is_valid_iso_utc(now_utc_ms())


def test_monotonic_ms_is_non_negative_integer() -> None:
    value = monotonic_ms()
    assert isinstance(value, int)
    assert value >= 0
