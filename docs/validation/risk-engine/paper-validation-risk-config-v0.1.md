# Paper Validation Risk Configuration v0.1

Report date: 2026-08-17 · Status: **PAPER VALIDATION ONLY — NOT PRODUCTION**

## Objective

Apply the owner-approved risk parameters as `PAPER_VALIDATION_V0.1` so the
Risk Engine can be exercised during paper validation while production
configuration remains explicitly unlocked. The profile is fully configurable
via `RiskConfig.from_env()` and is slated for revision once paper-trading
evidence is available.

## Approved Parameters

```text
profile_name                  = PAPER_VALIDATION_V0.1
is_production                 = false
requires_paper_validation     = true

risk_basis                    = EQUITY
risk_per_trade                = 0.005      (0.5 % of equity)
max_simultaneous_positions    = 1
max_drawdown                  = 0.05       (5 %)

sl_distance_points            = 50   ( > observed spread 36 )
max_spread_points             = 45   ( paper threshold )
max_exposure_equity_ratio     = 1.0  ( exposure <= 100 % equity )
min_free_margin_equity_ratio  = 0.10 ( free margin >= 10 % equity )
margin_risk_budget_multiplier = 1.0  ( + 1 x next risk budget )
leverage_fallback             = 2000 ( observed runtime; fallback only )
compounding_reinvestment_ratio = 0.0 ( no auto compounding )

observed_spread_points        = 36   ( runtime evidence, median )
min_ai_confidence             = 0.5  ( filter only; never a risk multiplier )
```

All values configurable via `ABC_*` environment variables in
`RiskConfig.from_env()`; no hidden constants.

## Runtime Evidence

- HFM Cent REAL, hedging, `XAUUSDc`: digits 2, point 0.01, tick 0.01,
  tick_value 1.0 USC, contract_size 1.0, volume 0.01/1000/0.01,
  stops_level 0, freeze_level 8, calc CFD-on-leverage, leverage 2000:1.
- Spread: 61 samples — min 34, median 36, P90/P95/P99/max 36 points.
- Evidence source: `docs/validation/runtime/xauusdc-cent-readonly-observation.md`.

## Formula

- Risk budget = `capital_basis × risk_per_trade` (basis = EQUITY).
- SL price = entry ± `sl_distance_points × point` (directional; point = 0.01),
  clamped by `stops_level × point` minimum distance; SL must stay above the
  observed spread (sanity guard, fail-closed otherwise).
- Loss per lot = `(sl_distance_points / tick_size) × tick_value`.
- Raw lot = `risk budget / loss per lot` → floor to `volume_step` → min/max
  clamp. Flooring never increases risk above the budget (re-verified after
  clamping in the engine).
- Margin required = `broker margin_initial × lot` when supplied, else
  `exposure / leverage_fallback`.
- Exposure gate = `current_exposure + proposed_exposure ≤ equity × ratio`.
- Free margin gate = `free_margin - required_margin ≥ equity × 0.10 + budget × 1.0`.

## Broker Constraints

- volume min 0.01 / max 1000 / step 0.01 → enforced; below-min → `LOT_OUT_OF_RANGE`.
- stops_level 0 → no broker stop-distance restriction.
- freeze_level 8 (points) → informational for future close/modify.
- Leverage 2000 is broker-observed; it is a fallback, never a substitute for
  broker-provided margin data (`margin_initial` preferred when available).

## Known Limitations

- Not production: defaults were chosen for validation, not for final economics.
- 61-second single-session spread sample; other sessions untested.
- SL at 50 pts is above observed spread but still a starting choice; paper
  validation must confirm noise behavior.
- Slippage and realized costs unmeasured (no execution yet).
- Margin behavior inferred (account had no positions; balance nominal only).

## Pending Evidence

| Item | Status |
| --- | --- |
| Commission / swap treatment | `PENDING_PAPER_EVIDENCE` |
| Slippage | not observable until paper execution |
| Full-session spread distribution | not collected |
| Margin behavior with open position | not collected |
| Profit/wrong-side SL interaction on ABC exit | paper only |

## Revisit Conditions

Review/revise this profile when any of the following is satisfied:

- ≥ defined paper trade sample collected with recorded slippage/costs.
- Spread distribution from a full week observed (raise/lower `max_spread_points`).
- Stop-out frequency under SL 50 or timing of ABC close suggests SL distance changes.
- Broker-provided margin data available (drop the leverage fallback reliance).

## Validation Status

- Full suite **455 passed**: `pytest`; `ruff check .` clean; `ruff format --check .`
  clean (126 files); `mypy collector shared ai_decision risk_engine` clean (65 files).
- Profile applied in `risk_engine/`; production config remains UNLOCKED.
- No order/execution/EA capability added.