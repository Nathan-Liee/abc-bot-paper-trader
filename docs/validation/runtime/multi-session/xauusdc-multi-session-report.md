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
| LONDON/NY OVERLAP | ✅ | 2026-08-17 12:17:16 – 13:05:36 | 1966 |
| NEW_YORK | ❌ | — | 0 |
| OFF_HOURS | ❌ | — | 0 |

Three sessions collected (ASIAN + LONDON + LONDON/NY OVERLAP). Short-window
collection protocol (30–60 min, ~1 s interval) active — session windows run
only while the PC is available.

## 5b. Collection Window Record

| Window | Session | Start (UTC) | End (UTC) | Timezone | Samples |
| --- | --- | --- | --- | --- | --- |
| 1 | ASIAN | 2026-08-17 00:38:12 | 2026-08-17 00:48:12 | UTC (label: Asia/Jakarta +07) | 600 |
| 2 | ASIAN | 2026-08-17 00:51:11 | 2026-08-17 01:11:11 | UTC (label: Asia/Jakarta +07) | 1199 |
| 3 | ASIAN (partial, aborted continuous run) | 2026-08-17 01:39:26 | 2026-08-17 01:46:41 | UTC (label: Asia/Jakarta +07) | 441 |
| 4 | LONDON | 2026-08-17 09:56:14 | 2026-08-17 10:56:13 | UTC (label: Asia/Jakarta +07) | 3594 |
| 5 | LONDON_NY_OVERLAP | 2026-08-17 12:17:16 | 2026-08-17 12:35:03 | UTC (label: Asia/Jakarta +07) | 1067 |
| 6 | LONDON_NY_OVERLAP | 2026-08-17 12:50:37 | 2026-08-17 13:05:36 | UTC (label: Asia/Jakarta +07) | 899 |

Window 5 was interrupted by a session context compaction (process killed
mid-run); 1067 valid samples were recovered. A null-byte trailing line was
stripped during file re-validation. Window 6 is the continuation collection.

Window 3 is the retained tail of a 22.4 h continuous run that was terminated
per the short-window strategy switch; its samples are valid ASIAN evidence
(schema-identical, 0 malformed) and were kept per the do-not-delete rule.

## 6. Raw Sample Summary

- Total samples: **7800** (6 collection windows: 600 s + 1200 s + 441 s + 3600 s + 1067 s + 899 s @ 1 s).
- Timestamps: 2026-08-17 00:38:12+00:00 → 13:05:36+00:00 UTC.
- Bid range: 4379.69 – 4411.31 · Ask range: 4380.05 – 4411.67.
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

### LONDON_NY_OVERLAP (n=1966)

| Metric | Points |
| --- | --- |
| Window (UTC) | 12:17:16 – 13:05:36 |
| min | 34 |
| median | 36 |
| mean | 38.20 |
| P75 | 41 |
| P90 | 50 |
| P95 | 50 |
| P99 | 50 |
| max | 50 |
| above 36 pts | 543 (27.62 %) |
| above 40 pts | 543 (27.62 %) |
| above 45 pts | 374 (19.02 %) |
| above 50 pts | 0 (0.0 %) |
| spread values | 34 (36.9 %), 36 (35.2 %), 50 (10.1 %), 41 (7.0 %), 48 (3.4 %), 47 (3.0 %), 49 (1.6 %), 46 (1.0 %), 45 (0.9 %), 43–44 (0.7 %), 35 (0.2 %) |
| longest run > 34 pts | 1240 s |
| longest run > 36 pts | 543 s |
| longest run > 40 pts | 543 s |
| longest run > 45 pts | 374 s |

CRITICAL FINDING: Overlap spread is dramatically wider than ASIAN and LONDON.
- 27.62 % of samples exceed 36 pts (the max of all prior sessions).
- 19.02 % exceed 45 pts (the current `max_spread_points` threshold).
- Max = 50 pts — exactly equal to `sl_distance_points`.
- Longest continuous run above 45 pts: 374 seconds (~6.2 minutes).
- Bimodal distribution: cluster at 34–36 (72.1 %) and cluster at 45–50 (18.9 %).
- The 45–50 cluster represents a sustained widening event, not a single spike.

