# ABC Bot Phase A Data-Only Validation Report

- Date: 2026-08-14
- Auditor: Hermes (audit run on local PC, repository `D:\Project\abc-bot-paper-trader`)
- Repository HEAD at audit: `856c527` (`fix(collector): count malformed lines in ingestion stats`), baseline `36228cb`
- Method: source audit + regression suite (339 tests) + live runtime E2E run against committed replay fixtures (scratch SQLite under `data/validation/`, git-ignored). No MCP servers configured on this profile (`hermes mcp list` empty) -> MCP Thinking/Context7/Affine NOT USED; reasoning performed manually and documented inline.

---

## Current Phase

Phase A — Data-Only Validation (final infrastructure gate before AI Model Benchmark & Selection). Scope: prove the pipeline `MT5 → MQL5 Read-Only Bridge → JSONL → Collector Ingestion → Canonicalization → Schema Validation → Checksum → SQLite WAL → Reconciliation` is correct, safe, recoverable, and auditable. No execution, no AI, no risk/lot/exit engine, no strategy.

## Environment

| Aspect | Value |
|---|---|
| Target account | HFM Cent + `XAUUSDc` — NOT OBSERVED this run (no Cent account attached) |
| Technical harness | HFM Demo Premium + `XAUUSD` — documented in AGENTS.md as completed runtime validation; runtime JSONL artifacts not present in repo -> marked TECHNICAL_HARNESS_ONLY, re-observation NOT OBSERVED |
| Validation runtime | Local Windows 10, Python 3.11 (uv), scratch `data/validation/runtime.db` (WAL), replay fixtures `tests/replay/fixtures/*.jsonl` |
| Harness evidence usage rule | Premium/XAUUSD evidence used ONLY for pipeline correctness; NOT used for risk/lot/margin/spread-economics/strategy/profitability/Cent decisions |

## Repository Baseline

- Branch `main`, clean at audit start; 8 commits (`0a4fad4` .. `36228cb`); +1 fix commit from this audit (`856c527`).
- Required gates at HEAD:
  - `pytest`: **339 passed** (36.35s)
  - `ruff check .`: **All checks passed**
  - `ruff format --check .`: **92 files already formatted** (incl. new doc script after format)
  - `mypy collector shared`: **Success: no issues found in 48 files**
- MQL5 compile evidence `mql5-bridge/compile.log` (UTF-16): `Result: 0 errors, 0 warnings, 2975 ms, X64 Regular`.

## Evidence Inventory

| # | Evidence | Kind | Where |
|---|---|---|---|
| E1 | Full source audit of collector (event_model, adapters, persistence), reconciliation, shared, mql5-bridge | OBSERVED (static) | all files listed below |
| E2 | 339-test suite (unit + replay + MQL5 static) | TEST-VERIFIED | `tests/` |
| E3 | Live E2E runtime run: replay → SQLite → integrity → recovery → reconciliation → export | OBSERVED (this run) | `data/validation/runtime_validation.py`, 31/31 checks PASS |
| E4 | Bridge compile log | OBSERVED (artifact) | `mql5-bridge/compile.log` |
| E5 | HFM Demo Premium XAUUSD runtime validation claim | DERIVED (AGENTS.md) / NOT OBSERVED (no terminal here) | `AGENTS.md` §3 |
| E6 | Locked contract + validation report + JSON Schema | OBSERVED (unchanged) | `docs/contracts/canonical-event-contract.md`, `canonical-event-contract-validation.md`, `shared/schemas/canonical-event.schema.json` |
| E7 | Architecture + README | OBSERVED (unchanged) | `docs/architecture.md`, `README.md` |
| E8 | Live MT5 bridge attach + live JSONL growth on target (Cent/XAUUSDc) | NOT OBSERVED | — |
| E9 | Reconciliation against live MT5 adapter | NOT OBSERVED (adapter deliberately out of scope; mock boundary only) | `collector/reconciliation/` |

## MQL5 Bridge Validation  (A1)

Source: `mql5-bridge/src/{Bridge.mq5, Config.mqh, Export/JsonExporter.mqh, Events/EventBuilder.mqh, Health/HealthMonitor.mqh}`.

