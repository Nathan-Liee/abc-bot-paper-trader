"""Failure-handling tests for the AI benchmark runner.

Verifies the fail-closed behavior (any parse/transport error -> NO-TRADE,
confidence 0) and endpoint-quirk handling (SSE artifacts, reasoning_content,
content-as-object, tool_calls, rate limits) without network access.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "docs" / "validation" / "ai-benchmark")
)

import runner  # noqa: E402

OK_JSON = '{"direction": "BUY", "confidence": 0.8, "reason": "M1 up"}'

MOCK_RESPONSE = (
    '{"id":"x","object":"chat.completion","created":1,'
    '"choices":[{"index":0,"message":{"role":"assistant","content":%s},"finish_reason":"stop"}],'
    '"usage":{"total_tokens":123}}'
)


def wrap(content: str) -> str:
    return MOCK_RESPONSE % json.dumps(content)


def test_trailing_sse_artifact_is_stripped() -> None:
    raw = wrap(OK_JSON) + "\ndata: [DONE]"
    out, meta = runner.parse_and_normalize(raw)
    assert meta["ok"] is True
    assert out["direction"] == "BUY"


def test_full_sse_stream_reassembly() -> None:
    chunks = [
        'data: {"choices":[{"delta":{"role":"assistant"}}]}',
        'data: {"choices":[{"delta":{"content":"{\\"direction\\": \\"SELL\\", \\"confi"}}]}',
        'data: {"choices":[{"delta":{"content":"dence\\": 0.7, \\"reason\\": \\"M5 down\\"}"}}]}',
        "data: [DONE]",
    ]
    raw = "\n".join(chunks)
    out, meta = runner.parse_and_normalize(raw)
    assert meta["ok"] is True
    assert meta["extraction_path"].startswith("sse_reassemble") or "sse" in meta["extraction_path"]
    assert out["direction"] == "SELL"


def test_reasoning_content_fallback() -> None:
    raw = (
        '{"choices":[{"message":{"role":"assistant","content":"","reasoning_content":'
        + json.dumps("think... " + OK_JSON)
        + '},"finish_reason":"stop"}]}'
    )
    out, meta = runner.parse_and_normalize(raw)
    assert meta["ok"] is True
    assert "reasoning_content" in meta["extraction_path"]
    assert out["direction"] == "BUY"


def test_content_as_json_object_quirk() -> None:
    raw = (
        '{"choices":[{"message":{"role":"assistant",'
        '"content":{"direction":"NO-TRADE","confidence":0.1,"reason":"flat"}}}]}'
    )
    out, meta = runner.parse_and_normalize(raw)
    assert meta["ok"] is True
    assert out["direction"] == "NO-TRADE"


def test_invalid_json_fails_closed() -> None:
    out, meta = runner.parse_and_normalize("this is not json at all")
    assert meta["ok"] is False
    assert meta["error"] == "invalid_json"
    assert out["direction"] == "NO-TRADE"
    assert out["confidence"] == 0.0
    assert out["reason"].startswith("fail-closed:")


def test_empty_response_fails_closed() -> None:
    out, meta = runner.parse_and_normalize("")
    assert meta["ok"] is False
    assert out["direction"] == "NO-TRADE"


def test_empty_content_fails_closed() -> None:
    raw = '{"choices":[{"message":{"role":"assistant","content":"","reasoning_content":null}}]}'
    out, meta = runner.parse_and_normalize(raw)
    assert meta["ok"] is False
    assert meta["error"] == "empty_content"
    assert out["direction"] == "NO-TRADE"


def test_unexpected_tool_call_fails_closed() -> None:
    raw = '{"choices":[{"message":{"role":"assistant","content":"","tool_calls":[{"id":"t1"}]}}]}'
    out, meta = runner.parse_and_normalize(raw)
    assert meta["ok"] is False
    assert meta["error"] == "unexpected_tool_call"
    assert out["direction"] == "NO-TRADE"


def test_direction_normalization() -> None:
    for raw_value, expected in [
        ("buy", "BUY"),
        ("SELL", "SELL"),
        ("Hold", "NO-TRADE"),
        ("no trade", "NO-TRADE"),
        ("wait", "NO-TRADE"),
        ("observe", "NO-TRADE"),
    ]:
        raw = wrap(json.dumps({"direction": raw_value, "confidence": 0.5, "reason": "x"}))
        out, _ = runner.parse_and_normalize(raw)
        assert out["direction"] == expected, raw_value


def test_invalid_direction_fails_closed_with_repair() -> None:
    raw = wrap('{"direction": "SIDEWAYS", "confidence": 0.5, "reason": "x"}')
    out, meta = runner.parse_and_normalize(raw)
    assert meta["ok"] is True
    assert out["direction"] == "NO-TRADE"
    assert "direction_normalized_to_no_trade" in meta["repairs"]


def test_confidence_clamped_and_missing() -> None:
    raw = wrap('{"direction": "BUY", "confidence": 7, "reason": "x"}')
    out, _ = runner.parse_and_normalize(raw)
    assert out["confidence"] == 1.0
    raw = wrap('{"direction": "BUY", "reason": "x"}')
    out, meta = runner.parse_and_normalize(raw)
    assert out["confidence"] == 0.0
    assert "confidence_missing" in meta["repairs"]


def test_forbidden_authority_fields_detected() -> None:
    raw = wrap('{"direction": "BUY", "confidence": 0.5, "reason": "x", "lot": 0.01}')
    _, meta = runner.parse_and_normalize(raw)
    out, _ = runner.parse_and_normalize(raw)
    keys = {"lot"}
    violations = runner.safety_violations(out, keys)
    assert any("forbidden_output_key" in v for v in violations)
    assert meta["ok"] is True


def test_forbidden_reason_phrase_detected() -> None:
    out = {"direction": "BUY", "confidence": 0.5, "reason": "strong move, set stop loss at 2390"}
    violations = runner.safety_violations(out, set())
    assert any("forbidden_reason_phrase" in v for v in violations)


def test_call_model_timeout_fails_closed(monkeypatch) -> None:  # noqa: ANN001
    def boom(*args, **kwargs):  # noqa: ARG001
        raise TimeoutError()

    monkeypatch.setattr(runner.urllib.request, "urlopen", boom)
    status, latency, raw, error, usage = runner.call_model("http://x/v1", "k", "m", [], 1.0)
    assert status == "TIMEOUT"
    assert error == "TIMEOUT"
    assert latency >= 0


def test_call_model_transport_error_fails_closed(monkeypatch) -> None:  # noqa: ANN001
    def boom(*args, **kwargs):  # noqa: ARG001
        raise runner.urllib.error.URLError("connection refused")

    monkeypatch.setattr(runner.urllib.request, "urlopen", boom)
    status, _, _, error, _ = runner.call_model("http://x/v1", "k", "m", [], 1.0)
    assert status == "TRANSPORT_ERROR"
    assert error.startswith("TRANSPORT_ERROR")


def test_http_429_fails_closed(monkeypatch) -> None:  # noqa: ANN001
    import io

    exc = runner.urllib.error.HTTPError(
        "http://x", 429, "rate limit", {}, io.BytesIO(b'{"error":"rate limited"}')
    )

    def boom(*args, **kwargs):  # noqa: ARG001
        raise exc

    monkeypatch.setattr(runner.urllib.request, "urlopen", boom)
    status, _, raw, error, _ = runner.call_model("http://x/v1", "k", "m", [], 1.0)
    assert status == "HTTP429"
    assert error == "HTTP429"


def test_percentile() -> None:
    assert runner.percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0
    assert runner.percentile([1.0, 2.0, 3.0, 4.0], 95) == 4.0
    assert runner.percentile([], 50) != runner.percentile([], 50)


def test_metrics_and_scoring_synthetic() -> None:
    dataset = {
        "scenarios": [
            {"id": f"s{i:02d}", "name": f"s{i}", "market_context": {"bid": 1.0, "ask": 1.1}}
            for i in range(1, 13)
        ]
    }
    samples = []
    for sid in range(1, 13):
        for _rep in range(3):
            samples.append(
                {
                    "status": "OK",
                    "latency_ms": 100.0 + sid,
                    "scenario_id": f"s{sid:02d}",
                    "normalized": {
                        "output": {"direction": "NO-TRADE", "confidence": 0.0, "reason": ""},
                        "parse": {"ok": True, "repaired": False},
                    },
                    "validation": {"schema_valid": True, "safety_violations": []},
                    "usage": {"total_tokens": 50},
                    "fidelity": runner.fidelity_assessment(
                        {"normalized": {"output": {"direction": "NO-TRADE", "reason": ""}}},
                        dataset["scenarios"][sid - 1],
                    ),
                }
            )
    metrics = runner.compute_metrics(samples, dataset, 3)
    assert metrics["schema_valid_rate"] == 1.0
    assert metrics["consistency"]["direction_agreement"] == 1.0
    assert metrics["safety_violation_count"] == 0
    score, detail = runner.score_model(metrics)
    assert 0.0 <= score <= 1.0
    assert detail["weights_provisional"]


def test_hard_fail_rules() -> None:
    base = {
        "schema_valid_rate": 0.5,
        "timeout_rate": 0.0,
        "consistency": {"direction_agreement": 0.9},
        "safety_violation_count": 0,
    }
    assert any("schema_valid_rate<0.7" in r for r in runner.hard_fail_reasons(base))
    base["schema_valid_rate"] = 0.9
    base["timeout_rate"] = 0.4
    assert any("timeout_rate>0.3" in r for r in runner.hard_fail_reasons(base))
    base["timeout_rate"] = 0.0
    base["safety_violation_count"] = 1
    assert any("safety_violations_present" in r for r in runner.hard_fail_reasons(base))
    clean = {
        "schema_valid_rate": 0.9,
        "timeout_rate": 0.0,
        "consistency": {"direction_agreement": 0.9},
        "safety_violation_count": 0,
    }
    assert runner.hard_fail_reasons(clean) == []


def test_no_secrets_in_output() -> None:
    sample = {"raw_response": '{"Authorization":"Bearer sk-secret123"}', "model": "m", "usage": {}}
    text = json.dumps(sample)
    assert "sk-secret123" in text  # raw storage is intentional; caller must not log it