## 8. Aggregate Spread Distribution

All observed sessions, n=7800:

- Spread values: 34 pts (58.4 %), 36 pts (34.6 %), 50 pts (2.6 %), 41 pts (1.8 %),
  48 pts (0.8 %), 47 pts (0.7 %), 49 pts (0.4 %), 46 pts (0.2 %), 45 pts (0.2 %),
  43–44 pts (0.2 %), 35 pts (0.1 %).
- Total longest continuous run above 34 pts: 3244 s; above 36 pts: 543 s;
  above 40 pts: 543 s; above 45 pts: 374 s.
- Across-session variability: SIGNIFICANT — ASIAN and LONDON occupy a tight
  34–36 band; LONDON_NY_OVERLAP introduces a new 41–50 band absent in prior
  sessions. The overlap window is the first evidence of spread exceeding 36.

## 9. Threshold Sensitivity

Given the observed distribution across all three sessions (34–50 pts):

| Threshold | Samples ≤ threshold | Acceptance | Rejection | Note |
| --- | --- | --- | --- | --- |
| 36 | 7257 | 93.04 % | 6.96 % | rejects all overlap spike samples |
| 40 | 7257 | 93.04 % | 6.96 % | rejects same set (no 37–40 observed) |
| 45 (current) | 7426 | 95.21 % | 4.79 % | rejects 374 overlap samples (~19 % of overlap) |
| 50 | 7800 | 100 % | 0 % | max observed = threshold boundary |

**45 pts rejects ~19 % of LONDON/NY OVERLAP samples** — nearly 1 in 5 ticks
during the overlap window. This is economically significant: if the bot
operates during overlap, a 45-pt filter would block ~1/5 of all entry
opportunities. However, the blocked ticks coincide with the widest spread
conditions (45–50 pts), where slippage risk is highest — this may be
desirable from a safety perspective.

## 10. SL vs Spread Analysis

- Observed spread max = 50 pts (LONDON_NY_OVERLAP). `sl_distance_points = 50`
  clears the spread by 0 points at the peak — ZERO economic headroom.
- SL > spread invariant: holds (50 ≥ 50) with 0 % margin at peak overlap.
- During the 45–50 spread burst (374 seconds), the SL distance was equal to or
  barely above the spread — any slippage at entry could place the SL inside the
  adverse spread.
- For ASIAN and LONDON: SL 50 > max spread 36, headroom 14 pts, 38.9 % margin.
- Session-specific risk: the overlap window is the first session where SL 50
  has no margin over spread. If NY session shows similar or wider spreads,
  SL 50 may be econ-invalid for overlap+NY operation.
- Verdict: SL 50 pts is SAFE for ASIAN + LONDON (14 pt margin) but MARGINAL for
  LONDON/NY OVERLAP (0 pt margin at peak). Do NOT infer profitability.

## 11. Market-Transition Observations

- No London open observed (collection started 09:56 UTC, well into session).
- LONDON → OVERLAP transition: NOT directly captured (gap between LONDON end
  10:56 UTC and OVERLAP start 12:17 UTC). But the spread regime shift is
  evident: LONDON max 36 → OVERLAP max 50 within ~75 minutes.
- Within the overlap window, spread exhibited bimodal behavior: prolonged
  periods at 34–36 interspersed with sustained bursts at 45–50. The bursts
  appeared coherent (374 s continuous above 45), suggesting a structural
  liquidity event rather than random noise.

## 12. Comparison with Existing 61-Sample Evidence

