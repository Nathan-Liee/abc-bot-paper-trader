# ABC Bot Canonical Event Contract Specification

Status: Approved for Implementation
Version: 1.0.0
Scope: `abc-bot-paper-trader`

## 1. Contract Objective

Establish a single, immutable, versioned event contract that serves as the authoritative data exchange format between:

- MQL5 Bridge
- Python Collector
- Persistence Layer
- Trade Journal
- Reconciliation Service
- Observability
- Analytics Export

Non-goals:

- Trading decisions
- AI logic
- Risk calculations
- Execution logic
- Live trading logic

These are consumers of this contract, not part of the contract itself.

## 2. Canonical Event Envelope

Every event MUST use this envelope. Naked payloads are not permitted.

| Field | Type | Required | Owner | Immutable | Semantics |
|---|---|---|---|---|---|
| `event_id` | UUID v4 | YES | Collector | YES | Globally unique event identity |
| `event_type` | enum string | YES | Producer | YES | One event type from the catalog |
| `ts_event` | ISO8601 UTC | YES | Producer | YES | Business/source event time; precision follows source |
| `ts_collected` | ISO8601 UTC ms | YES | Collector | YES | Collector receipt time |
| `ts_monotonic` | integer ms | YES | Collector | YES | Monotonic processing timestamp for latency calculations |
| `correlation_id` | UUID v4 | CONDITIONAL | Collector | YES | Causal chain identity |
| `trade_id` | UUID v4 | CONDITIONAL | Collector | YES | Trade lifecycle anchor |
| `component` | string | YES | Producer | YES | Originating component |
| `severity` | enum | YES | Producer | YES | `INFO`, `WARN`, `ERROR`, `CRITICAL` |
| `schema_version` | semver string | YES | Collector | YES | Current: `1.0.0` |
| `payload` | object | YES | Producer | YES | Typed by `event_type` |
| `checksum` | string | YES | Collector | YES | SHA-256 of canonical event excluding checksum fields |

### Optional field policy

Required fields MUST exist and MUST NOT be null.

Optional/conditional fields MUST be omitted when not applicable. They MUST NOT be represented as JSON `null`.

For example, a `TICK_RECEIVED` event before any trade exists omits `trade_id` and `correlation_id`.

Unknown extension fields are preserved under `payload._unknown` according to the forward-compatibility policy.

## 3. Event Type Catalog

1. `TICK_RECEIVED`
2. `TRIGGER_DETECTED`
3. `CONTEXT_BUILT`
4. `AI_REQUEST`
5. `AI_RESPONSE`
6. `RISK_GATE`
7. `ORDER_SUBMITTED`
8. `ORDER_ACKNOWLEDGED`
9. `ORDER_FILLED`
10. `POSITION_OPENED`
11. `POSITION_UPDATED`
12. `NET_PROFIT_POSITIVE`
13. `EXIT_SUBMITTED`
14. `POSITION_CLOSED`
15. `RECONCILIATION`
16. `ERROR`
17. `TIMEOUT`

### Persistence

- Audit-critical events: persisted.
- High-frequency events such as `TICK_RECEIVED` and `POSITION_UPDATED`: persisted according to configured sampling/retention policy.
- No event may be deleted or rewritten from the canonical append-only audit stream.

## 4. Payload Contracts

### 4.1 `TICK_RECEIVED`

Purpose: Raw market tick for `XAUUSDc`.

Required payload:

- `symbol`: string
- `bid`: number, USD/oz
- `ask`: number, USD/oz
- `mid`: number, USD/oz
- `spread`: number, USD/oz
- `ts_source`: source timestamp
- `tick_volume`: integer, optional
- `tick_id`: string, optional, only when a unique source-side sequence/identifier can be established

Rules:

- No `trade_id` before a trade exists.
- No `correlation_id` before a trade chain exists.
- Append-only.
- Duplicate timestamps are valid and MUST NOT be deduplicated solely by `ts_event + symbol`.

### 4.2 `TRIGGER_DETECTED`

Purpose: System-owned trigger event. It never contains an AI direction decision.

Required payload:

- `trigger_source`: `TECHNICAL`, `MARKET_EVENT`, `SAFETY_FILTER`, or `HYBRID`
- `trigger_category`
- `trigger_metadata`
- `context_reference`

On this event the System creates:

- `trade_id`
- `correlation_id`

Important: `TRIGGER_DETECTED` is an event, not an `ORDER_SUBMITTED` state transition.

### 4.3 `CONTEXT_BUILT`

Required payload:

- `symbol`
- `m1_context_ref`
- `m5_context_ref`
- `atr_m1`
- `atr_m5` if available
- `derived_features` if available
- `context_snapshot_id`

The snapshot represents the exact market context exposed to AI or a mock signal adapter.

### 4.4 `AI_REQUEST`

