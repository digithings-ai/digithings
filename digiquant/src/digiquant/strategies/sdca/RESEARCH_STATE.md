# SDCA research state

Canonical answer to "what's the current best validated candidate right now."
Every trial report compares against **this file's current entry**, not against
memory, prose from an earlier session, or `settings.json`. This file exists
because those three previously disagreed about which config was "the
baseline," which cost a `git log -p settings.json` dig to untangle.

Update this file only on an explicit accept from Chris. Update `settings.json`
separately (his call, possibly later — accepting a candidate here does not
by itself mean it ships).

## Current best validated candidate

- **Weights:** `power_law=1.0, m2=0.5, dxy=0.5` (all other indicators — `rs_eth`,
  `weekly_rsi`, `weekly_macd`, `sma_band` — at `0.0`)
- **Curve:** published `btc_optimized` shape (buy knee 24.1, sell knee 71.9)
- **Validated:** +84.90% OOS (`curve_simulator`), +84.78% OOS (`nautilus`,
  `evaluate_sdca_trial_nautilus`) — same 3-fold walk-forward split, both
  evaluators agree to within 0.1pp once both are run fresh under current code.
- **Date:** 2026-09-03

## Known discrepancy: this is NOT what's live in settings.json

`digiquant/src/digiquant/strategies/settings.json`'s `btc_sdca` block currently
has `weekly_rsi=0.25, weekly_macd=0.5` turned on in addition to the three
weights above (set by commit `82cd1ddcc`, an unrelated "Cursor Agent" commit
that itself documents `beats_flat_dca_oos: false`). That 5-weight live config
has been walk-forward-validated twice this session and loses both times:

- `btc_5member_curve_walkforward_provenance.json`: mean OOS vs-flat-DCA =
  **-16.21%** (curve re-fit to match the live 5-weight index, still loses OOS)
- Ad-hoc fresh 7-indicator Stage-A search scoring the exact live weight set:
  **-46.23% to -51.28%** OOS (varies with rolling-composite window; see
  git log on `composite_rolling_window` work, commit `b38c89440`)

No provenance file currently has `beats_flat_dca_oos: true`. The 3-weight
baseline above is the best validated result, not a strategy that reliably
beats flat DCA — "current best candidate" and "beats the public benchmark"
are different claims; don't conflate them in a trial report.

**Open question for Chris:** is the "Cursor Agent" process still actively
changing this composite? Reverting `settings.json` to the validated 3-weight
baseline is only safe to propose once that's confirmed — see immediate
backlog item 3 below.

## Standard trial protocol

Every iteration, in order:

1. State the hypothesis (what's changing and why) up front.
2. "Index then curve, repeat" (`digiquant/AGENTS.md` § index-then-curve) —
   re-run the Stage-A weight search if the index changed, then re-fit the
   curve against the new index. Never fit a curve against a stale index.
3. `curve_simulator` first for a fast go/no-go. Only promote to a full
   Nautilus walk-forward if the candidate clears `curve_simulator` — don't
   spend a Nautilus pass on a loser.
4. Emit a tearsheet via `scripts/emit_sdca_trial_tearsheet.py` — get the
   visual before any accept/reject discussion. See its `--help` / module
   docstring for the CLI and the preview flow
   (`frontend/digiquant-web/app/strategies/preview/page.tsx`).
5. Report a compact metrics table (IS/OOS vs-flat-DCA under both evaluators,
   max drawdown, capital_deployed_pct, buy/sell dwell time) alongside the
   preview link.
6. Only on Chris's explicit accept: update this file, and separately
   (his call) `settings.json`.

Never call a config "the baseline" without citing this file's current entry.
If a trial's own weight set is later validated and accepted, replace the
"Current best validated candidate" section above — don't leave two entries
that could both be read as "the baseline."

## Phase B: indicator validation gate

`indicator_catalog.py`'s per-field comments (`adx`, `stochastic`, `vol_regime`,
`halving_cycle`) refer to a staged "Phase B" gate for admitting a new
indicator into the composite. That gate was never written up here — this
section is the missing write-up, reconstructed from those comments and from
the (mostly uncommitted, one-off) scripts they name. It runs *before* the
"Standard trial protocol" above: Phase B decides whether a candidate
indicator is worth carrying into a full trial at all; the standard protocol
then governs how any resulting weight/curve change gets accepted.

Four stages, in order — a candidate must clear one to be tried at the next:

1. **Solo-validation.** Score the candidate alone (not blended into any
   existing pool) via a `combined` cycle-overlap-style objective against a
   `0.00` noise baseline, via a one-off `scripts/run_<indicator>_solo_
   validation.py` script (`.scratch/`-style, not committed per the
   project's "persist last" convention — these are cheap to regenerate and
   not meant to live in the repo).
2. **Fixed-baseline reweight.** Add the candidate at a positive weight on
   top of the current validated baseline (`power_law=1.0, m2=0.5, dxy=0.5`)
   and check whether it improves the objective at any positive weight.
3. **Joint reweight.** Re-run the full pool search
   (`optimize_stage_a_weights_combined`/`_multi_ratio`) with the candidate
   included, to see how it behaves once every other indicator is free to
   move too (not just added on top of a fixed set).
4. **Curve + OOS walk-forward.** Only Stage-3 survivors get a curve re-fit
   and a full 3-fold walk-forward OOS check — at that point they've entered
   the "Standard trial protocol" above and are gated the same as any other
   trial (Chris's explicit accept before touching this file or
   `settings.json`).

**Where each candidate currently stands:**

- `adx`, `stochastic` — cleared Stage 1 (2026-09-17, via
  `scripts/run_adx_stochastic_solo_validation.py`, script no longer in the
  repo). **Not yet reached Stage 2** — blocked on `ExtraIndicatorSources`
  OHLC high/low plumbing not yet wired into `build_extra_indicators` (every
  other indicator in the catalog derives from close alone; ADX/stochastic
  need high/low).
