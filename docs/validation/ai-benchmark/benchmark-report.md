# AI Benchmark Report

Benchmark version `1.0.0` · dataset `1.0.0` · prompt `v1.0.0`
Report generated: 2026-08-15 (after run window 2026-08-14 17:39–18:14 UTC = 00:39–01:14 +07)
Evidence base: `benchmark-spec.md`, `inventory-report.md`, `dataset.json`, `results/raw/*.jsonl` (11 files, 396 records), `results/normalized/results.json` + `metrics.json`, `runner.py`, `tests/benchmark/test_benchmark_runner.py` (22 tests).

## 1. Executive Summary

396/396 requests complete for 11 candidate models (12 scenarios × 3 repeats) against the internal router `http://10.139.136.202:20128/v1`. Raw results verified: no duplicates, no missing combinations, no malformed records, timestamps monotonic, payloads real. Independent recomputation of every metric and score matches the stored `metrics.json` exactly (0 diffs across 11 models).

- **Benchmark Winner:** `groq/llama-3.3-70b-versatile` (0.9903).
- **Operational Winner:** `cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast` (0.9901; p95 777 ms vs 1107 ms, worst-case 2.7 s vs 10.9 s, confidence std 0.0, fewer tokens).
- **Final Approved Model: PENDING USER/PROJECT APPROVAL.** No model selected in this task.

Two hard-fail candidates: `cf/@cf/zai-org/glm-4.7-flash` (0/36 usable — 31 HTTP400 + 5 transport) and `cf/@cf/meta/llama-3.2-1b-instruct` (schema-valid 0.2778). All 11 models achieved 100% fail-safe behavior (s10–s12 → NO-TRADE); zero safety violations; zero timeouts (request timeout was 60 s per spec §5 — none hit it).

## 2. Benchmark Scope

- Measure technical performance, structured-output reliability, consistency, context fidelity, failure safety — NOT trading profitability (no ground-truth labels; spec §1).
- 11 shortlisted models (inventory-report.md §11; spec §3) — see §4.
- Endpoint: `http://10.139.136.202:20128/v1` (OpenAI-compatible, custom router, ~400–500 ms overhead floor per spec §2).
- Fail-closed contract: any error → `NO-TRADE`, confidence 0.0 (spec §8).
- Fixed: 12 scenarios × 3 repeats = 36 requests/model, temp 0.0, max_tokens 512, inter-request delay 0.4 s, timeout 60 s, HTTP429 retry 3×10 s (spec §5; runner.py lines 58–62).

## 3. Benchmark Specification

Verified against `benchmark-spec.md` and `tests/benchmark/test_benchmark_runner.py` (22 tests, TEST-VERIFIED):

| Item | Spec value | Evidence |
|---|---|---|
| version | 1.0.0 (runner/dataset/prompt) | runner.py:26–27 |
| scenarios | 12 (s01–s12) | dataset.json (OBSERVED) |
| repeats | 3 | spec §5; raw records (OBSERVED) |
| request timeout | 60 s | spec §5; runner.py:699 |
| retry | HTTP429 only, max 3, sleep 10 s | spec §5; runner.py:327–329, tests |
| stopping rule | abort after 5 consecutive transport failures | spec §5; runner.py:642–652 (NOT OBSERVED — no model aborted) |
| payload | prompt-mode JSON (no `response_format`) | spec §2/§3; runner.py:307–309 |
| scoring weights | PROVISIONAL: latency .25, schema .25, consistency .20, fidelity .15, safety .10, tokens .05 | spec §10; runner.py:472–511 |
| hard-fail | schema<0.70, timeout>0.30, agreement<0.60, any safety violation, aborted | spec §11; runner.py:514–525 |

Specification NOT modified.

## 4. Candidate Models

11 selected, exact IDs from inventory-report.md §11 (OBSERVED). Cost status VERIFIED from inventory §5/§7 (probe responses, not guessed):

