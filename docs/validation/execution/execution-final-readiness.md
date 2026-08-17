# Execution Engine Final Readiness & EA Integration Readiness

Implementation milestone: the `execution/` package is now **implemented and
tested** against the architecture-readiness contracts. This report is the
final technical review of that implementation — authority boundaries,
contracts, state machine, idempotency, retry, partial fill, simulator,
reconciliation, safety, and EA interface readiness.

Scope boundaries honored (task §20):

- NO MT5 / MQL5 EA / broker API / live order / position modification
- NO production RiskConfig change
- NO automatic production unlock
- NO EA implementation

---

## 1. Scope

Final review of the `execution/` package against:

- `AGENTS.md` authority boundaries (§11) and safety rules (§12)
- Obsidian source-of-truth docs (00-Core, 02-Architecture, 04-Risk, 05-Execution)
- `ai_decision/` forbidden-output enforcement
- `risk_engine/` APPROVE/REJECT gate + TradePlan construction
- `paper_validation/` simulator boundary
- `shared/contracts/` canonical event model alignment
- `docs/validation/execution/execution-architecture-readiness.md` OD-1..OD-10

Deliverable: verified implementation + EA interface specification +
reconciliation-readiness definition + this readiness report.

## 2. Architecture

Implemented pipeline (this repository):

```text
AI Decision (direction, confidence, reason)
  ↓
Risk Engine (APPROVE/REJECT → lot, SL, risk, exposure, TradePlan)
  ↓
TradePlan (immutable, System-owned)
  ↓
Execution Engine (validate → create_command → submit → SL attach → close)
  ↓
SimulatedExecutor (paper/validation; broker-agnostic)
  ↓
Reconciliation Boundary (broker-as-truth adoption from UNKNOWN)
  ↓
ExecutionJournal (SQLite WAL, append-only audit + keyed projection)
```

Package layout (`execution/`):

| Module | Responsibility |
|---|---|
| `models.py` | TradePlan, ExecutionCommand, ExecutionResult, PositionSnapshot, CommandState, ResultStatus, ExitReason, EntryType, Direction |
| `validation.py` | Plan/command validation, expiry enforcement, field forbidden-list |
| `state_machine.py` | Deterministic transitions, RECONCILABLE_STATES, TRANSITION_TABLE |
| `retry.py` | ErrorCode (18), RetryClass (6), RETRY_MATRIX, RetryPolicy, classify_error |
| `journal.py` | SQLite WAL, append-only triggers, keyed projection, active-trade uniqueness, restart recovery |
| `engine.py` | ExecutionEngine lifecycle: create_command, submit, post_fill (SL attach + partial cancel), close, reconcile, recover |
| `executor.py` | Executor Protocol (submit / get_position / attach_sl / close_position / query) |
| `simulated.py` | SimulatedExecutor + SimulatorScenario + SubmitMode (13 scenarios) |
| `reconciliation.py` | ReconciliationBoundary Protocol, ReconciliationOutcome, StaticReconciliation |
| `errors.py` | ExecutionError, DuplicateCommandError, ExecutionStateError, JournalError |
| `__init__.py` | Public re-exports |

## 3. Authority Boundaries

### AI may produce

`direction` (BUY/SELL/NO-TRADE), `confidence` (0..1), `reason` (string).

Enforced by `ai_decision/validation.py` FORBIDDEN_OUTPUT_KEYS (lot, sl, tp,
risk, exposure, margin, order, etc.) → `AUTHORITY_VIOLATION` rejection.
Parsing normalizes to exactly `{direction, confidence, reason}`.

### Risk/System may produce

APPROVE/REJECT, lot, SL, risk_amount, risk_percent, exposure, TradePlan,
exit policy (NET_PROFIT > 0), policy_profile.

### Execution may produce

Validate TradePlan, generate ExecutionCommand, lifecycle management,
idempotency, retry classification, submit abstraction, fill tracking,
close lifecycle, reconciliation boundary.