Optional until a real AI integration exists.

Required payload:

- `inference_id`
- `request_ts`
- `context_snapshot_id`

Optional:

- `model_ref`

### 4.5 `AI_RESPONSE`

Required payload:

- `inference_id`
- `decision`: `BUY`, `SELL`, or `NO-TRADE`
- `confidence`: 0–1, audit/analytics only
- `reason`: audit/forensics only
- `latency_ms`
- `valid`

Optional:

- `error` when `valid = false`

Authority boundary:

- AI does not output lot.
- AI does not output risk limits.
- AI does not output exposure.
- AI does not output margin instructions.
- AI does not control execution.
- AI does not control exit.
- AI does not control compounding.

Any extra AI fields are ignored by the System.

### 4.6 `RISK_GATE`

System-owned risk decision.

Required payload:

- `gate_result`: `ALLOW` or `REJECT`
- `risk_budget_usd`
- `candidate_lot`
- `final_lot`
- `aggregate_risk_usd`
- `aggregate_exposure_usd`
- `free_margin_usd`

Conditional:

- `rejection_reason` when `gate_result = REJECT`

The Risk Gate remains System-owned.

### 4.7 `ORDER_SUBMITTED`

Required payload:

- `requested_price`
- `requested_volume`
- `direction`
- `order_type`
- `submission_ts`

`requested_volume` MUST reflect System-owned `final_lot`.

Broker order identifiers are recorded only when actually supplied by MT5.

### 4.8 `ORDER_ACKNOWLEDGED`

Required payload:

- `broker_order_id`
- `broker_state`
- `ack_ts`

Broker-owned IDs MUST be recorded verbatim.

### 4.9 `ORDER_FILLED`

Required payload:

- `broker_order_id`
- `broker_deal_id`
- `fill_price`
- `fill_volume`
- `fill_ts`
- `slippage`

### 4.10 `POSITION_OPENED`

Derived from an actual fill.

Required payload:

- `broker_position_id`
- `direction`
- `volume`
- `open_price`
- `open_ts`
- `state = OPEN`

### 4.11 `POSITION_UPDATED`

High-frequency position telemetry. Sampling is permitted.

Required payload:

- `broker_position_id`
- `current_price`
- `running_pnl_usd`
- `running_net_pnl_usd`
- `mfe_usd`
- `mae_usd`
- `spread_current`

### 4.12 `NET_PROFIT_POSITIVE`

Deterministic System-owned exit trigger.

Required payload:

- `broker_position_id`
- `trade_id`
- `running_net_pnl_usd`
- `detection_ts`
- `observed_bid`
- `observed_ask`
- `spread_at_detection`
- `reason = NET_PROFIT_THRESHOLD_CROSSED`

Rules:

- It is produced by the Profit Monitor.
- It MUST NOT wait for AI.
- AI cannot veto, delay, or override it.

### 4.13 `EXIT_SUBMITTED`

Required payload:

- `broker_position_id`
- `requested_close_price`
- `close_volume`
- `submission_ts`

### 4.14 `POSITION_CLOSED`

Required payload:

- `broker_position_id`
- `exit_fill_price`
- `exit_fill_volume`
- `exit_fill_ts`
- `realized_pnl_usd`
- `transaction_cost_usd`
- `net_pnl_usd`
- `exit_reason`
- `final_state = CLOSED`

### 4.15 `RECONCILIATION`

Required payload:

- `reconciliation_id`
- `trigger`
- `local_state`
- `broker_state`
- `mismatch`
- `result`
- `action`
- `ts`

`mismatch_details` is optional when `mismatch = true`.

Valid triggers include:

- `STARTUP`
- `POST_EXECUTION`
- `HEARTBEAT`
- `MISMATCH`

Results include:

- `SYNCED`
- `ADOPTED_BROKER`
- `ESCALATED`

### 4.16 `ERROR`

Required payload:

- `error_code`
- `component`
- `severity`
- `message`

Optional:

- `trade_id`
- `recovery_action`

### 4.17 `TIMEOUT`

Required payload:

- `timeout_code`
- `component`
- `severity`
- `message`

Optional:

- `trade_id`
- `recovery_action`

## 5. Identity & Traceability

System-owned:

- `event_id`
- `trade_id`
- `correlation_id`
- `inference_id`
- `reconciliation_id`
- `schema_version`
- `checksum`

Broker-owned:

- `broker_order_id`
- `broker_deal_id`
- `broker_position_id`
- broker state and broker timestamps

Rules:

- Broker IDs are never fabricated.
- System UUIDs are generated once and never reused.
- `trade_id` anchors the trade lifecycle from trigger to close.
- `correlation_id` links the causal chain.
- IDs are immutable.

## 6. Timestamp Model

Three time domains MUST remain distinct:

