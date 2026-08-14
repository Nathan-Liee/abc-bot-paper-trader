"""Raw bridge line normalization tests."""

from __future__ import annotations

import pytest

from collector.adapters.errors import InvalidLineError
from collector.adapters.normalize import RawLineKind, normalize_bridge_line, parse_raw_line
from shared.contracts.types import EventType

TS = "2026-08-14T09:00:00Z"
TS_COLLECTED = "2026-08-14T09:00:00.000Z"


def _line(payload: dict, event_type: str = "TICK_RECEIVED") -> dict:
    return {"event_type": event_type, "source": "mql5", "ts_bridge": TS, "payload": payload}


def _norm(payload: dict, event_type: str = "TICK_RECEIVED"):
    return normalize_bridge_line(_line(payload, event_type), ts_collected=TS_COLLECTED)


def test_valid_bridge_tick_normalizes() -> None:
    result = _norm(
        {
            "symbol": "XAUUSDc",
            "bid": "2000.5",
            "ask": 2000.6,
            "mid": 2000.55,
            "spread": "0.1",
            "ts_source": TS,
            "tick_volume": "3",
        }
    )
    assert result.kind is RawLineKind.CANONICAL
    assert result.event_type is EventType.TICK_RECEIVED
    assert result.payload is not None
    assert result.payload["symbol"] == "XAUUSDc"
    assert result.payload["bid"] == 2000.5
    assert result.payload["ask"] == 2000.6
    assert result.payload["spread"] == 0.1
    assert result.payload["tick_volume"] == 3
    assert isinstance(result.payload["tick_volume"], int)
    assert result.payload["ts_source"] == TS


def test_symbol_preserved_verbatim_no_remap() -> None:
    for symbol in ("XAUUSDc", "XAUUSD"):
        result = _norm(
            {"symbol": symbol, "bid": 1.0, "ask": 2.0, "mid": 1.5, "spread": 1.0, "ts_source": TS}
        )
        assert result.payload["symbol"] == symbol


def test_null_fields_dropped() -> None:
    result = _norm(
        {
            "symbol": "XAUUSDc",
            "bid": None,
            "ask": 2.0,
            "mid": 1.5,
            "spread": 1.0,
            "ts_source": TS,
        }
    )
    assert result.payload is not None
    assert "bid" not in result.payload


def test_unknown_fields_preserved_under_unknown_placeholder() -> None:
    result = _norm(
        {
            "symbol": "XAUUSDc",
            "bid": 1.0,
            "ask": 2.0,
            "mid": 1.5,
            "spread": 1.0,
            "ts_source": TS,
            "future_field": 123,
        }
    )
    assert result.payload is not None
    assert result.payload["_unknown"] == {"future_field": 123}
    assert "future_field" not in result.payload


def test_timestamp_falls_back_from_payload_to_bridge_to_receipt() -> None:
    explicit = _norm(
        {"symbol": "X", "bid": 1.0, "ask": 2.0, "mid": 1.5, "spread": 1.0, "ts_source": TS}
    )
    assert explicit.payload["ts_source"] == TS

    no_field = _norm({"symbol": "X", "bid": 1.0, "ask": 2.0, "mid": 1.5, "spread": 1.0})
    assert "ts_source" not in no_field.payload


def test_internal_heartbeat_classified() -> None:
    result = _norm({"status": "RUNNING"}, event_type="HEARTBEAT")
    assert result.kind is RawLineKind.INTERNAL
    assert result.event_type is None


def test_internal_snapshots_classified() -> None:
    for event_type in ("POSITION_SNAPSHOT", "ORDER_SNAPSHOT"):
        result = _norm({"dummy": 1}, event_type=event_type)
        assert result.kind is RawLineKind.INTERNAL


def test_unknown_event_type_classified_unknown() -> None:
    result = _norm({}, event_type="NOT_A_REAL_EVENT")
    assert result.kind is RawLineKind.UNKNOWN
    assert result.event_type is None
    assert result.code == "UNKNOWN_EVENT_TYPE"


def test_missing_event_type_raises() -> None:
    with pytest.raises(InvalidLineError, match="event_type"):
        normalize_bridge_line({"payload": {}}, ts_collected=TS_COLLECTED)


def test_missing_payload_raises() -> None:
    with pytest.raises(InvalidLineError, match="payload"):
        normalize_bridge_line({"event_type": "TICK_RECEIVED"}, ts_collected=TS_COLLECTED)


def test_malformed_json_raises() -> None:
    with pytest.raises(InvalidLineError, match="JSON"):
        parse_raw_line("{not json")


def test_non_object_line_raises() -> None:
    with pytest.raises(InvalidLineError, match="object"):
        parse_raw_line("[1, 2, 3]")


def test_bridge_out_of_band_error_event_normalizes() -> None:
    result = _norm(
        {"error_code": "E1", "component": "bridge", "severity": "ERROR", "message": "boom"},
        event_type="ERROR",
    )
    assert result.kind is RawLineKind.CANONICAL
    assert result.event_type is EventType.ERROR
    assert result.payload == {
        "error_code": "E1",
        "component": "bridge",
        "severity": "ERROR",
        "message": "boom",
    }