- `vol_regime` — cleared Stage 1 (2026-09-18, best `short=60/long=180`,
  `combined=71.11`, via `run_vol_regime_solo_validation.py`). **Stage 2
  REJECTED** (dead end #21, via `run_vol_regime_stage2_fixed_baseline.py`):
  any positive weight on top of the fixed baseline monotonically degrades
  the objective.
- `halving_cycle` — cleared Stage 1 (2026-09-18, best
  `cycle_length=1317.6d/phase_shift=+0.30`, `combined=140.42`, via
  `run_halving_cycle_solo_validation.py`; confirmed not an edge-of-grid
  artifact by widening the phase-shift grid). **Stage 2 REJECTED** (dead
  end #22, via `run_halving_cycle_stage2_fixed_baseline.py`): same
  monotonic-degradation pattern as `vol_regime`.

None of the four has reached Stage 3 or 4 yet. (`indicator_catalog.py`'s
`halving_cycle` comment describes its rejection as following "the same
pattern as adx/stochastic/vol_regime" — read that as referring to the
general fixed-baseline-degradation pattern, not as a claim that adx/
stochastic have themselves been Stage-2-tested; their own comment is
explicit that they're still blocked on Stage 2's OHLC plumbing.)

## Immediate backlog (proposed order)

1. Fresh Stage-A weight search on the dead-zone-fixed rolling composite
   (`composite_rolling_min_samples=20`, window ∈ [1095, 1825] days — OOS was
   flat across that range, see commit `b38c89440`), scored against the
   corrected true baseline above, not the live 5-weight config.
2. Joint period re-tuning of the five confluence indicators (RSI 8/7, MACD
   6/13 or 8/17, SMA-band 60/10, rs_eth 90/45, power_law-trend 120d) — each
   was smoke-tested individually; never applied jointly. Absorbed into item 6
   below: the medium-term cycle windows are exactly what the daily/fast legs
   of this joint re-tune should be scored against, instead of re-tuning blind.
3. Ask Chris directly whether the "Cursor Agent" process is still active on
   this composite — determines whether reverting `settings.json` to the
   validated baseline is safe to propose.
4. Infra: fix `nautilus_evaluator.py`'s one-`BacktestEngine()`-per-process
   crash (currently forces a subprocess-per-fold workaround) — worth doing
   early since this loop leans on Nautilus validation every iteration.
5. Regenerate the stale `btc_optimized_provenance.json` (predates this
   session's confluence-indicator upgrades, so its cached numbers no longer
   describe the current code path).
6. **Dual-timeframe valuation framework** (Chris's 2026-09-04 direction, then
   redirected 2026-09-04→05 to a single composite — see
   `../DCA_VALUATION_FRAMEWORK.md`): composite smoothing landed
   (`compute_composite_risk`'s `smoothing_window`); a medium-term `CycleWindow`
   set landed (75-pivot zigzag, `cycle_windows.py`, chart-review-corrected
   2026-09-04); the two-composite diagnostic (`scripts/run_stage_a_cycle_overlap.py`)
   confirmed long-term (`power_law=1.0` alone, objective 64.2) and medium-term
   (`power_law=0.0, sma_band=0.5` alone, objective 41.4) pull in different
   directions — exactly why Chris rejected a two-composite architecture and
   asked for one composite scored against both timeframes at once, weighted
   3:1 toward long-term so long-term extremes are never missed while
   medium-term zones are covered where possible, with a diversification floor
   so the mix never collapses onto a single indicator (hedge against
   power-law degrading later).

   That single-composite search (`scripts/run_dual_timeframe_composite_search.py`,
   `stage_a.optimize_stage_a_weights_combined()` +
   `weight_search.search_oscillator_periods_by_cycle_overlap()`) has now run
   twice against real BTC-USD data — **diagnostic only, not an accepted
   candidate**:
   - First pass (coarse period grids): kept all five tunable indicators:
     `power_law` (180d trend, anchor), `weekly_rsi` (8/7), `weekly_macd`
     (12/26/12/26 — default periods won), `sma_band` (120/30), `rs_eth`
     (60/20). Equal-weight recombination (7 indicators incl. `m2`/`dxy`, 1/7
     each): long=25.76, medium=12.83, combined=90.12 (3:1 ratio).
     Floor-diversified aggregate reweight (floor 0.25): `power_law=1.0,
     sma_band=1.0`, everything else (`m2`, `dxy`, `weekly_rsi`, `weekly_macd`,
     `rs_eth`) floored at `0.25`. long=42.97, medium=24.00, combined=152.89 —
     beats the equal-weight baseline on every axis. Ratio sensitivity (2:1 /
     3:1 / 5:1): identical winning mix across all three; only the combined
     objective's scale changes (109.93 / 152.89 / 238.82).
   - Second pass (2026-09-05, Chris's request: "widen the grid for
     weekly_rsi and weekly_macd, also worth exploring is a monthly RSI and
     monthly MACD for the longer term cycle"): widened `weekly_rsi`'s period
     grid (50 combos, was ~4) and `weekly_macd`'s (21 combos, was ~4), and
     added a diagnostic-only Stage 2b that solo-scores new
     `monthly_rsi_confluence_z()`/`monthly_macd_confluence_z()` kernels
     (`price_oscillators.py`) for direct comparison against their weekly
     counterparts — these two monthly indicators are NOT in
     `EXTRA_INDICATOR_NAMES`/`build_extra_indicators()`/settings.json, only
     dormant zero-weight fields on `SdcaCompositeWeights` plus the
     `WEIGHT_PARAM_BY_NAME` entries required by `two_stage.py`'s exhaustive
     `freeze_weight_params()`. Results:
     - Widened grids found different optima than the coarse pass:
       `weekly_rsi` → `weekly_length=5, daily_length=5` (long=21.84,
       medium=20.41, combined=85.93 solo) vs. the coarse pass's `8/7`;
       `weekly_macd` → `weekly_fast=16, weekly_slow=35, daily_fast=12,
       daily_slow=26` (long=39.61, medium=16.06, combined=134.88 solo) vs.
       the coarse pass's `12/26/12/26` default. Both solo scores still trail
       `sma_band` (196.83) and `power_law` (225.24) by a wide margin.
     - `monthly_rsi` (Stage 2b, diagnostic): `monthly_length=3,
       daily_length=7` scores long=50.87, medium=18.10, combined=170.71 —
       notably higher than widened `weekly_rsi`'s 85.93, but `monthly_length=3`
       sits at the short edge of its candidate grid `(3,5,7,9,12,14,18)`,
       so this reads as a plausible overfit/edge-of-grid artifact rather
       than a clean win. Needs a wider or shifted grid before trusting it.
     - `monthly_macd` (Stage 2b, diagnostic): `monthly_fast=4,
       monthly_slow=9, daily_fast=12, daily_slow=26` scores long=40.54,
       medium=15.44, combined=137.05 — close to and slightly better than
       widened `weekly_macd`'s 134.88, a much less suspicious comparison
       (not at a grid edge).
     - Stages 3-5 correctly exclude `monthly_rsi`/`monthly_macd` (weight=0.0
       throughout) confirming the scoping decision held, and reproduce the
       *identical* winning aggregate mix from the first pass: `power_law=1.0,
       sma_band=1.0`, everything else floored at 0.25 — long=43.69,
       medium=24.88, combined=155.96 (3:1). The widened weekly grids and
       monthly exploration changed per-indicator solo scores but not which
       mix wins the aggregate reweight. Ratio sensitivity again shows an
       identical mix at 2:1/5:1, only the objective's scale changes
       (112.26 / 155.96 / 243.34).
   Neither monthly indicator has been proposed as a promotion candidate —
   they'd need a wider monthly-period grid (to rule out the edge-of-grid
   artifact on RSI) and an explicit decision from Chris before touching
   `EXTRA_INDICATOR_NAMES` or settings.json. Curve/threshold optimization
   against this index (Chris's explicitly separate stage 5) hasn't started.

   - Third pass (2026-09-05, same session: "expand the monthly RSI grid"):
     widened `MONTHLY_RSI_CANDIDATES`' `monthly_length` down to `2` (RSI's
     mathematical floor — `length=1` degenerates to a single-delta RSI,
     confirmed via `_wilder_rsi()`'s `ewm_mean` formula in
     `price_oscillators.py`) from the prior floor of `3`, plus added `4`/`6`
     for resolution (grid: `(2,3,4,5,6,7,9,12,14,18)` × 5 daily lengths, 50
     combos). Added `test_short_length_boundary_does_not_crash` to
     `test_price_oscillators.py` confirming `length=2` produces finite,
     correctly clipped output. `monthly_macd`'s grid was left unchanged (its
     winner isn't at an edge).
     Result: **the edge-of-grid concern is reinforced, not resolved.** The
     winner moved from `monthly_length=3` (score 170.71) to `monthly_length=2`
     (long=58.89, medium=28.84, combined=205.52) — i.e. it tracked the new
     floor rather than settling on an interior value. This is consistent with
     `monthly_rsi` at very short lengths degenerating toward a near-binary
     up-month/down-month signal that happens to line up well with this
     specific, small set of cycle pins (5 long + 75 medium windows) — a
     classic overfit signature. `monthly_rsi` stays diagnostic-only,
     excluded from Stages 3-5, and is **not** a promotion candidate.
     `monthly_macd`'s winner is unchanged and not suspect.
     A visual confluence check (`scripts/export_indicator_confluence_data.py`
     → standalone Chart.js dashboard, not checked into the repo) plots BTC
     price against all nine indicators' full z-score histories with the
     long-/medium-term cycle windows shaded behind them, for Chris to
     eyeball confluence before deciding on an equal-weight or
     floor-diversified aggregate index. Pending his review as of this entry.

   - Fourth pass (2026-09-05, same session: Chris visually reviewed the
     confluence dashboard, confirmed `monthly_rsi=2` is usable ("it bottoms
     out on both long- and medium-term lows... We could use it"), asked
     whether `monthly_length=14` (the classic RSI period) had been tried
     since he expected it to behave like `power_law` — a pure long-term
     top/bottom mapper — then gave a scoped green light: "go ahead with the
     equal-weight index"):
     - `monthly_length=14`'s best score (pulled from the widened grid's own
       `all_scores`, `daily_length=5`) is long=16.34, medium=8.43,
       combined=57.46 — far below both `power_law` (225.24 solo) and
       `monthly_rsi=2` (205.52 solo), despite visually mapping the same
       long-term turns as `power_law`. Every `monthly_length` in the grid
       from 5 up scores in the same low ~57-86 band; only lengths 2-4 (near
       the grid floor) score high. Hypothesis: the cycle-overlap objective
       rewards how sharply an indicator hits extreme z-values right at pin
       dates, not just directional correctness — a slower RSI(14) tracks the
       right shape but under-scores because it doesn't spike as hard at the
       pin. Not a promotion candidate, kept in the confluence dashboard only
       as a side-by-side visual comparison against `monthly_rsi=2`.
     - Built Stage 3b in `run_dual_timeframe_composite_search.py`: an
       equal-weight composite over **all nine** indicators (the surviving-7
       from Stage 3, plus `monthly_rsi=2` and `monthly_macd` at their Stage
       2b winning periods), 1/9 weight each — promoting both monthly
       indicators from diagnostic-only into a real weighted composite, per
       Chris's green light. Does not touch Stages 4-5 (floor-diversified
       reweight), which stay scoped to the surviving-7 mix pending a
       separate green light — Chris's own instructions describe that as the
       next, not-yet-authorized step.
       Result: long=33.25, medium=14.49, combined=114.23 (3:1) — beats the
       surviving-7 equal-weight baseline (long=27.65, medium=14.19,
       combined=97.15) on every axis, with the gain concentrated in the
       long-term score (+20%), consistent with both monthly indicators being
       long-cycle-biased.
     - Exported this composite's `composite_z` series (not the `[0,100]`
       risk rescaling, so it plots on the same -3..3 axis as every other
       indicator) via `export_indicator_confluence_data.py` and added it to
       the confluence dashboard as a headline "Equal-Weight Index (all 9)"
       panel, plotted first. Still pending Chris's visual review.
     - `monthly_rsi`/`monthly_macd` remain excluded from
       `EXTRA_INDICATOR_NAMES`/`build_extra_indicators()`/settings.json —
       this equal-weight-all9 composite exists only in the diagnostic search
       script and export/visualization, not in production config.

   - Fifth pass (2026-09-05, same session: Chris reviewed the equal-weight
     all-9 result and gave the next green light: "go ahead with the
     floor-diversified optimized weight version"):
     - Added Stage 4b to `run_dual_timeframe_composite_search.py`, extending
       `optimize_stage_a_weights_combined()`'s existing floor-diversified
       grid search (already used for the surviving-7 mix's Stage 4/5) to
       `search_names_all9` (adds `monthly_rsi`, `monthly_macd` to the 6
       surviving-7 extras — 8 names total). This is a brute-force search:
       going from 6 to 8 search names blows the grid up from `4**6` to
       `4**8` combinations (16,384 → 262,144 evaluations at the base 3:1
       ratio) — benchmarked at ~0.0136s/eval, an estimated ~1 hour just for
       the base ratio. Only the 3:1 base case is run in Stage 4b; the
       2:1/5:1 ratio-sensitivity sweep (Stage 5 does this for the
       surviving-7 mix) is deferred as a follow-up given the ~3x additional
       runtime a full sweep would add. Launched as a background job.
     - Result: winning mix is `power_law=1.0, sma_band=1.0, monthly_rsi=1.0`
       (all at the grid ceiling) with `m2, rs_eth, dxy, weekly_rsi,
       weekly_macd, monthly_macd` all floored at `0.25` — score long=46.96,
       medium=23.58, combined=164.47 (3:1), beating the surviving-7
       floor-diversified baseline (long=43.69, medium=24.88, combined=155.96)
       on long-term and combined, at a small (-1.30) cost to the medium-term
       score. `monthly_rsi` earning a ceiling weight alongside `power_law`
       and `sma_band` — rather than being floored out like `monthly_macd`
       and every non-anchor surviving-7 extra — is consistent with Chris's
       own visual read of it as a strong long-term bottom/top marker.
       Exported this composite's `composite_z` series (same pattern as
       `equal_weight_all9`) via `export_indicator_confluence_data.py` and
       added it to the confluence dashboard as a second headline panel.
     - `monthly_rsi`/`monthly_macd` still remain excluded from
       `EXTRA_INDICATOR_NAMES`/`build_extra_indicators()`/settings.json —
       both this and the equal-weight-all9 composite exist only in the
       diagnostic search script and export/visualization, not in production
       config. Neither is a validated trading candidate; this remains a
       diagnostic **index**, not a curve/threshold-tested strategy.

   - Sixth pass (2026-09-05, same session: Chris asked "We could play around
     with the ratio, see what it gives" re: the all-9 floor-diversified
     search's deferred 2:1/5:1 sweep from the Fifth pass):
     - Rather than re-running the ~1 hour, 262,144-evaluation brute-force
       search two more times (~3 hours total, mirroring how Stage 5 sweeps
       the cheap surviving-7 search), added
       `optimize_stage_a_weights_combined_multi_ratio()` to `stage_a.py`.
       For a fixed weight candidate, computing its composite risk series and
       long/medium `cycle_overlap_score()`s is the expensive part and does
       not depend on the long:medium ratio — only the final
       `objective = long_weight * long.objective + medium_weight *
       medium.objective` scalar combination does. The new function evaluates
       each candidate once and scores it under every requested ratio in the
       same pass, so a full N-ratio sweep costs the same ~1 hour as a single
       ratio. `run_dual_timeframe_composite_search.py`'s Stage 4b/5b now
       calls this once for `((2.0, 1.0), (3.0, 1.0), (5.0, 1.0))`.
     - Result: the winning mix is **identical across all three ratios** —
       same as Stage 5 found for the surviving-7 case — `power_law=1.0,
       sma_band=1.0, monthly_rsi=1.0` at the ceiling, `m2, rs_eth, dxy,
       weekly_rsi, weekly_macd, monthly_macd` all floored at `0.25`. Only the
       objective's scale shifts with the ratio: long=46.96 medium=23.58,
       combined=117.51 (2:1) / 164.47 (3:1) / 258.39 (5:1). The 3:1 row
       exactly reproduces the Fifth pass's single-ratio result, confirming
       the multi-ratio refactor is correct. Since the weight mix doesn't
       move across ratios, no visualization change was needed — the
       Fifth pass's `floor_diversified_all9` panel (built from the 3:1 mix)
       already represents all three.

7. **Remaining-book curve Stage A/B fit on the all-9 floor-diversified index**
   (Chris's 2026-09-05 direction, same session as item 6: "let's optimize the
   trading strategy itself around this aggregate indicator... fit the best
   buy and sell curves to the indicator which yield the highest risk adjusted
   returns... I wouldn't want the thresholds to play a role. I think we could
   just find the best buy and sell curves if it was a continuous thing and
   then we could just clean up the middle area, which has the least impact
   and just keep the edges"). Index is item 6's all-9 floor-diversified,
   optimized-weight composite (Sixth pass), frozen via
   `curve_optimize.load_frozen_index(..., weights=...)` rather than
   `settings.json` — that composite hasn't been promoted into production.
   **Diagnostic only, in-sample (`curve_simulator`), not a validated trading
   candidate.**

   - **Stage A** (`curve_optimize.search_continuous_curve` /
     `sample_continuous_curve_trials`): a single free `crossing_risk` plus a
     fixed `CONTINUOUS_CROSSING_EPS=0.5` gap (far below the 21-node
     `RISK_NODES` 5-point spacing) produces an effectively continuous
     buy/sell curve — no meaningful dead zone — reusing `SdcaCurveShape`
     unchanged (its only invariant is a *strict* `buy_knee_risk <
     sell_knee_risk`, no minimum gap). Objective is `risk_adjusted_return`
     (`total_return_pct / max_drawdown_pct`), not raw return.
   - **Stage B** (`curve_optimize.sweep_dead_zone_width` /
     `score_dead_zone_width`): fixes Stage A's winning crossing point, rates,
     and curvatures, then widens the knee gap (`width`) around that fixed
     crossing, clipped to valid knee bounds. Scores `risk_adjusted_return`
     against `trade_days` (`buy_days + sell_days`, read off the raw
     `SdcaBacktestReport` — `CurveTrialScore` doesn't carry trade-count
     fields) at each width, building the frontier for picking a realistic
     trade cadence without letting the threshold shape the underlying fit.

   First pass (`scripts/run_curve_stage_ab_search.py`, `n_random=400,
   seed=42`, full 2018-01-01→2026-08-30 cache, `signal_delay_days=3`):
   - Stage A winner: `buy_max_rate=35.0, buy_knee_risk≈39.75,
     sell_knee_risk≈40.25, sell_max_rate=8.0, buy_curvature=1.5,
     sell_curvature=3.5` (crossing ≈ risk 40). `risk_adjusted_return=56.60`
     (`total_return_pct=2865.58%`, `max_drawdown_pct=50.63%`) vs. today's
     published `btc_optimized` shape scored on this same index:
     `risk_adjusted_return=4.55` — expected, since that curve was tuned
     against the 3-weight validated baseline's index, not this one.
   - Stage B frontier (width → risk_adjusted_return / trade_days):
     `0.5→56.60/3102`, `3.0→55.18/3102`, `5.0→53.28/3102`,
     `7.5→49.79/3102`, `10.0→45.32/2500`, `15.0→35.78/2500`,
     `20.0→25.09/1822`, `25.0→13.47/1822`, `30.0→5.64/1173`; widths ≥40
     turn infeasible (`no_2025_sells` — too few sell days survive in 2025
     once the zone is this wide). Risk-adjusted return is nearly
     flat through width ≈5–7.5 while trade_days hasn't dropped at all yet
     (still 3102, one trade almost every day); the first real trade-count
     cut arrives at width=10 (3102→2500, -19%) for a modest return cost
     (56.60→45.32, -20%), and every wider step trades return away faster
     than it buys back trade-count headroom. **Reported to Chris, not yet
     accepted** — pending his pick of a practical width from this frontier.

8. **Wide-knee curve search: independent buy/sell dead zone, exponential
   ramp** (Chris's 2026-09-05 direction, same session as items 6-7, after
   seeing item 7's Stage A continuous-curve fill detail — `buy_days=398,
   sell_days=2704, trade_days=3102/3164 (98.0%)` — and its tearsheet):
   "Something I don't like about the behavior of the strategy is just how
   quick or how often we're transacting... visually looking at the risk
   chart... above, say, 75, I'd be selling aggressively, and below 25, I'd
   be buying very aggressively. And then above, say, 60, I'd start selling,
   and below 40, I'd start buying... it shouldn't be a linear line, it
   should be exponential... That's part of the optimization problem is
   finding a best selling and buying curve, which yields the best
   risk-adjusted returns... it's two separate curves, it could have
   different functions... looking at the fills, we never actually fully
   sell out the position... the lowest we are after selling is at about 25%
   cash... we could be more aggressive with our selling... I think we could
   try to calibrate the system where it's just targeting more, a few
   clusters of buys and sales and not a continuous range." His 40/60
   (aggressive by 25/75) split was offered explicitly as a starting-point
   seed, not a constraint ("we'll have to play around with those
   variables") — buy and sell knees/curvatures/rates are independently
   searched, not mirrored.

   `curve_shape.SdcaCurveShape.rate_at()` already gives the "slow near the
   knee, exponential toward the edge" ramp for any `curvature ≥ 1.0` and
   already allows fully independent buy/sell knees (only invariant: strict
   `buy_knee_risk < sell_knee_risk`) — no model change needed, only a wider
   search. Added `curve_optimize.WIDE_KNEE_SEARCH_BOUNDS` /
   `WIDE_KNEE_COARSE_GRID` / `sample_wide_knee_curve_trials()` /
   `search_wide_knee_curve()` (reusing the existing general `search_curve()`
   the same way `search_continuous_curve()` does) as a new, separate
   parameterization alongside Stage A/B — `CURVE_SEARCH_BOUNDS` (the
   original default search) is untouched. Bounds: `buy_knee_risk` (20-48),
   `sell_knee_risk` (52-80), both curvatures (1-6), `sell_max_rate` widened
   to (5-95) (vs. the default search's (3-40) ceiling) specifically to let
   the optimizer explore near-full liquidation if that's what the objective
   wants. `shape_from_bounds_ok()` generalized to accept a `bounds` param
   (default `CURVE_SEARCH_BOUNDS`) so both searches share one validator.

   Run (`scripts/run_curve_wide_knee_search.py`, `n_random=4000, seed=42`,
   same all-9 floor-diversified index as items 6-7, `risk_adjusted_return`
   objective, full 2018-01-01→2026-08-30 cache):
   - Winner: `buy_max_rate=35.0, buy_knee_risk=40.0, sell_knee_risk=70.0,
     sell_max_rate=30.0, buy_curvature=1.5, sell_curvature=1.5` out of 6097
     evaluated trials (5401 feasible). `risk_adjusted_return=57.82`
     (`total_return_pct=3153.35%`, `max_drawdown_pct=54.54%`) — a touch
     *better* than item 7's Stage A continuous winner (56.60), not a
     tradeoff. `buy_knee_risk=40.0` lands almost exactly on Chris's
     hypothesis; `sell_knee_risk=70.0` is more conservative than his 60
     seed — the objective prefers holding the winning asset longer before
     starting to sell.
   - Trade frequency, the headline ask: `buy_days=398, sell_days=174,
     no_trade_days=2530, trade_days=572/3164 (18.1%)` — down from item 7's
     98.0%. Same buy-day count as the continuous winner (buy behavior barely
     changed) but sell days collapsed 2704→174, which is exactly the
     "clusters of buys and sales, not a continuous range" behavior asked
     for.
   - Cash depletion (`cash / portfolio_value`, computed from the raw
     backtest frame — `run_backtest()` already exposes `portfolio_value`,
     no new field needed): during the 2018-19 bear the position gets to
     98.1% cash (was 98.6% on item 7's curve — already good); during the
     2022 bear, 81.6% cash (was 79.3%); but the weak case Chris was
     describing — the 2025 top-forming period — only reaches 64.9% cash
     (was 63.6%), barely moved despite `sell_max_rate` tripling (8.0→30.0)
     and the widened ceiling allowing up to 95.0. The optimizer had room to
     sell far more aggressively and chose not to: pure `risk_adjusted_return`
     doesn't want to liquidate hard into an ongoing rally, since BTC's
     right-skewed returns make premature selling expensive. Getting closer
     to Chris's "down to zero in a bear market" for the weak case likely
     needs either a different objective term (e.g. penalize a low
     `sell_frac`/reward `sell_notional_2025` directly) or an explicit
     floor on `sell_max_rate`/`sell_knee_risk` rather than relying on
     risk-adjusted return alone to discover it — flagged for Chris's next
     iteration, not resolved here.
   - Tearsheet emitted the same way as item 7's (`emit_sdca_trial_tearsheet.py`
     machinery, `.scratch/tearsheets/all9_wide_knee_winner.json`, gitignored):
     `net_profit_pct=3406.71%, max_drawdown_pct=-53.01%,
     vs_flat_dca_pct=631.91%` (vs. item 7's continuous curve:
     `3171.37% / -50.70% / 582.79%`) — improves on all three headline
     tearsheet numbers while trading 82% less often.

   **Diagnostic only, in-sample (`curve_simulator`,
   `beats_flat_dca_oos=False`), not a validated trading candidate.**
   Reported to Chris with the reference-risk-level rates (`rate_at(25)=+8.0,
   rate_at(40)=0.0, rate_at(60)=0.0, rate_at(75)=-2.0`) so the fitted curve's
   actual aggressiveness can be checked against his visual intuition
   directly — pending his read on the sell-side result and any further
   iteration on the bounds/objective per his own framing ("we'll have to
   play around with those variables").

9. **Task #93: full 17-indicator recalibration pass — three rounds, all
   rejected** (2026-09-23; worked from the existing 17-survivor pool
   (11 original + 6 on-chain/sentiment extras) as-is, predating the SDCA
   post-mortem's finding that `power_law`'s apparent search-dominance may
   trace to the band-crossing bug / sell-side z-score-denominator shrink
   rather than genuine edge):
   - **Round 1** (`81e5f1dc5`: `run_dual_timeframe_composite_search.py`
     Stage 1 extended to all 17 survivors +
     `run_aggregate_reweight_full17.py`/`_aggregate_reweight_parallel.py`
     Stage 2 floor-diversified reweight — exhaustive `2*2**16=131072`-combo
     coarse grid, fork-based multiprocessing + `run_full_recalibration.py`
     Stage 1-4 driver): Stage 3 in-sample curve search (5112 evals)
     `beats_baseline_return=False`, `beats_baseline_concentration=False`
     against the live 5-weight preset. Stage 4 walk-forward:
     `beats_flat_dca_oos=True` but thin and fragile — mean OOS vs. flat-DCA
     `+7.64%` (vs. the validated baseline's `+84.90%`), 2 of 3 folds
     infeasible (near-zero/negative `capital_deployed_pct`), held-out tail
     slightly negative (`-1.44%`), `sensitivity.stable=False`
     (`max_abs_delta_oos=5.71pp` under a ±5% weight perturbation).
     **REJECT.** Also closed two `.gitignore` gaps hit producing this run's
     artifacts: the data-cache glob only covered 2 levels under any `data/`
     dir (missed `digiquant/data/onchain/<source>/*.parquet`'s 3-level
     cache path) — generalized to `**/data/**/*.ext` for any nesting depth;
     and `.scratch/` (repeatedly described in this doc as "gitignored")
     had no actual ignore rule — added one.
   - **Round 2** (`60cf0777c`): found and fixed a window-default bug —
     `build_extra_indicators` (and its callers `extra_z_vectors`/
     `load_sdca_extra_z`/`load_frozen_index`) computed every macro/on-chain
     extra at one shared `window` kwarg, silently discarding each
     indicator's own Stage 1 period-search result. Added an opt-in
     `extra_windows: dict[str, int] | None` override, resolved
     per-indicator — an indicator present in the dict uses its own window,
     one absent (or the dict absent/`None`) keeps the prior shared-default
     behavior unchanged (additive, no existing caller affected). Re-ran the
     Stage 2b reweight + Stage 4 gate against the fixed index with each
     extra's real Stage 1 period (`dxy=60`, `onchain_*=365`,
     `fear_greed=270`) instead of the shared 90-day default:
     `beats_flat_dca_oos=True`, `sensitivity_stable=False`
     (`max_abs_delta_oos_pct=2.79` vs. the 2.0 threshold — improved from
     Round 1's 5.71 but still fails the stability gate). **Diagnostic
     only, not promoted.**
   - **Round 3** (`54c4a95f9`): built an opt-in, additive feasibility-aware
     curve-search objective (`curve_optimize_feasibility.py`,
     `score_shape_on_index_feasibility_aware`/
     `search_wide_knee_curve_feasibility_aware`) that penalizes/hard-
     rejects in-sample curve shapes whose `capital_deployed_pct` falls
     outside the walk-forward gate's own `[capital_deployed_floor_pct,
     100%]` band — aimed at the failure mode behind both prior rounds'
     rejections (OOS folds with 0%/negative capital deployed);
     `curve_optimize.py` itself untouched byte-for-byte. Re-ran Stage 4
     with Round 2's unchanged Stage 1 oscillators + Stage 2b weights,
     swapping in the feasibility-aware Stage 3b curve winner. **REJECT**
     — the new objective didn't rescue this round's curve winner:
     `beats_flat_dca_oos=False` (mean OOS `-2.66%`, down from Round 2's
     positive result), `sensitivity_stable=False`
     (`max_abs_delta_oos_pct=3.18`, worse than Round 2's 2.79),
     `feasible_fold_count=1/3` unchanged from Round 2 (fold 0 feasible,
     folds 1-2 still 0%-deployed OOS). It steered the in-sample search
     away from low-deployment shapes as designed, but the resulting curve
     still produced 0%-deployed OOS folds on data the in-sample search
     never saw.
   - All three rounds diagnostic only — `settings.json` and this file's
     "Current best validated candidate" section untouched throughout, per
     the standing accept gate. `tests/dq/strategies/sdca/` stayed green
     across all three (505→507 passed as new tests were added alongside
     each round, 38 skipped for optional deps throughout).

10. **SDCA post-mortem follow-up: band-bug fix, baseline-relative
    evaluator, re-score, iterative ablation** (2026-09-24; the post-mortem
    published after item 9 above flagged that `power_law`'s apparent
    search-dominance may trace to two real bugs, not genuine edge — see
    the plan at the top of this session's work). Four phases, all
    diagnostic — `settings.json` and this file's "Current best validated
    candidate" section untouched throughout:
    - **Phase 1 (band-crossing fix).** `btc_power_law.py`'s
      `_evaluate_rails()` and `quantile_rails.py`'s
      `evaluate_quadratic_log10()` both used a row-wise `np.sort()` to
      force `low < median < high`, which can silently splice a
      *different* quantile's raw curve into a mislabeled slot once two
      rails cross. Replaced both with `rearrange_non_crossing()` (clamps
      each quantile toward its already-reconciled inner neighbor —
      identity-preserving, never swaps labels) plus a `detect_crossings()`
      warning. **The bug is real and large**: real-data runs this session
      logged reconciliation on up to 856/856 rows in a fold's in-sample
      window (see `_evaluate_rails` warnings in any script's stdout) —
      not a rare edge case.
    - **Phase 2 (baseline-relative evaluator).** New
      `curve_shape.risk50_linear_reference_curve()` (buy below composite
      risk 50 / sell above, linear rate schedule, no optimization) and
      `baseline_evaluator.run_sdca_walk_forward_vs_baseline()` (runs
      candidate + risk50-linear baseline under identical folds/rails,
      returns both plus the delta). `optimize.py`'s `run_sdca_walk_forward`
      gained an additive `fold_weighting: Literal["unweighted",
      "duration"]` param; `SdcaWalkForwardResult` now always carries both
      the unweighted and duration-weighted mean OOS.
    - **Phase 3 (re-score, `scripts/run_baseline_relative_rescore.py`).**
      Re-ran the four live/recent candidates against the *fixed* rails and
      the new baseline. **Notable finding: the currently-accepted
      validated baseline itself changes under the fix** —
      `power_law=1.0, m2=0.5, dxy=0.5` now scores `+21.73%`
      duration-weighted OOS (down from the `+84.90%` on file, dated
      2026-09-03, which was computed pre-fix), still
      `beats_flat_dca_oos=True` but `beats_baseline_oos=False` (loses to
      the naive risk50-linear baseline's `+22.49%` by `-0.76%`) and
      `sensitivity.stable=False`. `live_settings_json` still loses
      outright (`-34.80%`, confirms the known discrepancy).
      `task93_round2`/`round3` both now clearly beat the baseline
      (`+53.52%`/`+46.85%` delta) but neither is a promotable candidate on
      its own steam (`round2` `beats_flat_dca_oos=True` at a thin
      `+4.07%`; `round3` `beats_flat_dca_oos=False`).
    - **Phase 4 (iterative ablation, `ablation.py` +
      `scripts/run_iterative_ablation.py`).** Reweight the full
      12-indicator pool (`power_law` + all 11 `EXTRA_INDICATOR_NAMES`),
      drop whichever comes out dominant, repeat, gated by a fast
      per-round sanity check. Full 8-round real-data run:
      `stop_reason=budget_exhausted`; dominant indicator per round —
      R1 `onchain_rhodl`, R2 `onchain_addr_ratio`, **R3 `power_law`**
      (only once two other ceiling-tied indicators are cleared — direct
      evidence that `power_law`'s historical round-1 dominance was partly
      a coarse-grid tie-break artifact, not privileged weighting), R4
      `onchain_mvrv`, R5 `weekly_monthly_macd`, R6 `onchain_puell`, R7
      `dxy`, R8 `m2`. Best round: **#8**, surviving pool
      `m2=1.0, rs_eth=0.1, onchain_asopr=0.1, fear_greed=0.1,
      weekly_monthly_rsi=0.1` (`power_law=0.0` — dropped entirely by
      round 8), fast-gate `+52.01%` duration-weighted OOS.
      **Full-resolution re-validation** of round 8
      (`scripts/run_ablation_best_round_full_resolution.py`, n_random=3000
      curve search + full walk-forward vs. baseline): confirms
      `+52.01%` OOS, `beats_flat_dca_oos=True`, **and
      `beats_baseline_oos=True`** (`+9.13%` over the risk50-linear
      baseline's own `+42.87%`) — the first candidate this session to
      clear that bar. But `sensitivity.stable=False`
      (`max_abs_delta_oos_pct=4.25` vs. the 2.0pp threshold), and
      **fold 1 (2019-09-12→2022-01-14) — one of the two OOS windows
      that have failed under every technique tried to date — is still
      `feasible=False`** (`capital_deployed_pct=-506%`, a degenerate
      simulation, not a real loss). Fold 2 (2022-01-15→2024-05-19, the
      other historically-failing window) is now feasible with a real if
      modest edge (`+8.23%`) — a genuine improvement over prior rounds,
      but fold 1's failure mode persists unchanged. **Not promoted** —
      same stability-gate failure as every other candidate tried under
      Task #93 and this follow-up.
    - **Net read for the Phase 5 decision**: fixing the crossing bug and
      searching the full pool (a) confirms `power_law`'s search-dominance
      was partly artifactual, (b) lowers the accepted baseline's own
      apparent edge from `+84.90%` to `+21.73%` and now shows it losing to
      a naive linear baseline, (c) produces one new candidate (round 8)
      that clears the baseline-relative bar Chris asked for, but (d) that
      candidate still fails the sensitivity-stability gate on the same
      2019-09-12→2022-01-14 window that has broken every technique tried
      across this entire research program. Presented to Chris as the
      sharpened choice the original plan anticipated: pursue a genuinely
      new, uncorrelated data source for that window, or accept that no
      technique explored so far — including this session's full ablation
      over 12 indicators — resolves it, and treat the current baseline
      (now understood to be weaker than believed, `+21.73%` not
      `+84.90%`) as the practical ceiling until new data arrives.
    - `tests/dq/strategies/sdca/` stayed green throughout (571 passed, 38
      skipped for optional deps, by the end of Phase 4).

7. **2026-09-24 — SDCA recalibration v1** (Chris: increase indicator breadth,
   fix M2/RSI z-score spikiness, add a drawdown cap + widen the curve search
   + enable crash_override, re-run and calibrate toward ~30% drawdown; "operate
   independently... treat this as exploration"). Design doc:
   `docs/superpowers/specs/2026-09-24-sdca-recalibration-v1-design.md`.
   - Phase 1 (floored 12-name weight search,
     `scripts/run_full_pool_floored_search.py`), Phase 3 (drawdown cap in
     `curve_optimize_feasibility.py`, widened `WIDE_KNEE_SEARCH_BOUNDS`/
     `WIDE_KNEE_COARSE_GRID`, `crash_override_enabled=True`) and Phase 4
     (combined re-run/calibration, `scripts/run_recalibration_v1_full_resolution.py`)
     are the diagnostic search work this backlog item covers — same
     never-writes-settings.json protocol as every prior round; see the design
     doc for the full walk-forward result once Phase 4 completes.
   - Phase 2 (z-score spikiness) landed as code, not just search config:
     `composite_risk.py` gained a `causal_ema_smooth` helper, applied only
     inside `m2_liquidity_z` (`indicator_catalog.py`, short 5-day halflife —
     the root cause is monthly FRED data forward-filled daily then
     rolling-z'd over a window with ~3 distinct real prints, a literal step
     function). `price_oscillators.py`'s `_RSI_CURVE_POWER` moved from 4.0
     (quartic, chosen 2026-09-07 specifically to stop a linear map from
     pegging a bull market at the z floor — see that section's
     `test_mid_bull_rsi_does_not_sit_at_floor_for_entire_bull` regression
     guard) to 3.5: quartic's near-zero read through ordinary 55-75 RSI
     followed by a steep run-up near the extremes, compounded with
     `agreement_scaled_blend`'s up-to-1.5x same-sign amplification, was
     reading as a flatline-then-spike. 3.5 is the lowest power that stays
     clear of the 2026-09-07 guard (empirically, power ≤3.25 already pushes
     that guard's mean mid-bull `|z|` back over its 1.25 threshold — the old
     pegging problem returns before reaching the originally-guessed 2.5-3.0
     range) while still measurably softening the ordinary-range flatline and
     verified clean against the real 2023-2024 BTC bull run (~4% of days
     pegged at the floor, not the whole run). `tests/dq/strategies/sdca/`
     green throughout (576 passed after adding coverage for
     `causal_ema_smooth` and the M2 step-vs-ramp behavior).
   - **Round 1 result (2026-09-24, commit `9abe32429`)** — Phase 3's blanket
     `MAX_DRAWDOWN_CAP_PCT`/`MAX_DRAWDOWN_COMFORT_PCT` gate set to 30.0/25.0
     (a binding search-time constraint, not a backstop) and Phase 4 run with
     `crash_override_enabled=True` (`trigger_z=-2.0, ramp_z=1.0,
     override_risk=95.0, window=14`). Winning shape: `buy_max_rate=15.0,
     buy_knee_risk=30.0, sell_knee_risk=45.0, sell_max_rate=15.0,
     buy_curvature=1.5, sell_curvature=1.0`. **Failed**: mean OOS
     (duration-weighted) `-37.31%` vs. flat DCA, `beats_flat_dca_oos=False`,
     `beats_baseline_oos=False` (that run's own risk50-linear baseline came
     in at `-27.32%`). A hollow win by construction — the tight cap forced
     the search to resolve the drawdown/capital-deployed tension by
     starving capital deployment (fold 0 `capital_deployed=-94.1%`, fold 1
     `0.3%`, fold 2 `-9.4%` — barely investing) instead of finding a
     genuinely safer shape. Not promoted.
   - **Round 2 result (2026-09-24→25, commit `f748630`)** — per Chris's
     direction to use `crash_override` as the primary crash-response lever
     instead of the blanket cap: loosened `MAX_DRAWDOWN_CAP_PCT`/
     `MAX_DRAWDOWN_COMFORT_PCT` to 50.0/45.0 (a true backstop, no longer the
     dominant force shaping the curve search); `crash_override` itself left
     unchanged and independently re-verified against the real Feb–Mar 2020
     COVID crash (fires exactly on 2020-03-12 "Black Thursday", forces risk
     to 95 for ~10 days, back to baseline by 03-26 — no retuning needed).
     Winning shape: `buy_max_rate=25.0, buy_knee_risk=40.0,
     sell_knee_risk=70.0, sell_max_rate=30.0, buy_curvature=1.5,
     sell_curvature=1.0`. Headline result is real and clears both bars for
     the first time this round: mean OOS (duration-weighted) `+3.53%`,
     `beats_flat_dca_oos=True`, `beats_baseline_oos=True` (`+36.30%` over
     that run's baseline of `-32.76%`). Two problems remain unresolved:
     (a) fold 2 `max_drawdown_pct=50.8%`, above both the original ~30%
     target and the loosened 50% backstop itself; (b) **all three OOS
     folds still fail `walk_forward.py`'s own
     `SdcaOptimizeObjective.capital_deployed_floor_pct=10.0` gate** (fold 0
     `-28.5%`, fold 1 `-1.1%`, fold 2 `-7.8%` — net sellers over each OOS
     window, not net buyers). The improved headline return is coming from a
     sell-and-stay-out curve correctly avoiding two bad windows, not from
     staying invested through them — fold 1's OOS window
     (2019-09-12→2022-01-14) swallows the entire 2020-21 bull run and
     fold 2's (2022-01-15→2024-05-19) swallows the 2023-24 recovery, both
     missed entirely (the "non-participation problem"). Two
     `test_curve_optimize_feasibility.py` drawdown-gate fixture tests
     needed recalibrating to the new 50/45 band (same commit).
     `tests/dq/strategies/sdca/` green (585 passed, 38 skipped). Not
     promoted.
   - **Phase 2 audit (2026-09-25)**: Chris flagged that round 1's own chat
     report described Phase 2 as "folded into Phase 1's indicator-breadth
     widening", which read as possibly not a real, separate code change.
     Checked against the bullet immediately above (already correct) and
     against current source: `causal_ema_smooth` (`composite_risk.py`),
     `_M2_SMOOTHING_HALFLIFE_DAYS=5.0` (`indicator_catalog.py`), and
     `_RSI_CURVE_POWER=3.5` (`price_oscillators.py`, moved from 4.0) are
     all still in place exactly as landed in commit `4e05eda9c`
     ("fix(sdca): damp M2/RSI composite z-score spikiness at the source"),
     confirmed via `git log -L` on each symbol's line — no round 1 or
     round 2 work touched or reverted any of it. **Real, implemented,
     unchanged — not open work.** The chat-report phrasing was just
     imprecise about timing (it landed as its own commit before Phase 1's,
     not "inside" Phase 1); RESEARCH_STATE.md's own record (bullet above)
     had it right all along.

## North-star ceiling (benchmark only — NEVER a trading candidate)

Chris's 2026-09-11 direction, after pausing new-indicator work to sanity-check
the optimization pipeline itself: "if we had the perfect indicator, then how
much could we really materially make? ... fit the perfect line, fit the
perfect valuation index, and then fit the perfect buy and sell strategy
around that and make a tier sheet for it ... as we add more indicators and
keep optimizing, that's what we aim for. We won't realistically reach it, but
at least it's a target."

`scripts/run_oracle_ceiling.py` builds a **non-causal** ("oracle") risk index
directly from realized BTC price — piecewise log-price position between the
actual local price extreme inside every documented cycle window
(`cycle_windows.SdcaCycleWindows.btc_v1()` / `btc_medium_term_v1()`), blended
3:1 long:medium wherever both timeframes have real (non-extrapolated)
coverage for a day, falling back to whichever timeframe does where only one
does. This index uses future price information no live indicator could ever
have — it is a theoretical ceiling, not a strategy, and must **never** be
added to the Strategy Book artifact's `candidates` collection or
`settings.json`. The resulting risk series is handed to the unmodified
production curve search (`curve_optimize.search_wide_knee_curve`, same
bounds/grid a real trial uses) so only the index is idealized, not the
curve-fitting methodology.

An independent adversarial review (2026-09-11) caught and fixed a real bug
before this number was final: the long-term anchor set's last pin trails the
price series by ~11 months, and the original naive fixed-ratio blend
flat-extrapolated that stale peak value across the entire tail at 3:1
weight — pinning risk to 75-100 through 2026-06-30's -53% trough and starving
the "perfect" curve of its best late buying opportunity. Fixed via a
coverage-aware blend (`_blend_risk`) that uses whichever timeframe has real
(non-extrapolated) coverage alone when the other doesn't. The corrected
ceiling is materially higher than the pre-fix run — this file records only
the corrected, reviewed result.

- **Window:** 2018-01-01 → 2026-09-02, $1,000 initial cash, unshifted (no
  `signal_delay_days` — see caveat below).
- **Benchmarks (same accounting `run_backtest`'s `vs_lump_pct`/
  `vs_flat_dca_pct` are measured against):** lump-sum from first trade day
  $17,340 (+1,634.0%); flat DCA from window start $4,791 (+379.1%).
- **Oracle-optimal SDCA:** $148,330 (+14,733.0%) — +755.4% vs lump, +2,995.9%
  vs flat DCA. Max drawdown 61.8%, `risk_adjusted_return=238.36`.
- **Winning curve** (production `WIDE_KNEE_SEARCH_BOUNDS`/`WIDE_KNEE_COARSE_GRID`,
  unmodified): `buy_max_rate=39.22, buy_knee_risk=21.81, sell_knee_risk=79.31,
  sell_max_rate=35.48, buy_curvature=3.97, sell_curvature=5.95`.
- **Caveats:**
  - Non-causal by construction — uses realized future price every day. This
    is a ceiling, never a deployable strategy.
  - Does **not** apply `signal_delay_days=3` (real trials do, and run through
    2026-08-30) — the oracle deliberately represents a zero-implementation-lag
    theoretical ceiling, not a directly comparable trial.
  - Not a claimed ceiling on `stage_a.combined_cycle_overlap_score` — that
    score rewards saturating an *entire* peak/trough window at risk ≥80/≤35,
    which a smooth interpolation does less aggressively than a step function
    would (diagnostic sensitivity sweep in the script output, not treated as
    a target to hit).
  - Full tier sheet (anchors, sensitivity sweep, coverage stats):
    `.scratch/oracle_ceiling/oracle_ceiling_result.json` (gitignored).

This is the target referenced in item 6-8 above and any future indicator
work: as real indicators + curve search improve, compare their OOS
`total_return_pct` against this $148,330 / +14,733% figure to see how much
headroom remains — never as a bar any real (causal) strategy is expected to
clear.
