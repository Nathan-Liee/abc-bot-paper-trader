# Execution Architecture Readiness

Design-only milestone: define the contract surface between the approved
Risk Gate output and a future EA/MT5 execution boundary. NO execution
implementation was written. NO RiskConfig value was changed. NO Obsidian
file was modified (conflicts are recorded, §21).

Scope boundaries honored (task §3, §25–§27):

- NO `OrderSend` / `PositionOpen` / `PositionClose` / modify / pending order
- NO EA execution, NO demo broker execution
- NO risk % / SL / spread / exposure / margin / leverage / compounding changes
- Obsidian is evidence and authority reference only; conflicts noted, never edited

---

## 1. Objective

Prepare the design and contracts for the Execution Engine → EA/MT5 path so
the implementation stage does not need to break boundaries that are already
locked upstream (AI isolation, System risk authority, deterministic exit).

Deliverables of this milestone:

1. `TradePlan` contract — the System-owned output that bridges Risk Gate
   approval and execution.
2. `ExecutionCommand` contract — the execution-layer input.
3. `ExecutionResult` contract — the execution-layer output.
4. Deterministic execution state machine with idempotency rules.
5. Broker-source-of-truth reconciliation design.
6. Failure-mode classification and retry policy.
7. EA boundary, observability, and security design.
8. Executor abstraction allowing simulated / demo / real MT5 execution on the
   same contract.
9. Readiness report with explicit OPEN DECISIONS before implementation.

## 2. Current State

| Component | State | Evidence |
|---|---|---|
| AI Decision Engine | COMPLETE | `ai_decision/`; 71 tests; live smoke PASS (BUY 0.8 @ 1032 ms, 2026-08-17) |
| Risk Engine + Gate | COMPLETE | `risk_engine/`; 23 risk tests; 476 suite PASS; gate interface `SystemRiskGate` |
| RiskConfig | PAPER_VALIDATION_V0.1 APPLIED; Production UNLOCKED | `risk_engine/config.py`; profile metadata `is_production=false` |
| Paper Validation Harness | COMPLETE | `paper_validation/` (8 modules, 21 tests); all evidence SIMULATED |
| Multi-Session XAUUSDc Telemetry | PARTIAL (ASIAN n=2240) | `docs/validation/runtime/multi-session/`; London/NY pending |
| MQL5 Read-Only Bridge | COMPLETE (telemetry only) | `mql5-bridge/src/Bridge.mq5`; static safety test blocks execution tokens; compile 0 errors |
| Canonical Event Contract | COMPLETE (17 event types, locked) | `docs/contracts/canonical-event-contract.md`; `shared/contracts/` |
| Execution Engine / EA | NOT IMPLEMENTED | — |

Pipeline position of this design:

```text
AI
 ↓
System / Risk Gate
 ↓
APPROVE / REJECT
 ↓
TradePlan           <- contract defined here
 ↓
Execution Engine
 ↓
ExecutionCommand    <- contract defined here
 ↓
EA / MT5
 ↓
ExecutionResult     <- contract defined here
 ↓
Broker
```

The read-only bridge remains telemetry-only (§17). The future EA is a
separate artifact that reuses the same read path and adds execution.

## 3. Authority Matrix

Source: Obsidian "05 - Authority & Boundaries" + AGENTS.md §11 + task §5.

| Function | AI | System (Risk/Engine) | Execution Engine | EA / MT5 | Broker |
|---|---|---|---|---|---|
| Entry direction (BUY/SELL/NO-TRADE) | PRIMARY | VALIDATE | NONE | NONE | NONE |
| confidence / reason | PRIMARY | CONSUME | NONE | NONE | NONE |
| approval (APPROVE/REJECT) | NONE | PRIMARY | NONE | NONE | NONE |
| risk (%, budget) | FORBIDDEN | PRIMARY | NONE | NONE | NONE |
| lot sizing | FORBIDDEN | PRIMARY | NONE | NONE | NONE |
| SL value | FORBIDDEN | PRIMARY | APPLY ONLY | APPLY ONLY | NONE |
| exposure / margin checks | NONE | PRIMARY | NONE | NONE | NONE |
| TradePlan creation | NONE | PRIMARY | NONE | NONE | NONE |
| TradePlan → command translation | NONE | NONE | PRIMARY | NONE | NONE |
| broker request submission | NONE | NONE | VIA EA ONLY | PRIMARY | NONE |
| broker response reading | NONE | NONE | VIA EA ONLY | PRIMARY | TRUTH |
| order/position state query | NONE | NONE | VIA EA ONLY | PRIMARY | TRUTH |
| exit condition (NET_PROFIT > 0) | FORBIDDEN | PRIMARY | EXECUTE | EXECUTE | NONE |
| TP (fixed take-profit) | NONE | NONE | FORBIDDEN | FORBIDDEN | NONE |
| reconciliation | NONE | PRIMARY | SUPPORT | SUPPORT | TRUTH |
| strategy decisions | NONE | NONE | NONE | FORBIDDEN | NONE |

