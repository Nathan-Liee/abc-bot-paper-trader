# ABC Bot Canonical Event Contract Validation & Correction Report

Status: PASS — CONTRACT READY FOR IMPLEMENTATION

## 1. Scope

Focused validation was performed on:

- Optional field / null semantics
- Event lifecycle vs state machine
- MQL5 timestamp semantics
- Checksum canonicalization
- Tick event idempotency

No redesign outside these areas was approved.

## 2. Optional Field / Null Semantics

Final rule:

- Required fields MUST exist and MUST NOT be null.
- Optional fields MUST be omitted when not applicable.
- `null` is not used as a substitute for absence.
- Unknown extension fields are preserved under `payload._unknown`.

Examples before trigger omit both `trade_id` and `correlation_id`.

## 3. Event Lifecycle vs State Machine

The contract separates:

- Event flow
- Trade lifecycle
- Order state
- Position state
- Reconciliation shadow state

Final trade event flow:

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

Important correction:

`TRIGGER_DETECTED` is not an `ORDER_SUBMITTED` state.

Risk rejection terminates the trade path without creating a position.

An order that never fills must not create `POSITION_OPENED`.

`UNKNOWN` exists only for state-integrity/reconciliation handling.

## 4. MQL5 Timestamp Semantics

Source timestamps may have seconds or milliseconds precision depending on the source field.

Rules:

* Do not fabricate millisecond precision from second-based MQL5 fields.
* Record source/broker time for audit/sequencing.
* Use collector monotonic time for latency deltas.
* Keep source wall-clock, collector wall-clock, and monotonic timing domains separate.
* Verify `DEAL_TIME_MSC` or equivalent millisecond fields during implementation before relying on them.

Latency is calculated from monotonic timestamps only.

## 5. Checksum Canonicalization

Final rule:

```text
checksum = SHA256(canonical_json(event_without_checksum_fields))
```

Canonical JSON requirements:

* deterministic key ordering
* no insignificant whitespace
* UTF-8
* deterministic numeric representation
* checksum fields excluded from the input
* SHA-256
* deterministic output representation

The checksum cannot hash itself.

## 6. Tick Event Idempotency

`TICK_RECEIVED` is append-only.

Do not deduplicate ticks solely by:

* `ts_event`
* `symbol`
* timestamp combinations without a true source-side identity

If the bridge can provide a valid source-side unique tick ID or sequence, that may be used as an optional deduplication key.

Otherwise, duplicate timestamps are accepted as distinct possible ticks.

## 7. Corrected Contract Examples

All examples must follow the optional-field rule:

* no `correlation_id: null`
* no `trade_id: null`

Before a trade exists, those keys are omitted entirely.

`checksum` is always calculated after removing all checksum fields from the object being hashed.

## 8. Cross-Document Consistency

The corrected contract remains consistent with:

* Requirements
* System Architecture
* AI Decision Engine
* Risk & Compounding
* Execution
* Paper-Trading Measurement Specification
* Collector Technical Design
* Implementation Foundation

No authority boundary changed.

## 9. Authority Boundary Validation

Confirmed:

* AI = Entry Proposal only
* BUY/SELL/NO-TRADE = AI decision domain
* confidence = audit/analytics
* reason = audit/forensics
* Risk Gate = System-owned
* Lot/Sizing = System-owned
* Exposure = System-owned
* Execution = System-owned
* Exit = System-owned
* `NET_PROFIT > 0` = deterministic System event
* Compounding = System-owned

No authority leakage found.

## 10. Broker vs System Ownership

Broker-owned values:

* broker order ID
* broker deal ID
* broker position ID
* broker state
* broker timestamps

System-owned values:

* event ID
* trade ID
* correlation ID
* inference ID
* reconciliation ID
* schema version
* checksum
* collector timestamps

Broker IDs must never be fabricated.

## 11. Remaining Implementation-Time Verification

The implementation team must verify:

1. millisecond broker timestamp capability
2. tick batching behavior
3. optional source tick sequence/ID availability
4. collector monotonic clock implementation
5. identical canonicalization rules when multiple emitters participate

These checks do not block implementation of the contract itself.

## 12. Final Verdict

PASS — CONTRACT READY FOR IMPLEMENTATION.

No unresolved contract contradiction remains inside the five reviewed areas.
