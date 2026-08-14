# mql5-bridge — Read-Only Telemetry Bridge

MQL5 Expert Advisor for the **abc-bot-paper-trader** project. Runs in
the MetaTrader 5 terminal and exports market/execution **telemetry** to
a local JSONL event stream matching the raw input requirements of the
Canonical Event Contract v1.0.0.

> **READ-ONLY GUARANTEE.** This bridge never places, modifies, or
> deletes orders — in demo or live mode. It contains no order-send API
> and no capability gate that could turn it into an execution engine.
> Enforcement: `tests/mql5/test_bridge_safety.py` fails the build if
> any execution token appears in the source tree.

## Purpose

Observe `XAUUSDc` ticks, terminal trade transactions, and
position/order state inside MT5 and append raw canonical-compatible
JSONL telemetry that a collector adapter (next phase) canonicalizes
into full contract events with identity and checksums. The bridge makes
no trading, risk, or reconciliation decisions.

## Installation / Attachment Model

1. Copy `src/` into the terminal's data folder:
   `<Terminal>\MQL5\Experts\abc-bot\` (keep the `src` sub-tree intact).
2. In MetaEditor, open `src\Bridge.mq5` and compile (F7).
3. In MT5, attach `Bridge` to the `XAUUSDc` chart (or any chart —
   the symbol input controls monitoring). Enable **Algo Trading** for
   the EA to receive ticks and trade transactions.
4. Check inputs on attach:

| Input | Default | Meaning |
|-------|---------|---------|
| `InpSymbol` | `XAUUSDc` | Single configured symbol (never hard-coded elsewhere). |
| `InpEventFile` | `data\raw\mql5_bridge_events.jsonl` | Output path relative to `MQL5\Files`. |
| `InpHeartbeatSec` | `5` | Heartbeat interval. |
| `InpSnapshotSec` | `30` | Position/order snapshot interval. |
| `InpPositionUpdateSec` | `5` | `POSITION_UPDATED` telemetry interval. |
| `InpFlushLines` | `100` | File flush cadence. |
| `InpMaxReopenAttempts` | `3` | Bounded write-failure retries. |

Output is written to `<Terminal>\MQL5\Files\data\raw\mql5_bridge_events.jsonl`
by default. Generated data is git-ignored (`data/raw/**`).

## Event Types Produced

Canonical-compatible raw input (payload fields match the contract
exactly; identity + checksum are added by the collector):

* `TICK_RECEIVED` — every tick, never deduplicated (mid = (bid+ask)/2,
  spread = ask−bid).
* `ORDER_ACKNOWLEDGED` / `ORDER_FILLED` — from terminal trade
  transactions (broker ids verbatim).
* `POSITION_OPENED` / `POSITION_UPDATED` / `POSITION_CLOSED`.
* `ERROR` / `TIMEOUT` — bridge faults and disconnection episodes.

Bridge-internal types (evidence/health, collector consumes):

* `POSITION_SNAPSHOT`, `ORDER_SNAPSHOT` — read-only evidence for
  collector-side reconciliation (the bridge never reconciles).
* `HEARTBEAT` — `STARTED` on init, `RUNNING`/`DEGRADED` periodically,
  `STOPPED` on deinit; exposes terminal/symbol availability, last tick,
  exporter status, last successful write, error count.

Never produced here: `TRIGGER_DETECTED`, `CONTEXT_BUILT`, `AI_REQUEST`,
`AI_RESPONSE`, `RISK_GATE`, `NET_PROFIT_POSITIVE`, `EXIT_SUBMITTED`
(collector/system-owned).

## No Execution Capability

* No `OrderSend` / `OrderSendAsync` / `OrderModify` / `OrderDelete`,
  no trade-request structs, no `OrderCalc*`, no `CTrade`.
* The only trade APIs used are the read side: `HistoryDeal*`,
  `HistoryOrder*`, `PositionGet*`, `OrderGet*`, `OrdersTotal`,
  `PositionsTotal`.
* `OnTradeTransaction` is telemetry-only and never triggers an action.

## Timestamp Limitations

* `ts_source` / `ack_ts` / `fill_ts` / `open_ts` / `exit_fill_ts` are
  broker server times at second precision (real values; seconds are
  never promoted to fake milliseconds).
* No `ts_monotonic` is emitted — the MQL5 environment provides no
  contract-aligned monotonic clock; the collector owns monotonic
  latency measurement and fills `ts_monotonic` at canonicalization.

## Checksum Decision

The bridge emits **raw JSONL lines without checksums**. Contract
checksums require Python's canonical serialization; duplicating it in
MQL5 would risk divergence. The collector canonicalizes + checksums at
ingestion. See `docs/ARCHITECTURE.md` for the full rationale.

## Limitations

* `mfe_usd`/`mae_usd` emitted as `0.0` (no trade-level extremum
  history in the bridge; collector owns trade state).
* `slippage` is approximate (market-price based at callback time).
* `exit_reason` is the deal comment verbatim or `"UNKNOWN"`.
* No file rotation yet (append-only, single file per run).
* Reconciliation decisions are never made by the bridge.

## Testing

Without a live account:

* `tests/mql5/test_bridge_safety.py` — static read-only verification.
* `tests/mql5/test_bridge_events.py` — canonicalization + JSON Schema
  compatibility of bridge output, duplicate-timestamp ticks,
  malformed-event rejection, append semantics.
* Compile: `metaeditor64.exe /compile:"<path>\src\Bridge.mq5"` (needs
  MT5 MetaEditor).
* Strategy Tester: synthetic ticks/transactions exercise the full
  lifecycle without any live account.

See `docs/ARCHITECTURE.md` for detailed design, raw line format, and
failure handling.