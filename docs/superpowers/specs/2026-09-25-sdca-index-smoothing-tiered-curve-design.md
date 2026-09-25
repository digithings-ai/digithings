# SDCA Composite-Index Smoothing + Tiered Response Curve — Design

Date: 2026-09-25
Status: proposed (approved by Chris in chat 2026-09-25; write-up pending his review of this file)
Owners: digiquant / SDCA strategy research
Related: `docs/superpowers/specs/2026-09-24-sdca-recalibration-v1-design.md` (prior round, Phases 1-3 done — M2/RSI source-level fix landed there), `src/digiquant/strategies/sdca/RESEARCH_STATE.md`, `scripts/build_round8_diagnostic_tearsheet.py`, `scripts/run_aggregate_reweight_full17_fixed_index.py` (canonical 17-name `SURVIVING_INDICATORS` pool), commit `4e05eda9c` ("fix(sdca): damp M2/RSI composite z-score spikiness at the source").

## 1. Problem

Chris reviewed round 8's tearsheet (`btc_sdca_round8`) and raised feedback: the composite valuation index is visibly spiky, traceable to M2 and RSI; he wants the index smoothed to look like the less-performant strategies' indices; he wants a tiered response curve — medium-term signals should move allocation by roughly half of the maximum rate, while true long/short-term extremes should still drive 100% investment/divestment; and he wants as many of the ~17 available indicators included as possible, gated on each indicator's z-scoring being verified free of "weird behaviors" once included.

**Important context discovered while grounding this spec**: the round-8 tearsheet Chris reviewed (`generated_at: 2026-09-24T13:50:01Z`) was generated roughly two hours *before* a source-level M2/RSI fix (commit `4e05eda9c`, from a prior, separate round of feedback documented in `2026-09-24-sdca-recalibration-v1-design.md`) landed in the codebase at 15:56:50 UTC the same day. That fix added a 5-day causal EMA smoothing pass inside `m2_liquidity_z()` and moderated the RSI curve power (`_RSI_CURVE_POWER`, 4.0 → 3.5) specifically to damp the same spikiness complaint. So the tearsheet Chris reacted to was already stale relative to an in-flight fix.

Re-running `scripts/build_round8_diagnostic_tearsheet.py` against current (post-fix) code changes the measured numbers (`net_profit_pct` 3523.5% vs. the ~6000% eyeballed against the stale run; `max_drawdown_pct` unchanged at -61.8%, as expected since the fix only touches index shape, not curve shape) and a direct roughness measurement on the regenerated index (`risk_from_weighted_z` output, `ROUND8_WEIGHTS`, 3137 trading days) shows:

| Metric | Value |
|---|---|
| mean \|Δrisk\| per day | 1.03 points |
| p95 \|Δrisk\| per day | 2.93 points |
| p99 \|Δrisk\| per day | 4.37 points |
| max \|Δrisk\| in one day | 10.0 points |
| days with \|Δrisk\| > 2 pts | 407 / 3137 (13%) |
| days with \|Δrisk\| > 5 pts | 17 / 3137 |
| days with \|Δrisk\| > 10 pts | 1 / 3137 |

So the landed fix genuinely helped on average (a ~1-point mean daily move is not itself alarming) but did not eliminate the spikiness Chris is reacting to — there is still a meaningful tail of double-digit-point single-day jumps. **This does not invalidate anything Chris asked for.** It reframes the scope: Component 1 below is "verify, extend, and fix a newly-found second bug" rather than "build a fix from scratch," and the round-8-specific reason the fix's effect is muted is independently explainable (see 2.1).

This document covers the four components of the approved design:

