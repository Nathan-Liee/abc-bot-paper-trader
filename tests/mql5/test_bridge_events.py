"""Contract compatibility tests for MQL5 bridge raw output.

Raw bridge lines (format documented in mql5-bridge/docs/ARCHITECTURE.md)
are canonicalized through the typed event model and validated against
shared/schemas/canonical-event.schema.json - exactly the path the
collector adapter will follow. No live account is required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from collector.event_model import (
    ContractValidationError,
    build_event,
    validate_event_dict,
)
from collector.settings import PROJECT_ROOT
from tests.unit.event_factories import TRADE_ID

SCHEMA_PATH = PROJECT_ROOT / "shared" / "schemas" / "canonical-event.schema.json"

TS = "2026-08-14T09:00:00Z"

TICK_LINE = {
    "event_type": "TICK_RECEIVED",
    "source": "mql5",
    "ts_bridge": TS,
    "payload": {
        "symbol": "XAUUSDc",
        "bid": 2000.0,
        "ask": 2000.5,
        "mid": 2000.25,
        "spread": 0.5,
        "ts_source": TS,
        "tick_volume": 1,
    },
}

TICK_LINE_NO_VOLUME = {
    "event_type": "TICK_RECEIVED",
    "source": "mql5",
    "ts_bridge": TS,
    "payload": {
        "symbol": "XAUUSDc",
        "bid": 1999.5,
        "ask": 2000.0,
        "mid": 1999.75,
        "spread": 0.5,
        "ts_source": TS,
    },
}

ORDER_ACK_LINE = {
    "event_type": "ORDER_ACKNOWLEDGED",
    "source": "mql5",
    "ts_bridge": TS,
    "payload": {
        "broker_order_id": "12345678",
        "broker_state": "PLACED",
        "ack_ts": TS,
    },
}

ORDER_FILL_LINE = {
    "event_type": "ORDER_FILLED",
    "source": "mql5",
    "ts_bridge": TS,
    "payload": {
        "broker_order_id": "12345678",
        "broker_deal_id": "87654321",
        "fill_price": 2000.3,
        "fill_volume": 0.1,
        "slippage": 0.05,
        "fill_ts": TS,
    },
}

POSITION_OPENED_LINE = {
    "event_type": "POSITION_OPENED",
    "source": "mql5",
    "ts_bridge": TS,
    "payload": {
        "broker_position_id": "11223344",
        "direction": "BUY",
        "volume": 0.1,
        "open_price": 2000.3,
        "open_ts": TS,
        "state": "OPEN",
    },
}

POSITION_UPDATED_LINE = {
    "event_type": "POSITION_UPDATED",
    "source": "mql5",
    "ts_bridge": TS,
    "payload": {
        "broker_position_id": "11223344",
        "current_price": 2010.0,
        "running_pnl_usd": 9.7,
        "running_net_pnl_usd": 8.9,
        "mfe_usd": 0.0,
        "mae_usd": 0.0,
        "spread_current": 0.5,
    },
}

POSITION_CLOSED_LINE = {
    "event_type": "POSITION_CLOSED",
    "source": "mql5",
    "ts_bridge": TS,
    "payload": {
        "broker_position_id": "11223344",
        "exit_fill_price": 2010.0,
        "exit_fill_volume": 0.1,
        "exit_fill_ts": TS,
        "realized_pnl_usd": 9.7,
        "transaction_cost_usd": 0.8,
        "net_pnl_usd": 8.9,
        "exit_reason": "tp",
        "final_state": "CLOSED",
    },
}

ERROR_LINE = {
    "event_type": "ERROR",
    "source": "mql5",
    "ts_bridge": TS,
    "payload": {
        "error_code": "BRIDGE_WRITE_FAILED",
        "component": "mql5-bridge",
        "severity": "WARN",
        "message": "bounded write failure",
    },
}

TIMEOUT_LINE = {
    "event_type": "TIMEOUT",
    "source": "mql5",
    "ts_bridge": TS,
    "payload": {
        "timeout_code": "TERMINAL_DISCONNECTED",
        "component": "mql5-bridge",
        "severity": "WARN",
        "message": "terminal connection lost",
    },
}

SNAPSHOT_LINE = {
    "event_type": "POSITION_SNAPSHOT",
    "source": "mql5",
    "ts_bridge": TS,
    "payload": {
        "symbol": "XAUUSDc",
        "positions": [
            {
                "broker_position_id": "11223344",
                "symbol": "XAUUSDc",
                "direction": "BUY",
                "volume": 0.1,
                "open_price": 2000.3,
                "current_price": 2010.0,
                "open_ts": TS,
                "state": "OPEN",
            }
        ],
    },
}

HEARTBEAT_LINE = {
    "event_type": "HEARTBEAT",
    "source": "mql5",
    "ts_bridge": TS,
    "payload": {
        "status": "RUNNING",
        "terminal_connected": True,
        "symbol_available": True,
        "last_tick_ts": TS,
        "exporter_status": "ok",
        "last_successful_write": TS,
        "error_count": 0,
        "tick_count": 42,
        "write_count": 41,
        "position_count": 1,
        "order_count": 0,
    },
}

CANONICAL_LINES = (
    TICK_LINE,
    TICK_LINE_NO_VOLUME,
    ORDER_ACK_LINE,
    ORDER_FILL_LINE,
    POSITION_OPENED_LINE,
    POSITION_UPDATED_LINE,
    POSITION_CLOSED_LINE,
    ERROR_LINE,
    TIMEOUT_LINE,
)

INTERNAL_LINES = (SNAPSHOT_LINE, HEARTBEAT_LINE)


def _schema() -> dict[str, object]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict[str, object]:
    return _schema()


def canonicalize(line: dict[str, object], *, trade_id: str | None = TRADE_ID):
    """Emulate the collector adapter: envelope identity + checksum."""
    payload = line["payload"]
    assert isinstance(payload, dict)
    return build_event(line["event_type"], payload, trade_id=trade_id)


def _validate_against_schema(envelope: object, schema: dict[str, object]) -> None:
    data = envelope.to_dict()
    validate_event_dict(data)
    Draft202012Validator(schema).validate(data)


@pytest.mark.parametrize("line", CANONICAL_LINES)
def test_canonical_bridge_lines_pass_schema(
    line: dict[str, object], schema: dict[str, object]
) -> None:
    envelope = canonicalize(line)
    assert envelope.event_type.value == line["event_type"]
    _validate_against_schema(envelope, schema)


def test_jsonl_line_format_is_single_line_and_ascii() -> None:
    for line in (*CANONICAL_LINES, *INTERNAL_LINES):
        serialized = json.dumps(line, ensure_ascii=True, separators=(",", ":"))
        assert "\n" not in serialized
        serialized.encode("ascii")
        parsed = json.loads(serialized)
        assert parsed["event_type"] == line["event_type"]


def test_tick_mid_and_spread_derivation() -> None:
    payload = TICK_LINE["payload"]
    bid = payload["bid"]
    ask = payload["ask"]
    assert payload["mid"] == (bid + ask) / 2
    assert payload["spread"] == ask - bid


def test_duplicate_timestamp_ticks_are_all_accepted(schema: dict[str, object]) -> None:
    first = canonicalize(TICK_LINE)
    second = canonicalize(TICK_LINE)
    _validate_against_schema(first, schema)
    _validate_against_schema(second, schema)
    assert first.event_id != second.event_id
    assert first.payload == second.payload


def test_malformed_payload_is_rejected_by_schema_layer() -> None:
    malformed = {
        "event_type": "TICK_RECEIVED",
        "source": "mql5",
        "ts_bridge": TS,
        "payload": {"symbol": "XAUUSDc", "bid": 2000.0, "ask": 2000.5},
    }
    with pytest.raises(ContractValidationError, match="missing required field"):
        canonicalize(malformed)


def test_internal_lines_are_json_but_not_canonicalizable() -> None:
    for line in INTERNAL_LINES:
        with pytest.raises(ContractValidationError, match="unknown event type"):
            canonicalize(line)


def test_append_behavior_and_restart(tmp_path: Path) -> None:
    path = tmp_path / "mql5_bridge_events.jsonl"
    lines = [json.dumps(line, ensure_ascii=True, separators=(",", ":")) for line in CANONICAL_LINES]
    with path.open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(lines[0] + "\n")
    stored = path.read_text(encoding="utf-8").strip().splitlines()
    assert stored == [*lines, lines[0]]
    for stored_line in stored:
        json.loads(stored_line)


def test_bridge_compat_roundtrip_via_event_model(schema: dict[str, object]) -> None:
    for line in CANONICAL_LINES:
        envelope = canonicalize(line)
        from collector.event_model import from_json, to_json

        restored = from_json(to_json(envelope))
        assert restored == envelope
