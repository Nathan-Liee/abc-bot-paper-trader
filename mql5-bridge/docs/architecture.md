# MQL5 Read-Only Bridge — Architecture

This document is the detailed design companion to `README.md`. It is
not part of the canonical event contract documentation; the contract
(`docs/contracts/`) remains the single source of truth for event
semantics.

## 1. Role and Boundary

The bridge runs inside the MetaTrader 5 terminal as an Expert Advisor
(EA). It is a **read-only telemetry source**: it observes the terminal
and appends raw, canonical-compatible event input to a local JSONL file.
It has no order capability of any kind — no placement, modification,
deletion, or capability gate that could be flipped into an execution
engine.

The bridge deliberately does **not** produce full canonical envelopes:
event identity (`event_id`, `correlation_id`, `trade_id`) and
`checksum` are owned by the collector (task sections 13 and 14).

## 2. Lifecycle

```
INIT
 ↓
VERIFY TERMINAL      (TerminalInfoInteger(TERMINAL_CONNECTED))
 ↓
VERIFY SYMBOL        (SymbolSelect + SymbolInfoTick probe)
 ↓
VERIFY ACCOUNT       (read-only account context; no order capability)
 ↓
INITIALIZE EXPORTER  (FileOpen FILE_READ|FILE_WRITE, seek to end)
 ↓
EMIT HEALTH/START    (HEARTBEAT status=STARTED)
 ↓
TICK COLLECTION      (OnTick, every tick, never deduplicated)
 ↓
TRADE TRANSACTION TELEMETRY (OnTradeTransaction, telemetry only)
 ↓
POSITION/ORDER SNAPSHOT     (periodic, read-only)
 ↓
HEALTH HEARTBEAT            (periodic)
 ↓
DEINIT               (flush, final HEARTBEAT status=STOPPED)
```

Failure is bounded: symbol or terminal problems put the bridge into a
**degraded read-only state** (heartbeat continues, ERROR/TIMEOUT
telemetry emitted), never into any execution state.

## 3. Raw Line Format

One JSON object per line, LF-terminated, strictly ASCII encoding
(non-ASCII escaped as `\uXXXX`, therefore byte-compatible with UTF-8):

```json
{"event_type":"TICK_RECEIVED","source":"mql5","ts_bridge":"2026-08-14T09:00:00Z","payload":{...}}
```

| Field | Meaning |
|-------|---------|
| `event_type` | Canonical type name where the contract defines one; bridge-internal name otherwise (see below). |
| `source` | Constant `"mql5"`. |
| `ts_bridge` | Bridge observation time (broker server time, ISO 8601 UTC seconds). Never fabricated precision. |
| `payload` | Contract payload fields verbatim where a canonical type exists. |

### Event types produced

**Canonical (collector maps 1:1 to envelopes):**

| event_type | Payload fields (contract-compliant) |
|------------|-------------------------------------|
| `TICK_RECEIVED` | `symbol`, `bid`, `ask`, `mid` (= (bid+ask)/2), `spread` (= ask−bid), `ts_source`, `tick_volume` (only when > 0) |
| `ORDER_ACKNOWLEDGED` | `broker_order_id` (verbatim ticket), `broker_state` (verbatim), `ack_ts` |
| `ORDER_FILLED` | `broker_order_id`, `broker_deal_id`, `fill_price`, `fill_volume`, `slippage`, `fill_ts` |
| `POSITION_OPENED` | `broker_position_id`, `direction`, `volume`, `open_price`, `open_ts`, `state` ("OPEN") |
| `POSITION_UPDATED` | `broker_position_id`, `current_price`, `running_pnl_usd`, `running_net_pnl_usd`, `mfe_usd`, `mae_usd`, `spread_current` |
| `POSITION_CLOSED` | `broker_position_id`, `exit_fill_price`, `exit_fill_volume`, `exit_fill_ts`, `realized_pnl_usd`, `transaction_cost_usd`, `net_pnl_usd`, `exit_reason`, `final_state` ("CLOSED") |
| `ERROR` | `error_code`, `component` ("mql5-bridge"), `severity`, `message` |
| `TIMEOUT` | `timeout_code`, `component`, `severity`, `message` |

**Bridge-internal (non-canonical evidence/health; collector consumes or ignores):**

| event_type | Purpose |
|------------|---------|
| `POSITION_SNAPSHOT` | Read-only open-position evidence for collector reconciliation. |
| `ORDER_SNAPSHOT` | Read-only pending-order evidence. |
| `HEARTBEAT` | Health telemetry: `status` (STARTED/RUNNING/DEGRADED/STOPPED), terminal/symbol availability, last tick, exporter status, last successful write, error count, counters. |

Never produced by the bridge (collector/system-owned):
`TRIGGER_DETECTED`, `CONTEXT_BUILT`, `AI_REQUEST`, `AI_RESPONSE`,
`RISK_GATE`, `NET_PROFIT_POSITIVE`, `EXIT_SUBMITTED`.

## 4. Timestamp Handling

* **Source time** — `ts_source` in `TICK_RECEIVED` is the tick's server
  time (`MqlTick.time`, seconds). The bridge never promotes seconds to
  fake milliseconds.
