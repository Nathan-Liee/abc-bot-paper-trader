# HFM Cent XAUUSDc Read-Only Runtime Observation

Report date: 2026-08-17 · Evidence window: 09:35:32–09:36:33 +07:00, active market
Verdict: **READ-ONLY XAUUSDc EVIDENCE COMPLETE**

## 1. Environment

| Item | Value |
| --- | --- |
| Terminal | MetaTrader 5 x64, build 6111 (started 06:25–06:27 +07, terminal data `D0E8209F77C8CF37AD8BF550E51FF075`) |
| Server / company | HFMarketsGlobal-Live19 · HF Markets (SV) Ltd. |
| Account login | 229105805 (`#nath xau - Dika Pramudita`) |
| Account type | REAL live (HFM Cent), account currency `USC` (USD Cent), hedging margin mode |
| Symbol | `XAUUSDc` — "Gold Spot (Cent)", instrument path `Metals & Energies\Spot\Gold & Silver Cent\XAUUSDc` |
| Access mechanism | Official `MetaTrader5` Python IPC package (5.0.6090) against the running terminal — **account_info / symbol_info / symbol_info_tick only** |

## 2. Safety Boundary

- Read-only only: `mt5.account_info()`, `mt5.symbol_info()`, `mt5.symbol_info_tick()`.
- No `order_send`, `order_calc_*`, `order_check`, `position_*`, `order_modify/delete`,
  no SL/TP/leverage/symbol mutation, no pending orders, no account changes.
- Static guard in the observation script failed-fast if any trade-capable call
  existed in its source; the script ran from the temp directory
  (`AppData\Local\Temp\opencode`) and is **not committed** to the repository.
- No strategy, AI engine, or benchmark executed. Existing positions: none opened/closed.

## 3. Account State

| Field | Value | Notes |
| --- | --- | --- |
| balance | 0.25 USC | nominal, recorded as observed only — NOT a config input |
| equity | 0.25 USC | nominal, recorded as observed only |
| margin | 0.0 USC | no open positions |
| free_margin | 0.25 USC | equals balance; no margin in use |
| margin_level | 0.0 | 0 when no positions (per broker convention) |
| leverage | 2000:1 | actual account leverage — direct evidence for the `leverage` fallback |
| margin_so_call / margin_so_so | 50.0 / 20.0 (%) | broker stop-out call level / stop-out level |
| currency | USC | Cent account |
| margin_mode | 2 (hedging) | `SYMBOL_MARGIN_MODE`-family: hedging enabled, `fifo_close=false` |
| trade_mode | 2 (REAL) | live account; observed values used for mechanics, not decisions |

> Note: balance/equity are nominal runtime snapshots. Per task §21 they are NOT
> used to set risk %, exposure, or budget.

## 4. XAUUSDc Symbol Specification

| Symbol field | Value | Meaning |
| --- | --- | --- |
| `point` | 0.01 | 1 point = $0.01 quote |
| `digits` | 2 | price precision |
| `trade_tick_size` | 0.01 | = point |
| `trade_tick_value` | 1.0 (USC) | per 0.01 move per 1.0 lot |
| `trade_contract_size` | 1.0 | 1.0 lot = 1.0 oz (Cent mini) |
| `volume_min` | 0.01 | min lot |
| `volume_max` | 1000.0 | max lot |
| `volume_step` | 0.01 | lot step |
| `volume_limit` | 6000.0 | max aggregate volume |
| `trade_mode` | 4 (FULL) | full access |
| `trade_calc_mode` | 4 | `SYMBOL_TRADE_CALC_MODE_CFD_LEVERAGE` |
| `trade_stops_level` | 0 | no stop distance restriction (points) |
| `trade_freeze_level` | 8 | freeze level in points (modify window) |
| currency_base/profit/margin | USD | settlement in USD(c) |
| swap_long / swap_short | -75.25 / 0.0 | per-lot swap (informational; SCALP, not cost input) |

