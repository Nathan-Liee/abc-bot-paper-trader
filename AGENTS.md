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
CURRENT PHASE:    PAPER VALIDATION EVIDENCE + EXECUTION IMPLEMENTATION
CURRENT MILESTONE: Execution Engine Final Review — implementation COMPLETE;
                        contracts + state machine + journal + retry +
                        simulated executor + reconciliation implemented;
                        625 tests PASS; ruff/mypy clean (85 files);
                        EA NOT implemented; production LOCKED
```

Benchmark status (evidence: `docs/validation/ai-benchmark/inventory-report.md`
verdict `INVENTORY COMPLETE`, `benchmark-spec.md` v1.0.0, `tests/benchmark/`
20 tests, CI green on `0a30071`):

- AI Model Discovery = COMPLETE (57 models via `GET /v1/models` 2026-08-14)
- AI Model Inventory = COMPLETE (11 benchmark candidates; free/paid verified, not guessed)
- Benchmark Specification = COMPLETE (`benchmark-spec.md` v1.0.0)
- Benchmark Runner = COMPLETE (runner + fail-closed tests 20, committed `aab70e5`)
- CI Baseline = GREEN (GitHub Actions all steps success, run on `0a30071`)
- AI Benchmark Execution = COMPLETE (396/396 requests; raw `results/raw/*.jsonl` + normalized/scored `results/normalized/`; run window 2026-08-15 00:40–01:14 +07)
- AI Benchmark Evaluation = COMPLETE (`benchmark-report.md`; results re-verified, ranking + recommendation produced)
- AI Model Selection = APPROVED (user approved config in AI Decision Engine task 2026-08-17; locked: primary `cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast`, secondary `groq/llama-3.3-70b-versatile`, fallback `cf/@cf/qwen/qwen2.5-coder-32b-instruct`; exact IDs verified vs endpoint)
- AI Decision Engine = COMPLETE (implemented `ai_decision/`; 71 new tests; validation report `docs/validation/ai-decision-engine/ai-decision-engine-validation.md`; live smoke PASS 2026-08-17 — BUY 0.8 @ 1032 ms)

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
| AI Model Benchmark | ✅ COMPLETE | 11 candidates (inventory-report.md §11); spec v1.0.0 + dataset 12 scenarios + runner + 22 fail-closed tests; execution 396/396 (2026-08-15 00:40–01:14 +07); normalization + evaluation done; report `docs/validation/ai-benchmark/benchmark-report.md` | `aab70e5` + worktree |
| AI Selection | ✅ APPROVED | user-approved config (engine task 2026-08-17): primary `cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast`, secondary `groq/llama-3.3-70b-versatile`, fallback `cf/@cf/qwen/qwen2.5-coder-32b-instruct`; exact IDs verified via `GET /v1/models` (HTTP 200) | `benchmark-report.md` |
| Market Context Engine | ⏳ PENDING | — | — |
| Trigger Engine | ⏳ PENDING | — | — |
| AI Decision Engine | ✅ COMPLETE | `ai_decision/` (config/prompt/client/parsing/validation/record/engine/gate); tests 71 (unit+integration, mocked provider); validation report `docs/validation/ai-decision-engine/ai-decision-engine-validation.md`; live smoke PASS (BUY 0.8, 1032 ms, 2026-08-17); no MT5/order capability, proposal-only | worktree → commit |
| Risk Engine | ✅ COMPLETE | `risk_engine/` (models/config/calculators/validators/engine/gate/reason_codes); tests 20 (unit+integration); validation report `docs/validation/risk-engine/risk-engine-validation.md`; verdict PASS WITH PENDING CONFIGURATION; no broker execution | `048bfcb` |
| Risk Configuration Finalization | ⏳ BLOCKED (evaluation complete) | audit + decision matrix + report `docs/validation/risk-engine/risk-config-finalization.md`; verdict PASS WITH HUMAN APPROVAL REQUIRED; 8 owner decisions pending; no numeric config locked | docs-only |
| HFM Cent XAUUSDc Runtime Evidence | ✅ COMPLETE | read-only IPC (`MetaTrader5` python) on account 229105805 / HFMarketsGlobal-Live19, symbol XAUUSDc; 61 spread samples (median 36pts), exact symbol spec/account/margin/leverage; report `docs/validation/runtime/xauusdc-cent-readonly-observation.md`; zero execution | docs-only |
| Risk Parameter Evaluation | ✅ COMPLETE (approval pending) | decision matrix + SL/spread/exposure/margin sensitivity + 3 profiles in `docs/validation/risk-engine/risk-parameter-evaluation.md`; no config locked | docs-only |
| Risk Configuration v0.1 (PAPER VALIDATION) | ✅ APPLIED FOR PAPER VALIDATION | `RiskConfig` (profile_name=PAPER_VALIDATION_V0.1, is_production=false, requires_paper_validation=true; risk 0.5% eq, pos 1, DD 5%, SL 50pts, spread 45pts, exposure 100% eq, margin 10% eq+1x budget, leverage 2000, compounding 0%); 23 risk tests; 455 suite PASS; reports `paper-validation-risk-config-v0.1.md` + `risk-config-finalization.md` §PAPER_VALIDATION_V0.1; production config UNLOCKED | `3b096c7` |
| Paper Validation Harness | ✅ COMPLETE | `paper_validation/` package (8 modules: models, cost_model, market_replay, execution_simulator, position_simulator, evidence, metrics, scenario_runner); 21 new tests (unit + integration); full suite 476 PASS; ruff/mypy clean (74 files); report `docs/validation/paper-trading/paper-validation-report.md`; all evidence SIMULATED; production RiskConfig UNLOCKED | `fc9d077` |
| Multi-Session XAUUSDc Telemetry | ⏳ PARTIAL (ASIAN + LONDON + OVERLAP collected) | 7800 read-only samples — ASIAN 2240 (median 36, max 36) + LONDON 3594 (median 34, max 36) + LONDON_NY_OVERLAP 1966 (median 36, max 50); spread 34–50 pts; OVERLAP 19% > 45 pts, max 50 = SL distance; raw `docs/validation/runtime/multi-session/xauusdc-spread-timeseries.jsonl` + report `xauusdc-multi-session-report.md`; NY/off-hours pending; production UNLOCKED | docs-only |
| Execution Architecture Design | ✅ READY (OPEN DECISIONS) | design-only report `docs/validation/execution/execution-architecture-readiness.md`: TradePlan/ExecutionCommand/ExecutionResult contracts, state machine (CREATED→CLOSED + 4 failure states), idempotency (command_id journal, trade_id uniqueness, reconcile-first), broker source of truth, partial-fill/SL-attachment/ABC-exit boundaries, error matrix + retry policy, EA boundary + security gate, paper/demo/real executor abstraction, 12 open decisions (OD-1..OD-12); NO code, NO RiskConfig change, NO Obsidian edit; 476 tests PASS, ruff/mypy clean; contracts consistent with locked canonical event model (no schema change) | docs-only |
| Lot Sizing | ⏳ PENDING | — | — |
| Exposure Engine | ⏳ PENDING | — | — |
| Execution Engine | ✅ COMPLETE (paper/simulation) | `execution/` package (10 modules); TradePlan/ExecutionCommand/ExecutionResult contracts; deterministic state machine; SQLite WAL journal (append-only + keyed projection); 18-code error matrix + 6-class retry policy; 13-scenario SimulatedExecutor; ReconciliationBoundary; OD-1..OD-10 implemented; 625 tests PASS; ruff/mypy clean (85 files); report `docs/validation/execution/execution-final-readiness.md`; verdict PASS WITH FINDINGS; NO MT5/EA/live broker; production LOCKED | this commit |
| Exit Engine | ⏳ PENDING | — | — |
| Paper Trading | ✅ HARNESS COMPLETE | `paper_validation/` (deterministic simulation, 15 scenario groups, cost model, trade evidence); 476 tests PASS; report `docs/validation/paper-trading/paper-validation-report.md`; verdict PASS WITH FINDINGS; production config UNLOCKED; cost treatment is critical pending | commit |
| ≥200 Strategy Trades | ⏳ PENDING | — | — |
| Empirical Analysis | ⏳ PENDING | — | — |
| Risk/Lot Finalization | ⏳ PENDING | — | — |
| AI Integration | ⏳ PENDING | — | — |
| Live Trading | ❌ FORBIDDEN | never in this repository | — |

## 5. Current Work

```
CURRENT TASK:   Execution Engine Final Review & EA Integration Readiness
OBJECTIVE:      Final technical review of `execution/` implementation:
                authority boundaries, contracts, state machine,
                idempotency, retry, partial fill, simulator,
                reconciliation, safety, EA interface specification.
                NO EA/MT5/live implementation.
DO NOT:         MT5 execution / MQL5 EA / broker API / live order /
                position modification / production RiskConfig change /
                automatic production unlock.
STATUS:         COMPLETE — `execution/` implemented + reviewed;
                625 tests PASS; ruff check/format clean; mypy clean
                (85 files); safety scan PASS (no MT5/network/secrets);
                EA interface spec documented; readiness report
                `docs/validation/execution/execution-final-readiness.md`;
                verdict PASS WITH FINDINGS; production LOCKED.
NEXT:           Implement the EA (MQL5 Expert Advisor) on the
                Executor Protocol — demo first (HFM Demo), then
                production (HFM Cent XAUUSDc) only after production
                RiskConfig locked + owner authorization. No contract
                changes required — Executor Protocol +
                ExecutionCommand + ExecutionResult = full interface.
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
12. **AI Benchmark Execution + Normalization** — 11 models × 12 scenarios × 3 repeats = 396 requests against `http://10.139.136.202:20128/v1` (run window 2026-08-15 00:40–01:14 +07; results uncommitted). Validated: raw 396/396 lines with real endpoint payloads, unique (model,scenario,repeat) 396/396, per-model coverage 36/36; normalized `results/normalized/metrics.json` + `results.json` (396 entries); hard-fail: `cf/@cf/zai-org/glm-4.7-flash` (0/36 OK — 31 HTTP400 + 5 TRANSPORT_ERROR) and `cf/@cf/meta/llama-3.2-1b-instruct` (schema_valid_rate 0.2778). No final model selected.
13. **AI Benchmark Evaluation + Final Report** — independent recomputation of all metrics and scores matches stored normalized results (0 diffs across 11 models); `benchmark-report.md` written (21 sections). Benchmark winner `groq/llama-3.3-70b-versatile` (0.9903); operational winner / recommended primary `cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast` (0.9901, p95 777 ms, confidence std 0.0); secondary `groq/llama-3.3-70b-versatile`; fallback `cf/@cf/qwen/qwen2.5-coder-32b-instruct`. Validation GREEN: 360 tests pass, ruff check/format clean, mypy clean (48 files). Final model selection STILL PENDING APPROVAL — nothing implemented.
14. **AI Decision Engine Implementation** — `ai_decision/` package (config/prompt/client/parsing/validation/record/engine/gate) with exact approved model IDs, deterministic fallback PRIMARY→SECONDARY→FALLBACK→NO-TRADE (bounded retry), strict schema/authority validation, fail-closed on all failure classes, observability (inference_id/model/latency/fallback/errors), SystemGate boundary interface only. Found + handled live router quirk: body + trailing `data: [DONE]`. 71 new tests (parsing/validation/engine/integration, mocked provider); full suite 431 PASS; ruff/format clean; mypy clean (57 files); live smoke PASS `BUY 0.8 @ 1032 ms` (2026-08-17). Report `docs/validation/ai-decision-engine/ai-decision-engine-validation.md`. Risk Engine / Execution / EA NOT implemented.
15. **Execution Architecture Readiness (design-only)** — `docs/validation/execution/execution-architecture-readiness.md` (23 sections): TradePlan / ExecutionCommand / ExecutionResult contracts; deterministic state machine CREATED→VALIDATED→SUBMITTED→PARTIALLY_FILLED→FILLED→MODIFYING→CLOSED + REJECTED/FAILED/EXPIRED/UNKNOWN; idempotency (command_id journal, trade_id uniqueness, reconcile-first, restart replay); broker source of truth choreography; partial fill / SL attachment (verbatim + emergency) / ABC exit / position management boundaries; freshness+expiry gates; 13-row error matrix + 4-class retry policy; EA boundary (responsibilities/forbidden) + security gate; 7-ID observability lineage mapped 1:1 to locked canonical events (no schema change); paper/demo/real executor abstraction; 12 open decisions OD-1..OD-12. No code written; RiskConfig unchanged; Obsidian not edited (partial-fill conflict documented). 476 tests PASS; ruff check/format clean; mypy clean (74 files).
16. **Execution Engine Implementation + Final Review** — `execution/` package (10 modules: models, validation, state_machine, retry, journal, engine, executor, simulated, reconciliation, errors); TradePlan/ExecutionCommand/ExecutionResult frozen dataclasses; deterministic state machine CREATE→VALIDATED→SUBMITTED→PARTIALLY_FILLED→FILLED→MODIFYING→CLOSED + REJECTED/FAILED/EXPIRED/UNKNOWN; SQLite WAL journal (append-only triggers + keyed projection + active-trade uniqueness + restart recovery); 18-code error matrix → 6-class retry policy (SAFE/UNSAFE/RECONCILE/PERMANENT/EMERGENCY/IDEMPOTENT); RetryPolicy (submit/close/sl_attach retries=2); 13-scenario SimulatedExecutor (full/partial/reject/timeout/ambiguous/requote/stale/position/SL fail/close fail/expired/duplicate); ReconciliationBoundary (UNKNOWN→broker-truth adoption); OD-1 (CANCEL_REMAINING) through OD-10 (retry budget) implemented; authority boundary clean (execution imports stdlib + own modules only — zero risk_engine/ai_decision/broker); safety scan PASS (no MT5/network/secrets); full suite 625 PASS; ruff check/format clean; mypy clean (85 files); readiness report `docs/validation/execution/execution-final-readiness.md` (17 sections + EA interface spec); verdict PASS WITH FINDINGS; EA NOT implemented; production RiskConfig not locked; production LOCKED.

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
| No HFM Cent `XAUUSDc` runtime data yet | RESOLVED | read-only evidence collected 2026-08-17 (spread median 36 pts, spec/account/margin) | runtime report `docs/validation/runtime/xauusdc-cent-readonly-observation.md`; slippage/commission/other sessions still unobserved |
| Harness (`XAUUSD` Premium) data ≠ Cent economics | WARNING | must never drive Cent decisions | keep TECHNICAL_HARNESS_ONLY tagging |
| `mfe_usd`/`mae_usd` raw 0.0 from bridge | WARNING | trade-level extremum must come from collector | collector owns trade state (by design) |
| `events_invalid` includes identity-pending trade lines | WARNING | metric readers may misread | read `events_identity_pending` |
| `POSITION_COMMISSION` deprecated → floating commission excluded | WARNING | `running_net_pnl_usd` approximation | collector normalization authority (by design) |
| `export_events_jsonl` loads all events in memory | WARNING | large DB risk at analytics phase | revisit before analytics |
| MCP servers (Thinking/Context7/Affine) not configured on dev profile | WARNING | agent tooling gap, not repo defect | configure if needed |

## 9. Environment Status

| Environment | Broker | Account | Symbol | Status | Use |
|---|---|---|---|---|---|
| Target | HFM | Cent | XAUUSDc | READ-ONLY EVIDENCE COLLECTED 2026-08-17 (account/spec/spread/mechanics; no execution, one session — see `docs/validation/runtime/`) | final decisions (risk, lot, spread, feasibility) once owner locks config |
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
LAST VERIFIED:          2026-08-17 +07:00
CURRENT PHASE:          PAPER VALIDATION EVIDENCE + EXECUTION IMPLEMENTATION
CURRENT MILESTONE:      Execution Engine Final Review — implementation
                        COMPLETE; 625 tests PASS; ruff/mypy clean (85 files);
                        EA NOT implemented; production LOCKED
LAST COMPLETED MILESTONE: Execution Engine Implementation + Final Review —
                        execution/ package (10 modules) + readiness report
                        docs/validation/execution/execution-final-readiness.md
LATEST COMMIT:          (this commit — feat(execution): implement + review)
TEST STATUS:            625 passed; ruff check/format clean; mypy clean
                        (85 files)
BLOCKER:                EA implementation (demo first). Production RiskConfig
                        not locked. Telemetry: London/NY sessions pending.
NEXT ACTION:            Implement the EA (MQL5 Expert Advisor) on the
                        Executor Protocol — demo first (HFM Demo), then
                        production (HFM Cent XAUUSDc) only after production
                        RiskConfig locked + owner authorization. No contract
                        changes required.
                        Production RiskConfig: NOT LOCKED.
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
| 2026-08-15 +07 | AI Benchmark Execution | IN PROGRESS | execution started | runner.py synced to 11 candidates (was 8) + spec §5 HTTP429 retry (max 3, sleep 10s) + 2 regression tests (22 benchmark tests PASS). Run: 11 models × 12 scenarios × 3 repeats = 396 requests on `http://10.139.136.202:20128/v1`; results → `docs/validation/ai-benchmark/results/`. |
| 2026-08-15 +07 | AI Benchmark Execution | COMPLETE | raw 396/396 (11 files × 36 lines, window 00:40–01:14 +07); status OK 360 / HTTP400 31 / TRANSPORT_ERROR 5 | 36/36 (scenario,repeat) combos per model; unique keys 396/396; payloads real (endpoint responses, not placeholders); all 31 HTTP400 + 5 TRANSPORT_ERROR belong to `cf/@cf/zai-org/glm-4.7-flash`; no missing/duplicate inference; no runner crash — process exited normally after last write (01:14:52). |
| 2026-08-15 +07 | Benchmark Normalization | COMPLETE | `results/normalized/metrics.json` + `results.json` (396 entries) written 01:14:52 +07 | Hard-fail (spec fail-closed): glm-4.7-flash n_ok=0, llama-3.2-1b schema_valid_rate 0.2778; ollama score 0.8946 (repair 0.2222), kilo 0.8754 (repair 0.1944); weights provisional; scoring ranking present; comparison not yet written to report. |
| 2026-08-15 +07 | AI Benchmark Execution — resume analysis | COMPLETE | interruption NOT confirmed; benchmark NOT in progress state | AGENTS.md work log was stale ("execution started") vs repository evidence (raw + normalized complete). Verdict: nothing to resume — all 396 inferences valid & stored; no duplicate prevention concern. Remaining: validation suite, final report, commit. |
| 2026-08-15 +07 | AI Benchmark Evaluation | COMPLETE | raw + normalized re-validated: 396/396 records, 0 duplicates, 0 missing combos, 0 malformed, timestamps monotonic; independent recompute of all metrics + scores = 0 diffs vs stored | 360 OK / 31 HTTP400 / 5 TRANSPORT_ERROR (all glm-4.7-flash); 0 timeouts, 0 aborted; hard-fails: glm-4.7-flash, llama-3.2-1b; failsafe rate 1.0 for all models; safety violations 0. |
| 2026-08-15 +07 | AI Benchmark Report | COMPLETE | `docs/validation/ai-benchmark/benchmark-report.md` (21 sections) | Benchmark winner groq/llama-3.3-70b-versatile 0.9903; operational winner + recommended primary cf/llama-3.1-8b-instruct-fp8-fast 0.9901 (p95 777 ms, std 0.0); secondary groq 70b; fallback cf/qwen2.5-coder-32b; cost: only kgw free-tier verified (3 routes), 8 models COST_UNKNOWN. Final model selection PENDING APPROVAL. |
| 2026-08-15 +07 | Validation suite | COMPLETE | pytest 360 passed (40.9 s); ruff check . clean; ruff format --check . clean (98 files); mypy collector shared clean (48 files) | No source changes required; all green before commit. |
| 2026-08-17 +07 | AI Model Selection Gate — ID verification | COMPLETE (READY FOR APPROVAL) | read-only `GET /v1/models` HTTP 200 @ `10.197.141.202:20128` (old `10.139.136.202` timed out) | Exact IDs verified present: `cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast`, `groq/llama-3.3-70b-versatile`, `cf/@cf/qwen/qwen2.5-coder-32b-instruct`, + rest of shortlist. Discrepancy resolved: `cf/llama-3.1-8b-fp8-fast` = shorthand ONLY, NOT a valid endpoint ID — implementation must use full route ID (raw benchmark records already store it). `benchmark-report.md` clarified (Exact ID note §4 + §20 status READY FOR APPROVAL). AI selection NOT approved — human approval next. |
| 2026-08-17 +07 | AI Model Selection | APPROVED | user-approved locked config in AI Decision Engine task | PRIMARY `cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast`, SECONDARY `groq/llama-3.3-70b-versatile`, FALLBACK `cf/@cf/qwen/qwen2.5-coder-32b-instruct`; exact IDs verified. |
| 2026-08-17 +07 | AI Decision Engine — implementation started | IN PROGRESS | `ai_decision/` planning | authority boundary, deterministic parsing, timeouts per spec v1.0.0, bounded retry/fallback, SystemGate interface-only. |
| 2026-08-17 +07 | AI Decision Engine — contract validation | COMPLETE | 71 tests green (parsing 19 / validation 13 / engine 34 / integration 5) | strict schema (confidence 0..1 reject not clamp; reason string), authority violations fail-closed, fail-safe aliases → NO-TRADE. |
| 2026-08-17 +07 | AI Decision Engine — live smoke | COMPLETE | single non-trading call: PRIMARY returned BUY 0.8 @ 1032 ms, validation_ok=True | Found live router quirk: JSON body + trailing `data: [DONE]` (no newline) — parser now strips SSE tail; regression tests added. No benchmark rerun. |
| 2026-08-17 +07 | AI Decision Engine — acceptance | COMPLETE | full suite 431 passed; ruff check/format clean; mypy clean (57 files); report `docs/validation/ai-decision-engine/ai-decision-engine-validation.md` | Acceptance criteria met (14/14); no MT5/order capability; no Risk/Execution/EA implemented. |
| 2026-08-17 +07 | Risk Engine Gate — implementation | COMPLETE | `risk_engine/` package (models/config/calculators/validators/engine/gate/reason_codes) + 20 tests (18 unit + 2 integration with ai_decision) | System-owned approval gate consuming AI proposals; deterministic SL→lot→risk/exposure chain; fail-closed REJECT on any uncertainty; zero broker/MT5 capability. |
| 2026-08-17 +07 | Risk Engine Gate — validation | COMPLETE | full suite 449 passed; ruff check/format clean; mypy clean (65 files); report `docs/validation/risk-engine/risk-engine-validation.md` | Verdict PASS WITH PENDING CONFIGURATION. Pending human locks: risk % per trade (1.0 default), SL distance (2.0 default), exposure/drawdown/spread/margin buffers, sizing formula. |
| 2026-08-17 +07 | Risk Engine Gate — acceptance | COMPLETE | commit `feat(risk): implement system risk gate`; main pushed | Acceptance met: AI never determines lot/risk/SL; System APPROVE/REJECT; deterministic math; margin/exposure/spread validated; no broker execution. |
| 2026-08-17 +07 | Risk Config Finalization — evaluation | COMPLETE | audit + decision matrix + report `docs/validation/risk-engine/risk-config-finalization.md`; 449 tests green, ruff/mypy clean | Verdict PASS WITH HUMAN APPROVAL REQUIRED. Obsidian marks all numeric risk thresholds PENDING DECISION → no config locked. LOCKED mechanisms: risk basis EQUITY, %-of-equity risk-budget lot formula, floor rounding, risk≤budget enforcement, fail-closed state handling, SL=loss-protection, ABC exit preserved. |
| 2026-08-17 +07 | Risk Config Finalization — approvals | BLOCKED | 8 owner decisions pending (risk %, SL, max exposure, max drawdown+window, max spread, margin buffer+leverage, cost treatment, compounding ratio) | Per task rule §29/§44: no unilateral numeric locking; commit docs-only. |
| 2026-08-17 +07 | HFM Cent XAUUSDc Read-Only Runtime Discovery | COMPLETE | read-only MT5 IPC (MetaTrader5 5.0.6090), account 229105805 / HFMarketsGlobal-Live19, symbol XAUUSDc; account/symbol/margin captured; 61 spread samples (min 34 / median 36 / max 36 pts); lot/tick/SL mechanics; report `docs/validation/runtime/xauusdc-cent-readonly-observation.md`; zero execution | Owner-locked already: basis EQUITY, risk/trade 0.5%, max positions 1, max drawdown 5%. New evidence for pending: leverage fallback 2000:1, spread ~36 pts (provisional SL 2.0 < spread → econ-invalid), exposure notional ~4370 USC/lot. No config auto-locked. |
| 2026-08-17 +07 | Risk Parameter Evaluation | COMPLETE | decision matrix + SL sensitivity + spread/exposure/margin options + 3 profiles; report `docs/validation/risk-engine/risk-parameter-evaluation.md`; 449 tests green | READY FOR HUMAN APPROVAL. Finding: SL 2.0pt invalid (spread 36pt); econ-valid SL 40–72pt needs equity 8,000–14,400 USC for 0.01 lot @ 0.5%; spread candidates 36–50pt accept observed window; leverage observed 2000; cost treatment NEEDS PAPER VALIDATION. No config locked. |
| 2026-08-17 +07 | Risk Configuration v0.1 (PAPER_VALIDATION) | APPLIED | owner-approved profile applied to `RiskConfig` (equity ratios, SL points, leverage fallback 2000, compounding 0%); exposure/margin now ratio-based; SL-above-observed-spread guard; 23 risk tests; 455 suite green; ruff/mypy clean; reports `paper-validation-risk-config-v0.1.md` + finalization §PAPER_VALIDATION_V0.1 | Profile metadata: is_production=false, requires_paper_validation=true. Production Risk Configuration remains UNLOCKED. Commission/swap = PENDING_PAPER_EVIDENCE. Next: paper validation → revisit → Execution design. |
| 2026-08-17 +07 | Paper Validation Harness | COMPLETE | `paper_validation/` package (8 modules: models, cost_model, market_replay, execution_simulator, position_simulator, evidence, metrics, scenario_runner); 21 new tests (unit + integration); full suite 476 PASS; ruff/mypy clean (74 files); report `docs/validation/paper-trading/paper-validation-report.md` | Verdict PASS WITH FINDINGS. All evidence SIMULATED. 15 scenario groups covered. Risk budget invariant holds at zero-slippage; overrun flagged under high costs → cost treatment is critical pending. ABC exit works (NET_PROFIT > 0 → close). SL 50pts valid. Production RiskConfig UNLOCKED. |
| 2026-08-17 +07 | Multi-Session XAUUSDc Telemetry | PARTIAL | 2240 read-only samples (ASIAN only, 00:38–01:46 UTC); spread stable 34–36 pts, 0% > 45; raw `docs/validation/runtime/multi-session/xauusdc-spread-timeseries.jsonl`; report `xauusdc-multi-session-report.md`; zero execution | Asian evidence consistent with prior 61-sample run. London/NY/overlap NOT collected → max_spread 45 and SL 50 cannot be locked. Production RiskConfig UNLOCKED. |
| 2026-08-17 08:47 +07 | Multi-Session Telemetry — strategy switch | DONE (switch) | continuous 22.4 h collector (proc PID 10588/2576) terminated; retained tail window 3 = 441 ASIAN samples (01:39:26–01:46:41 UTC); short-window protocol active (30–60 min, ~1 s, same JSONL schema, append-only, run only while PC available, no background > 2 h) | JSONL do-not-delete rule honored; 2240 total samples, all valid, 0 malformed. Windows remaining: LONDON, LONDON_NY_OVERLAP, NEW_YORK, OFF_HOURS. Next window: LONDON ~14:00–15:30 +07. No commit (per rule: commit only after a new window completes). |
| 2026-08-17 +07 | Execution Architecture Readiness | COMPLETE (design) | `docs/validation/execution/execution-architecture-readiness.md` (23 sections): TradePlan/ExecutionCommand/ExecutionResult contracts; state machine; idempotency; broker truth; partial fill/SL/ABC-exit; error matrix; retry policy; EA boundary; observability lineage (1:1 canonical events, no schema change); security; executor abstraction; OD-1..OD-12. 476 tests PASS; ruff/mypy clean (74 files) | VERDICT READY WITH OPEN DECISIONS. Design-only: no code, no RiskConfig change, no Obsidian edit (partial-fill conflict 08 vs Order Lifecycle recorded). Bridge telemetry-only. Production RiskConfig UNLOCKED. |
| 2026-08-17 +07 | Multi-Session XAUUSDc Telemetry — LONDON window | COMPLETE | LONDON n=3594 read-only samples (2026-08-17 09:56:14–10:56:13 UTC, 3600 s @ 1 s); spread min 34 / median 34 / P95 36 / max 36; 0% > 36; validation 0 malformed, 0 missing fields, 0 duplicate timestamps; total now 5834 (ASIAN 2240 + LONDON 3594); report `xauusdc-multi-session-report.md` updated §5b/§6/§7/§8–§16; zero execution | London median 2 pts tighter than Asian (34 vs 36); same 34–36 pt range, no widening; across-session drift NONE. Production RiskConfig UNLOCKED; max_spread 45 / SL 50 NOT locked (overlap/NY/off-hours pending). Remaining: LONDON_NY_OVERLAP ~19:00–22:00 +07, NEW_YORK ~21:00–03:00 +07, OFF_HOURS ~04:00–07:00 +07. |
| 2026-08-17 +07 | Execution Engine Implementation + Final Review | COMPLETE | `execution/` package (10 modules); 625 tests PASS; ruff check/format clean; mypy clean (85 files); safety scan PASS (no MT5/network/secrets); readiness report `docs/validation/execution/execution-final-readiness.md`; verdict PASS WITH FINDINGS | OD-1..OD-10 implemented; authority boundary clean (execution imports stdlib + own modules only); 13-scenario SimulatedExecutor; 18-code error matrix → 6-class retry policy; SQLite WAL journal (append-only + keyed projection + restart recovery); ReconciliationBoundary (UNKNOWN→broker-truth); EA NOT implemented; production RiskConfig not locked; production LOCKED. No contract/schema changes. No Obsidian edits. |
| 2026-08-17 +07 | Multi-Session XAUUSDc Telemetry — LONDON_NY_OVERLAP window | COMPLETE | OVERLAP n=1966 read-only samples (2026-08-17 12:17:16–13:05:36 UTC, 2 windows: 1067 + 899 @ 1 s); spread min 34 / median 36 / mean 38.20 / P75 41 / P90 50 / P95 50 / P99 50 / max 50; 27.62% > 36 pts, 19.02% > 45 pts, 0% > 50; longest run > 45: 374 s; bimodal: 72% at 34–36, 19% at 45–50; total now 7800 (ASIAN 2240 + LONDON 3594 + OVERLAP 1966); validation 0 malformed, 0 duplicates; zero execution | CRITICAL: first evidence of spread > 36. Max 50 pts = SL distance → zero headroom at peak overlap. max_spread 45 rejects 19% of overlap samples. SL 50 SAFE for ASIAN+LONDON (14pt margin), MARGINAL for overlap (0pt). Three spread regimes: ASIAN tight (34–36), LONDON tightest (34–36), OVERLAP bimodal (34–36 + 45–50). Production RiskConfig UNLOCKED. NY session NEXT (~21:00 WIB). |