| # | Model ID | Tier (verified) |
|---|---|---|
| 1 | `groq/llama-3.3-70b-versatile` | COST_UNKNOWN (no route-level evidence) |
| 2 | `cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast` | COST_UNKNOWN |
| 3 | `groq/openai/gpt-oss-120b` | COST_UNKNOWN |
| 4 | `cf/@cf/meta/llama-3.3-70b-instruct-fp8-fast` | COST_UNKNOWN |
| 5 | `cf/@cf/zai-org/glm-4.7-flash` | COST_UNKNOWN |
| 6 | `cf/@cf/qwen/qwen2.5-coder-32b-instruct` | COST_UNKNOWN |
| 7 | `ollama/gpt-oss:120b` | COST_UNKNOWN |
| 8 | `cf/@cf/meta/llama-3.2-1b-instruct` | COST_UNKNOWN |
| 9 | `kgw/nvidia/nemotron-3-super-120b-a12b:free` | FREE_TIER (`:free` suffix + 200 probe) |
| 10 | `kgw/nvidia/nemotron-3-ultra-550b-a55b:free` | FREE_TIER (`:free` suffix + 200 probe) |
| 11 | `kgw/kilo-auto/free` | FREE (name + 200 probe) |

Excluded (inventory §12): `Yall`/`code` aliases, `cx/*`, paid `kgw/kilo-auto/frontier|balanced` (HTTP402), `kgw/kwaipilot/kat-coder-pro-v2.5:free` (HTTP404), all `oc/*`. Candidate list NOT modified.

**Exact ID note (verified 2026-08-17, read-only `GET /v1/models` HTTP 200):** short labels in the tables below (e.g. `cf/llama-3.1-8b-fp8-fast`, `cf/llama-3.3-70b-fp8-fast`, `cf/qwen2.5-coder-32b`) are shorthand used in this report and in inventory-report.md §3 family lists. The endpoint does NOT accept them. The exact, implementation-valid identifiers are the full route IDs (raw benchmark records store these in the `model` field). Verified present on the endpoint: `cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast` ✓, `groq/llama-3.3-70b-versatile` ✓, `cf/@cf/qwen/qwen2.5-coder-32b-instruct` ✓, `cf/@cf/meta/llama-3.3-70b-instruct-fp8-fast` ✓, `cf/@cf/zai-org/glm-4.7-flash` ✓, `cf/@cf/meta/llama-3.2-1b-instruct` ✓, `ollama/gpt-oss:120b` ✓, `groq/openai/gpt-oss-120b` ✓, `kgw/*` free routes ✓. Endpoint reachable at `http://10.197.141.202:20128/v1` on 2026-08-17 (previous `10.139.136.202` timed out; model inventory unchanged for all shortlisted/recommended models).

## 5. Dataset & Scenarios

`dataset.json` — 12 scenarios (OBSERVED): s01 low_volatility_flat, s02 normal_volatility_range, s03 high_volatility_news (spread widened), s04 spread_normal, s05 spread_widened, s06 bullish_momentum (M1+M5), s07 bearish_momentum (M1+M5), s08 m1m5_aligned_bullish, s09 m1m5_aligned_bearish, s10 m1m5_conflicting (fail-safe: NO-TRADE), s11 ambiguous_no_trade (fail-safe), s12 insufficient_context (fail-safe). Each scenario carries symbol/timestamps/bid/ask/spread/mid/ATR M1/M5/summaries/derived features; s12 has `atr_m5: null` (insufficient context). Dataset NOT modified.

## 6. Execution Integrity

- Run performed in one continuous pass; raw write timestamps 2026-08-14 17:39:33→18:14:52 UTC (00:39–01:14 +07) (OBSERVED).
- No runner crash: all 11 per-model files closed by a final newline; normalized files written at 18:14:52 UTC as the last artifacts (OBSERVED).
- No evidence of interruption; no resume work exists (all combinations complete).
- 0 TIMEOUT, 0 HTTP429 (after retries), 0 aborted models (OBSERVED).
- Integrity rules honored: HTTP400 and transport errors kept as failures; no failure converted to success; no results deleted/edited (OBSERVED).

## 7. Raw Result Validation

Recomputed directly from `results/raw/*.jsonl` (OBSERVED/DERIVED):

