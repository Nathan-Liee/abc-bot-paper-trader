"""Low-level OpenAI-compatible chat completion transport.

Non-streaming POST to {base_url}/chat/completions using stdlib urllib
(no new dependency). Returns raw text + status so the caller can classify
timeout / 429 / 5xx / transport / HTTP400 exactly like the benchmark runner.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TransportResult:
    status: str  # "OK" | "TIMEOUT" | "TRANSPORT_ERROR" | "HTTP<code>"
    latency_ms: float
    raw: str
    error: str | None


def chat_completion(
    base_url: str,
    api_key: str,
    model_id: str,
    messages: list[dict[str, str]],
    *,
    timeout_s: float,
    max_tokens: int,
    temperature: float,
) -> TransportResult:
    body = json.dumps(
        {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    ).encode()
    req = urllib.request.Request(
        base_url + "/chat/completions",
        data=body,
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        ms = (time.monotonic() - t0) * 1000
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return TransportResult(f"HTTP{exc.code}", ms, "", f"HTTP{exc.code}:{detail}")
    except (TimeoutError, urllib.error.URLError) as exc:  # noqa: BLE001
        ms = (time.monotonic() - t0) * 1000
        reason = str(getattr(exc, "reason", exc))
        kind = "TIMEOUT" if isinstance(exc, TimeoutError) else "TRANSPORT_ERROR"
        return TransportResult(kind, ms, "", f"{kind}:{reason}")
    except Exception as exc:  # noqa: BLE001 - transport must never crash the engine
        ms = (time.monotonic() - t0) * 1000
        return TransportResult(
            "TRANSPORT_ERROR", ms, "", f"TRANSPORT_ERROR:{type(exc).__name__}:{exc}"
        )
    ms = (time.monotonic() - t0) * 1000
    return TransportResult("OK", ms, raw, None)


def infer_usage(raw: str) -> dict[str, Any]:
    """Best-effort token usage extraction from a raw completion body."""
    if not raw:
        return {}
    i = raw.rfind("}")
    if i < 0:
        return {}
    try:
        parsed = json.loads(raw[: i + 1])
    except json.JSONDecodeError:
        return {}
    usage = parsed.get("usage")
    return usage if isinstance(usage, dict) else {}
