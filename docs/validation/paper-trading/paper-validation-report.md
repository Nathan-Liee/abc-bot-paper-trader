# Paper Validation Report

Report date: 2026-08-17 · Verdict: **PASS WITH FINDINGS**

## 1. Objective

Build and exercise a deterministic paper-validation harness to test the full
trading lifecycle (AI proposal → Risk Engine → simulated entry → position
lifecycle → ABC/SL exit → trade evidence) under `PAPER_VALIDATION_V0.1`,
producing trade-level evidence for RiskConfig revision decisions. No broker
execution; no live orders.

## 2. Environment

- Harness: `paper_validation/` package (8 modules).
- Symbol: `XAUUSDc` (HFM Cent, observed spec: digits 2, point 0.01, tick 0.01,
  tick_value 1.0 USC, contract 1.0, vol 0.01/1000/0.01, stops 0, freeze 8).
- Risk Engine: `risk_engine/` (source of truth for all risk/lot/SL).
- AI: deterministic fixtures (BUY/SELL/NO-TRADE), no live endpoint calls.
- Simulation: deterministic tick replay (seeded), spread-only cost default,
  configurable slippage/commission/swap.

## 3. Risk Profile

`PAPER_VALIDATION_V0.1` — applied (production UNLOCKED). Parameters:
risk 0.5% equity, SL 50 pts, max spread 45 pts, exposure ≤ 100% equity, free
margin ≥ 10% equity + 1× budget, leverage fallback 2000, compounding 0%.

## 4. Data Source

- Deterministic synthetic fixtures (timestamped bid/ask ticks).
- No live or historical MT5 tick replay in this run (harness supports it via
  `MarketReplay.from_fixture_ticks`).
- All trade evidence labeled `SIMULATED`.

## 5. Simulation Rules

- Entry: BUY fills at ask, SELL at bid (never mid).
- SL: from Risk Engine output (50 pts × point = 0.50 price distance).
- ABC exit: `NET_PROFIT > 0 → CLOSE` (gross PnL minus commission/swap/slippage;
  spread already reflected in fill prices).
- SL exit: BUY bid ≤ SL price; SELL ask ≥ SL price.
- One position max; session end if no exit within tick window.

## 6. Cost Model

| Mode | Spread | Commission | Swap | Slippage |
| --- | --- | --- | --- | --- |
| SPREAD_ONLY | ✓ (in fill prices) | 0 | 0 | 0 |
| COMMISSION_CONFIGURED | ✓ | configurable | 0 | 0 |
| SLIPPAGE_CONFIGURED | ✓ | 0 | 0 | configurable |
| FULL_COST_MODEL | ✓ | configurable | configurable | configurable |

All costs labeled `SIMULATED`. Spread is OBSERVED at fill time; slippage is
synthetic (zero/fixed/bounded-random with seed). Commission/swap status:
`NOT_OBSERVED` until paper execution evidence.

## 7. Scenario Coverage

| Group | Scenarios | Status |
| --- | --- | --- |
| A. Normal market | BUY/SELL approve + ABC/SL | ✓ covered |
| B. Spread near threshold | 36 pts (within 45) | ✓ covered |
| C. Spread above threshold | 600 pts → SPREAD_TOO_HIGH | ✓ covered |
| D. BUY → ABC profit close | price up → net > 0 | ✓ covered |
| E. SELL → ABC profit close | price down → net > 0 | ✓ covered |
| F. BUY → SL | price drops below SL | ✓ covered |
| G. SELL → SL | price rises above SL | ✓ covered |
| H. Drawdown near threshold | DD 10% > 5% → DRAWDOWN_LIMIT | ✓ covered |
| I. Existing position blocks | pos=1 → EXPOSURE_LIMIT | ✓ covered |
| J. Insufficient margin | free_margin=50 → INSUFFICIENT_MARGIN | ✓ covered |
| K. Exposure cap | (via existing exposure) | ✓ covered |
| L. Invalid market state | NaN bid → INVALID_MARKET_CONTEXT | ✓ covered (risk_engine tests) |
| M. Missing symbol spec | (via invalid spec in risk_engine tests) | ✓ covered |
| N. Synthetic slippage | FULL_COST_MODEL with slippage | ✓ covered |
| O. Cost model variations | SPREAD_ONLY / FULL | ✓ covered |

## 8. Trade-Level Evidence

Each trade produces a `TradeEvidence` record with: trade_id, scenario_id,
timestamps, direction, confidence, risk_config_profile, equity_before,
risk_budget, lot, entry/sl/exit prices, spread_at_entry, gross/net PnL,
cost breakdown (spread/commission/swap/slippage), risk_realized,
MAE/MFE, holding_duration, risk_decision, reason_code, label.

## 9. Risk Metrics

- Theoretical risk (zero-slippage): realized loss ≤ risk budget (50 USC at
  10000 equity). Invariant holds: `risk_realized ≤ risk_theoretical × 1.0001`.
