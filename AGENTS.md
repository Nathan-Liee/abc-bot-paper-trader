# ABC Bot — Agent Context & Live Project State

## 1. Project Identity

| Field | Value |
|---|---|
| Project name | ABC Bot (Paper Trader) |
| Repository | `abc-bot-paper-trader` (`https://github.com/Nathan-Liee/abc-bot-paper-trader`) |
| Repository purpose | Paper-trading validation infrastructure: telemetry → persistence → reconciliation → measurement. NOT the live trading engine. |
| Target broker | HFM |
| Target instrument | XAUUSDc |
| Target account | HFM Cent |
| Platform | MetaTrader 5 |

## 2. Mission

This repository exists to collect **empirical evidence** and validate infrastructure before any final decision on:

- AI model/provider
- risk %
- lot sizing
- adverse move basis
- spread filter
- slippage threshold
- latency budget
- position behavior
- execution/exit rules

Pipeline being proven:

```text
MT5 → MQL5 Read-Only Bridge → JSONL → Collector → Canonical Event → SQLite WAL → Reconciliation → Analytics
```

**This repository is NOT a live trading engine.** It must never acquire order-submission capability. Live trading lives in a future, separate repository (explicitly authorized by a later task only).

## 3. Current Project Phase

```
CURRENT PHASE:    AI MODEL BENCHMARK
CURRENT MILESTONE: AI Benchmark Execution
```

Benchmark status (evidence: `docs/validation/ai-benchmark/inventory-report.md`
verdict `INVENTORY COMPLETE`, `benchmark-spec.md` v1.0.0, `tests/benchmark/`
20 tests, CI green on `0a30071`):

- AI Model Discovery = COMPLETE (57 models via `GET /v1/models` 2026-08-14)
- AI Model Inventory = COMPLETE (11 benchmark candidates; free/paid verified, not guessed)
- Benchmark Specification = COMPLETE (`benchmark-spec.md` v1.0.0)
- Benchmark Runner = COMPLETE (runner + fail-closed tests 20, committed `aab70e5`)
- CI Baseline = GREEN (GitHub Actions all steps success, run on `0a30071`)
- AI Benchmark Execution = IN PROGRESS (not yet run; no model selected)

Phase A Data-Only Validation completed with verdict **PASS WITH WARNINGS** (`docs/validation/phase-a-validation-report.md`). Environment verification for HFM Cent `XAUUSDc` is BLOCKED by ISP (Telkomsel MITM) — see §8. Current milestone: reproducible benchmark of 11 shortlist models on the custom endpoint `http://10.139.136.202:20128/v1`. No final model selection in this milestone.

## 4. Live Implementation Status

Evidence = commit / passing test / compiled artifact / runtime validation / generated data / verified integration / explicit report. Never mark COMPLETE on source-file presence alone.

