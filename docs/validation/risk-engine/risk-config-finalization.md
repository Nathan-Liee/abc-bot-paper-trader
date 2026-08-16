# Risk Configuration Finalization — Evaluation Report

Report date: 2026-08-17 · Verdict: **PASS WITH HUMAN APPROVAL REQUIRED**

## Executive Summary

The Risk Engine technical implementation (`risk_engine/`) is complete, tested
(449 passing incl. 20 risk-engine tests), and safe. This evaluation confirms
the design-environment evidence and the ABC architecture, but it **cannot
finalize the numeric risk thresholds**: Obsidian — the requirements source of
truth — explicitly marks every numeric risk decision as `PENDING DECISION`
(Risk %, Max Drawdown %, Max Exposure, Max Lot, sizing formula, spread
threshold, SL distance/formula). Per task rule §29/§44, the numeric
configuration stays PROVISIONAL until explicit human approval. This report
documents each parameter, its evidence, the recommendation options, and the
exact decision needed.

## Source of Truth

1. **Obsidian (requirements/design intent)** — primary. Every numeric threshold
   is `PENDING DECISION`:
   - `04 - Risk & Safety Requirements.md`: Max Drawdown, Max Lot, max spread
     threshold `PENDING DECISION` (RSK-001 limit unspecified).
   - `00/Position Sizing.md` & `00/Compounding & Lot Model.md`: sizing formula,
     risk %, min/max sizing `PENDING DECISION`.
   - `07 - Risk Philosophy.md`: max DD %, max exposure `PENDING DECISION`.
   - `08 - Circuit Breaker.md`: trigger numbers, reset behavior `PENDING DECISION`.
   - `01 - Functional Requirements.md` (FR-005): profit threshold `>0` kept
     (only value >0 is fixed; anything beyond ABC close is not required).
2. **Repository/implementation** — `risk_engine/config.py` defaults are safe
   baselines, explicitly tagged provisional.
3. **AGENTS.md** — current state (design itself, milestone tracking).
4. **Validation reports/tests** — `risk-engine-validation.md`,
   `ai-decision-engine-validation.md`, `tests/unit/test_risk_engine.py`,
   `tests/integration/test_ai_to_risk_gate.py`.

No web source was used to derive trading numbers; broker/symbol economics
(HFM Cent / XAUUSDc) are intentionally not assumed.

## Current Defaults

| Parameter | Config key | Current default | Tagged |
| --- | --- | --- | --- |
| Risk basis | `risk_basis` | `EQUITY` | provisional |
| Risk % / trade | `risk_pct_per_trade` | 1.0 | `*_locked=False` |
| SL distance | `default_sl_points` | 2.0 | `*_locked=False` |
| Max drawdown | `max_drawdown_pct` | 10.0 | provisional |
| Max exposure (USD) | `max_exposure_usd` | 5000.0 | provisional |
| Max positions | `max_simultaneous_positions` | 1 | provisional |
| Max spread | `max_spread` | 5.0 | provisional |
| Stale context | `max_stale_seconds` | 10.0 | safety |
| Free margin buffer | `min_free_margin_usd` | 50.0 | provisional |
| Leverage fallback | `leverage` | 100.0 | provisional |
| Min confidence | `min_ai_confidence` | 0.5 | provisional |

## Risk Basis

**Obsidian evidence:** `06 - Equity Management.md` defines Equity = Balance +
Floating PnL and calls Equity "basis utama sizing"; `06 - Compounding & Lot
Model.md` (dynamic lot follows equity); FR-007 "Updated Equity MUST be the
basis of next lot calc"; Goals "pertumbuhan modal berbasis ekuitas".

**Result:** risk basis = `EQUITY`, configurable to `BALANCE` (policy choice).
RECOMMENDATION: keep `EQUITY` (evidence-backed). Status: **LOCKED** (as
evidence-backed default; no human decision required to keep it).

## Risk %

**Obsidian evidence:** PENDING DECISION. No numeric source exists for the final
value; "risk per trade percentage" is explicitly open in Position Sizing,
Compounding & Lot, Risk & Safety.

**Scaling context:** ultra-fast scalp on a Cent account, one position, dynamic
lot, ABC exit (`NET_PROFIT > 0 → close`) which yields small profits per tick;
SL is the loss boundary. A low per-trade risk % is consistent with high
trade-frequency (many small winners), but the exact number remains the owner's
risk-appetite decision.

**Decision matrix:**

| Candidate | Rationale | Impact | Recommended usage |
| --- | --- | --- | --- |
| 0.5 % | Very defensive; high trade count; compounding slow | small lots (0.01 × many trades) | conservative paper validation |
| 1.0 % (current default) | Common 1-R-per-trade core; moderate compounding | moderate lot; ~10 consecutive stop-outs to −10 % | recommended starting band |
| 2.0 % | Aggressive scalp throughput | larger lots; faster drawdown path | only after paper-track record |

