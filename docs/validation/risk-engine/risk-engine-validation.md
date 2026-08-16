# Risk Engine Gate — Validation Report

Report date: 2026-08-17 · Verdict: **PASS WITH PENDING CONFIGURATION**

## Objective

Implement the System-owned Risk Engine Gate that consumes validated AI
proposals (BUY / SELL / NO-TRADE + confidence + reason), validates account and
market state, computes deterministic risk / lot / SL / exposure, enforces
fail-closed safety, and produces an APPROVE / REJECT trade plan. **No broker
execution** occurs anywhere in this task.

## Architecture

```text
AI Decision Engine (proposal)
        ↓
Risk Engine (System authority)
    ├─ validators     (input validation + fail-closed prechecks)
    ├─ calculators    (SL distance → raw lot → step check → final lot)
    └─ engine         (orchestration + margin/exposure/risk checks)
        ↓
RiskDecision (APPROVE / REJECT)
        ↓
SystemRiskGate boundary interface (future Execute/EA integration)
```

New package: `risk_engine/` (`models.py`, `config.py`, `calculators.py`,
`validators.py`, `engine.py`, `gate.py`, `reason_codes.py`). Risk logic is
kept fully separate from `ai_decision/`. No circular imports; the only
coupling is `risk_engine/engine.py` reading `DecisionRecord` (proposal input).

## Inputs

- `AI proposal`: direction (`BUY`/`SELL`/`NO-TRADE`), confidence, reason,
  `validation_ok`, inference_id, correlation_id.
- `AccountState`: balance, equity, free_margin, margin, position count,
  current exposure, current drawdown %.
- `MarketState`: bid, ask, spread, mid, symbol, timestamp.
- `SymbolSpecification`: contract_size, tick_size, tick_value, volume
  min/max/step, stops_level, freeze_level, margin_initial (optional).

`SymbolSpecification.margin_initial` is an explicit required field in the
System interface; when a broker does not supply it, the engine falls back to
leverage-based margin (`exposure / leverage`) — never hardcoded to
HFM Cent / XAUUSDc values.

## Outputs

```json
{
  "decision": "APPROVE|REJECT",
  "direction": "BUY|SELL|NO-TRADE",
  "lot": 0.0,
  "sl": 0.0,
  "risk_amount": 0.0,
  "risk_percent": 0.0,
  "exposure": 0.0,
  "reason_code": "string",
  "reason": "string"
}
```

Full observability record (`RiskEvaluationRecord`) carries additionally:
`risk_evaluation_id`, `correlation_id`, `inference_id`, `validation_failures`,
`timestamp_iso`. Maps to canonical `RISK_GATE` event fields
(`gate_result`, `risk_budget_usd`, `candidate_lot`, `final_lot`,
`aggregate_risk_usd`, `aggregate_exposure_usd`, `free_margin_usd`).

## Risk Policy

- Basis: configurable `EQUITY` (default, per Obsidian `06 - Equity
  Management.md` "Equity is sizing basis") vs `BALANCE`.
- `risk_pct_per_trade` default safe baseline 1.0 % — marked
  `PENDING CONFIGURATION` (Obsidian: "Risk percentage: PENDING DECISION").
- `max_drawdown_pct` guard 10 %, `max_exposure_usd` cap,
  `max_simultaneous_positions` = 1.
- AI confidence is validated and filtered (`min_ai_confidence` 0.5),
  **never** used as a risk/lot multiplier.

## Lot Calculation

Deterministic chain (matches documented dependency order; Obsidian does not
specify a conflicting order):

1. Risk Budget = capital basis × risk %.
2. SL / risk distance → loss per lot = (SL distance ÷ tick_size) × tick_value.
3. Raw lot = budget ÷ loss-per-lot.
4. Quantize down to `volume_step` (exact integer arithmetic, no float drift).
5. Clamp to `volume_min` / `volume_max`; reject if below min.

## SL Calculation

Loss-protection interface (`calculate_sl_price`): BUY → entry − dist;
SELL → entry + dist. `stops_level` clamp is honored for the minimum distance.
Configurable via `default_sl_points` (default 2.0). Formula/thresholds marked
`PENDING CONFIGURATION`. **No TP is created** (ABC exit = NET_PROFIT > 0 →
close, System-owned, out of scope for this task).