| Phase / Milestone | Status | Evidence | Last Commit |
|---|---|---|---|
| Repository Bootstrap | ✅ COMPLETE | repo structure, README, AGENTS.md, CI config | `172f6d2` |
| Canonical Event Contract | ✅ COMPLETE | `docs/contracts/canonical-event-contract.md` + validation report | `172f6d2` |
| Event Model + JSON Schema | ✅ COMPLETE | `collector/event_model/` + `shared/schemas/canonical-event.schema.json`; schema-validated by test suite | `c47d2d5` |
| SQLite WAL Persistence | ✅ COMPLETE | `collector/persistence/` (migrations 1–3, WAL, integrity, append-only triggers); E2E checks | `36228cb` |
| MQL5 Read-Only Bridge | ✅ COMPLETE | `mql5-bridge/src/`; static safety test blocks execution tokens; compile 0 errors | `0a4fad4` |
| MQL5 Compile | ✅ COMPLETE | `mql5-bridge/compile.log`: `Result: 0 errors, 0 warnings, 2975 ms, X64 Regular` | `0a4fad4` |
| MQL5 Runtime Validation | ✅ COMPLETE (harness) | documented run on HFM Demo Premium `XAUUSD` (TECHNICAL_HARNESS_ONLY; artifacts not committed; re-observation pending) | `0a4fad4` |
| JSONL Export | ✅ COMPLETE | `JsonExporter.mqh` (append-only, rename-on-corruption) + exporter directory tests | `dba744c` |
| JSONL Ingestion Adapter | ✅ COMPLETE | `collector/adapters/` (reader/normalize/pipeline/replay); tests + E2E replay 31/31 | `c47d2d5` |
| Reconciliation | ✅ COMPLETE | `collector/reconciliation/`; 4 triggers, idempotent, non-executive (runtime-verified) | `36228cb` |
| Phase A Data-Only Validation | ✅ COMPLETE | `docs/validation/phase-a-validation-report.md`; verdict PASS WITH WARNINGS; 339 tests | `44d090f` |
| Phase A Data Collection | ⏳ PENDING | next actionable; needs live bridge attach + collector tailer on HFM Cent `XAUUSDc` | — |
| AI Model Benchmark | 🔄 IN PROGRESS | 11 candidates (inventory-report.md §11: 8 prior + 3 kgw free); spec v1.0.0 + dataset 12 scenarios + runner + 20 fail-closed tests; execution not yet run | `aab70e5` |
| AI Selection | ⏳ PENDING | — | — |
| Market Context Engine | ⏳ PENDING | — | — |
| Trigger Engine | ⏳ PENDING | — | — |
| AI Decision Engine | ⏳ PENDING | — | — |
| Risk Engine | ⏳ PENDING | — | — |
| Lot Sizing | ⏳ PENDING | — | — |
| Exposure Engine | ⏳ PENDING | — | — |
| Execution Engine | ⏳ PENDING | — | — |
| Exit Engine | ⏳ PENDING | — | — |
| Paper Trading | ⏳ PENDING | — | — |
| ≥200 Strategy Trades | ⏳ PENDING | — | — |
| Empirical Analysis | ⏳ PENDING | — | — |
| Risk/Lot Finalization | ⏳ PENDING | — | — |
| AI Integration | ⏳ PENDING | — | — |
| Live Trading | ❌ FORBIDDEN | never in this repository | — |

## 5. Current Work

```
CURRENT TASK:   AI Benchmark Execution — live run (not yet executed)
OBJECTIVE:      Reproducible benchmark of 11 shortlist models on custom
                endpoint http://10.139.136.202:20128/v1 — identical dataset +
                prompt per model; measure latency (P50/P95/P99),
                structured-output reliability, consistency, context fidelity,
                failure safety.
SHORTLIST (11, per inventory-report.md §11 + benchmark-spec.md §3):
                groq/llama-3.3-70b-versatile
                cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast
                groq/openai/gpt-oss-120b
                cf/@cf/meta/llama-3.3-70b-instruct-fp8-fast
                cf/@cf/zai-org/glm-4.7-flash
                cf/@cf/qwen/qwen2.5-coder-32b-instruct
                ollama/gpt-oss:120b
                cf/@cf/meta/llama-3.2-1b-instruct (fallback/ultra-fast)
                kgw/nvidia/nemotron-3-super-120b-a12b:free
                kgw/nvidia/nemotron-3-ultra-550b-a55b:free
                kgw/kilo-auto/free (prompt-mode JSON; non-stream)
DO NOT:         select final model; touch contract/schema/risk/execution/exit
                authority; use cx/* as primary (quota-unstable); modify locked
                architecture; touch HFM Cent/XAUUSDc target.
```

## 6. Completed Work

