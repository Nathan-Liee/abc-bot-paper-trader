# ABC Bot Paper Trader — Persistent Agent Context

Persistent context for all coding agents working on the ABC Bot project.

---

## 1. Project Identity

- **Project:** ABC Bot
- **Repository:** `abc-bot-paper-trader`
- This repository is dedicated **paper-trading validation infrastructure**.
- This is **NOT** the final live trading engine repository.

## 2. Current Objective

```
HFM MT5
→ MQL5 Read-Only Bridge
→ JSONL
→ Python Collector
→ Canonical Event Model
→ SQLite WAL
→ Analytics
```

The end goal is to collect **empirical evidence** before any final decision on:

- lot sizing
- adverse move basis
- spread filter
- slippage threshold
- latency budget
- position behavior
- AI model/provider

## 3. Current Implementation Status

```
Repository Bootstrap                 ✅
Canonical Event Contract             ✅
Event Model + JSON Schema            ✅
SQLite WAL Persistence               ✅
MQL5 Read-Only Bridge                ✅
MQL5 Compile                         ✅
MQL5 Runtime Technical Validation   ✅
JSONL Export                         ✅
JSONL Ingestion Adapter              🔄 CURRENT
Reconciliation                       ⏳
Phase A Data Collection              ⏳
Paper Trading ≥200 trades            ⏳
Empirical Analysis                   ⏳
Risk/Lot Finalization                ⏳
AI Benchmark                         ⏳
AI Integration                       ⏳
Live Trading                         ❌ FORBIDDEN
```

Notes:

- The MQL5 Bridge has been technically validated using **HFM Demo Premium
  `XAUUSD`** as a harness.
- The target ABC Bot strategy remains:

```
HFM Cent
XAUUSDc
```

- Do **not** change the `XAUUSDc` target just because the technical harness
  uses `XAUUSD`.

## 4. Current Task

```
CURRENT TASK:
Collector JSONL Ingestion Adapter
```

Flow:

```
MQL5 JSONL
→ File Reader
→ Parse
→ Normalize
→ Collector-owned Enrichment
→ Canonical Event Builder
→ Schema Validation
→ Checksum
→ SQLite Persistence
→ Cursor
```

Agents must **not** jump ahead to:

- Reconciliation
- AI
- Risk
- Lot sizing
- Execution
- Exit
- Paper trading

...before the current task is finished and validated.

## 5. Architecture Rules

```
HFM MT5
    ↓
MQL5 Read-Only Bridge
    ↓
Local JSONL
    ↓
Python Collector
    ↓
Canonical Event Model
    ↓
SQLite WAL
    ↓
Analytics
```

Separation of concerns:

- **MQL5** = read-only telemetry producer
- **Python** = normalization / collector / persistence
- **Risk** = System-owned
- **Lot** = System-owned
- **Execution** = System-owned
- **Exit** = System-owned
- **AI** = Entry Proposal only

## 6. AI Authority Boundary

AI may only produce:

```
BUY
SELL
NO-TRADE
confidence
reason
```

AI must **not** control:

```
lot
risk
exposure
margin
execution
exit
compounding
```

`NET_PROFIT > 0` is a **deterministic system rule** and does not wait for AI.

## 7. Safety Rules

Mandatory:

```
live_trading_enabled = false
read_only_mode = true
demo execution = disabled by default
```

This repository must never acquire live trading capability.

Do **not**:

- send live orders
- send demo orders without an explicit task
- use live credentials
- change safety defaults to make development easier
- execute orders unless explicitly authorized by a later, separate task

## 8. Broker / Instrument

Target:

```
Broker:        HFM
Account:       Cent
Platform:      MT5
Symbol:        XAUUSDc
Contract Size: 1 oz/lot
Min Lot:       0.01
Lot Step:      0.01
```

The technical harness may use:

```
HFM Demo Premium
XAUUSD
```

but Premium results must **not** be used to alter the economics/risk model of
Cent `XAUUSDc`.

## 9. Important Event Contract Rules

- The 17 canonical event types are **locked**.
- Required fields must not be null.
- Optional fields are omitted.
- `TRIGGER_DETECTED` is not `ORDER_SUBMITTED`.
- Tick events are append-only.
- Do not dedupe ticks by timestamp alone.
- Broker IDs must not be fabricated.
- `ts_monotonic` comes from the collector.
- Do not fabricate timestamp precision.
- Checksum uses SHA-256 of the canonical event without the checksum field.
- Historical audit events are append-only.

## 10. Development Discipline

Coding agents **MUST**:

1. Read `AGENTS.md`.
2. Read the contract before changing event-related code.
3. Work only within this repository.
4. Make the smallest possible change.
5. Not jump to the next milestone.
6. Run test / lint / type-check after every change.
7. Make focused commits.
8. Not force push.
9. Report blockers instead of inventing workarounds.

## 11. Source of Truth

Authoritative references (in priority order):

- `docs/contracts/canonical-event-contract.md` — authoritative event contract
- `docs/contracts/canonical-event-contract-validation.md` — validation rules
- `shared/schemas/canonical-event.schema.json` — machine-checkable contract
- `docs/architecture.md` — system architecture and boundaries
- `README.md` — repository overview and setup
- source code — implemented behavior
- tests — executable behavior specification

`AGENTS.md` is guidance/instructions for coding agents. It is **not** a
replacement for the authoritative contracts. Do not duplicate full event
contract contents into this file.

## 12. Required Validation

The baseline project must keep satisfying:

```
pytest
ruff check .
ruff format --check .
mypy collector shared
```

Every task must keep existing tests PASSING.

## 13. Workflow

Official order:

```
Documentation
→ Technical Decision
→ Repository Foundation
→ Event Contract
→ Event Model
→ Persistence
→ MQL5 Bridge
→ JSONL Ingestion
→ Reconciliation
→ Phase A Data Collection
→ Paper Trading
→ Empirical Analysis
→ Finalize Risk/Lot
→ AI Benchmark
→ AI Integration
```

Do not skip stages.

## 14. Hermes vs Coding Agent

```
Hermes:
- reasoning
- research
- audit
- alignment
- documentation
- technical decision support

Coding Agent:
- source code
- implementation
- tests
- debugging
- repository changes
```

Hermes is **not** a coding agent for this repository.

## 15. Scope Boundary

`abc-bot-paper-trader` focuses on:

- telemetry
- paper-trading infrastructure
- event contracts
- persistence
- reconciliation
- measurement
- analytics

A future trading engine may live in a separate repository.

## 16. Agent Behavior

If a new task conflicts with:

- the canonical contract
- the authority boundary
- the safety boundary
- the current phase
- the repository scope

...the agent must **STOP** and report the conflict.

Do not change locked decisions based purely on implementation preference.