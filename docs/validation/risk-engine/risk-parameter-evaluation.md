# Risk Parameter Evaluation

Based on live HFM Cent `XAUUSDc` runtime evidence — options only, no final locking.
Report date: 2026-08-17 · Verdict: **RISK PARAMETER EVALUATION COMPLETE — READY FOR HUMAN APPROVAL**

## 1. Runtime Evidence

Observed directly from MT5 (read-only IPC, account 229105805 / HFMarketsGlobal-Live19, 2026-08-17 09:35–09:36 +07):

| Fact | Value |
| --- | --- |
| Account | HFM Cent REAL, hedging mode, currency USC |
| Leverage | 2000:1 |
| digits / point / tick_size | 2 / 0.01 / 0.01 |
| tick_value | 1.0 USC per 0.01 per 1.0 lot |
| contract_size | 1.0 (Cent mini; 1 lot = 1 oz) |
| volume_min / max / step | 0.01 / 1000.0 / 0.01 |
| stops_level / freeze_level | 0 / 8 (points) |
| spread (61 samples) | min 34 · median 36 · P90 36 · P95 36 · P99 36 · max 36 points |
| calc mode | CFD on leverage (4); margin_initial not exposed |
| Reference price (window) | ≈ 4,370 USC |

Source: `docs/validation/runtime/xauusdc-cent-readonly-observation.md`.

## 2. Locked Policies

- risk basis = EQUITY
- risk/trade = 0.5 %
- max simultaneous positions = 1
- max drawdown = 5.0 %

Not modified. Anything numeric beyond these remains un-locked in this task.

## 3. SL Candidates

SL distance is an engine INPUT (engine: budget → SL → loss/lot → lot). Candidates
(all in points; 1 pt = 0.01 price; spread ≈ 36 pts median):

| ID | Candidate SL | Description | Economic vs spread | stops_level OK | freeze_level (8) OK |
| --- | --- | --- | --- | --- | --- |
| A | spread + headroom | 40 / 45 / 50 pts (1.1×–1.4× spread) | outside (above 36) | 0 → any | 8 → fine |
| B | fixed-point conservative | 72 / 108 pts (2×–3× spread) | clearly outside | fine | fine |
| C | risk-budget-derived (existing) | SL chosen first → lot from 0.5 % equity | depends on value | fine | fine |
| D | hybrid | max(spread+headroom, strategy-min) e.g. max(45, X) | outside when headroom ≥ 9 | fine | fine |

The previous default **2.0 pts was economically invalid** (SL ≈ 0.18× spread) —
excluded from candidates.

Loss / lot: `loss_per_lot = (sl_pts / 0.01) × 1.0 USC`. Key values:

| SL | price distance | loss per 1.0 lot | loss per 0.01 lot |
| --- | --- | --- | --- |
| 36 pts | 0.36 | 3,600 USC | 36 USC |
| 40 pts | 0.40 | 4,000 USC | 40 USC |
| 45 pts | 0.45 | 4,500 USC | 45 USC |
| 50 pts | 0.50 | 5,000 USC | 50 USC |
| 72 pts | 0.72 | 7,200 USC | 72 USC |
| 108 pts | 1.08 | 10,800 USC | 108 USC |

## 4. SL Sensitivity Analysis

Max lot from 0.5 % equity budget = `floor(equity × 0.005 / loss_per_lot, step 0.01)`.
Theoretical loss = budget (≤ configured); exposure = lot × 1.0 × ≈4,370 USC.
`0.00` = below `volume_min` → gate REJECTs (LOT_OUT_OF_RANGE).

| SL | equity 100 | 500 | 1,000 | 5,000 | 10,000 |
| --- | --- | --- | --- | --- | --- |
| 20 pts (invalid: < spread) | 0.00 | 0.00 | 0.00 | 0.01 (44 exposure) | 0.02 (87) |
| 36 pts (= spread) | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 (44) |
| 40 pts (A) | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 (44) |
| 45 pts (A) | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 (44) |
| 50 pts (A) | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 (44) |
| 72 pts (B) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 108 pts (B) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

