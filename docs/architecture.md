# System Architecture

Architecture of the `abc-bot-paper-trader` repository: the paper-trading
validation collector for the ABC Bot project. This document describes the
**implemented** architecture and its boundaries. It does not redesign
anything; it mirrors the current repository state.

## Pipeline (implemented)

```text
HFM MT5
    ↓
MQL5 Read-Only Bridge        telemetry producer (read-only observer)
    ↓
Local JSONL                  append-only JSONL stream (LF-terminated)
    ↓
Python Collector             ingestion / normalization / persistence
    ↓
Canonical Event Model        validated canonical events (17 locked types)
    ↓
SQLite WAL                   append-only audit + derived state
    ↓
Analytics                    CSV / JSONL exports
```

This architecture is fixed and will not be changed.

## Component Boundaries

| Component       | Role                                                            |
| --------------- | -------------------------------------------------------------- |
| MQL5 Bridge     | Read-only telemetry producer. Observes MT5 terminal state and  |
|                 | appends events to the local JSONL channel. Never submits orders|
| Python Collector| Ingestion, normalization, collector-owned enrichment, contract |
|                 | validation, checksum, SQLite WAL persistence, ingestion cursor |
| Event Model     | Canonical event types, payload specs, envelope, checksum       |
| SQLite WAL      | Append-only audit stream + derived state (trades, orders,      |
|                 | positions, snapshots, reconciliation, ingestion cursor)        |
| Analytics       | Deterministic exports (JSONL / CSV) of events, trades,         |
|                 | reconciliations                                                |

## Owned Responsibilities

- **System-owned** (never delegated to AI): risk, lot sizing, exposure,
  margin, execution, exit, compounding.
- **AI** (future component): entry proposal only — `BUY`, `SELL`,
  `NO-TRADE`, `confidence`, `reason`. Confidence and reason are for
  audit/forensics only.
- `NET_PROFIT > 0` is a deterministic system rule and does not wait for AI.

## Safety Boundary

- Live trading is forbidden on this repository.
- Collector defaults are hard-coded read-only
  (`live_trading_enabled = false`, `read_only_mode = true`,
  `demo_execution_allowed = false`).
- No live credentials and no live order capability exist here.
- No order execution happens unless explicitly authorized by a later,
  separate task.
- Safety defaults are never weakened to simplify development.

## Target vs Technical Harness

| Aspect        | Target strategy        | Technical harness         |
| ------------- | ---------------------- | ------------------------- |
| Account       | HFM Cent               | HFM Demo Premium          |
| Symbol        | `XAUUSDc`              | `XAUUSD`                  |

The harness is used only for technical validation of the bridge. Premium
`XAUUSD` results never replace or alter the Cent `XAUUSDc` economics/risk
model.

## Out of Scope (this repository)

AI, risk engine, lot sizing, exposure engine, execution engine, profit
monitor, deterministic exit, compounding, MT5 order submission, and HFM
trading-account integration. They belong to a separate future engine
repository.

## Source of Truth

- `docs/contracts/canonical-event-contract.md` — authoritative event contract
- `docs/contracts/canonical-event-contract-validation.md` — validation rules
- `shared/schemas/canonical-event.schema.json` — machine-checkable contract
- `AGENTS.md` — current task and agent instructions
- `README.md` — repository overview and setup