RECOMMENDED RANGE: **0.5–1.0 %** for first paper/execution validation.
EXACT HUMAN DECISION REQUIRED.

## SL Policy

**Constraints from source:**

- `05 - Exit Philosophy.md` + `05 - Authority & Boundaries.md`: SL = LOSS
  protection (System-owned, directional, deterministic); ABC (`NET_PROFIT > 0`)
  is the profit exit; no TP.
- SL must satisfy broker `stops_level`/`freeze_level`; risk = SL distance ×
  loss-per-lot; risk/lot must not exceed budget.

**Options evaluated:**

| SL method | Assessment |
| --- | --- |
| Fixed points (current) | simple, deterministic, not adaptive; risk-per-lot varies with distance only via config; FINE as provisional |
| Volatility-based (e.g. ATR multiple) | adapts to market; needs ATR supply + latency budget; higher complexity |
| Market-structure-based | non-deterministic / contextual; conflicts with "SL = hard safety, deterministic" |
| Risk-distance-derived | **already the design**: lot = budget / (SL-dist × loss-per-lot); SL is an INPUT, not output — see dependency below |
| Hybrid (fixed + volatility guard) | refinement; needs market-context feature, out of current scope |

RECOMMENDATION: keep fixed-point provisional (2.0) until paper-track evidence
justifies volatility-based. Status:
- Policy shape (SL = loss protection, deterministic, System-owned): **LOCKED**.
- Numeric distance / method selection: **HUMAN APPROVAL REQUIRED**.

Dependency audit (no circularity):
`Risk Budget → SL distance → loss per lot → raw lot → step/min/max clamp → final lot → exposure/margin validation → risk-budget re-check → APPROVE/REJECT`.
Implementation order in `calculators.py` matches this exactly; no circular
reference. Confirmed correct.

## Lot Sizing

**Current:** risk-budget-driven percentage-of-equity
(`equity × risk% ÷ (SL-dist × loss-per-lot)`), floored to broker `volume_step`,
clamped to `volume_min`/`volume_max`. Recomputes actual risk from final lot and
re-checks against budget.

**Obsidian:** sizing = "Current Equity + Risk Rules + Instrument Constraints"
(Position Sizing); deterministic; lot dynamic; AI cannot alter. Consistent.

**Key invariant — no silent risk increase:** `round_down_step` floors to the
volume step; `final_lot ≤ candidate_lot` never exceeds the raw risk-budget lot;
then engine verifies `risk_amount ≤ budget × 1.0001` (epsilon). Rounding never
pushes risk above budget. Status of the mechanism: **LOCKED**.

The actual risk % value feeding the formula: HUMAN APPROVAL REQUIRED.

Lot step rounding direction: floor (0.05 lot, never 0.06 when budget says 0.056).
Broker volume min/max/step enforced; below-min → REJECT (`LOT_OUT_OF_RANGE`).

## Exposure

**Obsidian:** RSK-005 total exposure limit required; Risk Engine "Exposure
Limits" subsystem; not final numeric. No per-direction/per-symbol model exists
beyond the current one-position-per-account default (`max_simultaneous_positions=1`).

**Implementation:** projected exposure = current exposure + new position
exposure; reject if > `max_exposure_usd`. Because `max_simultaneous_positions=1`,
per-symbol, per-direction, and total exposure coincide. Simple and safe.

**Status:**
- Exposure validation mechanism + position cap = 1: **LOCKED** (Obsidian
  supports "batas posisi maksimal", and single-position matches the scalp
  determinism; open to review, but evidence-backed default).
- `max_exposure_usd` numeric value: **HUMAN APPROVAL REQUIRED**.

## Drawdown

**Obsidian:** RSK-003/RSK-009/RSK-010 require drawdown monitoring and safe
mode on overrun; numeric threshold `PENDING DECISION` (Risk & Safety, Risk
Philosophy, Circuit Breaker).

**Implementation:** `current_drawdown_pct >= max_drawdown_pct → REJECT`
(`DRAWDOWN_LIMIT`). Fail-closed behavior:
- If drawdown state is unavailable (missing/None/NaN), `AccountState.validate()`
  returns `INVALID_ACCOUNT_STATE` → REJECT. No silent pass when the policy
  requires drawdown guard. Verified in code and tests.

Rolling vs daily vs simple: Obsidian does not specify a window; current guard
is a current-equity drawdown % snapshot. Status of window/method:
**HUMAN APPROVAL REQUIRED** (numeric % and window).

## Spread

**Obsidian:** RSK-007 "detect extreme spread", defer entry if cost too high;
exact threshold `PENDING DECISION`. Premium (XAUUSD) values must never act as
final XAUUSDc economics — the implementation does not hardcode any symbol
spread; it configures `max_spread` (default 5.0) generically.