## Exposure

Exposure = final_lot × contract_size × entry_price, added to account's
current exposure. Reject (`EXPOSURE_LIMIT`) if projected total exceeds
`max_exposure_usd`.

## Margin

Required margin = final_lot × `margin_initial` when broker supplies it, else
exposure ÷ leverage. Reject (`INSUFFICIENT_MARGIN`) if free margin after the
trade drops below `min_free_margin_usd`.

## Spread

Reject (`SPREAD_TOO_HIGH`) when `MarketState.spread > max_spread`. Defaults stay
in config; no HFM Cent / XAUUSDc numbers are hardcoded.

## Failure Modes

Any critical uncertainty → REJECT (fail-closed):

- NaN / ±inf / boolean / non-numeric inputs → `INVALID_*` / `UNKNOWN_RISK_INPUT`.
- Unparseable or stale/future market timestamp → `STALE_CONTEXT`.
- Incomplete symbol spec (non-positive tick/tick_value/volume) → `BROKER_CONSTRAINT`.
- AI proposal already invalid or authority-violating → `AUTHORITY_VIOLATION`.
- SL cannot be computed safely → `INVALID_SL`.
- Lot cannot be computed safely → `LOT_OUT_OF_RANGE` / `LOT_STEP_INVALID`.
- Calculated risk above configured budget → `RISK_LIMIT`.

## Reason Codes

`APPROVED`, `AI_NO_TRADE`, `INVALID_MARKET_CONTEXT`, `INVALID_ACCOUNT_STATE`,
`SPREAD_TOO_HIGH`, `DRAWDOWN_LIMIT`, `EXPOSURE_LIMIT`, `INSUFFICIENT_MARGIN`,
`LOT_OUT_OF_RANGE`, `LOT_STEP_INVALID`, `RISK_LIMIT`, `INVALID_SL`,
`BROKER_CONSTRAINT`, `STALE_CONTEXT`, `UNKNOWN_RISK_INPUT`,
`AUTHORITY_VIOLATION` (superset of required, deterministic strings).

## Tests

`tests/unit/test_risk_engine.py` (18 tests) + integration
`tests/integration/test_ai_to_risk_gate.py` (2 tests):

- AI proposal: BUY approved, SELL approved, NO-TRADE rejected, invalid proposal
  / authority violation rejected.
- Risk: valid budget, budget exceeded, exposure exceeded, insufficient margin,
  spread exceeded, drawdown guard, invalid symbol spec, NaN/infinite values,
  stale context, lot below min, SL safety.
- Determinism: same inputs → identical lot/SL/risk/exposure.
- Boundary: System consumes AI proposal and never executes.
- Integration: `DecisionEngine (mocked transport) → SystemRiskGate`, no
  EA/MT5 path.

Full suite: **449 passed** (431 pre-existing + 20 new); ruff check clean; ruff
format clean; mypy clean (65 files).

## Safety

- Zero order capability: no HTTP to broker, no MT5/MQL5 import, no `OrderSend`,
  no modify/close, no position management. Verified by absence of any broker
  transport in `risk_engine/` and locked by tests.
- `NO-TRADE` proposals never produce a trade plan.
- AI confidence never scales lot/risk.
- Premium/XAUUSD values never used as Cent/XAUUSDc economics (no hardcoded
  target values exist in the module).

## Known Pending Configuration

Per Obsidian, all numeric risk thresholds remain `PENDING DECISION`. This
implementation exposes them as config (`RiskConfig.from_env()`), applies
safe baseline defaults, and keeps `*_locked` flags explicit:

- risk % per trade (1.0 % default) — `PENDING CONFIGURATION`.
- SL distance / formula (2.0 default) — `PENDING CONFIGURATION`.
- Max exposure/drawdown/spread/margin buffer — `PENDING CONFIGURATION`.
- Position sizing formula (fixed-ratio vs % vs other) — `PENDING CONFIGURATION`.

These safe defaults are documented by the `config.py` docstring and tagged.

## Acceptance

Met: AI proposal never determines lot/risk/SL; System produces APPROVE/REJECT;
lot/risk/SL deterministic; margin/exposure/spread validated; failures
fail-closed REJECT; no broker execution; 449 tests + ruff + mypy green;
validation report written; AGENTS.md updated; commit + push clean.