| Item | Verdict | Evidence |
|---|---|---|
| Initialization | TEST-VERIFIED | `OnInit`: terminal check → `SymbolSelect` + `SymbolInfoTick` probe → account context read → exporter open → `HEARTBEAT status=STARTED` → `EventSetTimer(1)`; compile 0 errors |
| Symbol verification | TEST-VERIFIED | probe failure → degraded mode, heartbeat continues; symbol configured once in `Config.mqh` (`InpSymbol = "XAUUSDc"`), never hard-coded elsewhere (static test) |
| Read-only behavior | TEST-VERIFIED | `tests/mql5/test_bridge_safety.py` blocks 17 execution tokens (`OrderSend` family, `OrderModify`, `OrderDelete`, `CTrade`, ...); `request.`/`result.` never dereferenced in `OnTradeTransaction`; audit confirms only read APIs used |
| Tick collection | TEST-VERIFIED | `OnTick` never deduplicates; write failure → log + health error, never silent drop |
| bid/ask/mid/spread | TEST-VERIFIED | `mid := (bid+ask)/2`, `spread := ask−bid` in `EventBuilder.mqh` + unit test |
| Source timestamp | TEST-VERIFIED | `ts_source = E_IsoTime(tick.time)` broker server seconds; no fabricated ms (`tick.time_msc` never promoted) |
| JSONL writing | TEST-VERIFIED | append-only `FILE_READ|FILE_WRITE` + `SEEK_END`; single `FileWriteString` per line; ASCII-escaped output; flush policy (`InpFlushLines=100`, heartbeat, deinit) |
| Directory creation | TEST-VERIFIED | segment-wise `FolderCreate` idempotent; `tests/mql5/test_exporter_directory_handling.py` (RefExporter mirror): missing dir created, existing idempotent, append preserved |
| Heartbeat | TEST-VERIFIED | `STARTED`/`RUNNING`/`DEGRADED`/`STOPPED` + counters; disconnect episode → one `TIMEOUT` per episode + `ERROR` on reconnect |
| Exporter recovery | TEST-VERIFIED | bounded reopen (max 3); unreadable file renamed `*.corrupted.<ts>` (history preserved), fresh file started |
| Graceful shutdown | TEST-VERIFIED | `OnDeinit`: `EventKillTimer`, flush, final `HEARTBEAT status=STOPPED`, `Close()` |

**Live attach (target Cent/XAUUSDc and harness Premium/XAUUSD) = NOT OBSERVED in this run.** Bridge runtime behavior on the harness was previously validated by the project (AGENTS.md §3); all guarantees are additionally pinned by static + mirror-replica tests. Gate A1 verdict: **PASS WITH WARNINGS**.

## JSONL Validation  (A2)

| Item | Verdict | Evidence |
|---|---|---|
| File exists / growth | NOT OBSERVED (no live MT5 run here); semantics TEST-VERIFIED | append + reopen tests (`test_append_behavior_and_restart`, RefExporter) |
| Valid JSON per line | TEST-VERIFIED | fixture lines parse; `parse_errors=0` in E2E replay (E3) |
| No unexplained malformed records | OBSERVED | `malformed_line_count=0` on all fixture replays |
| Timestamps valid | OBSERVED | 4/4 persisted events parseable ISO-8601 UTC (regex + `fromisoformat`) |
| Symbol preserved | OBSERVED | `{'XAUUSDc','XAUUSD'}` preserved verbatim through replay (harness symbol correctly passes through; never rewritten) |
| Duplicate tick timestamps do not lose ticks | TEST-VERIFIED | `test_duplicate_timestamp_ticks_are_all_accepted` (distinct `event_id`, equal payload); bridge never dedupes on timestamp |
| bid/ask/mid/spread consistency | OBSERVED | 2/2 tick events: `ask ≥ bid`, `mid == (bid+ask)/2`, `spread == ask−bid` (abs tol 1e-9) |

## Collector Ingestion Validation  (A3)

Path verified end-to-end: `reader.py (READ) → pipeline._process_line (PARSE → NORMALIZE → ENRICH/canonicalize → VALIDATE → CHECKSUM → PERSIST) → repository.insert_event_with_cursor`.

| Item | Verdict | Evidence |
|---|---|---|
| READ (JSONL tail, offset) | TEST-VERIFIED | `JsonlFileReader` poll/delta/partial-hold; E2E cursor at EOF = file size |
| PARSE (raw JSON) | TEST-VERIFIED | `parse_raw_line`; malformed line → skipped, cursor advances |
| NORMALIZE | TEST-VERIFIED | `normalize_bridge_line`; kinds canonical/internal/unknown; wrong `source` rejected |
| ENRICH (collector-owned identity) | TEST-VERIFIED | event_id/correlation/trade_id owned by collector; `ts_monotonic` filled here; no fabricated broker ids |
| CANONICALIZE | TEST-VERIFIED | `build_event` + schema validation against `canonical-event.schema.json` (Draft202012) |
| VALIDATE | TEST-VERIFIED | typed model + JSON Schema + lifecycle (`validate_transition`) |
| CHECKSUM | TEST-VERIFIED | SHA-256 canonical serialization; verified at persistence + integrity suite |
| PERSIST | OBSERVED | 4 events persisted atomically with cursor (single transaction) |
| Trade-path line without identity | OBSERVED (by design) | `ORDER_ACKNOWLEDGED` (fixture line 7) → `events_identity_pending=1`, `events_invalid=1`, raw preserved, cursor advances; identity never fabricated |

