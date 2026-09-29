# SDCA method reuse for other assets

The strategy-development method behind the BTC work (periodic
self-optimization loop, robust curve search, walk-forward gate, challenger
comparisons, attribution gates, diagnostic tearsheets) is intentionally kept
on this branch so it can be repurposed per asset. The reusable core already
lives in `src/` and is asset-agnostic; only the thin `scripts/` layer is
BTC-hardcoded (see seams below).

## Reusable core (src, no per-asset changes needed)

> Scope note: the search/gate/ablation modules below
> (`curve_optimize_feasibility.py`, `baseline_evaluator.py`, `ablation.py`)
> and the seven `scripts/` entries live on the research branch
> (`claude/sdca-full-recalibration`) and arrive on `develop` via follow-up
> ports — a develop reader hitting an ImportError should pull that branch,
> not assume the module was deleted. Everything else named here is already
> on `develop`.

- Trade mechanics: `AccumDistCurve` + `size_trade` + `run_backtest`
  (`strategies/sdca/backtest.py`, `curve.py`) — identical semantics to the
  production signals app.
- Index math: `compute_composite_risk`, `causal_rolling_z`,
  `causal_ema_smooth` (`composite_risk.py`); `build_risk_index`
  (`risk_index.py`); `risk_from_weighted_z` (`stage_a.py`).
- Search: `search_wide_knee_curve_multi_window_robust`
  (`curve_optimize_feasibility.py`) + tiered bounds/grid
  (`WIDE_KNEE_TIERED_SEARCH_BOUNDS`, `WIDE_KNEE_TIERED_COARSE_GRID` on the
  research branch; `_MID_TIER_KEYS` in `curve_shape.py`) — bounds suit any
  crypto-like risk series; revisit only for structurally different assets.
- Gate: `run_sdca_walk_forward` / `score_trial_on_folds` / `is_feasible` /
  sensitivity (`walk_forward.py`, `optimize.py`),
  `run_sdca_walk_forward_vs_baseline` (`baseline_evaluator.py`),
  `run_ablation_rounds` (`ablation.py`). Caps (dd 50, deployed floor,
  sensitivity 2.0) are policy — review per asset, don't silently inherit.
- Feeds: `load_sdca_ohlcv`, `load_sdca_extra_sources`,
  `load_date_value_frame` (`optimize.py`, `indicator_catalog.py`).
- Tearsheets: `from_nautilus_run`, `tearsheet_overlays`,
  `breakdown_from_daily` (`tearsheet_data.py`, `dca_metrics.py`).

## Per-asset seams (what changes for a new asset)

1. **Price history**: `data/price-history/<SYM>.csv` (`timestamp,close`
   columns). Rails fits need >= 730 rows AND >= 730 calendar-day span
   (`quantile_rails.validate_fit_series`); below that, `rolling_z` is the
   documented fallback (`rolling_z_is_fallback_for`).
2. **Rails fitter**: BTC uses `btc_power_law_rails_fitter` (genesis-anchored
   QuantReg). Other assets use the generic path — `generic_valuation.py`
   (`fit_generic_valuation`, origin = asset's own first bar) — selectable
   via `providers.resolve_sdca_risk_model` (`btc_power_law` |
   `generic_valuation` | `rolling_z`). Walk-forward callers pass the fitter
   in; no engine change needed.
3. **Extra feeds**: FRED M2/DXY siblings are USD-macro and reusable for any
   USD-quoted asset. Onchain legs depend on Bitview/CoinMetrics coverage
   for the asset (`data/onchain/bitview/`, `data/onchain/coinmetrics/`);
   assets without onchain coverage run price + macro only, with absent
   extras zeroed via `drop_extras_missing_sources`.
4. **Seed weights**: BTC's live 5-weights came from the Task-7 reweight
   search. A new asset seeds from the Stage-A weight search
   (`optimize_stage_a_weights` in `stage_a.py` on develop;
   `optimize_stage_a_weights_combined` on the research branch) or an
   educated prior, then enters the same loop.
5. **Frozen index**: each asset gets its own `load_inputs()`-equivalent
   (full-history rails + `extra_z` with per-feed windows). Never reuse one
   asset's frozen index for another.

## Script inventory (BTC-hardcoded lines to parameterize)

All seven take `DEFAULT_DATA_PATH = .../BTC-USD.csv`,
`symbols=["BTC-USD"]`, and (where gating)
`rails_fitter=btc_power_law_rails_fitter`:

- `run_periodic_self_optimization_cycle.py` — the loop itself
  (alternating ablation / robust curve search, vs-flat + vs-live gate).
- `run_replica_comparison.py` / `run_replica_3vote.py` — challenger
  protocol (same search budget both sides, raw + gated legs,
  `beats_production_oos`).
- `run_oscillator_dropone_gate.py` / `run_macro_dropone_gate.py` —
  fixed-shape drop-one attribution pattern (copy for any vote family).
- `build_cycle4_candidate_diagnostic_tearsheet.py` /
  `build_top3_diagnostic_tearsheets.py` — local-only tearsheet pattern
  (frozen index + `from_nautilus_run`, distinct diagnostic slugs).

Deferred follow-up (not done here): extract these hardcodings into one
shared `scripts/sdca_asset_config.py` (symbol, data path, rails fitter,
seed weights) with `--asset` on the loop driver. Until then, repurposing =
copy a script, swap the five hardcoded lines per the seams above.

## Checklist for a new asset

1. Land price history (see seam 1; rolling_z fallback if short).
2. Choose rails fitter (seam 2); verify fit converges on the asset.
3. Wire feeds present for the asset (seam 3); zero the rest.
4. Seed weights (seam 4); build the asset's frozen index (seam 5).
5. Run the loop; gate vs flat DCA + vs the asset's incumbent (if any).
6. Challenger + attribution before any promotion discussion.
7. Diagnostic tearsheets under distinct slugs; promotion follows the same
   owner-accept protocol (RESEARCH_STATE step 6 + test pins).