### Execution must NOT

Recalculate lot/SL/risk/exposure/margin, override RiskDecision, re-invoke
AI, or call broker execution directly.

**Verification (concrete):**

- `execution/` imports: stdlib only (`math`, `re`, `uuid`, `json`, `sqlite3`,
  `pathlib`, `dataclasses`, `enum`, `datetime`, `typing`, `collections`)
  + own `execution.*` modules. Zero imports of `risk_engine`, `ai_decision`,
  `paper_validation`, or any broker/MT5 SDK. (Static grep confirmed.)
- `ExecutionCommand` carries no `risk`, `confidence`, `reason`, `tp`, or
  `risk_amount` field — only `command_id`, `trade_id`, `symbol`, `direction`,
  `volume`, `entry_type`, `sl`, `created_at`, `expires_at`.
- `ExecutionEngine.create_command` maps `plan.lot → command.volume` and
  `plan.sl → command.sl` verbatim; no recalculation.
- Integration test `test_execution_from_risk_gate.py` proves a REJECTED
  RiskDecision never reaches Execution (no TradePlan constructed).

## 4. Contract Verification — TradePlan

`@dataclass(frozen=True)` — immutable by construction.

Lineage: `inference_id → risk_evaluation_id → trade_id → command_id`.

| Field | Type | Source | Verified |
|---|---|---|---|
| trade_id | str (UUID) | Risk Engine | is_valid_system_id |
| correlation_id | str (UUID) | Risk Engine | is_valid_system_id |
| inference_id | str \| None | AI Decision | is_valid_system_id (optional) |
| risk_evaluation_id | str (UUID) | Risk Engine | is_valid_system_id |
| direction | BUY / SELL | AI | validated |
| lot | float > 0 | Risk Engine | finite, positive |
| entry_reference | float > 0 | Risk Engine | finite, positive |
| sl | float > 0 | Risk Engine | finite, positive |
| risk_amount | float ≥ 0 | Risk Engine | finite, non-negative |
| risk_percent | float ≥ 0 | Risk Engine | finite, non-negative |
| exposure | float ≥ 0 | Risk Engine | finite, non-negative |
| symbol | str | Risk Engine | non-empty |
| generated_at | ISO 8601 | Risk Engine | parseable |
| expires_at | ISO 8601 | Risk Engine | parseable, > generated_at |
| policy_profile | str | Risk Engine | non-empty (PAPER_VALIDATION_V0.1) |

Tests: `test_models.py` (immutability, validation, expiry ordering, field
preservation), `test_validation.py` (validate_plan_dict, forbidden fields,
expiry).

## 5. Contract Verification — ExecutionCommand

`@dataclass(frozen=True)` — immutable by construction.

| Field | Type | Rule | Verified |
|---|---|---|---|
| command_id | str (UUID) | == idempotency_key (OD-9) | new_command_id |
| trade_id | str (UUID) | == plan.trade_id | preserved |
| symbol | str | == plan.symbol | preserved |
| direction | str | == plan.direction | preserved |
| volume | float | == plan.lot (verbatim) | no recalculation |
| entry_type | EntryType | MARKET only (OD-4) | validate rejects non-MARKET |
| sl | float | == plan.sl (verbatim) | no recalculation |
| created_at | ISO 8601 | engine timestamp | parseable |
| expires_at | ISO 8601 | == plan.expires_at | preserved |

No TP field. No risk/confidence/reason field. No sizing/recalculation field.

Test regression: `test_valid_plan_creates_created_command` asserts
`command.expires_at == plan.expires_at` and `command.volume == plan.lot`.

## 6. State Machine Verification

States (CommandState enum):

```text
CREATED → VALIDATED → SUBMITTED → PARTIALLY_FILLED → FILLED → MODIFYING → CLOSED
Failure: REJECTED | FAILED | EXPIRED | UNKNOWN
```

Transition table (`state_machine.py`):

