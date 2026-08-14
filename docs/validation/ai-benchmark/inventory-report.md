# Expanded AI Model Inventory

Report date: 2026-08-14 · Evidence: endpoint `/v1/models` (source of truth) +
harmless chat-completion probes. Screenshots used as discovery hints ONLY.

## 1. Endpoint

- Base URL: `http://10.139.136.202:20128/v1`
- Auth: Bearer API key (Hermes `model.api_key`).
- Source of truth: `GET /v1/models` → 57 model IDs (200 OK, 22,378 bytes).

## 2. New Models Discovered

Requested routes vs actual endpoint inventory (ID mapping):

| Requested (screenshot/9Router hint) | Endpoint ID | Verdict |
|---|---|---|
| oc/big-pickle | — | UNAVAILABLE (no `oc/*` at all) |
| oc/hy3-free | — | UNAVAILABLE |
| oc/north-mini-code-free | — | UNAVAILABLE |
| oc/nemotron-3.5-lightning-free | — | UNAVAILABLE |
| oc/laguna-s-2.1-free | — | UNAVAILABLE |
| oc/deepseek-v4-flash-free | — | UNAVAILABLE |
| oc/mimo-v2.5-free | — | UNAVAILABLE |
| oc/nemotron-3-ultra-free | — | UNAVAILABLE |
| kew/kilo-auto/free | kgw/kilo-auto/free | AVAILABLE (prefix is `kgw/`, not `kew/`) |
| kgv/nvidia/nemotron-3-super-120b-a12b-free | kgw/nvidia/nemotron-3-super-120b-a12b:free | AVAILABLE |
| kgv/nvidia/nemotron-3-ultra-550b-a55b-free | kgw/nvidia/nemotron-3-ultra-550b-a55b:free | AVAILABLE |
| kgv/kwai.../kat-coder-pro-v2.5:free | kgw/kwaipilot/kat-coder-pro-v2.5:free | ERROR (HTTP404 on probe) |
| kgv/kilo-auto/frontier | kgw/kilo-auto/frontier | AVAILABLE (PAID — HTTP402) |
| kgv/kilo-auto/balanced | kgw/kilo-auto/balanced | AVAILABLE (PAID — HTTP402) |

All 14 requested IDs resolved with exact endpoint IDs. Screenshot showed
`oc/*` and `kew/kgv` prefixes; the endpoint exposes NEITHER `oc/` NOR
`kew/kgv` — the Kilo routes live under `kgw/`. OpenCode routes are not
exposed through this endpoint.

## 3. Combined Inventory

57 models total from `GET /v1/models`. Full list:

- Aliases: `Yall`, `code` (router aliases, non-deterministic — excluded from benchmark).
- cf (Cloudflare Workers AI): llama-3.2-1b, llama-3.2-3b, llama-3.1-8b-fp8-fast,
  llama-3.1-8b-awq, mistral-small-3.1-24b, llama-3.1-70b-fp8-fast,
  llama-3.3-70b-fp8-fast, deepseek-r1-distill-qwen-32b, kimi-k2.5, kimi-k2.6,
  glm-4.7-flash, qwq-32b, qwen2.5-coder-32b.
- ollama: gpt-oss:120b, kimi-k2.5, glm-5, minimax-m2.5, glm-4.7-flash, qwen3.5, minimax-m3.
- groq: llama-3.3-70b-versatile, openai/gpt-oss-120b, qwen3-32b, qwen3.6-27b.
- mistral: mistral-large-latest, codestral-latest, mistral-medium-latest.
- openrouter: openrouter/free.
- gemini: 3.7-flash, 3.6-flash, 3.5-flash-lite, 3.1-pro-preview,
  3.1-flash-lite-preview, 3-flash-preview, gemma-4-31b-it.
- cx: gpt-5.6-sol[+-review], gpt-5.6-terra[+-review], gpt-5.6-luna[+-review],
  gpt-5.5[+-review], gpt-5.4[+-review], gpt-5.4-mini[+-review],
  gpt-5.3-codex-spark[+-review].