| Check | Result |
|---|---|
| Total records | 396 |
| Per-model records | 11 × 36 |
| Scenario coverage | 12/12 per model |
| Repeat coverage | {1,2,3} per model per scenario |
| Unique (benchmark_version, model, scenario, repeat) | 396 / 396 |
| Duplicates | 0 |
| Missing combinations | 0 |
| Malformed JSONL lines | 0 (391/396 non-empty payloads; 5 empty = transport-error bodies, correctly recorded as failures) |
| Timestamp order | ascending within every model (OBSERVED) |
| Batch order | matches runner MODELS order (groq → cf → groq → cf → cf → cf → ollama → cf → kgw ×3) |
| Status distribution | OK 360 · HTTP400 31 · TRANSPORT_ERROR 5 |

The 36 non-OK records are entirely `cf/@cf/zai-org/glm-4.7-flash` (31 HTTP400 + 5 TRANSPORT_ERROR `WinError 10060`). Every other model returned OK 36/36.

## 8. Normalized Result Validation

`results/normalized/results.json` — 396 entries, unique keys 396/396, 1:1 mapping to raw (OBSERVED). `metrics.json` — per-model metrics + scores (OBSERVED). Independent recomputation of all metrics (n_ok, latency percentiles/mean, timeout/error/schema/repair rates, agreement, confidence std, failsafe rate, citations, tokens) and of every score using the spec §10 formula produced **0 differences > 0.001** across all 11 models vs stored values (DERIVED). Scoring consistent with spec v1.0.0 (TEST-VERIFIED formula path also covered in `test_benchmark_runner.py`).

## 9. Aggregate Results

Sorted by aggregate score (spec §10, PROVISIONAL weights) (DERIVED from OBSERVED raw):

| Rank | Model | Score | n_ok | schema | err | repair | agr | p50 (ms) | p95 (ms) | p99 (ms) | mean (ms) | max (ms) | tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | groq/llama-3.3-70b-versatile | 0.9903 | 36 | 1.0 | 0.0 | 0.0 | 1.0 | 556 | 1107 | 10919 | 877 | 10919 | 54590 |
| 2 | cf/llama-3.1-8b-fp8-fast | 0.9901 | 36 | 1.0 | 0.0 | 0.0 | 1.0 | 606 | 777 | 2731 | 664 | 2731 | 46470 |
| 3 | cf/llama-3.3-70b-fp8-fast | 0.9843 | 36 | 1.0 | 0.0 | 0.0 | 1.0 | 1067 | 3297 | 3916 | 1264 | 3916 | 46277 |
| 4 | groq/openai/gpt-oss-120b | 0.9830 | 36 | 1.0 | 0.0 | 0.0 | 1.0 | 1114 | 11878 | 13376 | 2054 | 13376 | 61627 |
| 5 | cf/qwen2.5-coder-32b | 0.9820 | 36 | 1.0 | 0.0 | 0.0 | 1.0 | 1252 | 1690 | 2564 | 1317 | 2564 | 46259 |
| 6 | kgw/nemotron-3-super-120b:free | 0.9586 | 36 | 1.0 | 0.0 | 0.0 | 1.0 | 3113 | 6352 | 6956 | 3457 | 6956 | 49388 |
| 7 | kgw/nemotron-3-ultra-550b:free | 0.9030 | 36 | 1.0 | 0.0 | 0.1111 | 0.9722 | 7126 | 22271 | 49218 | 10180 | 49218 | 47987 |
| 8 | ollama/gpt-oss:120b | 0.8946 | 36 | 0.7778 | 0.2222 | 0.2222 | 0.8889 | 2211 | 3006 | 3419 | 2296 | 3419 | 0* |
| 9 | kgw/kilo-auto/free | 0.8754 | 36 | 0.8056 | 0.1944 | 0.1944 | 0.9444 | 4974 | 9926 | 14017 | 5604 | 14017 | 53935 |
| 10 | cf/llama-3.2-1b | 0.7924 | 36 | 0.2778 | 0.7222 | 0.7222 | 0.9167 | 648 | 868 | 1889 | 697 | 1889 | 46108 |
| 11 | cf/glm-4.7-flash | 0.5000 | 0 | 0.0 | 1.0 | 1.0 | 1.0 | — | — | — | — | — | 0 |

