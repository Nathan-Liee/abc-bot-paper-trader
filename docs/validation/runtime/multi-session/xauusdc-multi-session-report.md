# XAUUSDc Multi-Session Runtime Evidence

Report date: 2026-08-17 · Verdict: **PARTIAL — MORE SESSION EVIDENCE NEEDED**

## 1. Objective

Collect multi-session read-only market telemetry for HFM Cent `XAUUSDc` to
re-evaluate `PAPER_VALIDATION_V0.1` (especially `max_spread_points=45` and
`sl_distance_points=50`) before any Production RiskConfig lock. Pure
observation — no trading, no order, no account change.

## 2. Environment

| Item | Value |
| --- | --- |
| Terminal | MT5 x64 build 6111 (PID 11068), HFM Cent REAL |
| Server / account | HFMarketsGlobal-Live19 · 229105805 |
| Symbol | `XAUUSDc` (digits 2, point 0.01, tick 0.01, tick_value 1.0 USC, contract 1.0) |
| Access | `MetaTrader5` Python IPC (read-only) |
| Collection tool | isolated, read-only script (temp dir, not committed) |

## 3. Safety Boundary

- Only `mt5.initialize()`, `symbol_info`, `symbol_info_tick`, `account_info`, `shutdown`.
- Static guard in the collection script fails fast if any trade-capable call
  token appears in its source.
- Zero order/position/modify/leverage/symbol-mutation capability.
- Balance/equity remain unobserved and unused.

## 4. Collection Method

- `symbol_info_tick("XAUUSDc")` sampled ~1×/second.
- Session label derived from UTC hour (approximation, NOT from MT5):
  ASIAN 00–07, LONDON 07–12, LONDON_NY_OVERLAP 12–16, NEW_YORK 16–21, OFF_HOURS 21–24.
- Output: append-mode JSONL, UTF-8, one record per tick.

## 5. Session Coverage

| Session | Collected | Window (UTC) | Samples |
| --- | --- | --- | --- |
| ASIAN | ✅ | 2026-08-17 00:38:12 – 01:11:11 | 1799 |
| LONDON | ❌ | — | 0 |
| LONDON/NY OVERLAP | ❌ | — | 0 |
| NEW_YORK | ❌ | — | 0 |
| OFF_HOURS | ❌ | — | 0 |

Only the Asian session was observable during the collection windows.

## 6. Raw Sample Summary

- Total samples: **1799** (2 collection runs: 600 s + 1200 s @ 1 s).
- Timestamps: 2026-08-17 00:38:12+00:00 → 01:11:11+00:00 UTC.
- Bid range: 4387.42 – 4411.31 · Ask range: 4387.78 – 4411.67.
- All records `source = HFM_CENT_READ_ONLY`, `symbol = XAUUSDc`.
- Raw data: `docs/validation/runtime/multi-session/xauusdc-spread-timeseries.jsonl`.

## 7. Per-Session Spread Statistics

### ASIAN (n=1799)

| Metric | Points |
| --- | --- |
| min | 34 |
| median | 36 |
| mean | 35.04 |
| P75 | 36 |
| P90 | 36 |
| P95 | 36 |
| P99 | 36 |
| max | 36 |
| above 36 pts | 0 (0.0 %) |
| above 40 pts | 0 (0.0 %) |
| above 45 pts | 0 (0.0 %) |
| above 50 pts | 0 (0.0 %) |

## 8. Aggregate Spread Distribution

Same as the single observed session (only ASIAN data), n=1799:

- Spread values: 36 pts (52.1 %) and 34 pts (47.9 %); no other values.
- Longest continuous run above 34 pts: 74 s; above 36/40/45: 0 s.
- No outlier bursts, no widening during the ~33-minute combined window.

## 9. Threshold Sensitivity

Given the observed distribution (34–36 pts, mode 34):

| Threshold | Samples ≤ threshold | Acceptance | Rejection | Note |
| --- | --- | --- | --- | --- |
| 36 | 600 | 100 % | 0 % | all observed pass |
| 40 | 600 | 100 % | 0 % | +4 pt headroom |
| 45 (current) | 600 | 100 % | 0 % | +9–11 pt headroom |
| 50 | 600 | 100 % | 0 % | +14–16 pt headroom |

