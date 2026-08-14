"""Replay tests over committed synthetic fixtures.

The fixtures are produced by ``scripts/generate_replay_fixtures.py`` and
contain no real broker or demo data. These tests simulate replaying an
event stream: parse each line, verify checksums, and validate the
sequence against the contract lifecycle.
"""

from __future__ import annotations

import json

import pytest

from collector.event_model import ContractValidationError, from_json, validate_sequence
from collector.settings import PROJECT_ROOT

FIXTURES_DIR = PROJECT_ROOT / "tests" / "replay" / "fixtures"

FIXTURE_FILES = (
    "trade_lifecycle.jsonl",
    "risk_rejection.jsonl",
    "duplicate_ticks.jsonl",
    "malformed.jsonl",
    "checksum_tamper.jsonl",
)


def _read_lines(name: str) -> list[str]:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("name", FIXTURE_FILES)
def test_fixture_file_is_present_and_nonempty(name: str) -> None:
    assert (FIXTURES_DIR / name).is_file(), f"missing fixture {name}"
    assert _read_lines(name)


def test_trade_lifecycle_replays_end_to_end() -> None:
    events = [from_json(line) for line in _read_lines("trade_lifecycle.jsonl")]
    assert [event.event_type.value for event in events] == [
        "TRIGGER_DETECTED",
        "CONTEXT_BUILT",
        "AI_REQUEST",
        "AI_RESPONSE",
        "RISK_GATE",
        "ORDER_SUBMITTED",
        "ORDER_ACKNOWLEDGED",
        "ORDER_FILLED",
        "POSITION_OPENED",
        "POSITION_UPDATED",
        "NET_PROFIT_POSITIVE",
        "EXIT_SUBMITTED",
        "POSITION_CLOSED",
    ]
    for event in events:
        assert event.verify_checksum()
    validate_sequence(events)


def test_risk_rejection_replays() -> None:
    events = [from_json(line) for line in _read_lines("risk_rejection.jsonl")]
    validate_sequence(events)
    assert events[-1].event_type.value == "ERROR"


def test_duplicate_ticks_replay_preserves_append_only_semantics() -> None:
    events = [from_json(line) for line in _read_lines("duplicate_ticks.jsonl")]
    validate_sequence(events)
    assert len(events) == 3
    ts_events = {event.ts_event for event in events}
    assert len(ts_events) == 1


def test_malformed_fixture_is_rejected() -> None:
    with pytest.raises((ContractValidationError, json.JSONDecodeError)):
        from_json(_read_lines("malformed.jsonl")[0])


def test_checksum_tamper_fixture_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="checksum mismatch"):
        from_json(_read_lines("checksum_tamper.jsonl")[0])


def test_every_fixture_line_is_compact_json() -> None:
    for name in FIXTURE_FILES:
        for line in _read_lines(name):
            parsed = json.loads(line)
            assert isinstance(parsed, dict)
