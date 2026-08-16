"""Integration test: MarketContext -> AI Decision -> validation -> system gate.

No live broker, no MT5, no order capability. Provider is mocked.
"""

from __future__ import annotations

import json

from ai_decision.client import TransportResult
from ai_decision.config import EngineConfig, ModelConfig, Secrets
from ai_decision.engine import DecisionEngine
from ai_decision.gate import SystemGate

PRIMARY = "cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast"
SECONDARY = "groq/llama-3.3-70b-versatile"
FALLBACK = "cf/@cf/qwen/qwen2.5-coder-32b-instruct"

CONTEXT: dict = {
    "symbol": "XAUUSD",
    "bid": 100.0,
    "ask": 100.5,
    "spread": 0.5,
    "mid": 100.25,
    "atr_m1": 0.1,
    "atr_m5": 0.2,
    "m1": {"close": 100.1},
    "m5": {"close": 100.2},
    "context_snapshot_id": "ctx-int-1",
}

NO_EXECUTABLE_FIELDS = {
    "lot",
    "lots",
    "position_size",
    "position",
    "risk",
    "risk_percent",
    "risk_amount",
    "sl",
    "tp",
    "stop_loss",
    "take_profit",
    "exposure",
    "margin",
    "order",
    "order_type",
    "volume",
    "execution",
    "exit",
}


class StubTransport:
    def __init__(self, raw: str) -> None:
        self._raw = raw

    def __call__(
        self,
        base_url: str,
        api_key: str,
        model_id: str,
        messages: list[dict[str, str]],
        *,
        timeout_s: float,
        max_tokens: int,
        temperature: float,
    ) -> TransportResult:
        return TransportResult("OK", 120.0, self._raw, None)


def make_engine(raw: str) -> DecisionEngine:
    config = EngineConfig(
        primary=ModelConfig.of(PRIMARY),
        secondary=ModelConfig.of(SECONDARY),
        fallback=ModelConfig.of(FALLBACK),
        base_url="http://router.test/v1",
        timeout_s=5.0,
        max_attempts=2,
        retry_429_sleep_s=0.0,
        max_tokens=128,
        temperature=0.0,
    )
    return DecisionEngine(config, Secrets(api_key="test-key"), transport=StubTransport(raw))


def ok_raw(direction: str, confidence: float, reason: str) -> str:
    return json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"direction": direction, "confidence": confidence, "reason": reason}
                        )
                    }
                }
            ]
        }
    )


def test_full_pipeline_valid_buy_approved() -> None:
    engine = make_engine(ok_raw("BUY", 0.75, "momentum up"))
    record = engine.decide(CONTEXT)
    assert record.validation_ok and record.direction == "BUY"

    verdict = SystemGate().evaluate(record)
    assert verdict.verdict == "APPROVE"


def test_full_pipeline_valid_sell_approved() -> None:
    engine = make_engine(ok_raw("SELL", 0.6, "downtrend"))
    record = engine.decide(CONTEXT)
    verdict = SystemGate().evaluate(record)
    assert record.direction == "SELL"
    assert verdict.verdict == "APPROVE"


def test_gate_rejects_invalid_proposal() -> None:
    engine = make_engine(ok_raw("BUY", 3.5, "bad confidence"))
    record = engine.decide(CONTEXT)
    assert not record.validation_ok
    verdict = SystemGate().evaluate(record)
    assert verdict.verdict == "REJECT"
    assert verdict.rejection_code == "SCHEMA_ERROR"


def test_gate_approves_no_trade_non_executable() -> None:
    engine = make_engine(ok_raw("NO-TRADE", 0.2, "conflict"))
    record = engine.decide(CONTEXT)
    assert record.direction == "NO-TRADE"
    verdict = SystemGate().evaluate(record)
    assert verdict.verdict == "APPROVE"
    assert "non-executable" in verdict.reason


def test_record_never_contains_executable_fields() -> None:
    engine = make_engine(ok_raw("BUY", 0.8, "up"))
    record = engine.decide(CONTEXT)
    keys = set(record.to_dict())
    assert keys.isdisjoint(NO_EXECUTABLE_FIELDS)


def test_engine_has_no_order_or_execution_capability() -> None:
    assert not hasattr(DecisionEngine, "execute")
    assert not hasattr(DecisionEngine, "submit_order")
    assert not hasattr(DecisionEngine, "open_position")
    assert not hasattr(DecisionEngine, "close_position")


def test_ai_decision_modules_never_import_mt5_or_broker() -> None:
    import ast
    import inspect

    import ai_decision.client  # noqa: F401
    import ai_decision.config  # noqa: F401
    import ai_decision.engine  # noqa: F401
    import ai_decision.gate  # noqa: F401
    import ai_decision.parsing  # noqa: F401
    import ai_decision.prompt  # noqa: F401
    import ai_decision.record  # noqa: F401
    import ai_decision.validation  # noqa: F401

    forbidden_import_tokens = {"mt5", "metatrader", "order_send", "mql5"}
    for module in (
        ai_decision.client,
        ai_decision.config,
        ai_decision.engine,
        ai_decision.gate,
        ai_decision.parsing,
        ai_decision.prompt,
        ai_decision.record,
        ai_decision.validation,
    ):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    imported = alias.name.lower()
                    for token in forbidden_import_tokens:
                        assert token not in imported, (
                            f"{module.__name__} imports forbidden symbol {imported}"
                        )