1. **Repository Bootstrap** — structure, README, governance. Commit `b428f33`/`172f6d2`. Validated: repo builds, tests run.
2. **Canonical Event Contract v1.0.0** — 17 locked event types, envelope, lifecycle, checksum rule (`sha256:` of canonical serialization). Commit `172f6d2`. Validated: contract + validation report reviewed; schema tests pass.
3. **Event Model + JSON Schema** — typed envelopes, ids, timestamps (no fabricated precision), lifecycle FSM. Commit `d3a1f30`/`c47d2d5`. Validated: schema validation + roundtrip tests.
4. **SQLite WAL Persistence** — migrations 1–3, WAL, FK, append-only triggers, integrity suite, duplicate/checksum-conflict guards. Commit `c47d2d5`/`36228cb`. Validated: E2E integrity aggregate PASS.
5. **MQL5 Read-Only Bridge** — telemetry-only EA; no order API; heartbeat/snapshot/transaction telemetry. Commit `0a4fad4`(+fixes `6dbf5ce`, `dba744c`). Validated: compile log 0 errors; `tests/mql5/test_bridge_safety.py` blocks execution tokens.
6. **MQL5 Runtime Validation (harness)** — run on HFM Demo Premium `XAUUSD`. Validated: documented in AGENTS.md history; TECHNICAL_HARNESS_ONLY; artifacts not committed.
7. **JSONL Ingestion Adapter** — tail-reader (cursor, partial-line hold, rotation), normalize, canonicalize, schema-validate, checksum, atomic persist. Commit `d3a1f30`/`c47d2d5`. Validated: unit + replay tests; E2E replay of committed fixtures 31/31 checks PASS.
8. **Reconciliation Service** — OBSERVE→COMPARE→CLASSIFY→RECORD→ESCALATE/ADOPT only; STARTUP/HEARTBEAT/POST_EXECUTION/MISMATCH; deterministic uuid5 ids; no execution. Commit `36228cb`. Validated: E2E (SYNCED / ADOPTED_BROKER / ESCALATED, idempotent skip, orders/positions untouched).
9. **Phase A Data-Only Validation** — full pipeline audit + fixes (malformed-line metric). Commits `856c527`, `44d090f`. Validated: 339 tests passed, ruff/mypy clean, verdict **PASS WITH WARNINGS**.
10. **CI Regression Cleanup** — reader rotation bug (inode reuse after unlink→recreate; reproduced on Linux/WSL) fixed with disappearance-gap detection. Commit `1ba7fff`. Validated: CI BASELINE GREEN — run 31820083519 on `aab70e5` all steps success; 359 tests; report `docs/validation/ci-regression-cleanup-report.md`.
11. **AI Model Discovery + Inventory + Benchmark Spec + Runner** — 57 models via `GET /v1/models`; inventory report verdict `INVENTORY COMPLETE`, 11 benchmark candidates (free/paid verified by probe); spec v1.0.0; runner + 20 fail-closed tests. Commit `aab70e5`. Validated: `docs/validation/ai-benchmark/inventory-report.md`, `benchmark-spec.md`, `tests/benchmark/`.

## 7. Pending Work (dependency order)

1. **Phase A Data Collection** ← NEXT ACTIONABLE (requires: live HFM Cent `XAUUSDc` terminal; bridge attach; collector tailer; reconciliation heartbeat)
2. Paper Trading ≥200 trades (needs collection running)
3. Empirical Analysis (needs ≥200 trades)
4. AI Model Benchmark (preliminary requirements exist; final needs analysis)
5. AI Selection
6. Risk/Lot Finalization (needs analysis)
7. AI Integration → Market Context → Trigger → AI Decision → Risk → Lot/Exposure → Execution → Exit (needs AI selection + finalized risk/lot)
8. Live Trading — FORBIDDEN in this repository

## 8. Blockers & Warnings

Blockers: `None`