1. `ts_event`: business/source event time.
2. `ts_collected`: collector wall-clock receipt time.
3. `ts_monotonic`: monotonic local time for latency measurement.

For MQL5:

- Source timestamps may have seconds precision.
- Millisecond precision MUST NOT be fabricated.
- `DEAL_TIME_MSC` or equivalent millisecond capabilities MUST be verified at implementation time before being relied upon.
- Latency calculations MUST use monotonic timestamps, never source wall-clock timestamps.

`ts_source` is used for source verification on market events such as ticks.

## 7. Event / Trade / Order / Position Lifecycle

These are separate concepts.

### Trade-level event flow

```text
TRIGGER_DETECTED
→ CONTEXT_BUILT
→ AI_REQUEST
→ AI_RESPONSE
→ RISK_GATE
→ ORDER_SUBMITTED
→ ORDER_ACKNOWLEDGED
→ ORDER_FILLED
→ POSITION_OPENED
→ POSITION_UPDATED
→ NET_PROFIT_POSITIVE
→ EXIT_SUBMITTED
→ POSITION_CLOSED
````

Risk rejection:

```text
TRIGGER_DETECTED
→ RISK_GATE(REJECT)
→ trade terminates
```

Order failure without a fill:

```text
ORDER_SUBMITTED
→ ERROR / RECONCILIATION
→ no POSITION_OPENED
```

Position lifecycle:

```text
POSITION_OPENED
→ POSITION_UPDATED
→ POSITION_CLOSED
```

Reconciliation shadow state:

```text
UNKNOWN
→ RECONCILIATION
→ SYNCED / ESCALATED
```

`UNKNOWN` is not a normal trade state.

## 8. Idempotency

Critical broker events use broker-owned identifiers where available:

* `ORDER_ACKNOWLEDGED`: `broker_order_id`
* `ORDER_FILLED`: `broker_deal_id`
* `POSITION_OPENED`: `broker_position_id`
* `POSITION_CLOSED`: `broker_position_id + exit_fill_ts`
* `RECONCILIATION`: `reconciliation_id`

`TICK_RECEIVED` is append-only unless a true source-side unique tick ID is available.

A repeated `ts_event` does not make a tick a duplicate.

## 9. Schema Versioning & Compatibility

Current version: `1.0.0`

Rules:

* Minor additions that are backward compatible may add optional fields.
* Consumers must ignore unknown extension fields.
* Breaking changes require a MAJOR version bump and explicit migration handling.
* Unknown extension fields are preserved under `payload._unknown`.

## 10. Serialization & Units

Serialization:

* JSON
* UTF-8
* `snake_case`
* deterministic key ordering
* no gratuitous whitespace
* UTC timestamps
* explicit numeric units
* optional fields omitted

Unit standards:

| Quantity                               | Unit        |
| -------------------------------------- | ----------- |
| Price / Bid / Ask / Mid / Spread / ATR | USD/oz      |
| Lot / Volume                           | lots        |
| PnL / Cost / Margin / Budget           | USD         |
| Account-denominated PnL                | USC         |
| Latency / Duration                     | ms          |
| Timestamp                              | UTC ISO8601 |
| Confidence                             | ratio 0–1   |

## 11. Checksum & Integrity

Checksum algorithm:

`SHA-256`

Input:

```text
canonical_json(event_without_checksum_fields)
```

Canonicalization:

1. Remove the envelope `checksum`.
2. Remove any nested `checksum` fields.
3. Sort object keys deterministically.
4. Serialize with no insignificant whitespace.
5. Use UTF-8.
6. Use deterministic number encoding.
7. Hash the resulting bytes with SHA-256.
8. Store checksum as a deterministic hex string prefixed with `sha256:`.

A checksum MUST NOT include itself in the input it hashes.

## 12. Event Integrity

Audit-critical events are:

* immutable
* append-only
* traceable
* checksum-protected

Corrections are represented as new adjustment/correction events rather than mutation of historical events.

## 13. State & Race Safeguards

Important race cases:

* acknowledgement vs fill
* fill vs position creation
* positive-net detection vs close fill
* duplicate broker events
* reconnect replay
* late event
* missing broker event

The consumer MUST accept valid out-of-order arrival while preserving immutable history and preventing impossible state transitions.

Examples of invalid transitions:

* `POSITION_CLOSED` → non-terminal state
* `ORDER_FILLED` without a corresponding order context, unless explicitly treated as an orphan requiring reconciliation
* `NET_PROFIT_POSITIVE` without an open position
* duplicate fill for the same broker deal ID

## 14. Implementation-Time Verification

The following remain implementation checks rather than contract blockers:

* MQL5 millisecond timestamp field availability
* tick batching behavior
* optional source tick ID availability
* collector monotonic clock implementation
* identical canonicalization rules when multiple emitters participate

## 15. Approval Status

PASS — CONTRACT READY FOR IMPLEMENTATION.
