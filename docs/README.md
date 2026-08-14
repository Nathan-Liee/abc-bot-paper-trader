# Documentation foundation

Index of repository documentation.

## Baseline specifications (external references)

Implementation work in this repository must follow:

1. **Implementation Foundation Specification** (approved)
2. **Paper-Trading Collector Technical Design** (approved)
3. **HFM MT5 Paper-Trading Measurement Specification** (approved)

The specifications drive later milestones; bootstrap deliberately
implemented none of them.

## Remaining implementation steps (later milestones, not this repo's bootstrap)

1. Define the canonical event contract in `shared/contracts` + final
   `shared/schemas/event.schema.json` — **implemented**.
2. Implement MQL5 bridge (`mql5-bridge/src`) — read-only observer that
   emits events to the local IPC / JSONL channel.
3. Implement collector adapters (`collector/adapters`) reading the
   channel — **implemented** (JSONL ingestion).
4. Implement event model + journal (`collector/event_model`,
   `collector/journal`).
5. Implement SQLite WAL persistence (`collector/persistence`) — final
   schema decided by the technical design — **implemented**.
6. Implement observability hooks (`collector/observability`).
7. Wire configuration loader (`collector/config`) against the templates.

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