Metrics (E2E run, fixture `bridge_raw_mixed.jsonl`, 8 lines): `lines_read=8`, `events_parsed=8`, `events_valid=4`, `events_persisted=4`, `events_invalid=1` (identity-pending), `parse_errors=0`, `malformed_line_count=0`, `internal_event_count=3` (HEARTBEAT + 2 snapshots), `unknown_event_count=0`, `cursor_offset=1714` (EOF), `last_event_timestamp` set, `ingestion_lag_ms` computed from `ts_monotonic`, `current_source_file` set, `rotations_seen=1` (rotation scenario). All 14 required metrics exist and are wired (bug found and fixed: `malformed_line_count` was never incremented — see Code Changes).

## Cursor / Recovery Validation  (A4)

| Scenario | Verdict | Evidence |
|---|---|---|
| Initial ingestion | OBSERVED | cursor advances only after successful persistence (same tx) — code path + runtime |
| Restart | OBSERVED | re-open at saved cursor → 0 re-processed lines, no duplicate events; new process `quick_check` + integrity pass |
| Duplicate replay | OBSERVED | re-insert identical envelope (deterministic id) → `duplicate` flag, row count unchanged; conflicting checksum on same id → `PersistenceError`, original preserved |
| Persistence failure | TEST-VERIFIED | `_persist_cursor` failure → `PersistenceIngestionError`, cursor only advanced on success (transactional); suite covers rollback |
| Incomplete final line | OBSERVED | partial line held (`holds_partial=True`), 0 events persisted; when writer completes the line in-place → exactly 1 event persisted |
| File rotation | OBSERVED | file shrunk/replaced below cursor → `rotations_seen=1`, cursor reset, fresh stream ingested |
| Unavailable source file | OBSERVED | missing file → 0 events, cursor unchanged |
| Malformed permanent line | TEST-VERIFIED | skipped once, cursor advances (no infinite retry) |

## SQLite Validation  (A5)

| Item | Verdict | Evidence |
|---|---|---|
| WAL | OBSERVED | `PRAGMA journal_mode = wal` |
| Foreign keys | OBSERVED | `PRAGMA foreign_keys = 1` |
| Migration version | OBSERVED | `schema_migrations = [1,2,3]`, applied transactionally |
| Schema integrity | OBSERVED | integrity check aggregate PASS (quick_check + per-table checks) |
| Append-only event protection | OBSERVED | triggers `events_no_update`, `events_no_delete` present |
| Checksum integrity | OBSERVED | integrity suite verifies every stored checksum; tamper → FAIL (fixture `checksum_tamper.jsonl` covered by suite) |
| Duplicate event detection | OBSERVED | no duplicate `event_id`; idempotent `INSERT OR IGNORE` + conflict rejection |
| Transaction rollback | TEST-VERIFIED | event+cursor atomic; persistence failure leaves DB consistent |
| Restart recovery | OBSERVED | re-open + integrity pass; no partial state |

## Reconciliation Validation  (A6)

Flow verified: `OBSERVE (broker snapshot) → COMPARE (classify: local vs broker) → CLASSIFY (NO_MISMATCH / MISSING_* / CONFLICTING_STATE / RECOVERABLE / UNKNOWN) → RECORD (canonical RECONCILIATION event, uuid5 deterministic id, single tx) → ESCALATE | ADOPT (records only)`.

| Trigger | Verdict | Evidence |
|---|---|---|
| STARTUP | OBSERVED | empty broker → `SYNCED`, recorded |
| HEARTBEAT | OBSERVED | identical repeat (same trigger) → skipped (`skipped_identical=1`); signature includes trigger, so each trigger keeps its own audit trail |
| POST_EXECUTION | OBSERVED | broker orphan (position 9001) → `ADOPTED_BROKER`, adoption row written |
| MISMATCH | OBSERVED | local OPEN BUY vs broker SELL → `CONFLICTING_STATE` → `ESCALATED` |
| Snapshot unavailable | TEST-VERIFIED | provider raises `BrokerUnavailableError` → `TIMEOUT` event, no phantom state |