| From | Event | To |
|---|---|---|
| CREATED | VALIDATE_OK | VALIDATED |
| CREATED | VALIDATE_FAIL / EXPIRE | FAILED / EXPIRED |
| VALIDATED | SUBMIT | SUBMITTED |
| VALIDATED | VALIDATE_FAIL / EXPIRE | FAILED / EXPIRED |
| SUBMITTED | PARTIAL_FILL | PARTIALLY_FILLED |
| SUBMITTED | FULL_FILL | FILLED |
| SUBMITTED | REJECTED / FAILED / EXPIRE / UNKNOWN | REJECTED / FAILED / EXPIRED / UNKNOWN |
| PARTIALLY_FILLED | FULL_FILL | FILLED |
| PARTIALLY_FILLED | CLOSED / UNKNOWN / FAILED | CLOSED / UNKNOWN / FAILED |
| FILLED | SL_ATTACHING | MODIFYING |
| FILLED | CLOSED / UNKNOWN / FAILED | CLOSED / UNKNOWN / FAILED |
| MODIFYING | SL_ATTACHED | FILLED |
| MODIFYING | CLOSED / UNKNOWN / FAILED | CLOSED / UNKNOWN / FAILED |
| UNKNOWN | RECONCILED (target) | any RECONCILABLE_STATE |

Rules:

- `transition()` raises `ExecutionStateError` on illegal transitions.
- `RECONCILED` requires `target` and is only valid from `UNKNOWN`.
- Terminal states: CLOSED, REJECTED, FAILED, EXPIRED.
- Any non-terminal state may reach UNKNOWN.

**Audit-event projection integrity:**

`EXECUTOR_RESULT`, `CLOSE_RESULT`, `RECONCILE_AFTER_TIMEOUT` are audit-only
journal rows. They carry the **current projection state** via
`_current_state()` helper and never advance the projection prematurely. The
state machine transition is applied separately via `_record_transition()`
which calls `transition()` + persists.

Regression test `test_audit_rows_never_move_projection_prematurely` asserts
all `EXECUTOR_RESULT` rows carry `CommandState.SUBMITTED` (not FILLED) in a
timeout-retry scenario — the projection advances only via the explicit
`FULL_FILL` / `UNKNOWN` transition, never via audit rows.

Tests: `test_state_machine.py` (all transitions, illegal transitions,
RECONCILED target validation), `test_engine.py` (lifecycle scenarios).

## 7. Partial-Fill Verification (OD-1)

Policy: `CANCEL_REMAINING`.

```text
Requested = 0.10
Fill      = 0.06
Remaining = 0.04  → CANCELLED (no second order)
Final     = FILLED (filled_volume = 0.06, sl_applied = True)
```

Code path (`engine.py _post_fill`): on `PARTIALLY_FILLED`, journal records
`CANCEL_REMAINDER` event with payload `{cancelled_volume, policy:
"CANCEL_REMAINING", second_order: False, requested_volume}`, then promotes
to FILLED with SL confirmed. Single executor call.

Regression test `test_partial_fill_cancels_remainder_no_second_order`:
- `result.status == FILLED`
- `result.filled_volume == 0.06`
- `executor.submit_calls == 1` (never a second order)
- `CANCEL_REMAINDER` event payload verified

Lineage preserved: same `command_id`, same `trade_id`, no AI re-decision,
no Risk recalculation.

## 8. Idempotency Verification

Rules and enforcement:

| Rule | Enforcement |
|---|---|
| Duplicate command never creates second submission | `create_command` checks journal, raises `DuplicateCommandError` on active trade_id |
| Same command_id returns stored result | `submit()` replays stored result if terminal; `close()` replays CLOSED result |
| Timeout does not imply successful submission | TIMEOUT → state stays SUBMITTED → reconcile first; `submitted_state_never_resends` test |
| Ambiguous response → UNKNOWN | AMBIGUOUS scenario → `UNKNOWN` state + `AMBIGUOUS_RESPONSE` error |
| UNKNOWN → reconciliation | `reconcile()` only valid from UNKNOWN; raises `ExecutionStateError` otherwise |
| Reconciliation before resend | Retry loop calls `reconcile()` before each retry; no blind resend |
| Retry uses same command identity | Same `command_id` / `idempotency_key` across all retries |