**Options:**

| Basis | Assessment |
| --- | --- |
| Absolute points (current) | simple; generic; meets RSK-007 minimal bound |
| Monetary impact (spread × loss-per-lot × lot) | more precise; needs per-trade linkage; possible v2 |
| % of typical move (XAUUSDc M1 ATR) | requires ATR supply + Cent contract semantics; not before paper data |

RECOMMENDATION: keep absolute-points filter; derive a Cent-specific threshold
from Phase-A collection, NOT from Premium. Status: mechanism **LOCKED**;
numeric threshold **HUMAN APPROVAL REQUIRED**.

## Margin

**Obsidian:** Risk Engine responsibilities include account protection &
eligibility; no numeric margin buffer defined. No Cent/XAUUSDc spec available
in repo (Phase A blocked). `SymbolSpecification.margin_initial` is an explicit
interface input; when 0, engine uses `exposure ÷ leverage` (default 100).

**Safety invariant:** margin check uses broker-supplied `free_margin` minus the
new trade's `required_margin`, keeping ≥ `min_free_margin_usd` free. Because
`free_margin` already reflects existing-position margin usage, existing
exposure is implicitly included when data is supplied. Reject otherwise
(`INSUFFICIENT_MARGIN`). Mechanism: **LOCKED**; buffer/leverage numbers:
**HUMAN APPROVAL REQUIRED** (requires real HFM Cent/XAUUSDc spec).

## Broker Constraints

- volume min/max/step: enforced → REJECT on below-min or NaN/invalid.
- stops_level: min SL distance clamp (SL distance = max(sl_points, stops_level)).
- freeze_level: present in spec for future close/modify constraints (currently
  informational — execution is out of scope this task).
- Invalid direction / invalid SL price (from cross) → REJECT.
- Status: mechanism **LOCKED**; per-symbol numeric values (volume bounds,
  tick/tick_value, margin) come from broker spec feed, not config constants.

## Slippage/Cost Treatment

Obsidian FR-004 requires PnL to include spread, commission, swap — that is the
ABC profit definition (exit side). For the risk estimate on the ENTRY side, the
engine currently counts only the SL-distance loss (tick-value × points).
Slippage/commission/swap are NOT included in `risk_amount_usd` today.

Status: mechanism as-is is a defensible conservative lower-bound only if the
positive SL buffer absorbs the difference — this is NOT proven. Two options
forward, decision required:

1. Add a cost add-on to the risk budget (e.g. `risk = SL loss + estimated
   spread + commission`) — safer, slightly larger than nominal.
2. Keep nominal and document that realized loss may exceed theoretical risk by
   costs (verification deferred to paper-track data).

**Recommendation options documented; implementation change gated on human
decision + paper economics. Status: HUMAN APPROVAL REQUIRED** (either strategy).

## ABC Interaction

- PROFIT: `NET_PROFIT > 0 → ABC CLOSE` (System rule, FR-005, Exit Philosophy) —
  preserved; out of scope for config; no TP exists.