**No execution capability (runtime-verified):** during reconciliation runs, `orders=0` rows, `positions` untouched by the service (only the pre-seeded derived-state row), `reconciliation_runs=4`, `reconciliation_adoptions=1`. Classifier never auto-closes local orphans (`MISSING_BROKER → investigate, not close`); live MT5 adapter deliberately out of scope (mock boundary only).

## End-to-End Traceability  (A8)

OBSERVED (single chain):
`MT5 tick line (fixture) → JSONL line 1 → IngestionAdapter (parse→normalize→envelope) → event_id → checksum (sha256:2a545bfdc...) → SQLite row ×1 → export_events_csv (4 rows) + export_events_jsonl (4 lines) → roundtrip from_json(to_json(event)) == event`.

## Data Quality Audit

| Rule | Verdict |
|---|---|
| ask ≥ bid | PASS (0 violations) |
| spread == ask − bid | PASS |
| mid == (bid+ask)/2 | PASS |
| event_id unique | PASS (4/4) |
| checksum valid | PASS (integrity suite + persistence-time verify) |
| timestamp parseable | PASS (0 bad) |
| symbol preserved | PASS (`XAUUSDc` + harness `XAUUSD` verbatim) |
| broker IDs preserved | TEST-VERIFIED (bridge passes tickets verbatim; collector never fabricates — `e.g. broker_order_id = "12345678"` in tests) |
| no unexplained data loss | PASS (raw lines vs persisted: 8 lines → 4 canonical + 3 internal + 1 identity-pending; no silent drop path found) |
| no impossible lifecycle state | PASS (lifecycle FSM enforced; `RISK_GATE REJECT` and reconciliation order-failure terminate the path) |

## Safety Audit

| Item | Verdict | Evidence |
|---|---|---|
| Live trading disabled | PASS | `settings.py` safety defaults: `live_trading_enabled=false`, `read_only_mode=true`; no execution code exists anywhere |
| Read-only enabled | PASS | bridge read-only (static test + source audit); collector is observer only |
| Demo execution disabled | PASS | no order path, no `OrderSend` in repo (grep `OrderSend|TradeAction|CTrade` → 0 hits in collector/shared/bridge) |
| No AI execution | PASS | AI engines do not exist in this repo (AGENTS.md authority boundary: AI = entry proposal only) |
| No Risk/Lot/Exit engine execution | PASS | no engine modules; risk-gate is contract type only, never evaluated |
| Reconciliation non-execution | PASS | OBSERVE→…→RECORD only; runtime check: no order/position mutation |

## Performance Evidence

- No dedicated benchmark run this phase (data volume is trivial: fixture replays < 2 KB). Timestamp deltas available in DB (`ts_monotonic`, `ts_collected`, `ts_event`) — ingestion_lag_ms measured by pipeline.
- MQL5 compile: 2.975 s, 0 errors.
- 339 tests: 36.35 s. E2E runtime suite: 31/31 checks.
- NOT OBSERVED: sustained throughput, tick-rate stress, WAL checkpoint churn at scale — defer to Phase A Data Collection.

## Code Changes (this audit)

1. `collector/adapters/pipeline.py` — increment `malformed_line_count` on `InvalidLineError` (observability metric was declared but never incremented; `parse_errors` alone could not distinguish malformed JSON from other invalid lines). Minimal, no contract/architecture change, no new capability.
2. `tests/unit/test_ingestion_pipeline.py` — regression assertion `malformed_line_count == 1` in existing malformed-line test.
3. `.gitignore` — `data/validation/**` (generated Phase A validation artifacts).
   Commit: `856c527`. Re-verified after fix: pytest 339 passed, ruff/mypy clean, runtime E2E 31/31.

## Acceptance Gates

| Gate | Verdict | Note |
|---|---|---|
| A1 Bridge Runtime | **PASS WITH WARNINGS** | compile + static + mirror tests PASS; live attach (Cent target or harness re-run) NOT OBSERVED here |
| A2 JSONL Integrity | **PASS** | structure/semantics verified; live file growth NOT OBSERVED (deferred to data collection) |
| A3 Ingestion | **PASS** | full path exercised; 1 observability bug fixed |
| A4 Cursor/Replay | **PASS** | 7/7 scenarios (initial, restart, dup, failure, partial, rotation, unavailable) |
| A5 SQLite Persistence | **PASS** | WAL/FK/migrations/integrity/triggers/dupes/rollback |
| A6 Reconciliation | **PASS** | 4 triggers + 3 results + idempotency + non-execution |
| A7 Safety | **PASS** | no execution capability anywhere |
| A8 Traceability | **PASS** | full chain demonstrated |