`*` ollama route returned no `usage` object → token component scored 1.0 by default (bias noted in §19). `n_ok` = records with HTTP status OK; parse/schema failures within OK responses counted in err/schema/repair columns.

All models: failsafe rate 1.0 (s10–s12 → NO-TRADE, 9/9), safety violations 0, timeout rate 0.0, hard-fail reasons only for glm-4.7-flash and llama-3.2-1b (`schema_valid_rate<0.7`).

## 10. Latency Analysis

Target criterion (project): decision latency < 2000 ms per trade; request timeout 60 s (spec §5). All latencies include router overhead (~400–500 ms, spec §2).

| Model | p50 | p95 | p99 | mean | max | >2000 ms (of 36 OK) | Meets <2s (p95) |
|---|---|---|---|---|---|---|---|
| groq/llama-3.3-70b-versatile | 556 | 1107 | 10919 | 877 | 10919 | 1 | YES (1 tail outlier at 10.9 s) |
| cf/llama-3.1-8b-fp8-fast | 606 | 777 | 2731 | 664 | 2731 | 1 | YES (1 mild outlier 2.7 s) |
| cf/llama-3.3-70b-fp8-fast | 1067 | 3297 | 3916 | 1264 | 3916 | 3 | NO (p95 3.3 s) |
| groq/gpt-oss-120b | 1114 | 11878 | 13376 | 2054 | 13376 | 4 | NO (heavy tail) |
| cf/qwen2.5-coder-32b | 1252 | 1690 | 2564 | 1317 | 2564 | 1 | YES |
| kgw/nemotron-3-super:free | 3113 | 6352 | 6956 | 3457 | 6956 | 35 | NO |
| kgw/nemotron-3-ultra:free | 7126 | 22271 | 49218 | 10180 | 49218 | 34 | NO |
| ollama/gpt-oss:120b | 2211 | 3006 | 3419 | 2296 | 3419 | 25 | NO |
| kgw/kilo-auto/free | 4974 | 9926 | 14017 | 5604 | 14017 | 36 | NO |
| cf/llama-3.2-1b | 648 | 868 | 1889 | 697 | 1889 | 0 | YES (but 72% invalid output) |
| cf/glm-4.7-flash | — | — | — | — | — | — | UNUSABLE |

Latency-viable (p95 < 2 s AND schema 1.0): **cf/llama-3.1-8b-fp8-fast** (best tail), groq/llama-3.3-70b-versatile, cf/qwen2.5-coder-32b. llama-3.2-1b is fast but fails quality. Tradeoff note: groq/llama-3.3-70b-versatile has the best p50 (556 ms) but a 10.9 s tail outlier → under a strict <2 s SLA it would fail-closed (NO-TRADE) on that call; cf/llama-3.1-8b's outlier is 2.7 s (milder).

## 11. Reliability Analysis

- Transport: 0 timeouts, 0 429-after-retry, 0 aborted; 5 transport errors total (all glm-4.7-flash). OBSERVED.
- HTTP errors: 31 HTTP400 (all glm-4.7-flash). OBSERVED.
- Parse reliability: llama-3.2-1b 26/36 `extraction_failed`; ollama 8/36 `extraction_failed`; kilo 7/36 `empty_content`; ultra 4/36 repaired (repair rate 0.1111) — all fail-closed to NO-TRADE with confidence 0.0 (OBSERVED).
- Consistency across repeats (direction agreement per scenario, majority heuristic): 1.0 for 7 models; 0.9722 ultra (unstable s03); 0.9444 kilo (s08, s09); 0.9167 llama-1b (s05, s06, s07); 0.8889 ollama (s03, s06, s07, s08). Confidence std mean 0.0 for cf/llama-3.1-8b, cf/llama-3.3-70b-fp8-fast, cf/qwen (maximally deterministic at temp 0.0).
- Every model: fail-safe scenarios (s10–12) → NO-TRADE in all 9/9 repeats (OBSERVED). Context citation heuristic: 0 for all models (reason strings never contained exact `%.2f` context figures — heuristic limitation, see §19).
- Highest combined reliability: cf/llama-3.1-8b-fp8-fast and groq/llama-3.3-70b-versatile (schema 1.0, err 0, repair 0, agr 1.0).