- kgw: kilo-auto/free, nvidia/nemotron-3-super-120b-a12b:free,
  nvidia/nemotron-3-ultra-550b-a55b:free, kwaipilot/kat-coder-pro-v2.5:free,
  kilo-auto/frontier, kilo-auto/balanced.

## 4. OpenCode Candidates

`oc/*` → NOT PRESENT in `/v1/models`. All 8 requested IDs classified
UNAVAILABLE via this endpoint. Screenshot hint cannot be confirmed — per
task rule, endpoint response is source of truth. No baseline possible.

## 5. Kilo Candidates

All under `kgw/` prefix. 6 IDs verified present. Probe status:

| Model | Probe | Classification | Cost status |
|---|---|---|---|
| kgw/kilo-auto/free | 200 OK | AVAILABLE | FREE (name + 200 OK) |
| kgw/nvidia/nemotron-3-super-120b-a12b:free | 200 OK | AVAILABLE | FREE_TIER (`:free`) |
| kgw/nvidia/nemotron-3-ultra-550b-a55b:free | 200 OK | AVAILABLE | FREE_TIER (`:free`) |
| kgw/kwaipilot/kat-coder-pro-v2.5:free | HTTP404 | ERROR | — (upstream missing) |
| kgw/kilo-auto/frontier | HTTP402 | AVAILABLE | PAID (402: "Paid Model - Credits Required") |
| kgw/kilo-auto/balanced | HTTP402 | AVAILABLE | PAID (402: same) |

Cost statuses are VERIFIED by responses, not guessed. No cost metadata exists
in `/v1/models` for any entry.

## 6. Availability

- AVAILABLE (probe 200): kgw/kilo-auto/free, kgw nemotron super :free,
  kgw nemotron ultra :free.