1. **Composite-index smoothing** — finish what the landed M2/RSI fix started: diagnose roughness across the full indicator pool, generalize the smoothing utility, and fix a second, distinct bug found this round.
2. **Tiered response curve** — extend `SdcaCurveShape` so medium-term signals produce a partial (~50% of max rate) allocation change, reserving the full 100% response for true extremes.
3. **Full ~17-indicator pool re-weight** — re-run the existing reweight/ablation machinery over the complete, previously-validated `SURVIVING_INDICATORS` pool (not the narrow 5-indicator round-8 config, and not the ablation driver's broader 22-name default).
4. **Testing** — regression coverage for all of the above, keeping `tests/dq/strategies/sdca/` green.

This is diagnostic/research work per the standing accept gate — nothing here writes `settings.json` or promotes a candidate in `RESEARCH_STATE.md`'s validated-candidate section without Chris's explicit accept.

## 2. Root causes and fixes

### 2.1 Composite index roughness

**Already fixed (prior round, commit `4e05eda9c`)**: `m2_liquidity_z()` (`indicator_catalog.py`) applies `causal_ema_smooth(z, half_life=_M2_SMOOTHING_HALFLIFE_DAYS=5.0)` to turn M2's monthly-print step function into a few-day ramp. `rsi_continuous_z()` (`price_oscillators.py`) moderates its power-curve mapping (`_RSI_CURVE_POWER = 3.5`, down from the quartic 4.0 that caused the original flatline-then-spike shape), the lowest value that clears the existing 2026-09-07 anti-pegging regression guard.

**Why round 8 still looks spiky despite the fix — three compounding causes, only one of which the landed fix touched**:

- **(a) M2's remaining ramp is still visible at 71% weight.** `ROUND8_WEIGHTS` (`build_round8_diagnostic_tearsheet.py`) sets `m2=1.0` against `rs_eth=onchain_asopr=fear_greed=weekly_monthly_rsi=0.1` each and `power_law=0.0` — M2 alone is 1.0 of a 1.4 weight total, i.e. ~71% of the blend. Even a 5-day EMA ramp, at that concentration, reads as a near-step on an 8-year chart. This is a config problem, not a code problem — full-pool dilution (Component 3) is the real fix here, independent of any further per-indicator smoothing.
- **(b) Other timeframe-blended indicators never received M2's treatment.** `weekly_rsi_z`, `monthly_rsi_z`, `weekly_macd_z`, `monthly_macd_z`, and their confluence variants (`monthly_rsi_confluence_z`, `weekly_monthly_rsi_confluence_z`, and the MACD equivalents) all broadcast a weekly/monthly-cadence value to daily via `_asof_to_daily()`'s backward as-of join (`price_oscillators.py`) — structurally the same step-function pattern M2 had, but none of them got an anti-spike EMA pass. Only the RSI curve's power was softened; the underlying cadence-driven step was never smoothed for any oscillator.
- **(c) `agreement_scaled_blend`'s sign-crossing multiplier is a second, previously-unidentified bug.** `agreement_scaled_blend()` (`price_oscillators.py:458-497`, used by every RSI/MACD confluence function) blends two timeframe legs with a discontinuous multiplier: same-sign agreement scales up by `1.0 + agreement_boost * agreement_frac`, opposite-sign disagreement flattens to `disagreement_damp`, and either leg crossing exactly zero passes through at `1.0`. This multiplier jumps at every sign-crossing — a kink independent of, and not addressed by, the RSI curve-power fix.

**Fix, this round**:

1. **Systematic roughness diagnostic.** A small script/module computing the day-over-day `|Δz|` (or `|Δrisk|`) distribution — mean, p95, p99, max, and spike-count above threshold, the same shape as the table above — run per-indicator across all 17 `SURVIVING_INDICATORS`, not just M2/RSI. This surfaces which of the remaining oscillator variants (from 2.1(b)) actually need smoothing versus which are already smooth enough (e.g., `power_law`, the on-chain indicators, and `dxy` are not cadence-broadcast the same way and may already be fine).
2. **Generalize `causal_ema_smooth` as a reusable per-indicator utility.** It already exists in `composite_risk.py` and is already used by `m2_liquidity_z`; apply it at the same call sites the diagnostic flags, with a cadence-appropriate half-life per indicator (weekly-cadence legs likely want a shorter half-life than monthly-cadence legs — M2's 5-day value was tuned for a monthly print; a weekly print should ramp faster). Land each new half-life as a named constant next to its indicator, following the `_M2_SMOOTHING_HALFLIFE_DAYS` pattern.
3. **Fix `agreement_scaled_blend`'s discontinuity.** Replace the two-branch step (`same-sign → boost`, `opposite-sign → flat damp`) with a continuous function of signed agreement — e.g. interpolate the multiplier linearly (or via a smoothstep) across the sign-crossing zone instead of switching abruptly, so the multiplier itself has no kink. Exact interpolation shape to be finalized during implementation against the existing `test_price_oscillators.py` fixtures (there is already at least one crash-response regression test that depends on `agreement_scaled_blend`'s current behavior at extremes — any change must preserve behavior at the far tails, only smooth the transition zone).

### 2.2 Tiered response curve

`SdcaCurveShape` (`curve_shape.py`) has exactly one knee and one curvature per side: `rate_at(risk)` ramps from 0 at `buy_knee_risk`/`sell_knee_risk` up to `buy_max_rate`/`sell_max_rate` at the risk extremes (0/100), with `buy_curvature`/`sell_curvature` controlling the ramp's shape. There is no way today to express "50% of max rate at a medium-risk signal, 100% only at a true extreme" — the curve either reaches max rate at the single knee or doesn't.

**Fix**: extend `SdcaCurveShape` with a mid-tier knee and curvature per side (e.g. `buy_mid_knee_risk`, `buy_mid_curvature`, and symmetric sell-side fields), and make `rate_at()` piecewise: from the far knee toward the mid knee, ramp toward roughly half of `max_rate`; from the mid knee to the extreme (risk 0 or 100), ramp the remaining half up to full `max_rate`. `to_nodes()` continues to sample `rate_at()` at the existing 21-node `RISK_NODES` grid unchanged — only the shape function gains a second segment.

Corresponding search-space changes: `WIDE_KNEE_SEARCH_BOUNDS`/`WIDE_KNEE_COARSE_GRID` (`curve_optimize.py`) and `search_wide_knee_curve_feasibility_aware` (`curve_optimize_feasibility.py`) need new dimensions for the mid-tier knee/curvature parameters, bounded so the mid knee always sits strictly between its side's outer knee and the risk-50 midpoint (never crossing into the other side's territory, never collapsing onto the extreme knee). Exact numeric bounds to be set during implementation from a coarse manual sweep, mirroring how `WIDE_KNEE_SEARCH_BOUNDS`'s existing bounds were set.