## 12. Cost Analysis

VERIFIED cost evidence only (inventory-report.md §5/§7, probe responses — no guessing per policy):

| Model | Verified tier | Evidence |
|---|---|---|
| kgw/kilo-auto/free | FREE | name + probe 200 OK |
| kgw/nemotron-3-super-120b-a12b:free | FREE_TIER | `:free` suffix + 200 |
| kgw/nemotron-3-ultra-550b-a55b:free | FREE_TIER | `:free` suffix + 200 |
| groq/*, cf/*, ollama/* (8 models) | COST_UNKNOWN | no route-level cost metadata in `/v1/models` (inventory §7) |

Free-tier note: FREE_TIER ≠ guaranteed unlimited quota; rate limits may apply (TFREE). Among verified-free candidates the best aggregate score is `kgw/nemotron-3-super-120b:free` (0.9586) but it does not meet the <2 s latency criterion (p50 3.1 s). No per-token price exists for any model; token efficiency used as proxy (see §9 scores) with ollama's missing-usage caveat.

## 13. Model Comparison

See §9 table for full numeric comparison. Notable failure modes (OBSERVED): glm-4.7-flash = route-level rejection (HTTP400 bodies + WinError 10060); llama-3.2-1b = emits non-JSON prose (26/36 extraction_failed) — too small for the contract prompt; ollama/gpt-oss:120b = inconsistent JSON + no usage reporting; kilo-auto/free = 7/36 empty content (stream-shape quirk, spec §2/§3) + 36/36 >2s; nemotron-ultra = slow + s03 direction flip. See §18.

## 14. Ranking

**Overall (aggregate score, PROVISIONAL):**
1. groq/llama-3.3-70b-versatile (0.9903)
2. cf/llama-3.1-8b-fp8-fast (0.9901)
3. cf/llama-3.3-70b-fp8-fast (0.9843)
4. groq/gpt-oss-120b (0.9830)
5. cf/qwen2.5-coder-32b (0.9820)
6. kgw/nemotron-3-super:free (0.9586)
7. kgw/nemotron-3-ultra:free (0.9030)
8. ollama/gpt-oss:120b (0.8946)
9. kgw/kilo-auto/free (0.8754)
10. cf/llama-3.2-1b (0.7924, HARD FAIL)
11. cf/glm-4.7-flash (0.5000, HARD FAIL)

**Fastest viable (p95 < 2 s + schema 1.0):** cf/llama-3.1-8b-fp8-fast (p50 606 / p95 777) → groq/llama-3.3-70b-versatile (556/1107) → cf/qwen2.5-coder-32b (1252/1690).

**Most reliable (schema 1.0, err 0.0, repair 0.0, agreement 1.0):** cf/llama-3.1-8b-fp8-fast (confidence std 0.0) → groq/llama-3.3-70b-versatile (0.0118) → cf/llama-3.3-70b-fp8-fast & cf/qwen (0.0).

**Best accuracy/quality (aggregate top with 1.0 schema):** groq/llama-3.3-70b-versatile (0.9903) vs cf/llama-3.1-8b (0.9901) — statistically indistinguishable at n=36; distinguished by tail latency.

**Best cost (verified free):** kgw/nemotron-3-super:free (0.9586) — only verified-free model with schema 1.0; latency tradeoff explicit (p50 3.1 s).

## 15. Benchmark Winner

**A. Benchmark Winner: `groq/llama-3.3-70b-versatile`** — aggregate score 0.9903 (highest). Perfect schema/consistency/fidelity/safety; p50 556 ms. Weakness: single 10.9 s tail outlier (p99 10919 ms). Margin over #2 is 0.0002 — not meaningful at n=36.

## 16. Operational Winner

**B. Operational Winner: `cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast`** — why it beats the benchmark winner for the actual ultra-fast scalping workload:
- Quality parity: schema 1.0, agreement 1.0, failsafe 1.0, safety 0 violations — same as groq.
- Better tail: p95 777 vs 1107 ms; max 2731 vs 10919 ms. Under fail-closed design, groq's 10.9 s outlier becomes a missed trade (NO-TRADE), and at <2 s target loop frequency that matters.
- Determinism: confidence std 0.0 (temp 0) vs 0.0118.
- Efficiency: 46470 vs 54590 tokens (~15% fewer); mean 664 vs 877 ms.
- Score difference 0.9903 vs 0.9901 is DERIVED noise-level — operational criteria break the tie.

## 17. Recommended Primary

**C. Recommended Primary: `cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast`** (operational winner). **Secondary: `groq/llama-3.3-70b-versatile`** (benchmark winner; use where p50/max-quality dominates and tail outliers are acceptable). **Fallback: `cf/@cf/qwen/qwen2.5-coder-32b-instruct`** (schema 1.0, p95 1690 ms — under 2 s; avoids single-vendor dependence since CF and Groq are different backends).

Recommendation matrix:

| Candidate | Quality | Latency | Reliability | Cost | Scalability evidence | Strength | Weakness | Recommendation | Status |
|---|---|---|---|---|---|---|---|---|---|
| cf/llama-3.1-8b-fp8-fast | 1.0 schema | p95 777 ms | agr 1.0, std 0.0 | COST_UNKNOWN | 36/36 OK continuous | deterministic, fast tail, efficient | one 2.7 s outlier; price unverified | PRIMARY | RECOMMENDED |
| groq/llama-3.3-70b-versatile | 1.0 schema | p50 556 ms | agr 1.0 | COST_UNKNOWN | 36/36 OK | best p50; large model quality | 10.9 s tail outlier; cost unknown | SECONDARY | RECOMMENDED |
| cf/qwen2.5-coder-32b | 1.0 schema | p95 1690 ms | agr 1.0, std 0.0 | COST_UNKNOWN | 36/36 OK | deterministic; fits <2 s | slower p50 than top-2 | FALLBACK | RECOMMENDED |
| cf/llama-3.3-70b-fp8-fast | 1.0 schema | p95 3297 ms | agr 1.0 | COST_UNKNOWN | 36/36 OK | quality parity | misses <2 s (p95) | SECONDARY-quality | NOT RECOMMENDED (latency) |
| groq/gpt-oss-120b | 1.0 schema | p95 11878 ms | agr 1.0 | COST_UNKNOWN | 36/36 OK | large model | heavy tail; most tokens | NOT RECOMMENDED (latency) |
| kgw/nemotron-3-super:free | 1.0 schema | p50 3113 ms | agr 1.0 | FREE_TIER verified | 36/36 OK | free + JSON-native + high score | 35/36 >2 s; quota unknown | FALLBACK (cost-driven) | NEEDS MORE EVIDENCE |
| kgw/nemotron-3-ultra:free | 1.0 schema | p95 22271 ms | agr 0.9722 | FREE_TIER verified | 36/36 OK | free, 550b | very slow; s03 unstable; p99 49 s | NOT RECOMMENDED |
| ollama/gpt-oss:120b | 0.7778 schema | p50 2211 ms | agr 0.8889 | COST_UNKNOWN | 36/36 OK | local option | 22% parse fail; unstable; no usage; local 120b unrealistic (i5-3470/16 GB) | NOT RECOMMENDED |
| kgw/kilo-auto/free | 0.8056 schema | p50 4974 ms | agr 0.9444 | FREE verified | 36/36 OK | free | 36/36 >2 s; 19% empty-content; mixed pool backend | NOT RECOMMENDED |
| cf/llama-3.2-1b | 0.2778 schema | p50 648 ms | agr 0.9167 | COST_UNKNOWN | 36/36 OK | fastest; cheapest class | HARD FAIL (schema<0.7); 72% prose | NOT RECOMMENDED |
| cf/glm-4.7-flash | 0.0 usable | — | — | COST_UNKNOWN | 0/36 usable | — | 31 HTTP400 + 5 transport; HARD FAIL | NOT RECOMMENDED |

## 18. Failure Analysis

| Model | Failure | Count | Mode | Fail-closed behavior |
|---|---|---|---|---|
| cf/glm-4.7-flash | HTTP400 | 31 | route rejects requests (repeated, deterministic) | 31 × NO-TRADE 0.0 |
| cf/glm-4.7-flash | TRANSPORT_ERROR (WinError 10060) | 5 | connect timeout to upstream | 5 × NO-TRADE 0.0 |
| cf/llama-3.2-1b | PARSE extraction_failed | 26 | prose output, no JSON object found | 26 × NO-TRADE 0.0 |
| ollama/gpt-oss:120b | PARSE extraction_failed | 8 | inconsistent JSON shape | 8 × NO-TRADE 0.0 |
| kgw/kilo-auto/free | PARSE empty_content | 7 | stream-shape quirk (no delta.content, spec §2) | 7 × NO-TRADE 0.0 |
| kgw/nemotron-3-ultra:free | repair (4/36) + s03 direction flip | 4+1 | repair = direction normalized to NO-TRADE; coherence issue on s03 | fail-closed + one unstable scenario |

All failures recorded verbatim in raw (status/error fields); none overwritten (OBSERVED). Consecutive transport abort rule never triggered (max 5 was for glm but its 31×HTTP400 + 5×transport came interleaved — HTTP400 resets the counter per runner.py:642–645; OBSERVED: model completed, not aborted. This is spec-compliant: only TIMEOUT/TRANSPORT_ERROR/HTTP429 count as transport).

## 19. Limitations

1. Sample size 36/model — score gaps < ~0.005 are noise (DERIVED note; not claimed as significant).
2. Scoring weights PROVISIONAL (spec §10) — re-ranking possible after human rebalance; report ranking depends on them.
3. Context citation heuristic = 0 for all models: reasons never contained exact `%.2f`-formatted figures; heuristic under-reports fidelity (NOT a claim of low fidelity; failsafe behavior was 100%).
4. `ollama/gpt-oss:120b` returned no `usage` → token component defaulted to 1.0, slightly inflating its score (runner.py:436).
5. COST_UNKNOWN for 8/11 models — no cost comparison possible beyond the 3 verified-free kgw routes; cost evidence NOT OBSERVED.
6. Single router session; router overhead (~400–500 ms) is included in all latencies; production latencies on another endpoint will differ.
7. No ground-truth labels — "quality" here = contract/schema/consistency/fidelity proxies, not directional accuracy.
8. Router alias quirk: `kgw/kilo-auto/free` backend is a mixed pool (`stepfun/step-3.7-flash`, inventory §8) — ID stability is router-managed, not provider-guaranteed.
9. Benchmark vs production: prompt-mode JSON, temp 0.0, max_tokens 512 — production prompt may differ; re-verify on any prompt change.
10. 5 transport errors (glm) occurred over ~35 min — no other model showed transport failures, so network path was stable during the window.

## 20. Final Model Selection Status

**D. Final Approved Model = PENDING USER/PROJECT APPROVAL.** This report recommends (not selects):
- Primary: `cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast`
- Secondary: `groq/llama-3.3-70b-versatile`
- Fallback: `cf/@cf/qwen/qwen2.5-coder-32b-instruct`

Exact IDs verified against `GET /v1/models` (2026-08-17, read-only, HTTP 200). Model selection status: READY FOR APPROVAL. Approval requirements before final: (1) cost verification for cf/groq routes, (2) confirmation of <2 s latency target, (3) scoring-weight sign-off (PROVISIONAL), (4) end-to-end re-verify with production prompt. Hard-fail candidates are excluded by spec §11.

## 21. Next Action

1. Human review of this report + approval of Recommended Primary (or requested re-run/reweight).
2. Verify pricing/availability for cf/groq routes (inventory §13 secondary probing).
3. On approval: implement AI Decision Engine (separate task) wired to the approved model; system-side risk/lot/SL authority remains per architecture.
4. Phase A data collection (pipeline) may proceed independently: `AGENTS.md` pending-work §7 item 1.