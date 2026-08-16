"""Unit tests: strict parsing + normalization for the AI Decision Engine."""

from __future__ import annotations

import json

from ai_decision.parsing import (
    extract_json_object,
    parse_and_normalize,
    reassemble_sse,
)

OK_CONTENT = json.dumps({"direction": "BUY", "confidence": 0.7, "reason": "trend up"})


def body_with(content: object, extra: dict | None = None) -> str:
    message = {"message": {"content": content}}
    obj: dict = {"choices": [message]}
    if extra:
        obj.update(extra)
    return json.dumps(obj)


# --- extraction quirks -------------------------------------------------------


def test_extract_json_object_trailing_sse_artifact() -> None:
    raw = (
        'data: {"choices": [{"delta": {"content": '
        '"{\\"direction\\": \\"BUY\\"}"}}]}\n\ndata: [DONE]'
    )
    obj, repair = extract_json_object(raw)
    assert obj is not None
    assert repair == "sse_reassemble"


def test_reassemble_sse_full_stream() -> None:
    raw = (
        'data: {"choices":[{"delta":{"content":"{\\"dir"}}]}\n'
        'data: {"choices":[{"delta":{"content":"ection\\": \\"SELL\\","}}]}\n'
        'data: {"choices":[{"delta":{"content":'
        '"\\"confidence\\": 0.6, \\"reason\\": \\"down\\"}"}}]}\n'
        'data: {"choices":[{"delta":{}}]}\n'
        "data: [DONE]\n"
    )
    rejoined = reassemble_sse(raw)
    assert '"direction": "SELL"' in rejoined


def test_parse_content_as_object() -> None:
    raw = json.dumps(
        {
            "choices": [
                {"message": {"content": {"direction": "SELL", "confidence": 0.5, "reason": "r"}}}
            ]
        }
    )
    result = parse_and_normalize(raw)
    assert result.ok
    assert result.output["direction"] == "SELL"
    assert result.output["confidence"] == 0.5


def test_parse_string_json() -> None:
    result = parse_and_normalize(body_with(OK_CONTENT))
    assert result.ok
    assert result.output["direction"] == "BUY"
    assert result.output["confidence"] == 0.7


def test_parse_reasoning_content() -> None:
    raw = json.dumps({"choices": [{"message": {"content": None, "reasoning_content": OK_CONTENT}}]})
    result = parse_and_normalize(raw)
    assert result.ok
    assert result.output["direction"] == "BUY"


def test_parse_direct_object_body() -> None:
    raw = json.dumps({"direction": "NO-TRADE", "confidence": 0.2, "reason": "flat"})
    result = parse_and_normalize(raw)
    assert result.ok
    assert result.output["direction"] == "NO-TRADE"


def test_parse_body_with_trailing_done_sse_marker() -> None:
    # Observed on the live router 2026-08-17: complete JSON body followed by
    # `data: [DONE]` with NO newline separator.
    raw = json.dumps({"choices": [{"message": {"content": OK_CONTENT}}]}) + "data: [DONE]"
    result = parse_and_normalize(raw)
    assert result.ok
    assert result.output["direction"] == "BUY"


def test_parse_body_with_newline_trailing_done() -> None:
    raw = json.dumps({"choices": [{"message": {"content": OK_CONTENT}}]}) + "\n\ndata: [DONE]\n"
    result = parse_and_normalize(raw)
    assert result.ok
    assert result.output["direction"] == "BUY"


def test_parse_missing_choices() -> None:
    result = parse_and_normalize(json.dumps({"choices": []}))
    assert not result.ok
    assert result.error == "missing_choices"


def test_parse_empty_response() -> None:
    result = parse_and_normalize("")
    assert not result.ok
    assert result.output["direction"] == "NO-TRADE"


def test_parse_natural_language_only() -> None:
    result = parse_and_normalize("The market looks bullish, I would go long.")
    assert not result.ok
    assert result.error in ("invalid_json", "extraction_failed")


def test_parse_malformed_json() -> None:
    result = parse_and_normalize('{"choices":[{"message":{"content":"{broken"}}]}')
    assert not result.ok


# --- normalization strictness -------------------------------------------------


def test_normalize_direction_aliases_fail_closed() -> None:
    for alias in ("hold", "none", "wait", "neutral", "no trade"):
        raw = body_with(json.dumps({"direction": alias, "confidence": 0.5, "reason": "r"}))
        result = parse_and_normalize(raw)
        assert result.ok
        assert result.output["direction"] == "NO-TRADE"
        assert result.repair is None  # known alias, normalized without repair


def test_normalize_unknown_direction_fail_closed_with_repair() -> None:
    raw = body_with(json.dumps({"direction": "maybe long", "confidence": 0.5, "reason": "r"}))
    result = parse_and_normalize(raw)
    assert result.ok
    assert result.output["direction"] == "NO-TRADE"
    assert result.repair == "direction_normalized_to_no_trade"


def test_normalize_rejects_out_of_range_confidence() -> None:
    for bad in (1.5, -0.1, 2):
        raw = body_with(json.dumps({"direction": "BUY", "confidence": bad, "reason": "r"}))
        result = parse_and_normalize(raw)
        assert result.output["confidence"] is None
        assert "confidence_rejected_or_missing" in (result.repair or "")


def test_normalize_rejects_nan_confidence() -> None:
    raw = body_with(json.dumps({"direction": "BUY", "confidence": float("nan"), "reason": "r"}))
    result = parse_and_normalize(raw)
    assert result.output["confidence"] is None


def test_normalize_rejects_non_string_reason() -> None:
    raw = body_with(json.dumps({"direction": "BUY", "confidence": 0.5, "reason": 42}))
    result = parse_and_normalize(raw)
    assert result.output["reason"] is None
    assert "reason_rejected_or_missing" in (result.repair or "")


def test_normalize_keeps_exact_string_reason() -> None:
    raw = body_with(json.dumps({"direction": "BUY", "confidence": 0.5, "reason": ""}))
    result = parse_and_normalize(raw)
    assert result.ok
    assert result.output["reason"] == ""


def test_normalize_exposes_payload_keys() -> None:
    raw = body_with(json.dumps({"direction": "BUY", "confidence": 0.5, "reason": "r", "lot": 0.1}))
    result = parse_and_normalize(raw)
    assert "lot" in result.payload_keys
    assert "direction" in result.payload_keys
