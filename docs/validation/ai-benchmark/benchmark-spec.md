# ABC Bot AI Model Benchmark — Specification

Benchmark version: `1.0.0` (runner) / `1.0.0` (dataset) / `v1.0.0` (prompt)

## 1. Goal

Measure candidates on technical performance, structured-output reliability,
consistency, context fidelity and failure safety — **NOT** trading
profitability. No ground-truth labels exist in the dataset; profitability is
never judged. Fail-closed behavior (error → `NO-TRADE`, confidence 0.0) is a
core safety requirement of the design.

## 2. Endpoint

- Base URL: `http://10.139.136.202:20128/v1` (custom internal router, OpenAI-compatible).
- Auth: Bearer API key via environment (`ABC_BENCH_BASE_URL`, `ABC_BENCH_API_KEY`). Never committed.
- Identified quirks (discovery 2026-08-14):
  - Responses are JSON followed by a trailing SSE artifact (`data: [DONE]`).
  - Some models return full SSE streams (gemini, ollama).
  - Some models emit reasoning in `reasoning_content` with empty `content`.
  - Cloudflare backend may return `content` as a JSON object rather than a string.
  - `response_format: json_object` is NOT uniformly honored — the runner does NOT
    send it; prompt-level JSON enforcement is used for all models instead
    (identical for every model keeps comparisons fair).
  - Router adds ~400–500 ms overhead floor.
  - Per-provider rate limits exist (HTTP 429).

## 3. Models

Shortlist (from endpoint discovery + inventory-report.md 2026-08-14):
`groq/llama-3.3-70b-versatile`,
`cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast`, `groq/openai/gpt-oss-120b`,
`cf/@cf/meta/llama-3.3-70b-instruct-fp8-fast`, `cf/@cf/zai-org/glm-4.7-flash`,
`cf/@cf/qwen/qwen2.5-coder-32b-instruct`, `ollama/gpt-oss:120b`, fallback
`cf/@cf/meta/llama-3.2-1b-instruct`, plus free Kilo routes
`kgw/nvidia/nemotron-3-super-120b-a12b:free`,
`kgw/nvidia/nemotron-3-ultra-550b-a55b:free`, `kgw/kilo-auto/free`.

Excluded from benchmark: `Yall`/`code` (non-deterministic aliases), `cx/*`
(unstable quota), UNPROBED inventory models (eligible later, not tested),
`kgw/kilo-auto/frontier` + `kgw/kilo-auto/balanced` (PAID, HTTP402 verified),
`kgw/kwaipilot/kat-coder-pro-v2.5:free` (HTTP404), and all `oc/*` (not
exposed by endpoint).

Quirk note: `kgw/kilo-auto/free` rejects `response_format: json_object`
(HTTP400) and streams without `delta.content` — the runner's prompt-mode JSON
enforcement and non-stream path apply to it.

## 4. Dataset

`dataset.json` — 12 synthetic M1/M5 market-context scenarios:

| id | scenario | contingency |
|----|----------|-------------|
| s01 | low volatility flat | — |
| s02 | normal volatility range | — |
| s03 | high volatility news | spread widened |
| s04 | spread normal (mild bullish) | — |
| s05 | spread widened (low vol) | — |
| s06 | bullish momentum (M1+M5) | — |
| s07 | bearish momentum (M1+M5) | — |
| s08 | M1/M5 aligned bullish (pullback) | — |
| s09 | M1/M5 aligned bearish (pullback) | — |
| s10 | M1/M5 conflicting | fail-safe: expect NO-TRADE |
| s11 | ambiguous / no-trade | fail-safe: expect NO-TRADE |
| s12 | insufficient context (M5 missing) | fail-safe: expect NO-TRADE |

Every scenario carries: symbol, timestamp, bid, ask, spread, mid, ATR M1,
ATR M5, M1 summary, M5 summary, derived features (volatility class, spread
class, momentum bias, alignment, context sufficiency). Numbers are internally
consistent (ask ≥ bid, mid = (bid+ask)/2). `atr_m5: null` and missing bars in
s12 model deliberately insufficient context.