Hard rules (locked, unchanged):

- AI output reaches Execution ONLY via an approved TradePlan.
- Execution Engine never recalculates lot, risk, or SL; it never selects
  direction; it never adds its own SL/TP.
- EA never overrides System; EA has no model, direction, or sizing authority.
- `NET_PROFIT > 0 → CLOSE` is deterministic and never waits for AI
  (Obsidian 05 - Exit Philosophy / 06 - Exit Execution).

## 4. TradePlan Contract

Producer: **System Risk Gate** (Risk Engine APPROVE path). It is a frozen
snapshot of the approved decision; execution may NOT alter its numeric
content. Consumer: Execution Engine.

Fields (JSON object, all required unless noted):

```text
TradePlan
├── trade_id             uuid      system-owned; binds the whole trade path
│                                  (envelope trade_id in canonical events)
├── correlation_id       uuid      lineage root: AI inference -> risk -> execution
├── inference_id         uuid?     required when an AI proposal produced the plan
│                                  (this System owns trade_id/correlation_id;
│                                   inference_id is inherited, never synthesized)
├── risk_evaluation_id   uuid      audit id of the approving RiskEvaluationRecord
│                                  (additive; REQUIRED by §18 lineage; see §21 OD-8)
├── direction            "BUY" | "SELL"      from AI, validated by System
├── lot                  number    final quantized lot (volume_step compliant;
│                                  broker min/max enforced upstream)
├── entry_reference      number    price used at System approval:
│                                  BUY = market ask, SELL = market bid
│                                  (reference only; broker fill is truth)
├── sl                   number    SL price (System-calculated, round 5 dp)
├── risk_amount          number    planned risk USD at lot/SL (loss protection)
├── risk_percent         number    planned risk % of capital basis
├── exposure             number    notional exposure USD (lot x contract x entry)
├── symbol               str       broker symbol ("XAUUSDc")
├── generated_at         iso_ts    plan creation time (UTC)
├── expires_at           iso_ts    hard deadline; stale_after = expires_at
└── policy_profile       str       RiskConfig.profile_name ("PAPER_VALIDATION_V0.1")
```

Reasoning for each field (per task §6 "no field without reason"):

- `trade_id` — canonical event stream requires a UUID `trade_id` for every
  trade-path event (`shared/contracts/identity.py` SYSTEM_ID_FIELDS;
  `collector/event_model/validation.py`).
- `correlation_id` — canonical lineage root; TRIGGER_DETECTED requires it.
- `inference_id` — AI ancestry (AI_RESPONSE event key; optional at event level,
  required here for observability completeness when AI proposed the trade).
- `risk_evaluation_id` — references the approving audit record;
  RiskEvaluationRecord already carries this id
  (`risk_engine/models.py`); adding it to the plan is additive lineage.
- `entry_reference` — needed by Execution for freshness/deviation checks
  (§14, §17) without letting execution compute anything risk-relevant.
- `expires_at` — freshness control; stale plan must be REJECTED/EXPIRED
  (§14).
- `policy_profile` — auditability: which risk profile produced this plan.

The plan is immutable between System and Execution. It carries NO TP
(fixed TP is forbidden), NO slippage tolerance (policy PENDING per Obsidian
05-Entry Execution), NO order type (entry type is an execution concern
resolved at Execution layer; default MARKET, limit PENDING).

## 5. ExecutionCommand Contract

Producer: **Execution Engine** (only from an approved, fresh TradePlan).
Consumer: **EA / MT5** boundary.

```text
ExecutionCommand
├── command_id        uuid      unique command id; ALSO the idempotency_key
├── trade_id          uuid      = TradePlan.trade_id (one command per trade)
├── symbol            str       = TradePlan.symbol; EA validates against target
├── direction         "BUY" | "SELL"
├── volume            number    = TradePlan.lot (never recomputed here)
├── entry_type        "MARKET"  (LIMIT/STOP reserved; PENDING DECISION, §21 OD-4)
├── sl                number    = TradePlan.sl (System value, applied verbatim)
├── created_at        iso_ts
├── expires_at        iso_ts    = TradePlan.expires_at (command dies with plan)
└── idempotency_key   uuid      = command_id for market orders (see §8)
```

Constraints encoded at the boundary (EA side):

- `command_id` must be a fresh UUID; EA has never journaled it (§8).
- `trade_id` must not already own a position/command in the Execution state
  journal (max_simultaneous_positions = 1 enforced upstream; double-checked here).
- `volume` must equal `TradePlan.lot`; volume quantization is NOT an
  execution concern (already volume_step-compliant upstream).
- `sl` is applied verbatim; no adjustment, no recomputation, no recreation.
- No TP field exists in the command by construction.
- No risk/lot/slippage fields exist; execution cannot reassess risk.

## 6. ExecutionResult Contract

Producer: **EA / MT5**. Consumer: Execution Engine state + canonical events.

