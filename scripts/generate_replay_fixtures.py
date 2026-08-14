"""Generate synthetic replay fixtures for the canonical event contract.

The fixtures are fully deterministic (fixed ids, timestamps, monotonic
values) and contain no real broker or demo data. They are committed to
``tests/replay/fixtures`` and consumed by ``tests/replay``.

Run from the repository root:

    uv run python scripts/generate_replay_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from collector.event_model import EventEnvelope, build_event, to_json  # noqa: E402
from shared.contracts.types import EventType  # noqa: E402
from tests.unit.event_factories import (  # noqa: E402
    CORRELATION_ID,
    TRADE_ID,
    ai_request_payload,
    ai_response_payload,
    context_payload,
    error_payload,
    exit_submitted_payload,
    net_profit_positive_payload,
    order_acknowledged_payload,
    order_filled_payload,
    order_submitted_payload,
    position_closed_payload,
    position_opened_payload,
    position_updated_payload,
    risk_gate_payload,
    tick_payload,
    trigger_payload,
)

FIXTURES_DIR = Path("tests/replay/fixtures")
TS = "2026-08-14T09:00:00Z"
TS_MS = "2026-08-14T09:00:00.000Z"
MONO = 1_000_000


def _trade_event(
    event_type: EventType, payload: dict[str, object], monotonic: int
) -> EventEnvelope:
    return build_event(
        event_type,
        payload,
        correlation_id=CORRELATION_ID,
        trade_id=TRADE_ID,
        ts_event=TS,
        ts_collected=TS_MS,
        ts_monotonic=monotonic,
    )


def _tick(monotonic: int, **overrides: object) -> EventEnvelope:
    return build_event(
        EventType.TICK_RECEIVED,
        tick_payload(**overrides),
        ts_event=TS,
        ts_collected=TS_MS,
        ts_monotonic=monotonic,
    )


def trade_lifecycle() -> list[EventEnvelope]:
    flow: list[tuple[EventType, dict[str, object]]] = [
        (EventType.TRIGGER_DETECTED, trigger_payload()),
        (EventType.CONTEXT_BUILT, context_payload()),
        (EventType.AI_REQUEST, ai_request_payload()),
        (EventType.AI_RESPONSE, ai_response_payload()),
        (EventType.RISK_GATE, risk_gate_payload()),
        (EventType.ORDER_SUBMITTED, order_submitted_payload()),
        (EventType.ORDER_ACKNOWLEDGED, order_acknowledged_payload()),
        (EventType.ORDER_FILLED, order_filled_payload()),
        (EventType.POSITION_OPENED, position_opened_payload()),
        (EventType.POSITION_UPDATED, position_updated_payload()),
        (EventType.NET_PROFIT_POSITIVE, net_profit_positive_payload()),
        (EventType.EXIT_SUBMITTED, exit_submitted_payload()),
        (EventType.POSITION_CLOSED, position_closed_payload()),
    ]
    return [
        _trade_event(event_type, payload, MONO + index)
        for index, (event_type, payload) in enumerate(flow)
    ]


def risk_rejection() -> list[EventEnvelope]:
    return [
        _trade_event(EventType.TRIGGER_DETECTED, trigger_payload(), MONO),
        _trade_event(
            EventType.RISK_GATE,
            risk_gate_payload(
                gate_result="REJECT", final_lot=0.0, rejection_reason="budget exhausted"
            ),
            MONO + 1,
        ),
        _trade_event(
            EventType.ERROR,
            error_payload(error_code="RISK_GATE_REJECTED", message="risk gate rejected the trade"),
            MONO + 2,
        ),
    ]


def duplicate_ticks() -> list[EventEnvelope]:
    return [
        _tick(MONO, tick_volume=1),
        _tick(MONO + 1, tick_volume=2),
        _tick(MONO + 2, tick_volume=3),
    ]


def malformed() -> list[dict[str, object]]:
    event = _tick(MONO)
    data = event.to_dict()
    del data["payload"]["bid"]
    return [data]


def checksum_tamper() -> list[dict[str, object]]:
    event = _tick(MONO)
    data = event.to_dict()
    data["payload"] = dict(data["payload"])
    data["payload"]["bid"] = 9999.0
    return [data]


def _dump(events: list[EventEnvelope] | list[dict[str, object]]) -> str:
    lines: list[str] = []
    for event in events:
        if isinstance(event, EventEnvelope):
            lines.append(to_json(event))
        else:
            lines.append(
                json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "trade_lifecycle.jsonl": trade_lifecycle(),
        "risk_rejection.jsonl": risk_rejection(),
        "duplicate_ticks.jsonl": duplicate_ticks(),
        "malformed.jsonl": malformed(),
        "checksum_tamper.jsonl": checksum_tamper(),
    }
    for name, events in fixtures.items():
        path = FIXTURES_DIR / name
        path.write_text(_dump(events), encoding="utf-8")
        print(f"wrote {path} ({len(events)} events)")


if __name__ == "__main__":
    main()