**45 is neither too restrictive nor too permissive within this data** — all
samples pass, and it provides 9–11 points of headroom over the observed max.
However, **one session cannot prove headroom adequacy** for news spikes or
session transitions; the data is insufficient to lock 45.

## 10. SL vs Spread Analysis

- Observed spread max = 36 pts. `sl_distance_points = 50` (0.50 price) clears
  the spread by 14 points = 0.14 price units of economic headroom.
- SL > spread invariant: holds (50 > 36) with 38.9 % margin.
- Session-specific spread risk: not observable from this single window —
  if NY/London transitions lift spread > 50, the 50-pt SL would sit inside the
  adverse spread; that cannot be ruled out without those sessions.
- Verdict: 50 pts remains economically sensible for the observed spread, but is
  NOT proven robust across sessions. Do NOT infer profitability — this is
  spread/safety analysis only.

## 11. Market-Transition Observations

- None (single continuous Asian window; no London open, no NY open, no
  reopen/transition occurred during collection).
- No evidence of spread widening at session boundaries in this task.
- New evidence collected during the Asian session shows spread near the low end
  (34–36) — consistent with the earlier 61-sample observation (34–36, median 36).

## 12. Comparison with Existing 61-Sample Evidence

| Metric | Prior (61 samples) | This (1799 samples) |
| --- | --- | --- |
| Window | 09:35–09:36 +07 (Asian) | 07:38–08:11 +07 (Asian) |
| min | 34 | 34 |
| median | 36 | 36 |
| max | 36 | 36 |
| above 36 | 0 | 0 |
| Price area | ~4370 | ~4387–4411 |

Consistent spread behavior across windows within the Asian session: spread is
stable at 34–36 points, never exceeding 36. The 1799-sample window strengthens
the conclusion for the Asian session without proving other sessions.

## 13. Impact on PAPER_VALIDATION_V0.1

- `max_spread_points = 45`: no sample exceeded it (0 % rejection). Consistent
  with a permissive-but-safe threshold for the Asian session. **Not** proven for
  London/NY.
- `sl_distance_points = 50`: remains economically valid for observed spread;
  headroom 14 pts above max. Evidence suggests no change needed for the paper
  profile **for the Asian session**, but cross-session evidence is required
  before production lock.
- No other v0.1 parameter was touched. Profile unchanged.

## 14. Production-Lock Readiness

| Parameter | Ready to lock? | Evidence status |
| --- | --- | --- |
| SL 50 pts | No | INSUFFICIENT EVIDENCE (single session) |
| Max spread 45 pts | No | INSUFFICIENT EVIDENCE (single session) |
| Exposure/margin/cost | No | NOT OBSERVED / insufficient |

Locking any spread/SL threshold requires London, NY, and overlap windows plus a
news/transition sample. **Production RiskConfig remains UNLOCKED.**

## 15. Remaining Evidence Gaps

1. London session (07:00–12:00 UTC) spread distribution.
2. New York session (12:00–21:00 UTC) + London/NY overlap.
3. Session transitions (open/reopen, DST edges).
4. News/volatility bursts (cannot be scheduled).
5. Full 24-hour rolling spread profile.
6. Slippage and realized costs (needs execution paper/demo — out of scope here).

## 16. Verdict

**PARTIAL — MORE SESSION EVIDENCE NEEDED** — 1799 samples of stable Asian
spread (34–36 pts, 0 % > 45) were collected; every observed sample passes the
v0.1 `max_spread_points=45` and clears SL 50 by ≥14 pts. But London/NY/overlap
and transition windows remain unobserved, so neither 45 nor 50 can be locked
for production.

## 17. Next Action

Run the read-only collection script during London and NY windows (e.g. 14:00–16:00
+07 London; 21:00–03:00 +07 NY/overlap) using the same JSONL schema, merge into
`xauusdc-spread-timeseries.jsonl`, recompute aggregate distribution, then
re-evaluate `max_spread_points` and `sl_distance_points` lock-readiness.
Production RiskConfig stays UNLOCKED until then.