- Risk budget breaches: 0 in SPREAD_ONLY mode.
- Risk overrun due to simulated cost: detected and flagged
  `RISK_BUDGET_OVERRUN_DUE_TO_SIMULATED_COST` when commission/slippage pushes
  realized loss above theoretical. This is evidence for RiskConfig revision
  (cost treatment must be addressed before production lock).

## 10. ABC Exit Metrics

- ABC close fires when NET_PROFIT > 0 (gross PnL > commission + swap + slippage;
  spread already in fill prices).
- BUY ABC close: price moves up sufficiently → close at bid.
- SELL ABC close: price moves down sufficiently → close at ask.
- No fixed TP. ABC is the only profit-exit mechanism.

## 11. SL Metrics

- SL fires at BUY bid ≤ SL_price / SELL ask ≥ SL_price.
- SL 50 pts = 0.50 price distance > observed spread 0.36 → economically valid.
- SL stop produces realized loss ≤ theoretical risk (zero-slippage invariant).

## 12. Spread Sensitivity

- Observed spread 36 pts (median); max_spread_points = 45 → 9-pt headroom.
- Scenario with 600-pt spread → REJECT (SPREAD_TOO_HIGH).
- Spread is floating; 61-sample window is insufficient for production lock.

## 13. Margin/Exposure Sensitivity

- Free margin 50 USC → REJECT (INSUFFICIENT_MARGIN; threshold = 10% equity +
  1× budget = 1050 USC at 10000 equity).
- Existing position count = 1 → REJECT (EXPOSURE_LIMIT; max positions = 1).
- Exposure cap = 100% equity; projected exposure includes existing + new.

## 14. Slippage Sensitivity

- Zero slippage: risk budget invariant holds (realized ≤ theoretical).
- Configured slippage (50 pts): increases realized loss; can cause
  `RISK_BUDGET_OVERRUN_DUE_TO_SIMULATED_COST` — evidence that production
  config must include cost add-on or wider SL.

## 15. Commission/Swap Status

- Commission: `NOT_OBSERVED` (no execution data). Configurable in harness as
  `commission_per_lot`; default 0.
- Swap: `NOT_OBSERVED`. Configurable as `swap_per_lot_per_night`; default 0.
- Both remain `PENDING_PAPER_EVIDENCE` for production RiskConfig.

## 16. Risk Budget Integrity

- At SPREAD_ONLY: `risk_realized ≤ risk_theoretical × 1.0001` (verified by
  test + invariant check in scenario runner).
- At FULL_COST_MODEL with high commission/slippage: overrun detected and
  flagged — not hidden. This is evidence for RiskConfig revision.
- Lot rounding: floor to volume_step → never increases risk above budget.

## 17. Findings

1. **SL 50 pts is economically valid** above observed spread (36 pts) and
   produces correct SL_STOP exits.
2. **ABC exit works as designed** — closes on NET_PROFIT > 0 with no fixed TP.
3. **Risk budget invariant holds** at zero-slippage; breaks under high
   simulated costs → cost treatment must be addressed before production lock.
4. **Max spread 45 pts** accepts the observed 36-pt median with 9-pt headroom;
   insufficient for production lock (single-session sample).
5. **One-position cap** correctly blocks new entries when a position is open.
6. **Margin gate** correctly rejects when free margin < 10% equity + budget.
7. **Drawdown guard** correctly rejects at 10% > 5% threshold.
8. **NO-TRADE never produces a position**.

## 18. RiskConfig Revisit Conditions

| Parameter | Evidence sufficient to lock? | Status |
| --- | --- | --- |
| SL distance (50 pts) | Partially — economically valid, ABC/SL work; need paper trade sample for noise behavior | PENDING MORE EVIDENCE |
| Max spread (45 pts) | No — single 61-sample session insufficient | PENDING MORE EVIDENCE |
| Exposure (100% equity) | Partially — works as backstop; rarely binds at 0.5% risk | PENDING MORE EVIDENCE |
| Margin buffer (10% + budget) | Partially — gate works; real margin behavior untested | PENDING MORE EVIDENCE |
| Cost treatment | No — slippage/commission not observed; overrun evidence shows this must be solved | PENDING MORE EVIDENCE |

## 19. Limitations

- Synthetic tick data (not live market); profitability not meaningful.
- Slippage model is synthetic (zero/fixed/seeded-random), not observed.
- Commission/swap are configurable placeholders, not broker-verified.
- No multi-session spread distribution.
- No real margin behavior with open position.

## 20. Verdict

**PASS WITH FINDINGS** — harness complete, 476 tests green, all scenario
groups covered, risk budget integrity verified, ABC/SL behavior correct,
risk overruns flagged (not hidden). Production RiskConfig remains UNLOCKED;
cost treatment is the most critical pending item.

## 21. Next Action

1. Run paper validation with recorded MT5 telemetry (Phase A data collection)
   to get real spread/session distribution.
2. Execute paper trades (simulated) with varying slippage/commission to
   quantify cost impact on risk budget.
3. Revisit SL 50 pts and max_spread 45 pts after multi-session evidence.
4. Lock cost treatment policy (add-to-risk vs deferred) before production
   RiskConfig lock.
5. Proceed to Execution Engine design once RiskConfig is locked.