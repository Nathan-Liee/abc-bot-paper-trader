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
| ASIAN | ✅ | 2026-08-17 00:38:12 – 01:46:41 | 2240 |
| LONDON | ✅ | 2026-08-17 09:56:14 – 10:56:13 | 3594 |
| LONDON/NY OVERLAP | ❌ | — | 0 |
| NEW_YORK | ❌ | — | 0 |
| OFF_HOURS | ❌ | — | 0 |

Two sessions collected (ASIAN + LONDON). Collection strategy switched
2026-08-17 08:47 +07 to **short-window collection (30–60 min)** — session
windows run only while the PC is available.

## 5b. Collection Window Record

| Window | Session | Start (UTC) | End (UTC) | Timezone | Samples |
| --- | --- | --- | --- | --- | --- |
| 1 | ASIAN | 2026-08-17 00:38:12 | 2026-08-17 00:48:12 | UTC (label: Asia/Jakarta +07) | 600 |
| 2 | ASIAN | 2026-08-17 00:51:11 | 2026-08-17 01:11:11 | UTC (label: Asia/Jakarta +07) | 1199 |
| 3 | ASIAN (partial, aborted continuous run) | 2026-08-17 01:39:26 | 2026-08-17 01:46:41 | UTC (label: Asia/Jakarta +07) | 441 |
| 4 | LONDON | 2026-08-17 09:56:14 | 2026-08-17 10:56:13 | UTC (label: Asia/Jakarta +07) | 3594 |

Window 3 is the retained tail of a 22.4 h continuous run that was terminated
per the short-window strategy switch; its samples are valid ASIAN evidence
(schema-identical, 0 malformed) and were kept per the do-not-delete rule.

## 6. Raw Sample Summary

- Total samples: **5834** (4 collection windows: 600 s + 1200 s + 441 s + 3600 s @ 1 s).
- Timestamps: 2026-08-17 00:38:12+00:00 → 10:56:13+00:00 UTC.
- Bid range: 4387.42 – 4411.31 · Ask range: 4387.78 – 4411.67.
- All records `source = HFM_CENT_READ_ONLY`, `symbol = XAUUSDc`.
- Raw data: `docs/validation/runtime/multi-session/xauusdc-spread-timeseries.jsonl`.

## 7. Per-Session Spread Statistics

### ASIAN (n=2240)

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

### LONDON (n=3594)

| Metric | Points |
| --- | --- |
| Window (UTC) | 09:56:14 – 10:56:13 |
| min | 34 |
| median | 34 |
| mean | 34.47 |
| P75 | 34 |
| P90 | 36 |
| P95 | 36 |
| P99 | 36 |
| max | 36 |
| above 36 pts | 0 (0.0 %) |
| above 40 pts | 0 (0.0 %) |
| above 45 pts | 0 (0.0 %) |
| above 50 pts | 0 (0.0 %) |
| spread values | 34 pts (76.5 %), 36 pts (23.5 %), 35 pts (0.03 %) |
| longest run > 34 pts | 845 s |

London spread is TIGHTER than Asian: median 34 (vs 36), 76.5 % of samples at
34 pts, zero samples above 36 — no widening, no spikes during the 09:56–10:56
UTC window.

## 8. Aggregate Spread Distribution

All observed sessions, n=5834:

- Spread values: 34 pts (65.6 %) and 36 pts (34.3 %) and 35 pts (one sample).
- Total longest continuous run above 34 pts: 2004 s; above 36/40/45: 0 s.
- No outlier bursts, no widening in any observed window (ASIAN + LONDON).
- Across-session drift: NONE observed — both ASIAN and LONDON stayed within
  34–36 pts; London median is 2 pts lower than Asian.

## 9. Threshold Sensitivity

Given the observed distribution across both sessions (34–36 pts, mode 34):

| Threshold | Samples ≤ threshold | Acceptance | Rejection | Note |
| --- | --- | --- | --- | --- |
| 36 | 5834 | 100 % | 0 % | all observed pass |
| 40 | 5834 | 100 % | 0 % | +4 pt headroom |
| 45 (current) | 5834 | 100 % | 0 % | +9–11 pt headroom |
| 50 | 5834 | 100 % | 0 % | +14–16 pt headroom |

**45 is neither too restrictive nor too permissive within this data** — all
samples pass, and it provides 9–11 points of headroom over the observed max.
However, **two sessions cannot prove headroom adequacy** for news spikes or
NY/overlap transitions; the data is insufficient to lock 45.

## 10. SL vs Spread Analysis

