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
CURRENT PHASE:    AI BENCHMARK — Model Benchmark (IN PROGRESS)
CURRENT MILESTONE: CI REGRESSION CLEANUP
```

CI regression cleanup is in progress (failure inventory + recovery) before
the benchmark resumes. Root cause found: `JsonlFileReader` rotation detection
relied on `(st_dev, st_ino)` identity, which is unreliable after
unlink→recreate because filesystems (ext4; observed via WSL Linux) may reuse
the inode number immediately — the pipeline then tailed a NEW stream as if it
were the old one (silent data misalignment). Fixed with disappearance-gap
detection.

Phase A Data-Only Validation completed with verdict **PASS WITH WARNINGS** (`docs/validation/phase-a-validation-report.md`). Environment verification for HFM Cent `XAUUSDc` is BLOCKED by ISP (Telkomsel MITM) — see §8. Current milestone: reproducible benchmark of 8 shortlist models on the custom endpoint `http://10.139.136.202:20128/v1`. No final model selection in this milestone.

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
| AI Model Benchmark | 🔄 IN PROGRESS | shortlist 8 models fixed (endpoint discovery 2026-08-14); runner/dataset/results in `docs/validation/ai-benchmark/` | — |
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
CURRENT TASK:   AI Model Benchmark — implementation + live run
OBJECTIVE:      Reproducible benchmark of shortlist models on custom endpoint
                http://10.139.136.202:20128/v1 — identical dataset + prompt per
                model; measure latency (P50/P95/P99), structured-output
                reliability, consistency, context fidelity, failure safety.
SHORTLIST:      groq/llama-3.3-70b-versatile
                cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast
                groq/openai/gpt-oss-120b
                cf/@cf/meta/llama-3.3-70b-instruct-fp8-fast
                cf/@cf/zai-org/glm-4.7-flash
                cf/@cf/qwen/qwen2.5-coder-32b-instruct
                ollama/gpt-oss:120b
FALLBACK:       cf/@cf/meta/llama-3.2-1b-instruct
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
LAST VERIFIED:          2026-08-14 21:08 +07:00
CURRENT PHASE:          AI BENCHMARK — Model Benchmark
CURRENT MILESTONE:      AI Model Benchmark
LAST COMPLETED MILESTONE: Phase A Data-Only Validation (PASS WITH WARNINGS)
LATEST COMMIT:          44d090f
TEST STATUS:            339 passed; ruff check/format clean; mypy clean (48 files)
BLOCKER:                None (Cent env verification ISP-blocked — §8)
NEXT ACTION:            Build benchmark dataset + runner; live benchmark run;
                        comparison + recommendation; final report.
```

Read this block first. Then §3–§8. Then the repo.

## 16. CURRENT WORK LOG

Append-only log of important benchmark milestones. Old entries are never rewritten.

| Time | Milestone | Status | Evidence | Notes |
| ---- | --------- | ------ | -------- | ----- |
| 2026-08-14 21:08 +07 | Benchmark kickoff | DONE | this entry | shortlist 8 models fixed; live tracking established; no model final yet |
| 2026-08-14 21:08 +07 | Benchmark design | IN PROGRESS | — | spec/dataset/runner pending in `docs/validation/ai-benchmark/` |
| 2026-08-15 +07 | CI regression cleanup | IN PROGRESS | failure inventory + root cause found | GitHub Actions Test step red on last 5 main runs; local Windows suite green. Root cause: reader rotation relied on inode identity; Linux reuses inode after unlink → recreate same-size stream misdetected as tail. Fix: disappearance-gap rotation. Local validation PASS (pytest exit 0, ruff/format/mypy clean). |
