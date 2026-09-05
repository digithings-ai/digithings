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