Tests: `test_submit_is_idempotent_replay`, `test_close_is_idempotent`,
`test_reconcile_before_resend`, `test_submitted_state_never_resends`.

## 9. Journal / Restart Recovery

`ExecutionJournal` (`journal.py`):

- SQLite WAL mode, `execution_commands` (keyed projection) +
  `execution_journal` (append-only audit).
- `BEFORE UPDATE` / `BEFORE DELETE` triggers → `RAISE(ABORT)` on audit table.
- Partial unique index `uq_execution_commands_active_trade` on `trade_id`
  WHERE state NOT IN terminal — enforces one live command per trade.
- `store_result()` persists latest result into projection (audit already
  appended via `record()`).
- `get_command()` returns `StoredCommand` (state + result) for idempotency lookup.
- `get_active_for_trade()` returns non-terminal commands for the gate.

Restart recovery (`engine.py recover()`):

| Stored state | Recovery action |
|---|---|
| CREATED | SUBMIT_SAFE (never reached executor) |
| VALIDATED | SUBMIT_SAFE |
| SUBMITTED | RECONCILE (write-ahead: crash after journal = reconcile first) |
| PARTIALLY_FILLED | RECONCILE |
| FILLED / MODIFYING | RECONCILE |
| UNKNOWN | RECONCILE |
| Terminal | NONE |

Tests: `test_journal.py` (append-only, replay, triggers), `test_engine.py`
`TestRecovery` (created/submitted/unknown recovery, events survive restart).

## 10. Retry / Error Policy

`RetryPolicy` (owner-approved OD-4/OD-5/OD-6):

| Parameter | Default | Meaning |
|---|---|---|
| submit_retries | 2 | Max retries after initial attempt (total 3) |
| close_retries | 2 | Max retries after initial close attempt (total 3) |
| sl_attach_retries | 2 | Max retries after initial SL attach (total 3) |

Error classification (`retry.py RETRY_MATRIX`):

| ErrorCode | RetryClass | Behavior |
|---|---|---|
| NETWORK_TIMEOUT | SAFE | Bounded retry same command_id after reconcile confirms no broker evidence |
| CLOSE_FAILED | SAFE | Bounded retry close, then reconcile |
| SL_ATTACH_FAILED | EMERGENCY | SL attach retry budget → emergency close |
| EMERGENCY_CLOSE_FAILED | RECONCILE | No action until broker truth |
| AMBIGUOUS_RESPONSE | RECONCILE | No action until broker truth |
| RECONCILIATION_PENDING | RECONCILE | Blocked until reconcile |
| BROKER_REJECT | PERMANENT | Terminal, no retry |
| INSUFFICIENT_MARGIN | PERMANENT | Terminal, no retry |
| INVALID_VOLUME_SL | PERMANENT | Terminal, no retry |
| REQUOTE_SLIPPAGE | PERMANENT | Terminal, no retry |
| STALE_FEED | PERMANENT | Terminal, no retry |
| POSITION_EXISTS | PERMANENT | Terminal, no retry |
| MARKET_CLOSED | PERMANENT | Terminal, no retry |
| INVALID_COMMAND | PERMANENT | Terminal, no retry |
| AUTHENTICATION | PERMANENT | Terminal, no retry |
| EXPIRED | PERMANENT | Terminal, no retry |
| DUPLICATE_COMMAND | IDEMPOTENT | Replay stored result |
| FAILED | UNSAFE | Never blind resend |

Retry guard: after budget exhausted → `UNKNOWN` + reconciliation required.
No infinite loops. No retry after permanent rejection. No retry on
requote/slippage/invalid volume. Reconciliation always before resend.

