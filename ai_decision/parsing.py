"""Strict response parsing for the AI Decision Engine.

Handles the endpoint quirks documented in benchmark-spec.md §2 (trailing SSE
`[DONE]`, content-as-object, reasoning_content, full SSE streams) without
accepting arbitrary text as a valid decision. Any failure returns a
fail-closed NO-TRADE output rather than a loose parse.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

DIRECTION_MAP = {
    "buy": "BUY",
    "sell": "SELL",
    "no-trade": "NO-TRADE",
    "no trade": "NO-TRADE",
    "notrade": "NO-TRADE",
    "none": "NO-TRADE",
    "neutral": "NO-TRADE",
    "hold": "NO-TRADE",
    "wait": "NO-TRADE",
    "observe": "NO-TRADE",
    "flat": "NO-TRADE",
}

FAIL_CLOSED_OUTPUT: dict[str, Any] = {
    "direction": "NO-TRADE",
    "confidence": 0.0,
    "reason": "fail-closed: benchmark error",
}


@dataclass(frozen=True)
class ParseResult:
    ok: bool
    error: str | None
    output: dict[str, Any]
    payload_keys: frozenset[str] = frozenset()
    repair: str | None = None


def _valid_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _strip_trailing_sse(text: str) -> str:
    """Strip trailing SSE markers observed on the router (e.g. `data: [DONE]`).

    The router appends `data: [DONE]` directly after a complete JSON body
    (observed 2026-08-17 on cf/* routes), which breaks json.loads. This finds
    the LAST closing `}` and drops anything after it — safe because a valid
    completion body always contains at least one `}` (and nested objects end
    with `}` before any SSE tail).
    """
    i = text.rfind("}")
    if i < 0 or i == len(text) - 1:
        return text
    tail = text[i + 1 :]
    if re.search(r"\s*data:\s*(?:\[DONE\])?\s*$", tail):
        return text[: i + 1]
    return text


def reassemble_sse(text: str) -> str:
    """Reassemble a full SSE stream into its joined content string."""
    pieces: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        delta = (
            chunk.get("choices", [{}])[0].get("delta", {})
            if isinstance(chunk.get("choices"), list) and chunk.get("choices")
            else {}
        )
        content = delta.get("content")
        reasoning = delta.get("reasoning_content")
        if isinstance(content, str):
            pieces.append(content)
        elif isinstance(reasoning, str):
            pieces.append(reasoning)
    return "".join(pieces)


def extract_json_object(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Extract the final JSON object from model text."""
    if not text or not text.strip():
        return None, "empty"
    stripped = text.strip()
    repair: str | None = None
    if stripped.startswith("data:"):
        rejoined = reassemble_sse(stripped)
        if rejoined.strip():
            text = rejoined
            repair = "sse_reassemble"
    i = text.rfind("}")
    if i >= 0:
        candidate = text[: i + 1]
        start = candidate.find("{")
        if start >= 0:
            parsed = _valid_json_object(candidate[start:])
            if parsed is not None:
                return parsed, repair or "json_extract"
    parsed = _valid_json_object(text)
    if parsed is not None:
        return parsed, "json_direct"
    return None, "invalid_json"


def _normalize_direction(raw_value: object) -> str | None:
    if not isinstance(raw_value, str):
        return None
    return DIRECTION_MAP.get(raw_value.strip().lower())


def _normalize_confidence(raw_value: object) -> float | None:
    """Float 0..1 or None. Out-of-range / non-finite values are rejected."""
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float, str)):
        return None
    try:
        conf = float(raw_value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(conf) or conf < 0.0 or conf > 1.0:
        return None
    return round(conf, 4)


def normalize_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize a parsed payload into the strict contract shape.

    Direction is normalized fail-closed (invalid -> NO-TRADE, benchmark
    behavior). Confidence and reason are left as None when rejected so the
    strict schema validator can REJECT the decision instead of silently
    repairing it.
    """
    repairs: list[str] = []
    direction = _normalize_direction(payload.get("direction"))
    if direction is None:
        direction = "NO-TRADE"
        repairs.append("direction_normalized_to_no_trade")
    confidence = _normalize_confidence(payload.get("confidence"))
    if confidence is None:
        repairs.append("confidence_rejected_or_missing")
    reason = payload.get("reason")
    if not isinstance(reason, str):
        reason = None
        repairs.append("reason_rejected_or_missing")
    output = {"direction": direction, "confidence": confidence, "reason": reason}
    return output, repairs


def parse_message(message: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Extract AI decision content from an OpenAI-compatible message dict.

    Supported shapes: string content, content-as-object, reasoning_content
    fallback. Anything else (lists, tool calls, empty) is a parse failure.
    """
    content = message.get("content")
    if isinstance(content, dict):
        return dict(content), "content_object"
    if isinstance(content, str) and content.strip():
        obj, _repair = extract_json_object(content)
        if obj is not None:
            return obj, "content_string"
        return None, "extraction_failed"
    if content is None or (isinstance(content, str) and not content.strip()):
        reasoning = message.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            obj, _repair = extract_json_object(reasoning)
            if obj is not None:
                return obj, "reasoning_content"
        return None, "empty_content"
    return None, "unexpected_content_shape"


def parse_and_normalize(raw: str) -> ParseResult:
    """Full parse chain. Always returns a fail-closed contract shape.

    The incoming message body could be a normal JSON chat completion or a full
    SSE stream (spec §2 quirks) — both are handled; arbitrary prose is NOT.
    """
    if not raw or not raw.strip():
        return ParseResult(ok=False, error="empty_response", output=dict(FAIL_CLOSED_OUTPUT))

    cleaned = _strip_trailing_sse(raw)
    body = _valid_json_object(cleaned)
    if body is not None and "choices" in body:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            return ParseResult(ok=False, error="missing_choices", output=dict(FAIL_CLOSED_OUTPUT))
        message = choices[0].get("message")
        if not isinstance(message, dict):
            return ParseResult(ok=False, error="missing_message", output=dict(FAIL_CLOSED_OUTPUT))
        payload, path = parse_message(message)
    elif body is not None:
        # Some routers return the decision object directly.
        payload, path = dict(body), "direct_object"
    else:
        # Full SSE stream or trailing SSE artifact.
        rejoined = reassemble_sse(raw)
        if rejoined.strip():
            payload, path = parse_message({"content": rejoined})
            path = f"sse_body/{path}"
        else:
            payload, path = None, "invalid_json"

    if payload is None:
        return ParseResult(
            ok=False, error=path or "extraction_failed", output=dict(FAIL_CLOSED_OUTPUT)
        )

    normalized, repairs = normalize_payload(payload)
    repair = ",".join(repairs) if repairs else None
    keys = frozenset(str(k) for k in payload)
    return ParseResult(ok=True, error=None, output=normalized, payload_keys=keys, repair=repair)