Minimum equity to trade one 0.01 lot at 0.5 % with an economically valid SL:
```
SL 36 pts → 7,200 USC     SL 40 pts → 8,000 USC
SL 45 pts → 9,000 USC     SL 50 pts → 10,000 USC
SL 72 pts → 14,400 USC    SL 108 pts → 21,600 USC
```
**Finding:** at this account scale (equity < ~7,000 USC), the fixed 0.5 %
+ economically-valid SL combination cannot produce a tradable 0.01 lot. This is
a policy tension to resolve: loosen risk %, shrink SL below economic minimum
(discouraged), or grow/reload equity. Not auto-decided.

Exposure per 0.01 lot ≈ 43.7 USC at observed price → negligible vs max exposure candidates.

## 5. Max Spread Candidates

Observed: min 34, median/P90/P95/P99/max 36 points (61 samples, one active session).

| Threshold (pts) | Accepted (observed) | Rejected | Safety margin above observed | Ultra-fast scalp implication |
| --- | --- | --- | --- | --- |
| 36 | 100 % | 0 % | 0 | rejects any tick above P95 of this window |
| 40 | 100 % | 0 % | 4 pts | small cushion; tight for spike days |
| 45 | 100 % | 0 % | 9 pts | reasonable headroom for scalping |
| 50 | 100 % | 0 % | 14 pts | comfortable buffer; may admit higher-cost windows |

Honest limit: 61 s cannot predict other sessions (Tokyo/London/NY rollover, news).
Spread is floating (`spread_float=true`). These are evaluation candidates only.

## 6. Max Exposure Candidates

With max positions = 1, per-trade exposure = lot × 1.0 × price (≈4,370 USC/lot).
Exposure profile for a 40-pt SL / 0.5 % / equity 10,000 USC → lot 0.01 → ≈44 USC (≈0.4 % notional of equity).

| Policy | Candidate | Effect | Risk |
| --- | --- | --- | --- |
| Fixed currency cap | 5,000 USC | blocks > ~114 lot notional at once | too loose vs typical lot/equity; also arbitrary (no evidence) |
| Fixed currency cap (small) | 500 USC | suits tiny positions | painful if equity grows |
| Equity-relative | 50 % equity | exposure ≤ half equity notional | needless gate for most SL profiles; adequate |
| Equity-relative | 100 % equity | exposure ≤ equity | permissive but bounded; simpler |
| Risk-derived | exposure ≤ k × risk budget (e.g. 20×) | scales with risk model | no observed justification for k |

Notable: because tick value ≈ contract ≈ 1 USC-convention, notional exposure is
~price × lot; at the observed price and 0.5 % risk, the exposure gate almost
never binds — it is a structural backstop, not the active limiter. Recommend
equity-relative (50–100 %) over the arbitrary 5,000 fixed default.

## 7. Margin Buffer Candidates

Observed: free margin 0.25 USC (no positions), leverage 2000:1, calc CFD-lev,
margin_initial not exposed. Realized margin behavior cannot be inferred from an
empty 0.25-USC account.

| Policy | Candidate | Assessment |
| --- | --- | --- |
| Fixed free-margin buffer | 50 USC | meaningless at small equity (50 USC > equity) — rejects everything |
| Percentage buffer | free after trade ≥ 20 % equity | intuitive, scales with account |
| Margin + risk guard | free after ≥ margin_used + 2× risk budget | most defensible — bundles utilization + next-trade headroom |
| Fallback-guess only | rely on leverage only | weak; margin price moves with volatility |

Bounded recommendation: percentage buffer expressed in equity terms plus a
risk-derived component (2× next-trade budget). No runtime data supports a fixed
USC number at this account scale.

## 8. Leverage Policy

Observed leverage 2000:1 is **real broker data**, not a guess. Options:

1. **Keep 2000 as the config default** (evidence-backed; margin = exposure/2000). Simple, but margin is only as good as the assumption that the broker exposes the same calc-to-leverage relation.
2. **Fail-closed: refuse a fallback entirely** — require explicit broker-provided margin (SYMBOL margin via calc mode + actual leverage; `margin_initial` if provided) and REJECT if absent. Most conservative; forces bridge/runtime to supply margin.

Recommended: keep 2000 as documented default (it matches observed runtime) but
flag it PROVISIONAL, and design the execution stage to consume broker-provided
margin fields; the gate itself already prefers `margin_initial` when given.

