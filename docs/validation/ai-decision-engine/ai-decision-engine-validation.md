# AI Decision Engine — Validation Report

Version `0.1.0` · prompt `v1.0.0` · validated 2026-08-17
Implementation: `ai_decision/` (parse, validate, client, engine, gate, record)
Tests: `tests/unit/test_ai_decision_parsing.py`, `test_ai_decision_validation.py`,
`test_ai_decision_engine.py`, `tests/integration/test_ai_decision_system_gate.py`

## 1. Objective

Implement the AI Decision Engine as a **proposal-only** layer: market context
in -> `BUY|SELL|NO-TRADE` proposal out. The AI must never decide lot, risk, SL,
exposure, execution, or exit; the System stays authority for those, the EA stays
authority for MT5 execution. No live trading, no Risk Engine, no EA logic in
this task.

## 2. Architecture

```
Market Context (dict)
   -> validate_context         (INVALID_CONTEXT -> fail-closed NO-TRADE)
   -> Prompt Construction      (SYSTEM + USER, deterministic, sort_keys)
   -> AI Inference             (non-stream POST, stdlib urllib, 60 s timeout)
   -> Response Parsing         (parsing.py: JSON object, string JSON, SSE
                                [DONE] tail, reasoning_content, empty, malformed)
   -> Schema Validation        (validation.py: direction/confidence/reason/
                                authority boundary)
   -> Decision Validation      (strict: confidence 0..1, reason string, no
                                forbidden keys/phrases)
   -> DecisionRecord           (auditable, fallback_level + latency + errors)
   -> SystemGate               (interface only: APPROVE/REJECT; full Risk
                                Engine is a separate task)
```

Modules: `config.py` (approved model chain + env secrets), `prompt.py`,
`client.py` (urllib transport), `parsing.py`, `validation.py`, `record.py`,
`engine.py` (fallback + retry orchestration), `gate.py` (boundary interface).

## 3. AI Authority

AI produces ONLY: `direction`, `confidence`, `reason`.
AI NEVER produces: lot, position_size, risk_percent/amount, SL, TP, exposure,
margin, broker order parameters, execution/exit commands, compounding.
Enforced twice: `FORBIDDEN_OUTPUT_KEYS` (payload keys) + `FORBIDDEN_REASON_PHRASES`
(reason text); any violation -> `AUTHORITY_VIOLATION` -> fail-closed NO-TRADE,
decision NOT forwarded to system approval.

## 4. Model Configuration

Exact approved IDs (selection gate 2026-08-17, verified via `GET /v1/models`);
no shorthand accepted:

- PRIMARY: `cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast`
- SECONDARY: `groq/llama-3.3-70b-versatile`
- FALLBACK: `cf/@cf/qwen/qwen2.5-coder-32b-instruct`
- Endpoint: `http://10.197.141.202:20128/v1` (env `ABC_AI_BASE_URL`)
- API key: env `ABC_AI_API_KEY` only; never stored/committed/logged
- Request: max_tokens 512, temperature 0.0, timeout 60 s (spec v1.0.0)

## 5. Input Contract

Minimum locked market-context (project context): `symbol`, `bid`, `ask`,
`spread`, `mid`, `atr_m1`, `m1` (dict), `m5` (dict | None). Optional:
`atr_m5`, `derived`, `context_snapshot_id` (audit key), `m1_trend`/`m5_trend`
passed through unchanged. No new market features invented (task constraint).
Missing or malformed keys -> `INVALID_CONTEXT` -> NO-TRADE without inference.

## 6. Output Contract

```json
{"direction": "BUY|SELL|NO-TRADE", "confidence": 0.0, "reason": "string"}
```

- direction: exact token (aliases like hold/wait/none/neutral fail-closed to
  NO-TRADE, mirroring benchmark runner normalization)
- confidence: finite number in [0,1]; out-of-range/missing -> SCHEMA_ERROR
- reason: string (may be empty); non-string/missing -> SCHEMA_ERROR;
  length cap 2000
- NO-TRADE is a first-class valid output; every failure path also ends in
  NO-TRADE with confidence 0.0

## 7. Validation

Deterministic standalone validators (no risk logic inside):
`validate_direction()`, `validate_confidence()`, `validate_reason()`,
`validate_authority_boundary()`, `validate_schema()`. Schema strict on
confidence (reject, then NO-TRADE — never clamp) and reason; direction
normalized fail-closed. All failures persisted into DecisionRecord
(`schema_errors`, `error_class`).

## 8. Failure Handling

