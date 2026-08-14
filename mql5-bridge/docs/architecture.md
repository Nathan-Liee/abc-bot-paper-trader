# MQL5 Bridge — placeholder architecture

> Status: **placeholder only.** No `.mq5` / `.mqh` file exists and none
> should be created during bootstrap. The notes below record the agreed
> direction; the bridge implementation is a later milestone that will be
> driven by the approved specifications.

## Role

The MQL5 bridge is the single MT5-facing component. It runs inside the
HFM Demo MT5 terminal and observes market data events for the symbols and
timeframes defined by the measurement specification.

## Data flow (fixed)

```text
HFM Demo MT5 terminal
          |
          v
MQL5 Bridge (observer, read-only)
          |
          v
Local IPC / JSONL channel
          |
          v
Python Collector (this repository)
```

## Non-negotiable properties

- **Read-only**: the bridge must never place, modify, or cancel orders
  on the terminal, not even on demo accounts (`demo_execution_allowed`
  stays `False`).
- **Emit only**: the bridge only emits events (prices, ticks, bars /
  useful market data per spec). It never receives execution commands.
- **Credential-free**: connection/account credentials live in the
  terminal itself and are never exchanged with this repository.

## Event emission (planned)

- Events are serialized as JSONL records on the local IPC channel.
- The record shape follows the canonical event contract
  (`shared/contracts`, schema placeholder in `shared/schemas`).
- The contract fields are **not** invented at bootstrap time.

## Open items (later milestones)

- Exact event set per the HFM MT5 Paper-Trading Measurement Specification.
- IPC transport details (named pipe / local socket / file drop) per the
  Paper-Trading Collector Technical Design.
- Validation rules and back-pressure handling between bridge and collector.