- Observed spread max = 36 pts (both ASIAN and LONDON). `sl_distance_points =
  50` (0.50 price) clears the spread by 14 points = 0.14 price units of
  economic headroom.
- SL > spread invariant: holds (50 > 36) with 38.9 % margin.
- Session-specific spread risk: NY/overlap transitions not yet observable —
  if NY/overlap lifts spread > 50, the 50-pt SL would sit inside the adverse
  spread; that cannot be ruled out without those sessions.
- Verdict: 50 pts remains economically sensible for the observed spread
  (ASIAN + LONDON), but is NOT proven robust across all sessions. Do NOT infer
  profitability — this is spread/safety analysis only.

## 11. Market-Transition Observations

- No London open observed (collection started 09:56 UTC, well into session) —
  no reopen/transition occurred during collection.
- No evidence of spread widening at session boundaries in this task.
- Evidence from both sessions shows spread near the low end (34–36; London
  median 34, 76.5 % at the 34-pt floor) — consistent with the earlier
  61-sample observation (34–36, median 36).

## 12. Comparison with Existing 61-Sample Evidence

| Metric | Prior (61 samples) | ASIAN (2240) | LONDON (3594) |
| --- | --- | --- | --- |
| Window | 09:35–09:36 +07 (Asian) | 07:38–08:46 +07 (Asian) | 16:56–17:56 +07 (London) |
| min | 34 | 34 | 34 |
| median | 36 | 36 | 34 |
| max | 36 | 36 | 36 |
| above 36 | 0 | 0 | 0 |
| Price area | ~4370 | ~4387–4411 | ~4392–4406 |

Consistent spread behavior across windows and sessions: spread is stable at
34–36 points, never exceeding 36. London median (34) is 2 pts < Asian (36) —
same floor, no widening, no regime shift. The 5834-sample combined evidence
strengthens the conclusion without proving overlap/NY.

## 13. Impact on PAPER_VALIDATION_V0.1

- `max_spread_points = 45`: no sample exceeded it (0 % rejection) in ASIAN or
  LONDON. Consistent with a permissive-but-safe threshold for both observed
  sessions. **Not** proven for NY/overlap news conditions.
- `sl_distance_points = 50`: remains economically valid for observed spread
  (max 36 both sessions); headroom 14 pts above max. Evidence suggests no
  change needed for the paper profile **for ASIAN + LONDON**, but overlap/NY
  evidence is required before production lock.
- No other v0.1 parameter was touched. Profile unchanged.

## 14. Production-Lock Readiness

| Parameter | Ready to lock? | Evidence status |
| --- | --- | --- |
| SL 50 pts | No | INSUFFICIENT EVIDENCE (ASIAN + LONDON only; NY/overlap pending) |
| Max spread 45 pts | No | INSUFFICIENT EVIDENCE (ASIAN + LONDON only; NY/overlap pending) |
| Exposure/margin/cost | No | NOT OBSERVED / insufficient |

Locking any spread/SL threshold requires NY and overlap windows plus a
news/transition sample. **Production RiskConfig remains UNLOCKED.**

## 15. Remaining Evidence Gaps

1. London/NY overlap session (12:00–16:00 UTC) spread distribution.
2. New York session (16:00–21:00 UTC) spread distribution.
3. OFF_HOURS (21:00–24:00 UTC) — optional.
4. Session transitions (open/reopen, DST edges) — London open not captured.
5. News/volatility bursts (cannot be scheduled).
6. Full 24-hour rolling spread profile.
7. Slippage and realized costs (needs execution paper/demo — out of scope here).

## 16. Verdict

**PARTIAL — MORE SESSION EVIDENCE NEEDED** — 5834 samples across ASIAN
(n=2240, median 36) and LONDON (n=3594, median 34); spread stable 34–36 pts,
0 % > 45 in every observed window; every sample passes the v0.1
`max_spread_points=45` and clears SL 50 by ≥14 pts. But overlap/NY/off-hours
and transition windows remain unobserved, so neither 45 nor 50 can be locked
for production.

## 17. Next Action

Short-window protocol (30–60 min, ~1 s interval, same JSONL schema, append):
run the read-only collector during the next available session window — the
**LONDON/NY overlap ~19:00–22:00 +07 (12:00–15:00 UTC)**, then NY
~21:00–03:00 +07, then OFF_HOURS ~04:00–07:00 +07 if the PC is available.
After each window: recompute distribution, merge into
`xauusdc-spread-timeseries.jsonl`, re-evaluate `max_spread_points` and
`sl_distance_points` lock-readiness. Production RiskConfig stays UNLOCKED
until then. Do not commit until a new collection window completes.