| Item | Status | Impact | Resolution |
|---|---|---|---|
| Live MT5 attach not re-observed by validation audit | WARNING | bridge live-runtime evidence is documented harness + static tests only | re-verify during Phase A Data Collection |
| No HFM Cent `XAUUSDc` runtime data yet | WARNING | all spread/slippage/lot/margin economics unmeasured | collect during Phase A |
| Harness (`XAUUSD` Premium) data ≠ Cent economics | WARNING | must never drive Cent decisions | keep TECHNICAL_HARNESS_ONLY tagging |
| `mfe_usd`/`mae_usd` raw 0.0 from bridge | WARNING | trade-level extremum must come from collector | collector owns trade state (by design) |
| `events_invalid` includes identity-pending trade lines | WARNING | metric readers may misread | read `events_identity_pending` |
| `POSITION_COMMISSION` deprecated → floating commission excluded | WARNING | `running_net_pnl_usd` approximation | collector normalization authority (by design) |
| `export_events_jsonl` loads all events in memory | WARNING | large DB risk at analytics phase | revisit before analytics |
| MCP servers (Thinking/Context7/Affine) not configured on dev profile | WARNING | agent tooling gap, not repo defect | configure if needed |

## 9. Environment Status

| Environment | Broker | Account | Symbol | Status | Use |
|---|---|---|---|---|---|
| Target | HFM | Cent | XAUUSDc | NOT YET COLLECTED | all final decisions (risk, lot, spread, feasibility) |
| Technical harness | HFM | Demo Premium | XAUUSD | validated (runtime documented) | pipeline correctness ONLY |

**Rule:** Premium/XAUUSD evidence is `TECHNICAL_HARNESS_ONLY`. It may never be used for risk calibration, lot sizing, margin model, spread economics final, strategy feasibility, profitability, or any Cent-account decision. Do not change the `XAUUSDc` target because the harness uses `XAUUSD`.

## 10. Architecture

Implemented (actual):

```text
MT5
   ↓
MQL5 Read-Only Bridge
   ↓
JSONL
   ↓
Collector Ingestion
   ↓
Canonical Event Model
   ↓
SQLite WAL
   ↓
Reconciliation
   ↓
Analytics
```

Future (NOT implemented — do not build before its milestone):

```text
Market Context
   ↓
Trigger
   ↓
AI Decision
   ↓
Risk
   ↓
Lot / Exposure
   ↓
Execution
   ↓
NET_PROFIT Exit
```

## 11. Authority Boundaries

AI may only produce:

```text
BUY | SELL | NO-TRADE
confidence
reason
```

AI must never control: risk, lot, exposure, margin, execution, exit, compounding.

System owns: Risk, Lot, Exposure, Margin, Execution, Exit, Compounding. `NET_PROFIT > 0` is a deterministic system rule and never waits for AI.

Boundary is locked. No agent may change it.

## 12. Safety Rules (HARD)

- Live trading forbidden — this repository must never acquire order capability.
- Read-only default: `live_trading_enabled=false`, `read_only_mode=true`.
- Demo execution disabled unless explicitly authorized by a later separate task.
- No credentials in repository (`.env` never committed; `.gitignore` enforced).
- No automatic order execution of any kind.
- No live-account testing on the Cent target without an explicit task.
- Do not change safety defaults to make development easier.

## 13. Coding Agent Rules

1. Read this `AGENTS.md` first.
2. Read `docs/contracts/canonical-event-contract.md` before changing event-related code.
3. Respect the current milestone; do not jump ahead (workflow order in §7).
4. Do not skip dependencies.
5. Maintain backward compatibility with the locked contract and schema.
6. Run full validation after every change: `pytest`, `ruff check .`, `ruff format --check .`, `mypy collector shared`.
7. Make focused commits (conventional style).
8. Never force push.
9. Report blockers instead of inventing workarounds.
10. Source of truth priority: contract docs > `docs/architecture.md` > README > source > tests.

## 14. Milestone Handover Protocol

Every time a task completes, the agent MUST update this document:

1. Update `AGENTS.md`.
2. Update `CURRENT PHASE` (§3).
3. Update `CURRENT MILESTONE` (§3).
4. Update milestone status table (§4) with evidence.
5. Update Completed Work (§6) — result + commit + validation status.
6. Update Pending Work (§7) — next actionable milestone.
7. Update Blockers & Warnings (§8).
8. Record validation result.
9. Record commit hash.
10. Record next step.
11. Commit source changes + `AGENTS.md` consistently (same commit or immediately following).
12. Update the Handoff Snapshot (§15).

