"""Reproducible AI model benchmark runner for the ABC Bot paper-trader.

Benchmarks shortlisted models on a custom OpenAI-compatible endpoint using an
identical synthetic dataset and prompt for every model. Measures latency,
structured-output reliability, consistency, context fidelity and failure
safety. Any parse/transport error FAILS CLOSED to NO-TRADE / confidence 0.

Design: docs/validation/ai-benchmark/benchmark-spec.md
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

BENCHMARK_VERSION = "1.0.0"
PROMPT_VERSION = "v1.0.0"
SYSTEM_PROMPT = (
    "You are the market-context analysis module of a paper-trading research system. "
    "You ONLY propose directional entries. You NEVER control risk, lot size, exposure, "
    "margin, execution, exit, or compounding - those belong to the system.\n"
    "Respond with EXACTLY one valid JSON object and nothing else: "
    '{"direction": "BUY"|"SELL"|"NO-TRADE", '
    '"confidence": 0.0, "reason": "short string"}\n'
    "- direction: BUY or SELL only when the supplied context clearly "
    "supports it; otherwise NO-TRADE.\n"
    "- confidence: number 0.0 to 1.0.\n"
    "- reason: cite only facts present in the supplied context. "
    "Never invent prices, levels, or news.\n"
    "- If context is insufficient, conflicting, or ambiguous -> NO-TRADE with low confidence."
)
USER_TEMPLATE = "Market context JSON:\n{context}\n\nOutput the JSON decision object now."

MODELS = [
    "groq/llama-3.3-70b-versatile",
    "cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast",
    "groq/openai/gpt-oss-120b",
    "cf/@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "cf/@cf/zai-org/glm-4.7-flash",
    "cf/@cf/qwen/qwen2.5-coder-32b-instruct",
    "ollama/gpt-oss:120b",
    "cf/@cf/meta/llama-3.2-1b-instruct",
    "kgw/nvidia/nemotron-3-super-120b-a12b:free",
    "kgw/nvidia/nemotron-3-ultra-550b-a55b:free",
    "kgw/kilo-auto/free",
]

# Per benchmark-spec.md v1.0.0 §5: HTTP 429 -> sleep 10 s, retry, max 3 retries
# (4 attempts total). Measured latency excludes retry sleep: the benchmark
# prefers measurement over retried latency.
RETRY_429_MAX = 3
RETRY_429_SLEEP = 10.0

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

FORBIDDEN_OUTPUT_KEYS = {
    "lot",
    "risk",
    "exposure",
    "margin",
    "execution",
    "exit",
    "compounding",
    "stoploss",
    "takeprofit",
    "position_size",
}
FORBIDDEN_REASON_PHRASES = (
    "stop loss",
    "take profit",
    "lot size",
    "position size",
    "margin call",
    "compounding",
)

ERROR_NO_TRADE = {
    "direction": "NO-TRADE",
    "confidence": 0.0,
    "reason": "fail-closed: benchmark error",
}

DEFAULT_DIR = Path(__file__).resolve().parent


def load_env() -> tuple[str, str]:
    base = os.environ.get("ABC_BENCH_BASE_URL", "").strip()
    key = os.environ.get("ABC_BENCH_API_KEY", "").strip()
    if not base or not key:
        raise SystemExit("ABC_BENCH_BASE_URL and ABC_BENCH_API_KEY must be set")
    return base.rstrip("/"), key


def build_user_prompt(context: dict) -> str:
    return USER_TEMPLATE.format(context=json.dumps(context, sort_keys=True))


def extract_json_object(text: str) -> tuple[dict | None, str]:
    """Extract a JSON object from model text. Handles trailing SSE artifacts."""
    if not text or not text.strip():
        return None, "empty"
    stripped = text.strip()
    sse_used = False
    if stripped.startswith("data:"):
        reassembled, _ = reassemble_sse(stripped)
        if reassembled.strip():
            text = reassembled
            sse_used = True
    i = text.rfind("}")
    if i >= 0:
        candidate = text[: i + 1]
        start = candidate.find("{")
        if start >= 0:
            candidate = candidate[start:]
            try:
                parsed = json.loads(candidate)
                return parsed, ("sse_reassemble" if sse_used else "json_extract")
            except json.JSONDecodeError:
                pass
    try:
        return json.loads(text), "json_direct"
    except json.JSONDecodeError:
        return None, "invalid_json"


def reassemble_sse(text: str) -> tuple[str, str]:
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
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        content = delta.get("content")
        reasoning = delta.get("reasoning_content")
        if isinstance(content, str):
            pieces.append(content)
        elif isinstance(reasoning, str):
            pieces.append(reasoning)
    if pieces:
        return "".join(pieces), "sse_reassemble"
    return text, ""


def parse_message(raw: str) -> tuple[dict | None, str]:
    """Parse an OpenAI-compatible chat completion body into a usable message dict."""
    if not raw or not raw.strip():
        return None, "empty_response"
    i = raw.rfind("}")
    if i < 0:
        return None, "invalid_json"
    body_text = raw[: i + 1]
    try:
        body = json.loads(body_text)
    except json.JSONDecodeError:
        body = None
    choices = body.get("choices") if isinstance(body, dict) else None
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
    else:
        message = None
    if message is not None:
        msg, path = parse_message_content(message)
        return msg, path
    if body is not None and "choices" in body and not choices:
        return None, "missing_choices"
    # Full SSE stream: no complete body, only delta chunks.
    if "data:" in raw:
        joined = reassemble_sse(raw)[0]
        if joined.strip():
            msg, path = parse_message_content({"content": joined})
            return msg, f"sse_body/{path}"
    return None, "invalid_json" if body is None else "missing_message"


def parse_message_content(message: dict) -> tuple[dict | None, str]:
    """Handle content-shape quirks for an already-extracted message dict."""
    content = message.get("content")
    if isinstance(content, dict):
        return message, "content_is_object"
    if isinstance(content, list):
        return None, "unexpected_content_shape"
    if not content:
        if message.get("tool_calls"):
            return None, "unexpected_tool_call"
        reasoning = message.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            obj, path = extract_json_object(reasoning)
            if obj is not None:
                return {"content": reasoning}, f"reasoning_content:{path}"
        return None, "empty_content"
    if not isinstance(content, str):
        return None, "unexpected_content_shape"
    return {"content": content}, "content"


def normalize_decision(raw_value: object) -> str | None:
    if not isinstance(raw_value, str):
        return None
    key = raw_value.strip().lower()
    return DIRECTION_MAP.get(key)


def normalize_output(payload: dict) -> tuple[dict, list[str]]:
    """Normalize a parsed payload into the contract shape. Returns (output, repairs)."""
    repairs: list[str] = []
    direct = normalize_decision(payload.get("direction"))
    if direct is None:
        direct = "NO-TRADE"
        repairs.append("direction_normalized_to_no_trade")
    conf = payload.get("confidence")
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        conf = 0.0
        repairs.append("confidence_missing")
    conf = max(0.0, min(1.0, conf))
    reason = payload.get("reason")
    if not isinstance(reason, str):
        reason = ""
        repairs.append("reason_missing")
    reason = reason.strip()
    output = {"direction": direct, "confidence": round(conf, 4), "reason": reason}
    return output, repairs


def parse_and_normalize(raw: str) -> tuple[dict, dict]:
    """Full parse chain. Always returns a fail-closed contract-shaped output."""
    message, path = parse_message(raw)
    if message is None:
        error = path
        out = dict(ERROR_NO_TRADE)
        out["reason"] = f"fail-closed: {error}"
        return out, {"ok": False, "error": error, "extraction_path": path, "repaired": True}

    content = message.get("content", "")
    if isinstance(content, dict):
        payload = dict(content)
        extraction = "content_object"
    else:
        obj, extraction = extract_json_object(content)
        if obj is None:
            out = dict(ERROR_NO_TRADE)
            out["reason"] = "fail-closed: extraction_failed"
            return out, {
                "ok": False,
                "error": "extraction_failed",
                "extraction_path": path,
                "repaired": True,
            }
        payload = obj

    normalized, repairs = normalize_output(payload)
    return normalized, {
        "ok": True,
        "error": None,
        "extraction_path": path + "/" + extraction,
        "repaired": bool(repairs),
        "repairs": repairs,
    }


def safety_violations(output: dict, payload_keys: set[str]) -> list[str]:
    violations: list[str] = []
    bad_keys = FORBIDDEN_OUTPUT_KEYS & {k.lower() for k in payload_keys}
    if bad_keys:
        violations.append("forbidden_output_key:" + ",".join(sorted(bad_keys)))
    reason = (output.get("reason") or "").lower()
    for phrase in FORBIDDEN_REASON_PHRASES:
        if phrase in reason:
            violations.append("forbidden_reason_phrase:" + phrase)
    return violations


def call_model(
    base_url: str, api_key: str, model: str, messages: list[dict], timeout: float
) -> tuple[str, float, str, str | None, dict]:
    """POST /chat/completions. Returns (status, latency_ms, raw_text, error, usage)."""
    body = json.dumps(
        {"model": model, "messages": messages, "max_tokens": 512, "temperature": 0.0}
    ).encode()
    req = urllib.request.Request(
        base_url + "/chat/completions",
        data=body,
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.monotonic()
    attempts = 0
    while True:
        attempts += 1
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            ms = (time.monotonic() - t0) * 1000
            err = f"HTTP{exc.code}"
            body = exc.read().decode("utf-8", errors="replace")[:2000]
            if exc.code == 429 and attempts <= RETRY_429_MAX:
                time.sleep(RETRY_429_SLEEP)
                continue
            return err, ms, body, err, {}
        except TimeoutError:
            ms = (time.monotonic() - t0) * 1000
            return "TIMEOUT", ms, "", "TIMEOUT", {}
        except urllib.error.URLError as exc:
            ms = (time.monotonic() - t0) * 1000
            return "TRANSPORT_ERROR", ms, "", f"TRANSPORT_ERROR:{exc.reason}", {}
        except Exception as exc:  # noqa: BLE001 - benchmark must survive any error
            ms = (time.monotonic() - t0) * 1000
            return "TRANSPORT_ERROR", ms, "", f"TRANSPORT_ERROR:{type(exc).__name__}:{exc}", {}
        break
    ms = (time.monotonic() - t0) * 1000
    usage: dict = {}
    i = raw.rfind("}")
    if i >= 0:
        try:
            parsed = json.loads(raw[: i + 1])
            usage = parsed.get("usage") or {}
        except json.JSONDecodeError:
            pass
    return "OK", ms, raw, None, usage


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    k = min(len(ordered) - 1, max(0, math.ceil(p / 100 * len(ordered)) - 1))
    return ordered[k]


def context_values(context: dict) -> list[str]:
    """Flat list of numeric strings from the context, used for citation detection."""
    hits: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, (int, float)) and node is not None:
            hits.append(f"{node:.2f}".rstrip("0").rstrip("."))

    walk(context)
    return hits


def format_context_values(context: dict) -> list[str]:
    values = context_values(context)
    formatted = [f"{float(v):.2f}" for v in values]
    return formatted


def fidelity_assessment(sample: dict, scenario: dict) -> dict:
    ctx = scenario["market_context"]
    output = sample["normalized"]["output"]
    reason = output.get("reason", "").lower()
    assumptions: list[str] = []
    failsafe_ok = None
    scenario_id = scenario["id"]
    if scenario_id in {"s10", "s11", "s12"}:
        failsafe_ok = output["direction"] == "NO-TRADE"
        assumptions.append("fail_safe_scenario_expect_no_trade")
    citations = [v for v in format_context_values(ctx) if v in reason]
    return {
        "failsafe_ok": failsafe_ok,
        "context_citation_count": len(citations),
        "assumptions": assumptions,
    }


def compute_metrics(samples: list[dict], dataset: dict, repeats: int) -> dict:
    lat = [s["latency_ms"] for s in samples if s["status"] == "OK"]
    schema_valid = [s for s in samples if s["validation"]["schema_valid"]]
    timeout_rate = sum(1 for s in samples if s["status"] == "TIMEOUT") / max(1, len(samples))
    error_rate = sum(
        1 for s in samples if not s["normalized"]["parse"]["ok"] or s["status"] != "OK"
    ) / max(1, len(samples))
    safety_violations = [s for s in samples if s["validation"]["safety_violations"]]
    fail_closed_error_rate = sum(
        1
        for s in samples
        if not s["normalized"]["parse"]["ok"]
        and s["normalized"]["output"]["direction"] == "NO-TRADE"
    ) / max(1, sum(1 for s in samples if not s["normalized"]["parse"]["ok"]))
    agreement: list[float] = []
    conf_stds: list[float] = []
    from collections import defaultdict

    by_scenario: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        by_scenario[s["scenario_id"]].append(s)
    for _sid, group in by_scenario.items():
        dirs = [s["normalized"]["output"]["direction"] for s in group]
        if len(dirs) >= 2:
            agreement.append(max(dirs.count(d) for d in set(dirs)) / len(dirs))
        confs = [s["normalized"]["output"]["confidence"] for s in group]
        if len(confs) >= 2:
            conf_stds.append(statistics.pstdev(confs))
    fidelity_rows = [s["fidelity"] for s in samples if s["fidelity"].get("failsafe_ok") is not None]
    failsafe_ok_rate = sum(1 for f in fidelity_rows if f["failsafe_ok"]) / max(
        1, len(fidelity_rows)
    )
    citation_count = sum(f["context_citation_count"] for f in fidelity_rows)
    total_tokens = sum(s["usage"].get("total_tokens", 0) for s in samples if s["usage"])
    repaired = [s for s in samples if s["normalized"]["parse"].get("repaired")]
    return {
        "n_ok": len(samples) - sum(1 for s in samples if s["status"] != "OK"),
        "latency_ms": {
            "p50": percentile(lat, 50),
            "p95": percentile(lat, 95),
            "p99": percentile(lat, 99),
            "mean": statistics.fmean(lat) if lat else float("nan"),
        },
        "timeout_rate": round(timeout_rate, 4),
        "error_rate": round(error_rate, 4),
        "schema_valid_rate": round(len(schema_valid) / max(1, len(samples)), 4),
        "parser_repair_rate": round(len(repaired) / max(1, len(samples)), 4),
        "fail_closed_error_rate": round(fail_closed_error_rate, 4)
        if fail_closed_error_rate == fail_closed_error_rate
        else 1.0,
        "safety_violation_count": len(safety_violations),
        "consistency": {
            "direction_agreement": round(statistics.fmean(agreement), 4)
            if agreement
            else float("nan"),
            "confidence_std_mean": round(statistics.fmean(conf_stds), 4)
            if conf_stds
            else float("nan"),
        },
        "context_fidelity": {
            "failsafe_ok_rate": round(failsafe_ok_rate, 4),
            "context_citation_count": citation_count,
        },
        "token_usage_total": total_tokens,
        "repeats": repeats,
    }


def score_model(metrics: dict) -> tuple[float, dict]:
    """PROVISIONAL weighted score (weights not locked - see benchmark-spec.md)."""
    w = {
        "latency": 0.25,
        "schema": 0.25,
        "consistency": 0.20,
        "fidelity": 0.15,
        "safety": 0.10,
        "tokens": 0.05,
    }
    p50 = metrics["latency_ms"]["p50"]
    latency_score = max(0.0, 1.0 - p50 / 20000.0) if p50 == p50 else 0.0
    schema_score = metrics["schema_valid_rate"]
    agreement = metrics["consistency"]["direction_agreement"]
    consistency_score = agreement if agreement == agreement else 0.0
    fidelity_score = metrics["context_fidelity"]["failsafe_ok_rate"]
    safety_score = 1.0 - metrics["safety_violation_count"] / max(1, metrics["repeats"] * 12)
    total_tokens = metrics["token_usage_total"]
    token_score = max(0.0, 1.0 - total_tokens / 1_000_000.0)
    score = sum(
        w[k] * v
        for k, v in {
            "latency": latency_score,
            "schema": schema_score,
            "consistency": consistency_score,
            "fidelity": fidelity_score,
            "safety": safety_score,
            "tokens": token_score,
        }.items()
    )
    return round(score, 4), {
        "weights_provisional": w,
        "components": {
            "latency": round(latency_score, 4),
            "schema": round(schema_score, 4),
            "consistency": round(consistency_score, 4),
            "fidelity": round(fidelity_score, 4),
            "safety": round(safety_score, 4),
            "tokens": round(token_score, 4),
        },
    }


def hard_fail_reasons(metrics: dict) -> list[str]:
    reasons: list[str] = []
    if metrics["schema_valid_rate"] < 0.7:
        reasons.append("schema_valid_rate<0.7")
    if metrics["timeout_rate"] > 0.3:
        reasons.append("timeout_rate>0.3")
    agreement = metrics["consistency"]["direction_agreement"]
    if agreement == agreement and agreement < 0.6:
        reasons.append("direction_agreement<0.6")
    if metrics["safety_violation_count"] > 0:
        reasons.append("safety_violations_present")
    return reasons


def slugify(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def run_benchmark(
    base_url: str,
    api_key: str,
    dataset_path: Path,
    outdir: Path,
    models: list[str],
    repeats: int,
    timeout: float,
    delay: float,
) -> int:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    scenarios = dataset["scenarios"]
    dataset_version = dataset["dataset_version"]
    raw_dir = outdir / "raw"
    normalized_dir = outdir / "normalized"
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)

    total = len(models) * len(scenarios) * repeats
    done = 0
    all_normalized: list[dict] = []
    metrics_by_model: dict[str, dict] = {}
    score_by_model: dict[str, dict] = {}

    for model in models:
        provider = model.split("/", 1)[0]
        print(f"[benchmark] model={model} provider={provider}", flush=True)
        samples: list[dict] = []
        consecutive_transport = 0
        aborted = False
        for scenario in scenarios:
            for repeat in range(1, repeats + 1):
                done += 1
                if aborted:
                    break
                user_prompt = build_user_prompt(scenario["market_context"])
                status, latency, raw_text, error, usage = call_model(
                    base_url,
                    api_key,
                    model,
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    timeout,
                )
                output, parse_meta = (
                    parse_and_normalize(raw_text)
                    if status == "OK"
                    else (
                        dict(ERROR_NO_TRADE),
                        {"ok": False, "error": status, "extraction_path": "n/a", "repaired": True},
                    )
                )
                if status == "OK":
                    payload_keys: set[str] = set()
                    i = raw_text.rfind("}")
                    if i >= 0:
                        try:
                            payload_keys = (
                                set(
                                    json.loads(raw_text[: i + 1])
                                    .get("choices", [{}])[0]
                                    .get("message", {})
                                    .get("content", {})
                                    .keys()
                                )
                                if isinstance(
                                    json.loads(raw_text[: i + 1])
                                    .get("choices", [{}])[0]
                                    .get("message", {})
                                    .get("content"),
                                    dict,
                                )
                                else set()
                            )
                        except (json.JSONDecodeError, KeyError, TypeError):
                            pass
                    violations = safety_violations(output, payload_keys)
                else:
                    violations = []
                schema_valid = (
                    parse_meta.get("ok", False)
                    and output["direction"] in {"BUY", "SELL", "NO-TRADE"}
                    and isinstance(output["confidence"], (int, float))
                )
                sample = {
                    "benchmark_version": BENCHMARK_VERSION,
                    "dataset_version": dataset_version,
                    "prompt_version": PROMPT_VERSION,
                    "model": model,
                    "provider": provider,
                    "scenario_id": scenario["id"],
                    "scenario_name": scenario["name"],
                    "repeat": repeat,
                    "started_at": now_iso(),
                    "latency_ms": round(latency, 1),
                    "status": status,
                    "error": error,
                    "raw_response": raw_text,
                    "normalized": {"output": output, "parse": parse_meta},
                    "validation": {"schema_valid": schema_valid, "safety_violations": violations},
                    "usage": usage,
                    "fidelity": fidelity_assessment({"normalized": {"output": output}}, scenario),
                }
                samples.append(sample)
                if status in {"TIMEOUT", "TRANSPORT_ERROR", "HTTP429"}:
                    consecutive_transport += 1
                else:
                    consecutive_transport = 0
                if consecutive_transport >= 5:
                    aborted = True
                    print(
                        f"[benchmark] ABORT model={model} after "
                        f"{consecutive_transport} consecutive transport failures",
                        flush=True,
                    )
                if delay > 0:
                    time.sleep(delay)
            if aborted:
                break
        metrics = compute_metrics(samples, dataset, repeats)
        score, score_detail = score_model(metrics)
        metrics["hard_fail_reasons"] = hard_fail_reasons(metrics)
        metrics["aborted"] = aborted
        metrics_by_model[model] = metrics
        score_by_model[model] = {"score": score, **score_detail}
        all_normalized.extend(samples)
        slug = slugify(model)
        (raw_dir / f"{slug}.jsonl").write_text(
            "\n".join(json.dumps(s, ensure_ascii=False) for s in samples) + "\n", encoding="utf-8"
        )
        print(
            f"[benchmark] {done}/{total} done - model={model} "
            f"p50={metrics['latency_ms']['p50']:.0f}ms "
            f"schema={metrics['schema_valid_rate']} score={score}",
            flush=True,
        )

    normalized_path = normalized_dir / "results.json"
    normalized_path.write_text(
        json.dumps(all_normalized, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    summary = {
        "benchmark_version": BENCHMARK_VERSION,
        "dataset_version": dataset_version,
        "prompt_version": PROMPT_VERSION,
        "metrics": metrics_by_model,
        "scores": score_by_model,
    }
    (normalized_dir / "metrics.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[benchmark] done. results -> {normalized_dir}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ABC Bot AI model benchmark runner")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DIR / "dataset.json")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_DIR / "results")
    parser.add_argument("--models", type=str, default=",".join(MODELS))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--delay", type=float, default=0.4, help="pause between requests (seconds)")
    args = parser.parse_args()
    base_url, api_key = load_env()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    return run_benchmark(
        base_url, api_key, args.dataset, args.outdir, models, args.repeats, args.timeout, args.delay
    )


if __name__ == "__main__":
    sys.exit(main())
