# Documentation foundation

Index of repository documentation.

## Repository documentation

- `docs/architecture.md` — system architecture and boundaries
- `docs/contracts/canonical-event-contract.md` — authoritative event contract
- `docs/contracts/canonical-event-contract-validation.md` — validation rules
- `shared/schemas/canonical-event.schema.json` — machine-checkable contract
- `../AGENTS.md` — persistent context for coding agents

## Baseline specifications (external references)

Implementation work in this repository must follow:

1. **Implementation Foundation Specification** (approved)
2. **Paper-Trading Collector Technical Design** (approved)
3. **HFM MT5 Paper-Trading Measurement Specification** (approved)

## Implementation status (remaining milestones)

1. Canonical event contract in `shared/contracts` +
   `shared/schemas/event.schema.json` — **implemented**.
2. MQL5 bridge (`mql5-bridge/src`) — read-only observer that emits events
   to the local IPC / JSONL channel — **implemented**.
3. Collector adapters (`collector/adapters`) reading the channel —
   **implemented** (JSONL ingestion).
4. Event model + journal (`collector/event_model`, `collector/journal`).
5. SQLite WAL persistence (`collector/persistence`) — final schema decided
   by the technical design — **implemented**.
6. Observability hooks (`collector/observability`).
7. Configuration loader (`collector/config`) against the templates.

## JSONL ingestion adapter (implemented)

The `collector/adapters` package reads the MQL5 bridge's append-only
JSONL stream:

* `JsonlFileReader` — incremental tail reader with byte-accurate cursor
  accounting, partial-line holding, and rotation detection.
* `normalize.py` — raw bridge line classification (canonical / internal /
  unknown) and payload normalization preserving unknown fields verbatim.
* `pipeline.py` — READ -> NORMALIZE -> VALIDATE -> PERSIST; canonical
  out-of-band events are validated and persisted; trade-path events
  without orchestrator identity are counted (identity pending) and left
  raw for future reconciliation.
* `runner.py` — bounded-poll loop with cooperative shutdown.
* `replay.py` — deterministic replay into a fresh SQLite DB for verification.
* Durable per-source cursor in `ingestion_cursor` (persistence migration
  2); event row + cursor advance are committed in one transaction.

## Out of scope forever

AI, Risk Engine, Lot Sizing, Exposure Engine, Execution Engine, Profit
Monitor, Deterministic Exit, Compounding, MT5 order submission, HFM
integration, and **live trading** are all forbidden on this repository.
They belong to a separate future engine repository.