**`AGENTS.md` is a living document.**

- Status must never be stale — it must reflect repository HEAD.
- Never write "complete" without evidence.
- Never write "current" without validation.
- Every milestone completion must update this document.

## 15. Handoff Snapshot

```
LAST VERIFIED:          2026-08-15 +07:00
CURRENT PHASE:          AI MODEL BENCHMARK
CURRENT MILESTONE:      AI Benchmark Execution
LAST COMPLETED MILESTONE: CI Regression Cleanup (CI BASELINE GREEN)
LATEST COMMIT:          0a30071 (CI green, all steps success)
TEST STATUS:            359 passed; ruff check/format clean; mypy clean (48 files)
BLOCKER:                None (Cent env verification ISP-blocked — §8)
NEXT ACTION:            Run AI benchmark execution (11 models, spec v1.0.0);
                        no AI final selection on this milestone.
```

Read this block first. Then §3–§8. Then the repo.

## 16. CURRENT WORK LOG

Append-only log of important benchmark milestones. Old entries are never rewritten.

| Time | Milestone | Status | Evidence | Notes |
| ---- | --------- | ------ | -------- | ----- |
| 2026-08-14 21:08 +07 | Benchmark kickoff | DONE | this entry | shortlist 8 models fixed; live tracking established; no model final yet |
| 2026-08-14 21:08 +07 | Benchmark design | IN PROGRESS | — | spec/dataset/runner pending in `docs/validation/ai-benchmark/` |
| 2026-08-15 +07 | CI regression cleanup | IN PROGRESS | failure inventory + root cause found | GitHub Actions Test step red on last 5 main runs; local Windows suite green. Root cause: reader rotation relied on inode identity; Linux reuses inode after unlink → recreate same-size stream misdetected as tail. Fix: disappearance-gap rotation. Local validation PASS (pytest exit 0, ruff/format/mypy clean). |
| 2026-08-15 +07 | CI regression cleanup | DONE | CI BASELINE GREEN — run 31820083519 on `aab70e5` all steps success | Fix pushed (`1ba7fff`, `99b9653`, `aab70e5`); GitHub Actions test/lint/format/type-check all PASS; working tree clean; 359 tests. Handoff: RESUME AI MODEL BENCHMARK IMPLEMENTATION. |
| 2026-08-15 +07 | AI Model Discovery | COMPLETE | `GET /v1/models` 200 OK, 57 model IDs; `inventory-report.md` verdict `INVENTORY COMPLETE` | All 14 screenshot IDs resolved; `oc/*` 8 classified UNAVAILABLE; `kew/kgv` → `kgw/` prefix correction. |
| 2026-08-15 +07 | AI Model Inventory | COMPLETE | `inventory-report.md` §11 — 11 benchmark candidates | 8 prior shortlist + 3 kgw free (nemotron super/ultra :free, kilo-auto/free). Free/paid verified by probe (200/402), not guessed. |
| 2026-08-15 +07 | Benchmark Specification | COMPLETE | `benchmark-spec.md` v1.0.0 (12 scenarios, 3 repeats, fail-closed rules, scoring weights provisional) | 11 models × 36 req = 396 requests budget; runner does NOT send `response_format` (prompt-mode JSON). |
| 2026-08-15 +07 | Benchmark Runner | COMPLETE | `tests/benchmark/test_benchmark_runner.py` 20 fail-closed tests; runner.py committed `aab70e5` | Timeout/429/transport/parse/unexpected-tool-call → NO-TRADE, confidence 0.0. |
| 2026-08-15 +07 | AI Benchmark Execution | IN PROGRESS | not yet run — next actionable | AGENTS.md synced to 11 candidates; CI green (`0a30071`); no model selected. |
