"""Unit tests: DecisionEngine with mocked provider transport."""

from __future__ import annotations

import json
from collections import deque

from ai_decision.client import TransportResult
from ai_decision.config import EngineConfig, ModelConfig, Secrets
from ai_decision.engine import DecisionEngine
from ai_decision.prompt import PROMPT_VERSION

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
    "m1": {"close": 100.1, "high": 100.4, "low": 99.9},
    "m5": {"close": 100.2, "high": 100.6, "low": 99.8},
    "derived": {"trend": "up"},
    "context_snapshot_id": "ctx-0001",
}


def make_config(**overrides: object) -> EngineConfig:
    base: dict[str, object] = dict(
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
    base.update(overrides)
    return EngineConfig(**base)  # type: ignore[arg-type]


class FakeTransport:
    """Deterministic per-model result queues."""

    def __init__(self, results: dict[str, list[TransportResult]]) -> None:
        self._queues: dict[str, deque[TransportResult]] = {k: deque(v) for k, v in results.items()}
        self.calls: list[str] = []

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
        self.calls.append(model_id)
        queue = self._queues.get(model_id)
        if not queue:
            return TransportResult("TRANSPORT_ERROR", 1.0, "", "transport_error:no_mock_result")
        return queue.popleft()


def ok_raw(
    direction: str = "BUY",
    confidence: float = 0.7,
    reason: str = "trend up",
    extra: dict | None = None,
) -> str:
    content: dict = {"direction": direction, "confidence": confidence, "reason": reason}
    if extra:
        content.update(extra)
    return json.dumps({"choices": [{"message": {"content": json.dumps(content)}}]})


def make_engine(results: dict[str, list[TransportResult]]) -> tuple[DecisionEngine, FakeTransport]:
    transport = FakeTransport(results)
    engine = DecisionEngine(make_config(), Secrets(api_key="test-key"), transport=transport)
    return engine, transport


def ok_result(
    direction: str = "BUY",
    confidence: float = 0.7,
    reason: str = "trend up",
    extra: dict | None = None,
) -> TransportResult:
    return TransportResult("OK", 100.0, ok_raw(direction, confidence, reason, extra), None)


# --- valid outputs -----------------------------------------------------------


def test_valid_buy() -> None:
    engine, transport = make_engine({PRIMARY: [ok_result()]})
    record = engine.decide(CONTEXT)
    assert record.validation_ok
    assert record.direction == "BUY"
    assert record.confidence == 0.7
    assert record.model_id == PRIMARY
    assert record.provider == "cf"
    assert record.fallback_level == 0
    assert record.attempts == 1
    assert record.error_class is None
    assert record.context_snapshot_id == "ctx-0001"
    assert record.prompt_version == PROMPT_VERSION
    assert len(record.inference_id) == 36
    assert transport.calls == [PRIMARY]


def test_valid_sell() -> None:
    engine, _transport = make_engine({PRIMARY: [ok_result(direction="SELL", confidence=0.4)]})
    record = engine.decide(CONTEXT)
    assert record.validation_ok and record.direction == "SELL" and record.confidence == 0.4


def test_valid_no_trade_first_class() -> None:
    engine, _transport = make_engine(
        {PRIMARY: [ok_result(direction="NO-TRADE", confidence=0.9, reason="conflict")]}
    )
    record = engine.decide(CONTEXT)
    assert record.validation_ok
    assert record.direction == "NO-TRADE"
    assert record.confidence == 0.9


def test_correlation_id_passthrough() -> None:
    engine, _transport = make_engine({PRIMARY: [ok_result()]})
    record = engine.decide(CONTEXT, correlation_id="corr-9")
    assert record.correlation_id == "corr-9"


# --- invalid outputs (fail closed) -------------------------------------------


def test_invalid_direction_normalized_no_trade() -> None:
    engine, _transport = make_engine({PRIMARY: [ok_result(direction="maybe long")]})
    record = engine.decide(CONTEXT)
    assert record.validation_ok
    assert record.direction == "NO-TRADE"
    assert record.repair == "direction_normalized_to_no_trade"


def test_known_alias_direction_normalized_no_trade() -> None:
    engine, _transport = make_engine({PRIMARY: [ok_result(direction="hold")]})
    record = engine.decide(CONTEXT)
    assert record.validation_ok
    assert record.direction == "NO-TRADE"
    assert record.repair is None


def test_confidence_above_range_rejected() -> None:
    engine, _transport = make_engine({PRIMARY: [ok_result(confidence=1.5)]})
    record = engine.decide(CONTEXT)
    assert not record.validation_ok
    assert record.direction == "NO-TRADE"
    assert record.error_class == "SCHEMA_ERROR"


def test_confidence_below_range_rejected() -> None:
    engine, _transport = make_engine({PRIMARY: [ok_result(confidence=-0.2)]})
    record = engine.decide(CONTEXT)
    assert not record.validation_ok and record.error_class == "SCHEMA_ERROR"


def test_missing_confidence_rejected() -> None:
    engine, _transport = make_engine({PRIMARY: [ok_result(extra={"confidence": None})]})
    record = engine.decide(CONTEXT)
    assert not record.validation_ok
    assert record.error_class == "SCHEMA_ERROR"


def test_missing_reason_rejected() -> None:
    raw = json.dumps(
        {"choices": [{"message": {"content": json.dumps({"direction": "BUY", "confidence": 0.5})}}]}
    )
    engine, _transport = make_engine({PRIMARY: [TransportResult("OK", 9.0, raw, None)]})
    record = engine.decide(CONTEXT)
    assert not record.validation_ok
    assert record.error_class == "SCHEMA_ERROR"
    assert any("reason_not_string" in e for e in record.schema_errors)


def test_malformed_json_parse_fail() -> None:
    engine, _transport = make_engine({PRIMARY: [TransportResult("OK", 9.0, "{broken", None)]})
    record = engine.decide(CONTEXT)
    assert not record.validation_ok
    assert record.error_class == "PARSE_ERROR"


def test_natural_language_only_parse_fail() -> None:
    engine, _transport = make_engine(
        {PRIMARY: [TransportResult("OK", 9.0, "market bullish, go long", None)]}
    )
    record = engine.decide(CONTEXT)
    assert not record.validation_ok and record.error_class == "PARSE_ERROR"


def test_empty_content_parse_fail() -> None:
    engine, _transport = make_engine({PRIMARY: [TransportResult("OK", 9.0, "", None)]})
    record = engine.decide(CONTEXT)
    assert not record.validation_ok and record.error_class == "PARSE_ERROR"


def test_reasoning_only_content_parse_ok() -> None:
    decision = json.dumps({"direction": "BUY", "confidence": 0.7, "reason": "trend up"})
    raw = json.dumps({"choices": [{"message": {"content": None, "reasoning_content": decision}}]})
    engine, _transport = make_engine({PRIMARY: [TransportResult("OK", 9.0, raw, None)]})
    record = engine.decide(CONTEXT)
    assert record.validation_ok and record.direction == "BUY"


def test_forbidden_lot_field_authority_violation() -> None:
    engine, _transport = make_engine(
        {PRIMARY: [ok_result(extra={"lot": 0.1, "position_size": 200})]}
    )
    record = engine.decide(CONTEXT)
    assert not record.validation_ok
    assert record.error_class == "AUTHORITY_VIOLATION"
    assert record.direction == "NO-TRADE"
    assert record.schema_errors
    assert "lot" in record.schema_errors[0]


def test_forbidden_reason_phrase_authority_violation() -> None:
    engine, _transport = make_engine(
        {PRIMARY: [ok_result(reason="use stop loss 1.2 and take profit 1.5")]}
    )
    record = engine.decide(CONTEXT)
    assert not record.validation_ok
    assert record.error_class == "AUTHORITY_VIOLATION"


# --- provider failures --------------------------------------------------------


def test_timeout_retries_then_secondary() -> None:
    engine, transport = make_engine(
        {
            PRIMARY: [
                TransportResult("TIMEOUT", 60000.0, "", "TIMEOUT"),
                TransportResult("TIMEOUT", 60000.0, "", "TIMEOUT"),
            ],
            SECONDARY: [ok_result(direction="SELL")],
        }
    )
    record = engine.decide(CONTEXT)
    assert record.validation_ok
    assert record.direction == "SELL"
    assert record.model_id == SECONDARY
    assert record.fallback_level == 1
    assert record.attempts == 1  # success on first attempt of the secondary level
    assert transport.calls == [PRIMARY, PRIMARY, SECONDARY]


def test_429_retry_then_success() -> None:
    engine, transport = make_engine(
        {
            PRIMARY: [
                TransportResult("HTTP429", 45.0, "", "HTTP429"),
                ok_result(direction="BUY"),
            ]
        }
    )
    record = engine.decide(CONTEXT)
    assert record.validation_ok
    assert record.direction == "BUY"
    assert record.fallback_level == 0
    assert record.attempts == 2
    assert record.retried
    assert transport.calls == [PRIMARY, PRIMARY]


def test_400_no_retry_moves_fallback() -> None:
    engine, transport = make_engine(
        {
            PRIMARY: [TransportResult("HTTP400", 50.0, "", "HTTP400")],
            SECONDARY: [ok_result(direction="SELL")],
        }
    )
    record = engine.decide(CONTEXT)
    assert record.validation_ok
    assert record.model_id == SECONDARY
    assert record.attempts == 1  # no retry for HTTP400
    assert transport.calls == [PRIMARY, SECONDARY]


def test_500_retries_then_fallback() -> None:
    engine, transport = make_engine(
        {
            PRIMARY: [
                TransportResult("HTTP500", 200.0, "", "HTTP500"),
                TransportResult("HTTP500", 200.0, "", "HTTP500"),
            ],
            SECONDARY: [TransportResult("HTTP500", 200.0, "", "HTTP500")],
            FALLBACK: [ok_result(direction="SELL")],
        }
    )
    record = engine.decide(CONTEXT)
    assert record.validation_ok and record.model_id == FALLBACK and record.fallback_level == 2


def test_connection_error_retries_then_fallback() -> None:
    engine, _transport = make_engine(
        {
            PRIMARY: [
                TransportResult("TRANSPORT_ERROR", 1.0, "", "connection refused"),
                TransportResult("TRANSPORT_ERROR", 1.0, "", "connection refused"),
            ],
            SECONDARY: [
                TransportResult("TRANSPORT_ERROR", 1.0, "", "connection refused"),
                TransportResult("TRANSPORT_ERROR", 1.0, "", "connection refused"),
            ],
            FALLBACK: [ok_result(direction="SELL")],
        }
    )
    record = engine.decide(CONTEXT)
    assert record.validation_ok and record.model_id == FALLBACK and record.fallback_level == 2


def test_malformed_provider_response_parse_fail() -> None:
    engine, _transport = make_engine(
        {PRIMARY: [TransportResult("OK", 10.0, "not json at all", None)]}
    )
    record = engine.decide(CONTEXT)
    assert not record.validation_ok and record.error_class == "PARSE_ERROR"


# --- fallback chain exhausts --------------------------------------------------


def test_all_levels_fail_no_trade() -> None:
    engine, transport = make_engine(
        {
            PRIMARY: [TransportResult("HTTP500", 1.0, "", "HTTP500")],
            SECONDARY: [TransportResult("HTTP500", 1.0, "", "HTTP500")],
            FALLBACK: [TransportResult("HTTP500", 1.0, "", "HTTP500")],
        }
    )
    record = engine.decide(CONTEXT)
    assert not record.validation_ok
    assert record.direction == "NO-TRADE"
    assert record.confidence == 0.0
    assert record.error_class == "PROVIDER_FAILURE"
    assert record.fallback_level == 3
    # HTTP500 is retryable -> 2 attempts per level (max_attempts=2)
    assert transport.calls == [PRIMARY, PRIMARY, SECONDARY, SECONDARY, FALLBACK, FALLBACK]


# --- context validation -------------------------------------------------------


def test_invalid_context_no_inference() -> None:
    engine, transport = make_engine({PRIMARY: [ok_result()]})
    bad_context = dict(CONTEXT)
    del bad_context["symbol"]
    record = engine.decide(bad_context)
    assert not record.validation_ok
    assert record.error_class == "INVALID_CONTEXT"
    assert transport.calls == []


def test_context_m5_none_acceptable() -> None:
    engine, _transport = make_engine({PRIMARY: [ok_result()]})
    context = dict(CONTEXT)
    context["m5"] = None
    record = engine.decide(context)
    assert record.validation_ok


def test_context_m5_wrong_type_rejected() -> None:
    engine, _transport = make_engine({PRIMARY: [ok_result()]})
    context = dict(CONTEXT)
    context["m5"] = "not-a-dict"
    record = engine.decide(context)
    assert not record.validation_ok
    assert record.error_class == "INVALID_CONTEXT"


def test_non_finite_price_rejected() -> None:
    engine, _transport = make_engine({PRIMARY: [ok_result()]})
    context = dict(CONTEXT)
    context["bid"] = float("nan")
    record = engine.decide(context)
    assert not record.validation_ok and record.error_class == "INVALID_CONTEXT"