| Metric | Prior (61) | ASIAN (2240) | LONDON (3594) | OVERLAP (1966) |
| --- | --- | --- | --- | --- |
| Window | 09:35 +07 | 07:38–08:46 +07 | 16:56–17:56 +07 | 19:17–20:05 +07 |
| min | 34 | 34 | 34 | 34 |
| median | 36 | 36 | 34 | 36 |
| mean | — | 35.04 | 34.47 | 38.20 |
| P95 | — | 36 | 36 | 50 |
| max | 36 | 36 | 36 | 50 |
| above 36 | 0 | 0 | 0 | 543 (27.6 %) |
| above 45 | — | — | — | 374 (19.0 %) |
| Price area | ~4370 | ~4387–4411 | ~4392–4406 | ~4380–4404 |

Three distinct spread regimes observed:
1. ASIAN: stable 34–36, median 36 — tight, no spikes.
2. LONDON: stable 34–36, median 34 — tightest, no spikes.
3. OVERLAP: bimodal 34–36 + 45–50, median 36 — dramatically wider, sustained bursts.

## 13. Impact on PAPER_VALIDATION_V0.1

- `max_spread_points = 45`: ASIAN and LONDON pass 100 %, but OVERLAP rejects
  19.02 % of samples. The threshold is NOT too permissive (it correctly blocks
  high-spread ticks), but its downside is entry-frequency loss during overlap.
  **Not proven for NY session (not yet collected).**
- `sl_distance_points = 50`: SAFE for ASIAN + LONDON (14 pt headroom), but
  MARGINAL for OVERLAP — max spread = 50 = SL distance, zero headroom at peak.
  If NY shows similar spread behavior, SL 50 may need to be increased for
  overlap+NY operation, or the bot should avoid trading during peak overlap.
  **Not proven for NY session.**
- Operating window: if bot restricts to ASIAN + LONDON only (UTC 00–12),
  both 45 and 50 have comfortable margins. If overlap+NY are included,
  both parameters need re-evaluation.
- No other v0.1 parameter was touched. Profile unchanged.

## 14. Production-Lock Readiness

| Parameter | Ready to lock? | Evidence status |
| --- | --- | --- |
| SL 50 pts | No | INSUFFICIENT — safe for ASIAN/LONDON, MARGINAL for overlap (0 pt margin). NY pending. |
| Max spread 45 pts | No | INSUFFICIENT — valid filter but 19 % overlap rejection. NY pending. |
| Exposure/margin/cost | No | NOT OBSERVED / insufficient |

Locking any spread/SL threshold requires NY session evidence plus
news/transition coverage. **Production RiskConfig remains UNLOCKED.**

## 15. Remaining Evidence Gaps

1. New York session (16:00–21:00 UTC) spread distribution — NEXT.
2. OFF_HOURS (21:00–24:00 UTC) — optional.
3. Session transitions (London open, NY open) — not directly captured.
4. News/volatility bursts (cannot be scheduled) — overlap burst observed but
   cause unknown (no news feed).
5. Full 24-hour rolling spread profile.
6. Slippage and realized costs (needs execution paper/demo — out of scope here).

## 16. Verdict

**PARTIAL — MORE SESSION EVIDENCE NEEDED** — 7800 samples across ASIAN
(n=2240, 34–36 pts), LONDON (n=3594, 34–36 pts), and LONDON_NY_OVERLAP
(n=1966, 34–50 pts). The overlap session is the first evidence of spread
exceeding 36 pts: 19 % of overlap samples > 45 pts, max 50 pts = SL distance.
SL 50 has zero headroom at peak overlap. max_spread 45 rejects ~19 % of
overlap samples. NY session remains uncollected — neither parameter can be
locked for production.

## 17. Next Action

Short-window protocol: run the read-only collector during the **NEW_YORK
session ~21:00–22:00 +07 (14:00–15:00 UTC), 3600 s @ 1 s interval**,
session_label `NEW_YORK`. After NY: recompute aggregate (ASIAN + LONDON +
OVERLAP + NY), re-evaluate `max_spread_points` and `sl_distance_points`
lock-readiness, evaluate operating window. Production RiskConfig stays
UNLOCKED. Commit only after NY window completes.