Tests: `test_retry.py` (matrix completeness, classify_error), `test_engine.py`
`TestTimeoutRetries` (bounded retries, broker unreachable, timeout-landed,
reconcile-before-resend), `TestSlProtection` (SL attach budget + emergency
close), `TestClose` (close retry budget + reconcile).

## 11. Reconciliation

`ReconciliationBoundary` Protocol: `reconcile(command, hint) → ReconciliationOutcome`
and `query(command) → ReconciliationOutcome`.

`ReconciliationOutcome`: `discovered_state: CommandState | None`,
`ambiguous: bool`, `evidence: dict`.

Resolution flow:

```text
UNKNOWN
  ↓ reconcile(command)
  ↓ outcome.ambiguous?
  ├── True  → UNKNOWN (broker unreachable; AMBIGUOUS_RESPONSE)
  ├── discovered_state is None → safe to retry (no broker evidence)
  └── discovered_state set → adopt broker truth (RECONCILED transition)
```

Adopted states must be in `RECONCILABLE_STATES` (SUBMITTED, PARTIALLY_FILLED,
FILLED, MODIFYING, CLOSED, REJECTED, EXPIRED, FAILED).

**Reconciliation-readiness data requirements (EA must provide):**

| Field | Source | Purpose |
|---|---|---|
| command_id | Engine | Correlation key |
| trade_id | Engine | Lineage |
| broker_request_id | EA | Order correlation (if available) |
| broker order ticket | EA | Broker order identity |
| position ticket | EA | Position identity |
| actual volume | EA | Filled / remaining |
| actual fill price | EA | Broker truth (never assumed) |
| current position state | EA | Position lifecycle |
| SL state | EA | SL applied / pending / absent |
| timestamps | EA | Order/fill/close event times |
| broker retcode | EA | Broker return code |

Critical: broker is source of truth. Engine never assumes requested values
equal actual broker values.

Tests: `test_engine.py` `TestReconciliationGate` (requires UNKNOWN, adopts
broker truth, releases fail-closed gate, not-journaled raises).

## 12. Simulated Executor

`SimulatedExecutor` implements `Executor` Protocol with 13 scenarios
(`SubmitMode` enum):

| Scenario | Behavior |
|---|---|
| FULL_FILL | Complete fill at 4400.0, SL applied |
| PARTIAL_FILL | Partial fill (configurable ratio), remainder cancelled |
| REJECT | Broker rejection (BROKER_REJECT) |
| TIMEOUT | No broker order left (enables retry testing) |
| TIMEOUT_LANDED | Broker fill exists but submit timed out (reconcile discovers) |
| AMBIGUOUS | Ambiguous response (AMBIGUOUS_RESPONSE) |
| REQUOTE | Requote/slippage (REQUOTE_SLIPPAGE) — permanent |
| STALE_FEED | Stale feed (STALE_FEED) — permanent |
| POSITION_EXISTS | Position already exists — permanent |
| SL_ATTACH_FAIL | SL attach fails → emergency close path |
| CLOSE_FAIL | Close fails → close retry budget then UNKNOWN |
| EXPIRED | Command expired before submit |
| DUPLICATE | Duplicate command → IDEMPOTENT replay |

Determinism: no `random` import, no external state, pure config-driven.
Simulator never imports MT5 (`test_simulated_executor_confirmed_offline`).

Tests: `test_simulated.py` (all scenarios, position tracking, SL attach,
close, query), `test_engine.py` (integration scenarios).

## 13. EA Boundary (Interface Specification)

EA is NOT implemented. This section defines what the EA must eventually
provide on the `Executor` Protocol.

### Engine → EA (command data)

EA receives `ExecutionCommand` (frozen dataclass):