```text
ExecutionResult
├── command_id        uuid      echoes the command (idempotent lookup key)
├── trade_id          uuid      echoes the trade
├── broker_request_id broker_id opaque broker ticket if a request exists;
│                               absent/"" when the request never reached broker
├── status            str       terminal/local state: FILLED | PARTIALLY_FILLED |
│                               REJECTED | FAILED | EXPIRED | UNKNOWN | CLOSED
│                               (state machine §7; never fabricate broker states)
├── broker_retcode    int       MT5 retcode verbatim when present (else 0)
├── filled_volume     number    actual filled volume (0.0 until any fill)
├── fill_price        number    actual fill price (0.0 until any fill)
├── sl_applied        bool      true when position's SL equals TradePlan.sl
├── timestamp         iso_ts    result time (UTC)
├── error_code        str       classified error code (§15) or empty
└── error_message     str       human detail, broker message verbatim when present
```

Rules:

- `broker_request_id`/prices/volumes come ONLY from broker structures
  (`MqlTradeResult`, `HistoryDealGet*`, `PositionGet*`); never guessed
  (identity rule: broker-owned values are verbatim, never fabricated).
- `status` may be "live-mutated": EA first emits SUBMITTED-side evidence,
  then each fill event produces a fresh result. Terminal statuses follow
  broker truth after reconciliation (§9).
- `error_code` uses the classification matrix (§15) so upper layers react
  deterministically without parsing broker prose.

## 7. State Machine

Deterministic per-command lifecycle (happy path + failure states). States
mirror the canonical ORDER_* / POSITION_* event vocabulary where possible.

```text
CREATED ──> VALIDATED ──> SUBMITTED ──> PARTIALLY_FILLED ──> FILLED ──> MODIFYING ──> CLOSED
   │            │             │                    │             │
   │            │             └────> REJECTED      │             └── SL ok -> monitor
   │            │             └────> EXPIRED       │
   │            └────────────> FAILED              └──> FILLED (full) OR MODIFYING (SL attach)
   └────────────> FAILED                                          │
   (invalid command, expired before validation)                   └──> EMERGENCY close
                                                                         (SL absent, §11)
All non-final states can reach UNKNOWN (ambiguous broker response,
 timeout, restart) ——> UNKNOWN is always resolved by reconciliation (§9),
 then adopts broker truth: FILLED / REJECTED / EXPIRED / CLOSED / FAILED.
```

| From | To | Trigger |
|---|---|---|
| CREATED | VALIDATED | all boundary checks pass (symbol, volume, SL, expiry, idempotency journal) |
| CREATED | FAILED | command invalid / expired before validation |
| VALIDATED | SUBMITTED | broker request dispatched (OrderSend market) |
| VALIDATED | EXPIRED | expires_at passed before dispatch |
| SUBMITTED | PARTIALLY_FILLED | broker reports fill < requested volume |
| SUBMITTED | FILLED | broker reports fill == requested volume |
| SUBMITTED | REJECTED | definitive broker rejection (retcode) |
| SUBMITTED | EXPIRED | broker reports EXPIRED / command expired before any fill |
| PARTIALLY_FILLED | FILLED | remainder filled (or remainder canceled per §10 policy) |
| FILLED | MODIFYING | position open, SL not yet confirmed attached |
| MODIFYING | FILLED | SL confirmed attached (POSITION_SL == TradePlan.sl) |
| FILLED / MODIFYING | CLOSED | position closed (broker truth) — entry path ends |
| any non-terminal | UNKNOWN | timeout / ambiguous response / restart with state in flight |
| UNKNOWN | (any) | reconciliation result (broker truth; §9) |

Notes:

- `PARTIALLY_FILLED` exists because the bridge already emits PARTIAL order
  state (`OrderStateName` mapping) and Obsidian lists partial fill handling
  as a decision (§10).
- There is no `CANCELED` in the command machine: a canceled pending/rejected
  market command becomes REJECTED/EXPIRED. `CANCELED` is a broker order state,
  recorded verbatim in telemetry, not a command terminal state here
  (Obsidian conceptual states include Canceled; reconciliation adopts it as
  REJECTED-equivalent for a market command — see §21 OD-3).
- `MODIFYING` covers SL attachment (entry + SL atomicity is broker-dependent,
  §11). It is a minimal, single-purpose state.
- Terminal = REJECTED | FAILED | EXPIRED | CLOSED | UNKNOWN(after recon).
  A filled position then lives in Position Management (§13), not the command
  machine.

## 8. Idempotency

Goal: a command executes at most once — no double entry, no duplicate close.

Primaries:

- `idempotency_key` = `command_id` (system UUID). The EA journals
  `command_id → result` before/with submission; the journal survives restart
  (local file, append-only).
- `trade_id` uniqueness: at most one entry command per trade_id; at most one
  open position per trade_id on the account (System enforces
  max_simultaneous_positions=1; EA refuses a second command for a trade that
  already has an open/unknown position).
- `broker_request_id` (ticket) recorded when present; subsequent commands for
  the same trade_id are refused with the stored result returned.