## 9. Slippage/Commission

| Item | Status |
| --- | --- |
| Spread | OBSERVED (median 36 pts) |
| Commission | OBSERVED symbol-field only (`commission_blocked=0.0`; no execution) |
| Swap | OBSERVED raw (long −75.25/short 0.0 per lot; informational for scalps) |
| Slippage (fill vs request) | NOT OBSERVABLE YET — needs execution |
| Realized costs per trade | NOT OBSERVABLE YET |
| Cost treatment for risk amount | NEEDS PAPER VALIDATION — must reject claiming theoretical risk = realized loss |

Current engine risk amount = SL-distance loss only (§17 caveat stands). Options for
cost add-on (spread + commission estimate into risk budget) belong to profiles
below and must be verified in paper/demo, not assumed.

## 10. Combined Configuration Options

Option A — Conservative:
`SL = 72 pts (2× spread) · max spread 50 · exposure ≤ 50 % equity · free margin ≥ 20 % equity + 2× risk budget · cost add-on ≥ spread+buffer impl note · leverage 2000 (broker-supplied preferred)`

Option B — Balanced:
`SL = 50 pts · max spread 45 · exposure ≤ 100 % equity · free margin ≥ 10 % equity + risk budget · nominal risk (spread noted, not added) · leverage 2000`

Option C — Strict Scalping:
`SL = 40–45 pts (spread + 4–9) · max spread 36–40 · exposure ≤ 100 % equity · free margin ≥ 5 % equity + risk budget · spread counted into effective risk distance · leverage 2000`

## 11. Recommended Conservative Profile

(default candidate — presented for approval, NOT locked)
```
SL policy:            fixed 72 pts (0.72 price); loss-protection only
max spread:           50 pts (headroom 14 over P95)
max exposure:         ≤ 50 % equity (per trade notional)
margin buffer:        free ≥ 20 % equity + 2 × risk budget after trade
leverage fallback:    2000 (observed) OR broker-provided margin when available
cost treatment:       include spread + commission estimate in risk budget before lot sizing
```
Pros: never touches spread-noise; cost-safe; exposure/margin bounded. Cons: min
lot infeasible below ≈14,400 USC equity; may feel wide for scalps.

## 12. Tradeoffs

- Wide SL (72+) → fewer noise stop-outs, larger min-equity needed, smaller lots,
  longer loss windows.
- Tight SL (36–40) → noise-prone (spread ≈ 36), but viable at smaller equity.
- Tight max_spread (36) → max scalp quality filter but zero headroom on spikes.
- Equity-relative exposure scales automatically; fixed caps are arbitrary here.
- Fail-closed leverage is safest but makes live gate stricter than the
  0.25-USC demo-stage account.

## 13. Human Approval Items

| # | Decision | Candidates |
| --- | --- | --- |
| 1 | SL distance & method | 40 / 45 / 50 / 72 pts (fixed or spread-relative) |
| 2 | Max spread threshold | 36 / 40 / 45 / 50 pts |
| 3 | Exposure policy | ≤ 50 % or ≤ 100 % equity (equity-relative) or fixed cap (value) |
| 4 | Margin buffer | % equity (+ risk-derived component) vs fixed USC |
| 5 | Leverage handling | keep 2000 as documented default vs fail-closed broker-required |
| 6 | Cost treatment | add spread/commission into risk budget vs keep nominal + monitor |
| 7 | Compounding ratio | PENDING — no runtime evidence (outside this task) |

## 14. Paper Validation Required

- Longer/full-day spread distribution (across sessions) before max_spread lock.
- Realized slippage and commission via paper/demo execution before cost lock.
- Re-verify margin/free margin behavior with an actual (even tiny) position.
- Confirm min-lot feasibility at chosen SL/risk (sensitivity §4) on funded equity.
- ABC exit interaction (NET_PROFIT > 0 → close) tested in paper with chosen SL.

## 15. Final Verdict

**RISK PARAMETER EVALUATION COMPLETE — READY FOR HUMAN APPROVAL** — evidence
is real runtime data; the report offers options/profiles and does not lock any
final values. Next action: owner selects a profile (or per-item values) from
§10/§13; then RiskConfig update task applies them.