### 2.3 Full ~17-indicator pool re-weight

`SURVIVING_INDICATORS` (`scripts/run_aggregate_reweight_full17_fixed_index.py`) is the canonical, previously-validated 17-name pool: `power_law`, all 9 macro/on-chain names (`m2, rs_eth, dxy, onchain_mvrv, onchain_asopr, onchain_puell, onchain_rhodl, onchain_addr_ratio, fear_greed`), and all 7 price-oscillator variants (`weekly_monthly_rsi, weekly_monthly_macd, weekly_rsi, weekly_macd, sma_band, monthly_rsi, monthly_macd`). This cleanly excludes 5 names that don't belong in this workstream's pool: `fast_crash_vol` (deliberately fast/short-horizon, a poor fit for a smoothness-focused redesign), `adx`/`stochastic` (cleared Stage-1 solo-validation but never wired into `build_extra_indicators` — no source plumbing exists), and `vol_regime`/`halving_cycle` (both explicitly rejected at Stage 2 — any positive weight monotonically degraded the objective).

**Important**: `ablation.py`'s `_POOL_NAMES` currently defaults to *all 22* declared `SdcaCompositeWeights` fields via `extra_items()` — broader than `SURVIVING_INDICATORS`. This round's re-run must explicitly pass `SURVIVING_INDICATORS` as the pool rather than relying on the driver's default, so the 5 excluded names don't silently re-enter the search.

**Fix**: a new driver script (or a parameterized re-run of the existing `run_aggregate_reweight_full17_fixed_index.py` pattern) that:

1. Reweights across the 17-name pool using Component 1's now-smoothed indicators and Component 2's tiered curve search space together (not sequentially blind to each other — a smoother index changes what curve shape is optimal, and a tiered curve changes how much weight-search sensitivity matters at the margins).
2. Applies the same per-indicator Stage-1 window overrides already established (`EXTRA_WINDOWS`: `dxy=60`, on-chain names and `fear_greed` at their documented windows, `m2` at the shared 90-day default).
3. Runs the standard walk-forward + duration-weighted fold mean + sensitivity-stability check (`optimize.py`, `walk_forward.py`, `baseline_evaluator.py` — all reused unchanged) before anything is reported as a candidate.

### 2.4 Testing

- **Smoothness diagnostic tests**: synthetic step-function and ramp fixtures with known roughness, asserting the diagnostic's `mean`/`p95`/`p99`/spike-count outputs match hand-computed expectations (mirrors the existing `TestCausalEmaSmooth` pattern from the prior round).
- **Per-indicator smoothing regression tests**: for each indicator the diagnostic flags and Component 1 smooths, a step-vs-ramp integration test analogous to the existing M2 one — confirms the raw step becomes a bounded ramp, not just "smoother by eyeball."
- **`agreement_scaled_blend` discontinuity fix tests**: assert the multiplier is now continuous across a sign crossing (no jump greater than some small epsilon between adjacent-risk-node samples straddling a crossing), while behavior at the far same-sign and opposite-sign tails matches today's values (regression guard against changing extremes behavior, which the existing crash-response tests depend on).
- **Tiered curve shape tests**: `rate_at()` invariants — monotonicity from knee to extreme on both segments, the mid-tier rate lands at approximately half of `max_rate` at the mid knee, continuity at the segment boundary (no jump at the mid knee itself), and the existing single-knee behavior is recovered as a special case when the mid knee collapses onto the outer knee (backward-compatibility check against today's published curves).
- Full `tests/dq/strategies/sdca/` suite stays green throughout, same standing requirement as every prior round.

## 3. Status

| Component | Scope | Status |
|---|---|---|
| 1a | Verify landed M2/RSI fix against current code (fresh round-8 regen + roughness measurement) | **done** — see Problem section table; fix helps on average, doesn't eliminate the tail |
| 1b | Systematic roughness diagnostic across all 17 `SURVIVING_INDICATORS` | planned |
| 1c | Generalize `causal_ema_smooth` to flagged indicators (cadence-appropriate half-lives) | planned |
| 1d | Fix `agreement_scaled_blend` sign-crossing discontinuity | planned |
| 2 | Tiered `SdcaCurveShape` (mid-tier knee/curvature per side) + search-bound updates | planned |
| 3 | Full 17-indicator pool re-weight, explicitly scoped past `ablation.py`'s broader 22-name default | planned |
| 4 | Testing per 2.4 | planned |

## 4. Gate

Never writes `settings.json` or `RESEARCH_STATE.md`'s "Current best validated candidate" section without Chris's explicit accept. Diagnostic scripts write only to `.scratch/` or untracked local files under `apps/digiquant-web/public/strategies/` (new diagnostic slugs, distinct from `btc_sdca`). Reported to Chris as a walk-forward table (`beats_flat_dca_oos`, `sensitivity_stable`, realized max drawdown, plus the roughness diagnostic's before/after numbers) for explicit accept/reject, same protocol as every prior round.