| Class | Behavior |
|---|---|
| invalid context | NO-TRADE, `INVALID_CONTEXT`, no inference |
| parse fail (empty/malformed/prose/non-JSON) | NO-TRADE, `PARSE_ERROR`, no retry |
| schema fail (bad confidence/reason/authority) | NO-TRADE, `SCHEMA_ERROR`/`AUTHORITY_VIOLATION`, no retry |
| HTTP429 | bounded retry (1, sleep 10 s) then next fallback level |
| TIMEOUT / 5xx / connection | bounded retry (1) then next fallback level |
| HTTP400 / auth | no retry, next fallback level |
| all levels exhausted | NO-TRADE, `PROVIDER_FAILURE`, fallback_level=3 |

Invalid AI output is never rerun as a network retry (no data-quality retry
storm). Retry budget bounded: `max_attempts=2` per level (configurable).

## 9. Fallback

```
PRIMARY (cf/llama-3.1-8b-fp8-fast)
   ↓ failure/unavailable
SECONDARY (groq/llama-3.3-70b-versatile)
   ↓ failure/unavailable
FALLBACK (cf/qwen2.5-coder-32b)
   ↓ failure
NO-TRADE (fail-closed)
```

Bounded, deterministic, no infinite loops; `fallback_level` recorded (0..3).

## 10. Observability

Request-side: inference_id (uuid4), model_id, provider, request_ts, latency_ms,
context_snapshot_id, prompt_version, correlation_id (optional).
Response-side: direction, confidence, validation_ok, schema_errors, error_class,
error_detail, repair, fallback_level, attempts, retried, total_latency_ms.
Structured logs via `logging.getLogger("ai_decision")`; raw model output never
logged; secrets never logged. Fields align with canonical `AI_REQUEST` /
`AI_RESPONSE` payload specs so records can be emitted as events later without
contract change.

## 11. Tests

71 new tests (431 total repo-wide), all deterministic with mocked provider:

- Valid outputs: BUY, SELL, NO-TRADE (first-class)
- Invalid: unknown/aliased direction, missing/out-of-range/non-finite
  confidence, missing/non-string reason, malformed JSON, natural-language-only,
  empty content, forbidden keys (lot/position_size/SL/TP/...), forbidden reason
  phrases, reasoning-only response
- Provider failures: timeout, 429, 400, 500, connection error, malformed
  response, body + trailing `data: [DONE]`
- Fallback: primary success; primary fail -> secondary; secondary fail ->
  fallback; all fail -> NO-TRADE
- Safety: no executable order fields in DecisionRecord; engine has no
  execute/submit/order methods; ai_decision modules import no MT5/broker
  symbols (AST import scan); gate interface APPROVE/REJECT
- Integration: MarketContext -> engine (mocked) -> validation -> SystemGate

Live smoke (non-trading, single call, 2026-08-17): PRIMARY returned
`{"direction":"BUY","confidence":0.8,"reason":"m1_trend up, m5_trend sideways,
spread 0.3"}`, latency 1032 ms, validation_ok=True, fallback_level=0 — no
rerun of the benchmark.

## 12. Safety Verification

- No lot/risk/SL/exposure/margin/execution/exit computation anywhere in
  ai_decision (tests assert absence on record + API surface)
- No MT5 import/order capability (AST-scanned)
- No live broker contact (integration uses mocked transport)
- Fail-closed on every failure class; timeout per spec v1.0.0 (60 s)
- Secrets only from environment; report/commit contain no credentials

## 13. Known Limitations

- SystemGate is boundary-only: full Risk Engine gate (lot sizing, risk
  budget, exposures, SL rules) is a separate task, not implemented here.
- Confidence is not mapped to any risk scaling; AI output is proposal only.
- balance/margin/live paths intentionally absent (paper-trading project).
- `ollama`-style routes that omit `usage` are not relied upon (token metrics
  are informational only here).
- Prompt `v1.0.0` matches the benchmark prompt; any prompt change requires a
  new prompt version and re-benchmark evidence.

## 14. Acceptance

| Criterion | Status |
|---|---|
| Primary exact ID used (`cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast`) | ✅ |
| Fallback chain deterministic and bounded | ✅ |
| AI output strict schema | ✅ |
| AI never decides lot/risk/SL/exposure | ✅ (enforced + tested) |
| Timeout fail-closed | ✅ |
| Malformed response fail-closed | ✅ |
| Provider failure safe | ✅ |
| NO-TRADE valid first-class | ✅ |
| Observability (inference_id, model, latency, fallback, errors) | ✅ |
| pytest 431 passed | ✅ |
| ruff check / format clean | ✅ |
| mypy clean (57 files, incl. ai_decision) | ✅ |
| No MT5 order capability / no live trading | ✅ |
| AGENTS.md updated | ✅ |

VERDICT: PASS — AI Decision Engine ready; next milestone (separate task):
Risk Engine gate, then EA/execution integration.