## Blockers

None. No data loss, no checksum/integrity failure, no cursor corruption, no SQLite corruption, no reconciliation state-integrity gap, no execution capability, no architecture/contract conflict found. STOP conditions not triggered.

## Warnings

1. Live MT5 attach (both harness and Cent target) not re-observed in this environment — bridge live runtime evidence is derived (AGENTS.md) plus compile log plus static/mirror tests.
2. Cent/XAUUSDc runtime validation impossible here (no account); infrastructure readiness is broker-agnostic, but all economics (spread, slippage, lot, margin) remain pending measured Cent data. Premium/XAUUSD evidence stays TECHNICAL_HARNESS_ONLY.
3. First-run event identity is `uuid4` per observation: a manual re-read from offset 0 produces fresh ids by design (contract forbids timestamp-based dedupe). Real restart path uses the cursor, so no duplicates occur (verified).
4. Trade-path lines lacking `trade_id` are counted `events_invalid`/identity-pending and never persisted — correct, but metric consumers must read `events_identity_pending` to interpret.
5. `export_events_jsonl` loads all events into memory (≥2 GB table); fine at Phase A scale, revisit before analytics phase.
6. MCP servers (Thinking/Context7/Affine) not configured on this profile — audit performed without them; no doc correlation beyond repo docs (AGENTS.md/architecture/contracts cover Paper Trading, Market Data, Execution, Reconciliation, Audit Trail, Collector, M1/M5 context).
7. `POSITION_UPDATED` `mfe_usd/mae_usd` raw 0.0 by bridge design — collector owns trade-level state (documented limitation, not a defect).

## Final Verdict

**PASS WITH WARNINGS** — Phase A infrastructure is ready end-to-end: read-only bridge verified, JSONL transport sound, ingestion/canonicalization/checksum correct, cursor recovery complete, SQLite WAL integrity proven, reconciliation non-executive and idempotent, traceability demonstrated, no execution capability, regression gates green. Remaining warnings are observation-gap items (live attach, Cent data, scale performance), not defects. Final Cent/XAUUSDc validation and all economic/strategy decisions remain explicitly out of this phase's authority.

## Next Milestone

Phase A Data Collection → ≥200 paper trades on HFM Cent `XAUUSDc` (bridge attached live, collector tailer running, reconciliation heartbeats on); then Empirical Analysis; then AI Benchmark final + Risk/Lot finalization. No AI/risk/execution decision is made by this report.

## AI BENCHMARK REQUIREMENTS — PRELIMINARY

Identified without selecting any model (input for the next milestone's benchmark spec):

| Requirement | Preliminary figure / rationale |
|---|---|
| Latency budget | Contract chain `TRIGGER_DETECTED → CONTEXT_BUILT → AI_REQUEST → AI_RESPONSE → RISK_GATE` is per-trade, not per-tick. Target end-to-end AI decision < 2 s from `TRIGGER_DETECTED` (observed `ts_monotonic` deltas will confirm); model p95 inference ≤ 1.5 s. |
| Context size | M1+M5 market context window, preliminary 4–8 k tokens input (ticks batch + M5 candles + position state + rules); output < 256 tokens. Verify against actual serialized context during data collection. |
| Structured JSON output | Must emit exactly `{direction: BUY\|SELL\|NO-TRADE, confidence: 0..1, reason: str}`; JSON Schema-validated before `RISK_GATE`; malformed/empty output = NO-TRADE (hard fail-closed). |
| Timeout behavior | `AI_REQUEST → AI_RESPONSE` needs a hard timeout (preliminary 5 s); miss → timeout event + NO-TRADE; contract terminality rules apply (no trade-path event may follow a failed gate). |
| Inference observability | Every request/response must emit canonical `AI_REQUEST` / `AI_RESPONSE` events with `ts_monotonic`, model id, prompt/response sizes, latency, token counts; rejected/empty outputs recorded as `ERROR`-severity telemetry. |
| Expected request frequency | Per-trade only (trigger-gated); at M1/M5 cadence, orders of magnitude below tick rate (ticks are telemetry, never AI input per-tick). Target ≤ 1 request per trigger event; benchmark must hold latency at this low concurrency (1 request in flight). |
| Provider criteria (non-decision) | Deterministic JSON, bounded p95 latency, stable API schema, local-network reachability (user prefers local tools), cost per 1k requests at expected volume. |