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
   once against real BTC-USD data — **diagnostic only, not an accepted
   candidate**:
   - Per-indicator period optimization (solo, against the combined objective)
     kept all five tunable indicators: `power_law` (180d trend, anchor),
     `weekly_rsi` (8/7), `weekly_macd` (12/26/12/26 — default periods won),
     `sma_band` (120/30), `rs_eth` (60/20).
   - Equal-weight recombination (7 indicators incl. `m2`/`dxy`,
     1/7 each): long=25.76, medium=12.83, combined=90.12 (3:1 ratio).
   - Floor-diversified aggregate reweight (floor 0.25): `power_law=1.0,
     sma_band=1.0`, everything else (`m2`, `dxy`, `weekly_rsi`, `weekly_macd`,
     `rs_eth`) floored at `0.25`. long=42.97, medium=24.00, combined=152.89 —
     beats the equal-weight baseline on every axis.
   - Ratio sensitivity (2:1 / 3:1 / 5:1): the winning weight mix above is
     identical across all three ratios tried; only the combined objective's
     scale changes (109.93 / 152.89 / 238.82). Ratio choice is still open —
     Chris said he'd pick after seeing results — but isn't yet shown to change
     *which* mix wins, only how much long-term is weighted in the reported
     number.
   Curve/threshold optimization against this index (Chris's explicitly
   separate stage 5) hasn't started.