* **Execution times** — `ack_ts`, `fill_ts`, `open_ts`, `exit_fill_ts`
  come from `ORDER_TIME_SETUP` / `DEAL_TIME` (server time, seconds).
* **Bridge time** — `ts_bridge` is `TimeTradeServer()` at emission
  (seconds).
* **Monotonic time** — the MQL5 environment has no contract-aligned
  monotonic clock guarantee; the bridge therefore emits **no**
  `ts_monotonic` value. Monotonic latency measurement belongs to the
  collector, which fills `ts_monotonic` during canonicalization.

## 5. Checksum Decision

**The bridge emits raw payloads without checksums.** Rationale:

1. Contract checksum = `sha256:` over a *canonical serialization*
   (sorted keys, exact separators) defined and unit-tested in Python
   (`collector.event_model.checksum`).
2. Duplicating that serialization in MQL5 risks silent divergence;
   contract compatibility is only guaranteed if there is a single
   implementation of the checksum algorithm.
3. The collector adapter performs canonicalization + checksum at
   ingestion; compatibility is proven by the Python test suite
   (`tests/mql5/test_bridge_events.py`), which canonicalizes bridge
   raw lines through `collector.event_model` and validates them against
   `shared/schemas/canonical-event.schema.json`.

## 6. JSONL Transport

* **Append-only** — every open uses `FILE_READ|FILE_WRITE` and seeks to
  `SEEK_END`. A corrupt/unreadable file is renamed to
  `<name>.corrupted.<ts>` (historical stream preserved) and a fresh
  file is started.
* **Atomic line write** — a complete line (one JSON object + LF) is
  written with a single `FileWriteString` call.
* **Flush policy** — `FileFlush` after `InpFlushLines` writes
  (default 100), at every heartbeat, and in `OnDeinit`.
* **Path** — `InpEventFile`, default `data\raw\mql5_bridge_events.jsonl`
  relative to the terminal's `MQL5\Files` directory (readable by the
  collector adapter on the same host). Generated data is git-ignored
  (`data/raw/**`).
* **Concurrency** — opened with `FILE_SHARE_READ|FILE_SHARE_WRITE` so
  the collector can tail the file while the bridge is running.

## 7. Failure Handling

| Failure | Bridge behavior |
|---------|-----------------|
| File write failure | Not dropped silently: local `Print`, error counter incremented, bounded reopen (`InpMaxReopenAttempts`), degraded exporter status in heartbeat. No order action. |
| Symbol unavailable | `ERROR` telemetry + degraded state; heartbeat continues. |
| Terminal disconnected | One `TIMEOUT` (`TERMINAL_DISCONNECTED`) per episode; `ERROR` (`TERMINAL_RECONNECTED`) on recovery. |
| File/IO corruption | Never overwrites history (rename + fresh file), failure flagged in heartbeat. |
| Duplicate timestamps | Ticks are never deduplicated; every `OnTick` is appended. |

## 8. Read-Only Verification

The bridge references only read APIs: `SymbolInfoTick`, `SymbolInfoDouble`,
`SymbolInfoInteger`, `PositionGet*`, `OrderGet*`, `OrdersTotal`,
`PositionsTotal`, `HistoryDeal*`, `HistoryOrder*`, `AccountInfo*`,
`TerminalInfoInteger`, `File*`, `TimeTradeServer`, `GetTickCount`.
Static verification is enforced by `tests/mql5/test_bridge_safety.py`,
which scans the source tree and fails on any execution-related token
such as `OrderSend`, `OrderModify`, `OrderDelete`, `MqlTradeRequest`,
`OrderCalc*`, `CTrade`, or `CAccountStopout`.

## 9. Testing Without a Live Account

* **Static safety scan** — `tests/mql5/test_bridge_safety.py`.
* **Contract compatibility** — `tests/mql5/test_bridge_events.py`
  canonicalizes representative bridge raw lines and validates them
  against the canonical JSON Schema and the typed event model
  (including duplicate-timestamp ticks and malformed-event rejection).
* **MQL5 compile** — requires MetaEditor (`metaeditor64.exe
  /compile:...`). Not available in this development environment; the
  code is written conservatively against the standard MQL5 API.
* **Strategy Tester** — when a terminal with the bridge installed is
  available, a tester run generates synthetic ticks and transactions,
  exercising `OnTick` / `OnTradeTransaction` without any live account.

## 10. Known Limitations (by design)

* `mfe_usd` / `mae_usd` in `POSITION_UPDATED` are emitted as `0.0`
  (bridge lacks trade-level extremum history); the collector owns
  trade-level state.
* `slippage` in `ORDER_FILLED` is an approximation from the current
  market at callback time (no broker request price for market orders).
* `exit_reason` in `POSITION_CLOSED` is the deal comment verbatim, or
  `"UNKNOWN"`; the collector may normalize it.
* No reconciliation decisions are made by the bridge; snapshot
  evidence is the input for collector-side authoritative
  reconciliation.
* `tick_id` is never emitted: MQL5 provides no source-side unique tick
  identifier, and fabricating one is forbidden.