- LOSS: risk boundary reached → SL close (this task's SL engine).
- Both exits System-owned, deterministic, AI never involved. **LOCKED.**

## AI Boundary

AI remains proposal-only (BUY/SELL/NO-TRADE + confidence + reason + record
id). AI never computes/decides lot, risk, SL, exposure, margin, or approval —
enforced by `SystemRiskGate` placing all sizing/validation in `risk_engine/`.

## Final Configuration Matrix

| Parameter | Current Implementation | Obsidian Evidence | Recommendation | Status |
| --- | --- | --- | --- | --- |
| Risk basis | `EQUITY` (configurable BALANCE) | Equity = sizing basis (Equity Mgmt, FR-007) | keep `EQUITY` | **LOCKED** |
| Risk %/trade | 1.0 | PENDING DECISION | 0.5–1.0 % paper-first band | HUMAN APPROVAL REQUIRED |
| Sizing formula | %-of-equity / risk-budget-driven | sizing = Equity + Risk + Instrument (Position Sizing) | keep formula | **LOCKED** (value gated) |
| Lot rounding | floor to volume_step | CMP-004 deterministic/broker-validated | floor, never round-up | **LOCKED** |
| Risk ≤ budget | re-check after clamp (ε 1.0001) | report §33 requirement | keep enforcement | **LOCKED** |
| SL policy | fixed points, directional, stop-clamped | SL = loss protection; no TP (Exit/Auth) | fixed provisional; volatility later | Policy **LOCKED**; number HUMAN |
| SL distance | 2.0 | PENDING DECISION | from paper-track risk-per-lot | HUMAN APPROVAL REQUIRED |
| Max exposure | 5000.0 (USD) | RSK-005 limit required; number PENDING | scale from equity after paper | HUMAN APPROVAL REQUIRED |
| Max positions | 1 | "position limits" required; scalp single-shot | keep 1 | **LOCKED** (reviewable) |
| Max drawdown | 10.0 % | RSK-003/010; number PENDING | choose after paper; circuit-breaker reset pending | HUMAN APPROVAL REQUIRED |
| Max spread | 5.0 | RSK-007 detect extreme; number PENDING | derive from Cent data, not Premium | HUMAN APPROVAL REQUIRED |
| Margin buffer | 50.0 USD free margin | interface-defined, no Obsidian number | set from real HFM Cent spec | HUMAN APPROVAL REQUIRED |
| Leverage fallback | 100.0 | no source | replace with HFM Cent spec when available | HUMAN APPROVAL REQUIRED |
| Stale context | 10.0 s | freshness guard (report §13) | keep (scalping latency budget needs data) | PROVISIONAL |
| Drawdown missing state | validate() → REJECT (fail-closed) | RSK-010 safe mode on uncertain state | keep | **LOCKED** |
| Confidence filter | ≥ 0.5 | AI is filterable, never a multiplier (§18 task) | keep, non-multiplying | PROVISIONAL |
| Cost add-on (slippage/commission) | not in risk amount | FR-004 PnL includes costs | option 1 vs 2 | HUMAN APPROVAL REQUIRED |

## Final Risk Config (decision output — fill after human approval)

```text
RISK BASIS:                     EQUITY (LOCKED)
RISK PER TRADE:                 <human>        (candidate 0.5–1.0 %)
SL POLICY:                      fixed-point, loss protection (LOCKED); numeric <human>
SL CONFIG:                      <human>        (default 2.0 points, clamped by stops_level)
MAX EXPOSURE:                   <human>        (default 5000.0 USD)
MAX DRAWDOWN:                   <human>        (default 10.0 %; window unspecified)
MAX SPREAD:                     <human>        (default 5.0; derive from Cent data)
MARGIN BUFFER:                  <human>        (default 50.0 USD free margin)
LOT SIZING:                     risk-budget %-of-equity / lot (LOCKED)
LOT ROUNDING:                   floor to step (LOCKED)
BROKER CONSTRAINT POLICY:       min/max/step + stops_level enforced → REJECT (LOCKED)
SLIPPAGE/COMMISSION TREATMENT:  <human>        (option 1 cost add-on v2 / option 2 deferred)
FAIL-CLOSED POLICY:             any critical uncertainty → REJECT (LOCKED)
ABC EXIT:                       NET_PROFIT > 0 → close; no TP (LOCKED)
```

## Pending Human Decisions

1. **Risk % per trade** (recommend 0.5–1.0 % band).
2. **SL distance / method** (recommend fixed-point provisional, e.g. 2.0,
   revisit with volatility after paper data).
3. **Max exposure** (recommend scale from equity post-paper, e.g. 50–200 %
   of equity exposure cap).
4. **Max drawdown + window** (recommend ≤ 10 % with circuit-breaker reset
   policy Definition).
5. **Max spread threshold** (recommend derived from HFM Cent XAUUSDc data,
   NEVER Premium XAUUSD).
6. **Margin buffer + leverage assumption** (from real HFM Cent spec).
7. **Slippage/commission treatment** (add-to-risk vs deferred-verification).
8. **Compounding reinvestment ratio** (Obsidian itself leaves this open —
   gated for the compounding milestone).

Until approved, `RiskConfig` defaults remain PROVISIONAL test/paper values and
must NOT be treated as LOCKED for any live decision.

## Validation

- Full suite: **449 passed** (`pytest`), `ruff check .` clean,
  `ruff format --check .` clean (122 files), `mypy collector shared
  ai_decision risk_engine` clean (65 files). No code change required for this
  evaluation; existing tests already cover budget/clamping/SL/margin/exposure/
  spread/drawdown/NaN/None inputs. No configuration file changed.

## Risks/Limitations

- No HFM Cent XAUUSDc economics in the repo (Phase A blocked by the ISP/MITM
  warning). Any numeric decision made now is unverified against the real
  instrument.
- Lot/risk math is theoretical; realized PnL includes spread/commission/swap
  (FR-004) which the risk estimate currently excludes — see decision #7.
- Stale context default (10 s) is a latency-budget guess; scalping real latency
  profile unknown until Phase A collection.

## Next Action

Blocked on the 8 human decisions above. Once approved: update
`RiskConfig` defaults → add/extend tests for the newly locked numbers → final
commit `feat(risk): finalize risk configuration` → push → unlock the
Lot/Execution design using the confirmed config. Until then, keep the repo at
PROVISIONAL mode with the current 449-green baseline.