## 5. Spread Observations

61 samples @ ~1 s during an active market. Sample points:

| ts (+07) | bid | ask | spread_points | spread_price (USC) |
| --- | --- | --- | --- | --- |
| 09:35:32 | 4370.84 | 4371.20 | 36 | 0.36 |
| 09:35:45 | 4369.45 | 4369.81 | 36 | 0.36 |
| 09:35:57 | 4368.68 | 4369.04 | 36 | 0.36 |
| 09:36:15 | 4368.70 | 4369.06 | 36 | 0.36 |
| 09:36:33 | 4368.44 | 4368.80 | 36 | 0.36 |
| (representative; full 61 in collection artifact) | | | | |

One outbound sample read 34 points; the rest 36. Spread is floating (`spread_float = true`).

## 6. Spread Statistics

| Metric | points | price (USC) |
| --- | --- | --- |
| sample_count | 61 | 61 |
| min | 34 | 0.34 |
| median | 36 | 0.36 |
| P90 | 36 | 0.36 |
| P95 | 36 | 0.36 |
| P99 | 36 | 0.36 |
| max | 36 | 0.36 |

This is evidence for a **human/config decision** — not a final `max_spread`.
Derived insight: median spread (36 points) is 18× the provisional SL default of
2.0 points and 7.2× the provisional max_spread of 5.0 — any fixed SL tighter
than the spread is not executable economically. The provisional defaults in
`RiskConfig` would have REJECTED or mis-scaled every entry under this
observation, which is correct fail-closed behavior but proves the defaults
need owner update.

## 7. Lot Constraints

- Min 0.01 · Max 1000.0 · Step 0.01 · Limit 6000 · digit-clean (2-decimal).
- `volume_step` 0.01 is exactly representable; the engine's `round_down_step`
  floors correctly (verified: rounded values are exact step multiples in the
  calculation test below).
- With balance 0.25 USC the risk-budget model hits `LOT_OUT_OF_RANGE` for any
  SL distance ≥ 0.5 points (see §11): a 0.01-lot trade requires budget of at
  least 0.01 × loss/lot, far above this equity. Deterministic and correct —
  the gate rejects rather than trading disproportionate size.

## 8. Tick/Contract Mechanics

| Check | Value | Result |
| --- | --- | --- |
| tick_size > 0 | 0.01 | PASS |
| tick_value > 0 | 1.0 USC | PASS |
| contract_size > 0 | 1.0 | PASS |
| point == tick_size relation | point 0.01 = tick 0.01 | consistent |

- Loss per lot for SL = 2.0 points: `(2.0 / 0.01) × 1.0 = 200 USC/lot`.
- Loss per lot for SL = 0.5 points: 50 USC/lot; SL = 5.0 points: 500 USC/lot.

## 9. SL Constraints

| Field | Value | Meaning |
| --- | --- | --- |
| `trade_stops_level` | 0 | no minimum stop distance — broker enforces none |
| `trade_freeze_level` | 8 points | close/modify barrier near market (8 × 0.01 = 0.08 quote) |
| `point` / `digits` | 0.01 / 2 | SL prices must be 2-decimal normalized |
| minimum SL price distance | point × stops_level = 0.0 | broker-legal minimum = 0 |

No SL was attached (calculation-only analysis per task §19). Derived: an
economically valid SL must be > spread (≈0.36 quote / 36 points) to not be
instantly in loss; broker-legal minimum is 0, but economic minimum is the
spread. Both factual statements now have runtime evidence.

## 10. Margin/Leverage

| Field | Value |
| --- | --- |
| free_margin | 0.25 USC (no positions) |
| margin (current) | 0.0 USC |
| leverage | 2000:1 (actual broker account value) |
| margin_mode | 2 (hedging) |
| symbol calc mode | 4 (CFD on leverage) |
| margin_initial (symbol) | 0.0 — broker computes via leverage/calc mode; `margin_initial` per-lot not exposed |

