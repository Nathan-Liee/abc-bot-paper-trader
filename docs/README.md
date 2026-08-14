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
   `shared/schemas/event.schema.json`.
2. Implement MQL5 bridge (`mql5-bridge/src`) — read-only observer that
   emits events to the local IPC / JSONL channel.
3. Implement collector adapters (`collector/adapters`) reading the
   channel.
4. Implement event model + journal (`collector/event_model`,
   `collector/journal`).
5. Implement SQLite WAL persistence (`collector/persistence`) — final
   schema decided by the technical design.
6. Implement observability hooks (`collector/observability`).
7. Wire configuration loader (`collector/config`) against the templates.

## Out of scope forever

AI, Risk Engine, Lot Sizing, Exposure Engine, Execution Engine, Profit
Monitor, Deterministic Exit, Compounding, MT5 order submission, HFM
integration, and **live trading** are all forbidden on this repository.
They belong to a separate future engine repository.