| Field | Type | Constraint |
|---|---|---|
| command_id | str (UUID) | Idempotency key |
| trade_id | str (UUID) | Lineage to Risk TradePlan |
| symbol | str | e.g. XAUUSDc |
| direction | BUY / SELL | From AI via Risk |
| volume | float | Verbatim from plan.lot |
| entry_type | MARKET | Only MARKET in v0.1 |
| sl | float | Verbatim from plan.sl |
| created_at | ISO 8601 | Engine timestamp |
| expires_at | ISO 8601 | From plan.expires_at |

EA methods called by engine:
`submit(command)`, `get_position(command)`, `attach_sl(command, position_id, sl)`,
`close_position(command, position_id)`, `query(command)`.

### EA → Engine (acknowledgement / result data)

EA returns `ExecutionResult` (frozen dataclass):

| Field | Type | Meaning |
|---|---|---|
| command_id | str | Correlation key (same as command) |
| trade_id | str | Lineage |
| status | ResultStatus | FILLED / PARTIALLY_FILLED / REJECTED / FAILED / EXPIRED / UNKNOWN / CLOSED |
| timestamp | ISO 8601 | Broker event time |
| broker_request_id | str \| None | Broker order ticket (if available) |
| broker_retcode | int | Broker return code (0 = success) |
| filled_volume | float | Actual filled volume |
| fill_price | float | Actual fill price (broker truth) |
| sl_applied | bool | SL confirmed at broker |
| error_code | str \| None | ErrorCode value if failure |
| error_message | str \| None | Human-readable error detail |

### EA telemetry (reconciliation evidence)

For `query(command) → ReconciliationOutcome`, EA must return:

| Telemetry | Requirement |
|---|---|
| order ticket | broker_request_id / order ticket |
| position ticket | position identity |
| requested_volume | original command.volume |
| filled_volume | actual filled |
| actual fill price | broker truth (never assumed) |
| actual SL | SL state at broker (applied / pending / absent) |
| broker retcode | last operation return code |
| execution timestamp | order/fill/close event time |
| position state | open / closed / partially filled |
| close result | fill price + volume if closed |
| reconciliation evidence | full snapshot for UNKNOWN resolution |

### Critical requirement

**Broker is source of truth.** The engine never assumes `requested_volume ==
filled_volume` or `requested_sl == actual_sl`. All adoption goes through
reconciliation. The EA is the single component that communicates with the
broker/MT5. The engine is broker-agnostic.

## 14. Safety Verification

Static safety scan (`tests/execution/test_safety.py`, `tests/mql5/test_bridge_safety.py`):

| Token | Found in execution/ | Status |
|---|---|---|
| MetaTrader5 | No | PASS |
| mt5. | No | PASS |
| order_send | No | PASS |
| order_modify | No | PASS |
| OrderSend / OrderModify | No | PASS |
| position_modify | No | PASS |
| tradecopy / TradeCopy | No | PASS |
| import socket | No | PASS |
| http:// / https:// | No | PASS |
| requests. / import urllib | No | PASS |
| password / api_key / secret | No | PASS |
| .env / *.pem / *.key / credentials* | No | PASS |

Authority layering scan:
- `execution/` imports: stdlib + `execution.*` only. No `risk_engine`,
  `ai_decision`, `paper_validation`, or broker imports.
- Forbidden tokens appear only in `ai_decision/` (legitimate router HTTP
  client — the only network layer) and in safety-scanning test files themselves.

The execution package is broker-agnostic and remains a paper/validation layer.

## 15. Test Results

| Validation | Result |
|---|---|
| pytest (full suite) | **625 passed** in 74.38s |
| ruff check . | All checks passed |
| ruff format --check . | 162 files already formatted |
| mypy collector shared ai_decision risk_engine paper_validation execution | Success: no issues found in 85 source files |
| Static safety scan | PASS (no MT5 / network / broker / secrets in execution/) |

Test files:

| File | Coverage |
|---|---|
| `tests/execution/factories.py` | build_engine, make_plan, make_command, SimBrokerReconciliation, ts_in |
| `tests/execution/test_models.py` | TradePlan / ExecutionCommand / ExecutionResult immutability + validation |
| `tests/execution/test_validation.py` | validate_plan, validate_plan_dict, forbidden fields, expiry |
| `tests/execution/test_state_machine.py` | All transitions, illegal transitions, RECONCILED target |
| `tests/execution/test_retry.py` | RETRY_MATRIX completeness, classify_error, RetryPolicy |
| `tests/execution/test_journal.py` | Append-only triggers, replay, keyed projection, active-trade uniqueness |
| `tests/execution/test_simulated.py` | 13 scenarios, position tracking, SL attach, close, query |
| `tests/execution/test_engine.py` | Full lifecycle: create, submit, partial fill, SL attach, emergency close, close, retry, reconcile, recovery, audit-row projection integrity, sequential trade slot release |
| `tests/execution/test_safety.py` | Static scan: MT5 / network / secrets / broker tokens absent |
| `tests/integration/test_execution_from_risk_gate.py` | DecisionRecord → RiskEngine → APPROVED → TradePlan → ExecutionCommand → SimulatedExecutor → FILLED → CLOSED; REJECT → STOP |

## 16. Known Limitations / Production Blockers

| # | Limitation | Impact | Resolution |
|---|---|---|---|
| L1 | EA not implemented | No live/demo broker execution | Separate EA task (demo first, then production) |
| L2 | `trade_plan_ttl_seconds` in ExecutionConfig is reserved metadata, not enforced by engine | Plan TTL is entirely System-owned via `expires_at`; config field unused | Document; wire or remove in a future task |
| L3 | Reconciliation discovery of PARTIALLY_FILLED with remainder relies on EA to report/cancel remainder | Broker remainder cancellation is EA-side responsibility | EA reconciliation evidence must include remainder state |
| L4 | Engine cannot cryptographically verify TradePlan provenance (no signature from Risk Engine) | A fabricated TradePlan could structurally pass validation | Orchestrator boundary; provenance verification is a future task if needed |
| L5 | Journal is single-threaded (no concurrent write guard) | Race condition if engine is called from multiple threads | Document; add thread-safety if concurrent use is required |
| L6 | OD-8: RISK_GATE canonical payload has no `risk_evaluation_id` | TradePlan carries it additively (audit-only) | Contract extension is a separate decision |
| L7 | Production RiskConfig NOT LOCKED | PAPER_VALIDATION_V0.1 is paper-only | Owner must lock production config before live trading |

### Production blockers

1. EA implementation (no broker execution capability exists)
2. Production RiskConfig (PAPER_VALIDATION_V0.1 is `is_production=false`)
3. Owner authorization for demo/live execution (AGENTS.md §12)
4. L4 provenance verification (if orchestrator trust boundary is insufficient)

## 17. Final Verdict and Next Action

### Verdict

**PASS WITH FINDINGS**

The execution layer is implemented, tested, and verified against all authority
boundaries, contracts, state machine rules, idempotency, retry policy,
partial-fill policy, simulator coverage, and safety constraints. All
validation tools are green. The implementation is a validated paper/simulation
milestone — not live execution.

### Production status

**LOCKED.** Production remains locked:
- `PAPER_VALIDATION_V0.1`: `is_production=false`, `requires_paper_validation=true`
- No EA / MT5 / broker execution capability
- No production RiskConfig locked
- No automatic production unlock

### Exact next action

**Implement the EA (MQL5 Expert Advisor) on the `Executor` Protocol.**

1. Build a demo EA that implements `submit` / `get_position` / `attach_sl` /
   `close_position` / `query` against an HFM Demo account (not Cent).
2. Wire `ReconciliationOutcome` telemetry fields (§11, §13).
3. Run the full execution test suite against the demo EA on the same
   contract (no contract changes).
4. Only after demo validation passes + production RiskConfig is locked +
   owner authorizes: build a production EA for HFM Cent `XAUUSDc`.

No contract changes are required for EA implementation — the `Executor`
Protocol, `ExecutionCommand`, and `ExecutionResult` are the complete
interface surface.