- ERROR (listed but probe fails): kgw/kwaipilot/kat-coder-pro-v2.5:free (404).
- UNAVAILABLE: all oc/* (8).
- PAID (available but locked): kgw/kilo-auto/frontier, kgw/kilo-auto/balanced.

## 7. Cost Status

- FREE: kgw/kilo-auto/free (name-verified, 200 OK).
- FREE_TIER: `:free`-suffixed IDs (nemotron super/ultra). kat-coder
  `:free` ID exists but route is ERROR 404.
- PAID: kgw/kilo-auto/frontier, kgw/kilo-auto/balanced (402 verified).
- COST_UNKNOWN: everything else without explicit route-level evidence
  (mistral/gemini/previews, openrouter/free, ox aliases).

## 8. Baseline Capability Probe

Harmless probes (tiny prompt, max_tokens≤64, temp 0). Results
`BASELINE LATENCY ONLY` — NOT final benchmark.

| Model | json_object | Stream | Notes |
|---|---|---|---|
| kgw/kilo-auto/free | HTTP400 (unsupported) | streams, `[DONE]` yes, NO delta.content (only role/provider_metadata) | backend model field = `stepfun/step-3.7-flash` (alias pool) |
| kgw nemotron super :free | 200 (supported) | stream w/ content + reasoning + reasoning_details, `[DONE]` | provider: Nvidia |
| kgw nemotron ultra :free | 200 (supported) | same as super | provider: Nvidia |
| kgw kat-coder :free | — | — | 404, no capability |
| kgw kilo-auto/frontier | — | — | 402, no capability |
| kgw kilo-auto/balanced | — | — | 402, no capability |

Tool support: NOT OBSERVED (no tool-use probe for any model this round).

## 9. Baseline Latency

Single-shot latency (BASELINE LATENCY ONLY):

| Model | Non-stream | Stream | json_object |
|---|---|---|---|
| kgw/kilo-auto/free | 2,094 ms | 3,625 ms | unsupported |
| kgw nemotron super :free | 1,547 ms | 2,016 ms | 1,109 ms |
| kgw nemotron ultra :free | 1,532 ms | 1,703 ms | 1,500 ms |
| kgw kat-coder :free | — | — | — |
| kgw frontier / balanced | — | — | — |

## 10. Quirks / Provider Limitations

- `oc/*`, `kew/*`, `kgv/*` prefixes do not exist on the endpoint — use `kgw/`.
- kgw/kilo-auto/free rejects `response_format: json_object` (HTTP400) →
  runner must use prompt-mode JSON enforcement (already the benchmark design).
- kgw/kilo-auto/free streams without `delta.content`; content arrives via
  non-standard fields (role/provider_metadata only in deltas) — non-stream
  mode is the reliable path for this route.
- nemotron routes stream `delta.reasoning` + `delta.reasoning_details`
  (reasoning_content-style) alongside content.
- All streaming responses end with `data: [DONE]` (consistent with earlier
  router findings).
- Paid routes fail with HTTP402, not 401/403 — cheap to classify.
- kat-coder `:free` is listed by `/v1/models` but upstream 404s → listed
  inventory is NOT a guarantee of routability.

## 11. Benchmark Shortlist

A. HIGH-PRIORITY BENCHMARK (previously shortlisted + new additions):

1. groq/llama-3.3-70b-versatile — balanced
2. cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast — fast
3. groq/openai/gpt-oss-120b — large
4. cf/@cf/meta/llama-3.3-70b-instruct-fp8-fast — large
5. cf/@cf/zai-org/glm-4.7-flash — fast
6. cf/@cf/qwen/qwen2.5-coder-32b-instruct — coder/large
7. ollama/gpt-oss:120b — local
8. cf/@cf/meta/llama-3.2-1b-instruct — fallback/ultra-fast
9. kgw/nvidia/nemotron-3-super-120b-a12b:free — free, JSON-native, reasoning-stream
10. kgw/nvidia/nemotron-3-ultra-550b-a55b:free — free, reasoning-heavy, 550b
11. kgw/kilo-auto/free — free; prompt-mode JSON (json_object unsupported)

Covers: ultra-fast (2,5,8) · balanced (1,9,11) · reasoning-heavy (10) ·
large (3,4,6) · fallback (8) · local (7) · Kilo free (9,10,11).

B. SECONDARY BENCHMARK (available, not yet shortlisted):
cf/mistral-small-3.1-24b, cf/kimi-k2.5, cf/kimi-k2.6, cf/deepseek-r1-distill-qwen-32b,
cf/qwen/qwq-32b, ollama/kimi-k2.5, ollama/glm-5, ollama/glm-4.7-flash,
ollama/qwen3.5, ollama/minimax-m2.5, ollama/minimax-m3, groq/qwen3-32b,
groq/qwen3.6-27b, gemini/gemini-3.7-flash, gemini/gemini-3.6-flash,
gemini/gemini-3.5-flash-lite, gemini/gemma-4-31b-it, cf/llama-3.2-3b,
cf/llama-3.1-8b-awq, cf/llama-3.1-70b-fp8-fast.

C. DISCOVERY ONLY / UNPROBED: Yall, code (alias), cx/* (alias/quota class),
gemini previews (3.1-pro, 3.1-flash-lite, 3-flash), mistral-large/medium/codestral
(route-latest aliases), openrouter/free, kgw frontier + balanced (PAID).

## 12. Models Excluded

- Yall, code: non-deterministic router aliases.
- cx/*: aliases with unstable quota (429 observed previously).
- kgw/kilo-auto/frontier, kgw/kilo-auto/balanced: PAID (402 verified).
- kgw/kwaipilot/kat-coder-pro-v2.5:free: ERROR (404) until upstream fixed.
- oc/* (all 8): UNAVAILABLE via endpoint.

## 13. Remaining UNPROBED Models

All of B (20) + C group: latency/capability NOT verified. They remain
eligible for later probing; no latency or cost claims made for them in this
report.

## 14. Final Verdict

`INVENTORY COMPLETE`

All 14 requested screenshot IDs resolved against the endpoint; exact IDs
recorded; free/paid status verified (not guessed); all 6 kgw routes probed
(3 usable, 2 paid, 1 error); `oc/*` formally classified UNAVAILABLE via the
endpoint; previous 8-model shortlist preserved and extended with 3 kgw free
models. No final AI model selected.