No margin mutation or order simulation performed. Runtime leverage (2000:1)
differs from the `RiskConfig` fallback default (100:1) → leverage fallback now
has direct evidence to update, pending owner config decision.

## 11. Risk Engine Compatibility

Engine logic (`round_down_step` + budget model) checked against broker
mechanics (pure calculation):

| SL pts | risk % | raw lot | rounded lot | ≥ min | ≤ max | step multiple |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5 | 0.5 | 0.0000250 | 0.00 | ✗ | ✓ | ✓ |
| 0.5 | 1.0 | 0.0000500 | 0.00 | ✗ | ✓ | ✓ |
| 2.0 | 0.5 | 0.0000063 | 0.00 | ✗ | ✓ | ✓ |
| 2.0 | 1.0 | 0.0000125 | 0.00 | ✗ | ✓ | ✓ |
| 5.0 | 0.5 | 0.0000025 | 0.00 | ✗ | ✓ | ✓ |

- Rounding is step-exact and never rounds up → risk never exceeds budget.
- The account equity (0.25 USC) is below the minimum size for any lot ≥ 0.01 at
  these SL/risk inputs → all proposals REJECT (`LOT_OUT_OF_RANGE`). This is the
  gate working as designed (fail-closed on impossible size), not a defect.
- To ever produce a 0.01-lot order with SL 2.0 and 0.5 % risk, equity must be
  ≥ 0.01 × 200 / 0.005 = 400 USC. Useful sizing reference for the owner.

## 12. Pending Configuration Impact

### Now have runtime evidence (CONFIG IMPACT)

| Pending param | Evidence now | Status |
| --- | --- | --- |
| Leverage fallback | actual account leverage = 2000:1 (config assumed 100) | evidence ready; config update pending owner |
| Max spread | observed median/P95/P99 = 36 points, min 34 | provisional `max_spread=5` would REJECT all; owner should set ≥ typical spread; not auto-locked |
| SL distance | broker legal min = 0; economic min = spread ≈ 36 points; freeze 8 pts | provisional `default_sl_points=2.0` is economically invalid (< spread); owner decides real distance |
| Lot/rounding | step-exact floor verified on XAUUSDc volume_step 0.01 | confirmed working |
| Stops/freeze | stops_level 0, freeze_level 8 | confirms stops/close modeling assumptions |

### Still require owner/paper validation (STILL PENDING)

| Pending param | Reason |
| --- | --- |
| Exact SL distance & SL method | needs owner decision; value must be > spread (≈36 pts) |
| Exact max spread | needs owner decision; observation window is one session only |
| Max exposure | needs owner decision; exposure cap now expressible (notional ≈ 4370 USC/lot) |
| Margin buffer | needs owner decision; nominal balance observed only |
| Slippage/commission treatment | not observable read-only (would require order simulation) |
| Compounding ratio | separate milestone |

### LOCKED (unchanged, per owner)

`risk_basis = EQUITY` · `risk/trade = 0.5%` · `max positions = 1` · `max drawdown = 5.0%`.
These were not modified by this observation.

## 13. Limitations

- Balance is nominal runtime snapshots only; no config/decision used them.
- 61-sample spread window = one active session; no weekend/diurnal/E-U/N sessions.
- Commission/slippage not measurable without trades (not performed).
- `margin_initial` not exposed by broker symbol info → margin via leverage/calc mode.
- Prices shown in USC (Cent) quote; consistent within the account.

## 14. Final Verdict

**READ-ONLY XAUUSDc EVIDENCE COMPLETE** — broker mechanics, account state,
symbol spec, spread stats, lot/tick/SL constraints, and risk-engine
compatibility validated with zero execution. Pending configs get evidence; no
configuration was auto-locked. Next: owner decision on SL/max-spread/margin
using this evidence, then RiskConfig update.