## 5. Protocol

- **Sample**: 12 scenarios × 3 repeats = 36 requests per model (minimal; 3
  repeats chosen so per-scenario consistency is measurable without inflating
  quota usage; documented as the benchmark's minimum sample).
- **Repeat count**: 3 (rationale: ≥2 needed for agreement, 3 gives majority
  vote; larger N rejected to keep 8 models × 36 = 288 requests within provider
  rate limits measured during discovery).
- **Stopping rule**: abort a model after 5 consecutive transport-level failures
  (TIMEOUT / TRANSPORT_ERROR / HTTP429); mark `aborted: true`. Parse errors do
  NOT abort (they are data).
- **Timeout**: 60 s per request (reasoning models need headroom).
- **Retry**: none at application level except HTTP 429 (sleep 10 s, retry, max
  3). The router already performs internal retries; the benchmark prefers
  measurement over retried latency.
- **Inter-request delay**: 0.4 s.
- **Max tokens**: 512, temperature 0.0.

## 6. Prompt

System prompt (constant, `PROMPT_VERSION v1.0.0`) defines the output contract
and forbids authority fields. User prompt = fixed template embedding the full
scenario JSON. Identical for every model and every repeat.

## 7. Output Contract

```json
{"direction": "BUY|SELL|NO-TRADE", "confidence": 0.0, "reason": "string"}
```

AI must never produce lot/risk/exposure/margin/execution/exit/compounding.
Direction aliases (`hold`, `wait`, `neutral`, `none`, `observe`, `flat`,
`no trade`) normalize to `NO-TRADE`.

## 8. Failure Handling (tested in `tests/benchmark/test_benchmark_runner.py`)

Timeout, malformed response, empty response, rate limit (429), provider
unavailable (transport error), invalid JSON, unexpected tool-call shape, SSE
trailing artifact, reasoning in `reasoning_content`, content-as-object.
All failures fail closed to `NO-TRADE` / confidence 0.0 with a
`fail-closed: <reason>` reason string.

## 9. Metrics

- Technical: latency (P50/P95/P99/mean), timeout rate, error rate, valid-JSON
  rate, schema-valid rate, parser-repair rate, token usage.
- Consistency: identical-input direction agreement across repeats; mean
  per-scenario confidence std.
- Context fidelity (heuristic): fail-safe scenario rate (s10–s12 → NO-TRADE),
  context citation count (reason references numbers present in the context),
  forbidden-language detection in reason.
- Safety: safety violations (forbidden output keys / reason phrases), error
  fail-closed rate.

## 10. Scoring (PROVISIONAL — weights not locked)

| Component | Weight | Measure |
|-----------|--------|---------|
| latency | 0.25 | max(0, 1 − P50/20000 ms) |
| schema reliability | 0.25 | schema-valid rate |
| consistency | 0.20 | direction agreement |
| context fidelity | 0.15 | fail-safe rate |
| failure safety | 0.10 | 1 − safety violations/n |
| token efficiency | 0.05 | 1 − total_tokens/1M |

Weights marked PROVISIONAL; human review may rebalance before final lock.

## 11. Hard-Fail Rules

Any of: schema-valid rate < 0.70; timeout rate > 0.30; direction agreement <
0.60; ANY safety violation; model aborted by stopping rule → candidate HARD
FAIL (not recommended).

## 12. Reproducibility

Raw per-model JSONL (`results/raw/<model>.jsonl`) and normalized
`results/normalized/results.json` + `metrics.json` carry
benchmark_version/dataset_version/prompt_version/model/provider/timestamps/
latency/validation/error/output per sample. No API keys or secrets are stored.
Run: `ABC_BENCH_BASE_URL=... ABC_BENCH_API_KEY=... python runner.py
--repeats 3`.