Behavior per scenario (Obsidian 03-Position Lifecycle "Startup Recovery &
Re-attachment" is the authority):

| Scenario | Required behavior |
|---|---|
| Network retry (client-side) | Resend the SAME `command_id`. EA journal hit → return stored result, no new broker request. |
| EA restart | Replay journal. For SUBMITTED/UNKNOWN commands: QUERY broker first (history orders by magic + symbol + timestamp; positions by ticket). Never blind-resend. Verify Filled/Rejected/Expired; adopt broker truth (§9). |
| Broker timeout | Mark UNKNOWN. Reconcile (query order/position). Blind retry is FORBIDDEN ("unsafe retry", §16). |
| Duplicate command (same command_id or same trade_id) | Refuse at boundary; return the stored/known result (or the reconciled broker state) with `error_code=DUPLICATE_COMMAND`. Never submit twice. |
| Ambiguous response (e.g., retcode REQUEST sent but no deal evidence) | UNKNOWN → reconcile by ticket/position. Only after reconciliation proves no order exists may a NEW command_id be issued by the Execution Engine (owner-visible). |
| Close command | Idempotent on `trade_id` + `broker_position_id`: second close for an already closed position returns POSITION_CLOSED state, never a second order. |

Failure of the journal itself (write error): refuse new commands (fail-closed)
until the journal is repaired — consistent with the bridge's failure posture.

## 9. Broker Source of Truth

Principle (Obsidian 08-Execution Failure Handling, 03-Position Lifecycle;
AGENTS.md reconciliation service):

```text
Broker / MT5 state > local assumption
```

Reconciliation design (per command, per position):

1. **Command sent** — local journal entry (command_id, payload hash, ts).
2. **Response** — `MqlTradeResult` recorded verbatim (retcode, deal, order,
   volume, price). Retcode ≠ success → classify (§15).
3. **Actual order state** — `HistoryOrderGet*` (ORDER_STATE: STARTED/PLACED/
   PARTIAL/FILLED/REJECTED/EXPIRED/...) — the bridge already normalizes these
   strings; EA reuses the same vocabulary.
4. **Actual position state** — `PositionGet*` (ticket, volume, sl, open price,
   profit) — netting vs hedging handled by broker read API (position by
   trade/magic; trade_id correlation via comment if broker supports, else
   ticket journal mapping).

Conflict rules:

- If broker has a position and local state says NO position → adopt broker,
  re-attach monitoring, deterministic exit applies immediately
  (Obsidian 03 §Startup Recovery: `NET_PROFIT > 0` stays armed).
- If broker has NO position/order and local says FILLED → adopt broker
  (closed by SL adjusted/stop-out/partial cancel); reconcile; audit event.
- If broker state is unreachable → circuit breaker / safe mode per Obsidian
  (no new entry; existing positions stay monitored on live feed; deterministic
  exit stays active), then manual intervention after retry budget.
- `UNKNOWN` at the end of any verification leads to EMERGENCY no-entry state.

## 10. Partial Fill

Obsidian evidence (conflict — see §21 OD-1):

- `05 - EXECUTION/08 - Execution Failure Handling` — "Partial Fill Policy":
  partial fill is a valid OPEN position; remaining quantity gets a CANCEL;
  exposure uses filled qty only; deterministic exit applies to the filled
  position.
- `05 - EXECUTION/02 - Order Lifecycle` — "Penanganan Partial Fill: PENDING
  DECISION".

Because the two documents disagree, the contract MUST NOT hard-lock the
cancel-vs-keep policy. Design accommodates both (state machine has
PARTIALLY_FILLED); behavior follows the more specific policy (08) as a
DEFAULT, flagged OPEN DECISION.

Design answers (with the flag):

- Supported? **Yes — a broker partial fill is representable** (PARTIALLY_FILLED),
  and any filled quantity becomes a real OPEN position (exposure basis =
  filled qty — risk implication: actual risk scales with filled lot;
  planned risk in TradePlan is the cap, actual risk ≤ cap).
- State transition: SUBMITTED → PARTIALLY_FILLED → (FILLED if remainder
  fills/canceled per policy; or closed directly if position later closes).
- Remaining volume: default per Obsidian 08 = send CANCEL for remainder;
  **confirmed by owner** (OD-1).
- Risk implication: exposure & PnL based on filled volume only; risk budget
  bookkeeping updated by System/position manager, never by EA.
- Continue or stop? Default: entry stops (no re-fill); position stays OPEN
  and monitored with deterministic exit armed.
- **DESIGN DECISION REQUIRED**: OD-1 confirm; impact on max positions and
  risk budget accounting (OD-2).

## 11. SL Attachment

- System calculates SL (Risk Engine). Execution/EA applies the value
  verbatim — no adjustments, no recomputation (task §13).
- Preferred path — atomicity: market entry request carries SL in the same
  `MqlTradeRequest` (`sl` field, `ORDER_FILL_MODE` set by broker). When the
  broker returns a deal and position, EA verifies `POSITION_SL` == TradePlan.sl.
  If broker STOPS_LEVEL prevents the exact value, the System provided SL must
  already satisfy it (Risk Engine applies `stops_level`); EA still re-verifies
  vs `SYMBOL_TRADE_STOPS_LEVEL` and REJECTS the command (no silent adjustment).
- SL attach failure (position opened, SL absent):
  - state → MODIFYING; EA attempts `PositionModify` with the System SL value
    (bounded retries, e.g., 3; count is policy config, OD-6);
  - if still absent → **emergency protection**: close the position
    immediately (an open position without System SL violates loss-protection
    invariants; Obsidian Emergency Protection permits forced closure when
    policy allows — flagged OD-7), emit ERROR event, pause new entries.
- TP is NEVER attached (no fixed TP; ABC exit only — Obsidian 06-Exit
  Execution, 05-Exit Philosophy).
- SL is never moved by EA; SL movement is a System decision (none defined in
  current rules).

## 12. ABC Exit

- Rule (locked): `NET_PROFIT > 0 → CLOSE IMMEDIATELY`
  (Obsidian 05-Exit Philosophy; canonical `NET_PROFIT_POSITIVE` event;
  paper harness implements `net_pnl > 0`).
- Ownership split:
  - System / Position Management: monitors running PnL (net of swap/comm),
    detects threshold crossing, emits `NET_PROFIT_POSITIVE`, decides close.
  - EA: executes the close command only (idempotent on trade_id +
    broker_position_id); reports result; telemetry via EXIT_SUBMITTED /
    POSITION_CLOSED path.
  - Broker: source of truth for the closed state (final fill, realized PnL).
- Exit priority: close processing must not be blocked by AI inference or
  entry latency (Obsidian 06 — high priority).
- Threshold numerical value (> 0): paper harness uses > 0.0 strictly; numeric
  confirmation is PENDING (OD-5).
- Retry if close fails: PENDING DECISION (OD-6) — design default: bounded
  safe retries of the same close command id, then escalate to emergency
  protection; no infinite loop.

## 13. Position Management

Boundary:

| Function | Owner |
|---|---|
| Determine exit condition (NET_PROFIT > 0 after costs) | System (Position Manager) |
| Detect SL stop-out / micro conditions | System (from EA telemetry) |
| Execute close command | EA (broker request) |
| Read actual position state (volume, SL, price, profit) | EA (broker read path) |
| Source of truth | Broker |

- An OPEN position is monitored independent of the entry command machine:
  `NOT_OPEN → SUBMITTED → OPEN → CLOSING → CLOSED` (Obsidian 03)
  with every `UNKNOWN` triggering immediate reconciliation.
- Re-attachment: on restart, system queries broker positions; re-attaches
  monitoring; deterministic exit stays armed for re-attached positions.
- The System decides; the EA executes; the broker is truth. This split is
  identical for entry and exit.
- No position-management logic (MFA/MFE thresholds, holding rules) lives in
  the EA. (Paper harness `position_simulator` already demonstrates the
  System-side logic shape.)

## 14. Freshness / Expiry

- `created_at` on plan/command = System approval wall-clock (UTC).
- `expires_at` (stale_after): hard deadline for the whole entry path.
  Default proposal: `expires_at = generated_at + TTL`; TTL configurable,
  suggested 30 s — **owner-confirm** (OD-9). Rationale: Risk Engine already
  rejects market context older than `max_stale_seconds` (10 s); the plan TTL
  bounds the gap between approval and submission.
- Stale TradePlan behavior: REJECT/EXPIRED — execution refuses to translate,
  returns `EXPIRED`, emits audit; a NEW plan requires a new risk evaluation
  (no silent refresh, no value mutation).
- Expired command behavior: `VALIDATED→EXPIRED` or `CREATED→EXPIRED`; journal
  keeps the record; no broker request is ever sent for an expired command.
- EA-side freshness gate at submission: current tick age ≤ max stale
  (bridge HealthMonitor pattern); stale feed → refuse entry (Obsidian
  07-Execution Safety: no execution on stale data).

## 15. Error Classification

Mapping into the EA boundary. Codes are stable strings for determinism
(aligning with `risk_engine/reason_codes` naming style). `R` = reconcile
required before any decision. `N` = never retry without owner.

| Error | Retry | Fail | Reconcile | Reason |
|---|---|---|---|---|
| `INVALID_COMMAND` | NO | YES | NO | failed boundary validation (schema/symbol/volume/SL/expiry/idempotency) — fail-closed, journaled |
| `AUTHENTICATION` | NO (N) | YES | NO | terminal; broker/credentials broken; alarm + manual |
| `NETWORK_TIMEOUT` | NO (R) | pending | YES | unambiguous outcome unknown → reconcile order/position before retry or fail |
| `BROKER_REJECT` | NO (N) | YES | NO | definitive retcode rejection (e.g., TRADE_RETCODE_REJECT) → audit, no retry without owner (Obsidian 08) |
| `INSUFFICIENT_MARGIN` | NO (N) | YES | NO | deterministic rejection; risk gate guards upstream; log + idle |
| `INVALID_VOLUME` | NO | YES | NO | contract violation — volume outside min/max/step; plan error, system-side |
| `INVALID_SL` | NO | YES | NO | SL below stops level or inconsistent with direction; plan error, system-side |
| `MARKET_CLOSED` | NO (R) | YES | NO | session/closed symbol; no entry; re-evaluate later as new plan |
| `REQUOTE_SLIPPAGE` | YES (bounded, same command id) | after budget | NO | acceptable deviation policy PENDING (OD-4); default: bounded requote-safe resubmit of the SAME command, then FAIL |
| `DUPLICATE_COMMAND` | NO | YES | NO | journal dedup; return stored result (not a failure — idempotent replay) |
| `AMBIGUOUS_RESPONSE` | NO (R) | pending | YES | request accepted but no deal/position evidence → UNKNOWN → reconcile |
| `STALE_FEED` | NO | YES | NO | tick age beyond freshness gate; refuse entry (Obsidian 07) |
| `POSITION_EXISTS` | NO | YES | NO | trade_id/position conflict; System state mismatch → reconcile journal |

Every error produces an `ExecutionResult` with `error_code` + verbatim broker
message in `error_message`, and a canonical ERROR/TIMEOUT event where
applicable. Terminal failures also trigger the "no new entry" safe posture
(Obsidian 08: safe state; Circuit Breaker trigger on repeated failures).

## 16. Retry Policy

- Retry WITHOUT idempotency is forbidden (task §19). All retries resend the
  exact same `command_id` (or use journal replay).
- Categories:

| Category | Allowed? | Examples |
|---|---|---|
| SAFE RETRY | YES (bounded, same id) | transport-level resubmit before any broker acceptance evidence; requote (same command); journal replay returning stored results |
| UNSAFE RETRY | NO — FORBIDDEN | blind resend after broker timeout or after a request-accept without outcome (creates double-entry risk) |
| RECONCILE FIRST | mandatory gate | timeout, ambiguous response, EA restart, state mismatch — query broker, adopt truth, then decide |
| PERMANENT FAILURE | terminal | authentication, invalid command/volume/SL, definitive rejection, market closed, duplicate (replay-safe but terminal) |

- Bounded budgets: requote retries (proposal: max 2; OD-6), SL-attach
  retries (proposal: max 3 then emergency close §11). Budgets are control
  parameters for the implementation milestone, not lock decisions here.
- After ANY terminal failure of an entry command, new entries require a fresh
  plan from the System (re-evaluation), never reuse of the failed command.

## 17. EA Boundary

- The existing `mql5-bridge` is **telemetry only** and stays unchanged as the
  read path (tick/order/deal/position evidence, snapshots, heartbeat). This
  design DOES NOT convert it into an execution EA.
- The future **EA** is the only component that submits broker requests and
  only for commands that pass its boundary gate.

EA responsibilities (REQUIRED):

- receive `ExecutionCommand` (validated transport; e.g., local JSON file/IPC —
  channel PENDING, OD-10);
- validate command (§19);
- submit broker request (`MqlTradeRequest` MARKET, SL verbatim);
- read broker response (`MqlTradeResult` verbatim);
- read actual order/position state (history + position API);
- maintain execution state journal (idempotency, restart safety);
- emit telemetry (reuse bridge JSONL vocabulary: ORDER_ACK/ORDER_FILL/
  POSITION_OPENED/POSITION_UPDATED/POSITION_CLOSED/ERROR/TIMEOUT/
  RECONCILIATION-compatible lines).

EA FORBIDDEN:

- choosing a model or making any AI/strategy decision;
- choosing BUY/SELL (direction is verbatim from command);
- computing lot, risk, SL, exposure, margin, or any risk value;
- overriding System decisions (e.g., changing SL, adding TP, holding on);
- executing any command not originating from the approved TradePlan path
  (no arbitrary commands — includes operator-initiated "quick trades").

EA security posture (§19) is fail-closed: on any validation doubt, reject.

## 18. Observability

Required IDs (task §22) — producers:

| ID | Type | Produced by | Carried by |
|---|---|---|---|
| `inference_id` | uuid | AI Decision Engine | AI_REQUEST/AI_RESPONSE; TradePlan |
| `risk_evaluation_id` | uuid | Risk Engine | RiskEvaluationRecord; TradePlan (proposed additive, OD-8) |
| `trade_id` | uuid | System (plan creation) | envelope trade_id of every trade-path event; TradePlan; command; result |
| `command_id` | uuid | Execution Engine | command; result; journal |
| `broker_request_id` | broker_id | Broker (verbatim) | result; ORDER_ACKNOWLEDGED/ORDER_FILLED events |
| `position_id` (`broker_position_id`) | broker_id | Broker (verbatim) | POSITION_* events; result after fill |
| `correlation_id` | uuid | System (plan creation, or inherited from trigger) | TRIGGER_DETECTED + envelope of trade-path events |

Lineage chain (every hop carries the previous ids):

```text
AI proposal (inference_id, correlation_id)
  ↓  AI_RESPONSE
Risk decision (risk_evaluation_id, inference_id, correlation_id)
  ↓  RISK_GATE  (+ trade_id assigned)
TradePlan (trade_id, correlation_id, inference_id, risk_evaluation_id)
  ↓
ExecutionCommand (command_id, trade_id)
  ↓
Broker request (broker_request_id, command_id, trade_id)
  ↓
Order / Position (broker_order_id / broker_position_id, trade_id)
```

Event mapping (canonical, locked contract — no schema change needed for the
path itself):

| Milestone | Canonical event |
|---|---|
| command created/validated | ORDER_SUBMITTED (requested_price=entry_reference, requested_volume, direction, order_type, submission_ts) |
| broker accepted | ORDER_ACKNOWLEDGED (broker_order_id, broker_state, ack_ts) |
| fill(s) | ORDER_FILLED (broker_order_id, broker_deal_id, fill_price, fill_volume, slippage, fill_ts) |
| position open | POSITION_OPENED (broker_position_id, direction, volume, open_price, open_ts, state=OPEN) |
| running PnL | POSITION_UPDATED / NET_PROFIT_POSITIVE (broker_position_id, trade_id…) |
| close requested | EXIT_SUBMITTED (broker_position_id, requested_close_price, close_volume, submission_ts) |
| closed | POSITION_CLOSED (broker_position_id, exit_fill_*, realized/net pnl, exit_reason, final_state=CLOSED) |
| drift | ERROR / TIMEOUT (error_code, component=execution, severity, trade_id, recovery_action) |
| verification | RECONCILIATION (trigger POST_EXECUTION/STARTUP…, result SYNCED/ADOPTED_BROKER/ESCALATED) |

Consistency check performed (task §29): the proposed commands/results map
1:1 onto existing ORDER_SUBMITTED/ORDER_ACKNOWLEDGED/ORDER_FILLED/
POSITION_OPENED payload specs (`shared/contracts/payload_specs.py`) without
new fields; `broker_request_id` = broker_order_id + broker_deal_id (two
events); `sl_applied` lives in ExecutionResult only (no event field needed —
POSITION_UPDATED carries price/PnL; SL verification is EA-internal evidence).

## 19. Security

EA communication boundary (task §23):

- No arbitrary execution commands: only the Execution Engine endpoint may
  produce commands; EA accepts precisely one schema and refuses everything
  else (strict JSON schema + version).
- Command validation (all REQUIRED, fail-closed, in order):
  1. schema validity; unknown/extra fields → INVALID_COMMAND;
  2. symbol == configured target (`XAUUSDc`); anything else rejected;
  3. volume: equal to TradePlan lot, within broker min/max, on volume_step
     grid;
  4. SL: numeric, direction-consistent (BUY sl < reference, SELL sl >
     reference), ≥ broker stops level, equals TradePlan.sl;
  5. expiry: `expires_at` in future at validation time;
  6. idempotency: command_id fresh in journal; trade_id free.
- Journal integrity: append-only, checksummed lines (bridge JSONL pattern),
  write-failure → fail-closed (no commands accepted).
- Credentials: account/server/token remain local to EA config, never in the
  repository, never in commands (project rule: `.env` never committed).
- Local channel protection: command file/pipe restricted to the bot owner
  account; no network listener by default (channel decision OD-10).
- No privilege escalation: EA never mutates RiskConfig, AI config, or
  Obsidian; it cannot self-enable live trading flags.

## 20. Paper / Demo / Real Executor Abstraction

Obsidian 04-Broker Abstraction: `[Execution Engine] → [Execution Interface]
→ [Broker Adapter] → [API Broker]`; paper-first execution principle
(01-System Architecture: switching Simulation/Live must not change core
logic).

Design: a single `Executor` contract with three implementations sharing the
EXACT contracts from §5/§6:

| Implementation | Notes |
|---|---|
| Simulated executor | maps ExecutionCommand → deterministic fill (paper_validation `simulate_fill` shape — extend it to consume ExecutionCommand fields: same semantics, real contract); no broker; cost model applied |
| Demo executor | MT5 demo account; identical EA boundary, `is_production` flags false; used for cost/slippage evidence before real |
| Real MT5 executor | the EA boundary in §17; the ONLY path with broker credentials for the target account |

- Mode switching is configuration, not code path divergence (per-account
  gate: production executor requires explicit owner authorization + locked
  production RiskConfig — neither exists today).
- Execution Engine state machine (§7), idempotency journal (§8), error
  classification (§15), and observability ids (§18) are layer-agnostic; only
  the adapter layer at the bottom changes.
- The existing paper harness already validates the simulated-executor
  semantics (476 tests) — the abstraction formalizes its interface rather
  than replacing it.

## 21. Open Decisions

Recorded conflicts and decisions REQUIRED before implementation. Obsidian
was NOT modified (task §27).

| # | Decision | Status / Evidence | Needed from |
|---|---|---|---|
| OD-1 | Partial fill: CANCEL-remaining policy (Obsidian 08 §Partial Fill Policy) vs Order Lifecycle "PENDING DECISION" — documents conflict | CONFLICT NOTE; default = 08 policy (valid OPEN + CANCEL remainder + exposure on filled qty); contract supports both | Owner confirm |
| OD-2 | Partial fill effect on position cap / risk-budget bookkeeping (filled qty only) | design default set; needs owner sign-off | Owner |
| OD-3 | `CANCELED` broker order state handling (mapped to REJECTED-equivalent for market commands) | design default; Obsidian lists Canceled conceptually | Owner |
| OD-4 | Order type (MARKET vs LIMIT) and slippage/requote tolerance | Obsidian 05-Entry Execution: PENDING DECISION; design defaults: MARKET, requote budget 2 | Owner |
| OD-5 | Numeric profit threshold (currently > 0 strictly, per paper harness + canonical `running_net_pnl_usd > 0`) | Obsidian 05-Exit Philosophy: PENDING DECISION | Owner |
| OD-6 | Close retry policy + SL-attach retry budget (defaults: close retries bounded 2-3 then emergency; SL attach 3 then emergency close) | Obsidian 06-Exit Execution: PENDING DECISION | Owner |
| OD-7 | Emergency close when position open WITHOUT System SL (proposal: immediate close + ERROR + pause entries) | Obsidian 07-Emergency Protection: numeric triggers/actions PENDING | Owner |
| OD-8 | RISK_GATE canonical payload has no `risk_evaluation_id`; TradePlan carries it (additive, audit-only). Contract extension proposal (payload_specs change) is a SEPARATE decision | no schema change made here | Owner / contract steward |
| OD-9 | TradePlan/command TTL (proposal 30 s; risk context freshness gate is 10 s) | no Obsidian value exists | Owner |
| OD-10 | Command channel protocol (local JSON file / stdin-IPC / localhost HTTP; broker abstraction & message-broker PENDING in Obsidian) | PENDING DECISION (Obsidian 02-System Arch, 04-Broker Abstraction) | Owner |
| OD-11 | `max_simultaneous_positions=1` currently enforces one trade at a time; execution journal must honor it (no new entry until journal shows terminal or reconciled state) | locked config; mechanical consequence, no new decision | — |
| OD-12 | EA restart recovery: journal replay vs broker query ordering (query-first per Obsidian 03) | locked by Obsidian; no new decision | — |

## 22. Implementation Readiness

Verdict: **READY WITH OPEN DECISIONS**.

Ready-to-implement surface (no further design needed):

- `TradePlan` / `ExecutionCommand` / `ExecutionResult` contracts (§4–§6).
- State machine + idempotency journal rules (§7–§8).
- Reconciliation choreography vs broker truth (§9).
- SL verbatim attachment + absent-SL emergency path (§11, subject to OD-7
  owner sign-off default).
- ABC exit execution boundary (§12–§13).
- Freshness/expiry gates (§14).
- Error classification + retry policy (§15–§16).
- EA boundary + security gate (§17–§19).
- Executor interface abstraction (§20).
- Observability lineage + canonical event mapping (§18) — no contract
  modification required except OD-8 (optional).

Not implementable until decisions close: OD-1/OD-2 (partial fill final
behavior), OD-4 (entry type / requote), OD-6 (retry budgets), OD-7
(emergency close authorization), OD-9 (TTL), OD-10 (channel).

Safety posture at implementation start: entry executions ONLY under
paper/demo executor; production executor additionally requires production
RiskConfig (still UNLOCKED) + explicit owner authorization (AGENTS.md §12).

## 23. Next Action

1. Present this report + Open Decisions to the owner (OD-1..OD-10).
2. After decisions: implement `execution/` contracts package (dataclasses +
   JSON schema mirrors, no broker code) with unit tests.
3. Implement simulated executor on the agreed contract (extend paper harness
   path) and replay paper scenarios.
4. Separate task: build the EA (execution boundary) reusing bridge read
   utilities; demo executor first; real executor only after production config
   is locked and owner authorizes.
5. Keep read-only bridge unchanged; it remains the telemetry path.

Authoritative references (this report derives from, without modifying):

- Obsidian 02-Architecture/01, 02-Architecture/05-Authority & Boundaries,
  05-Execution 01–08, 04-Risk 01, 04-Risk 02, 04-Risk 07, 04-Risk 08,
  00-Core 04/05.
- `docs/contracts/canonical-event-contract.md`, `shared/contracts/*`,
  `collector/event_model/*`.
- `risk_engine/*` (SystemRiskGate, RiskConfig PAPER_VALIDATION_V0.1),
  `paper_validation/execution_simulator.py`, `mql5-bridge/src/Bridge.mq5`.
- Validation reports under `docs/validation/risk-engine/`,
  `docs/validation/paper-trading/`, `docs/validation/runtime/`.