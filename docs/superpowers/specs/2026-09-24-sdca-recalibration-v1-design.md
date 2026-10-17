# SDCA Recalibration v1 — Design

Date: 2026-09-24
Status: in progress (see per-phase status below)
Owners: digiquant / SDCA strategy research
Related: `src/digiquant/strategies/sdca/RESEARCH_STATE.md` ("Standard trial protocol", "Immediate backlog"), `scripts/run_ablation_best_round_full_resolution.py` (round 8 baseline, unpromoted). Round 8's drawdown has two documented figures, both real, measured differently: `scripts/build_round8_diagnostic_tearsheet.py` reports -61.32% from one continuous full-history (2015–2026) backtest; `.scratch/ablation/best_round_full_resolution.json` reports per-walk-forward-fold OOS drawdown (27.18% / 51.19% / 20.29%, 33.82% holdout) over the shorter fold windows. Phase 4 below compares against the walk-forward figures, since that's the apples-to-apples metric `run_sdca_walk_forward_vs_baseline` produces.

## 1. Problem

Chris reviewed the SDCA strategy and raised five asks, none yet reflected in code:

1. **Indicator breadth** — the validated pool (`EXTRA_INDICATOR_NAMES`, 11 names) is wider than any weight search has actually exercised together with a floor that forces every enabled indicator to carry real weight.
2. **M2 z-score is spiky** — the composite risk index visibly steps whenever the M2 liquidity indicator updates.
3. **RSI confluence z-score is spiky** — same visual complaint, different mechanism.
4. **No drawdown ceiling in the curve search** — `curve_optimize_feasibility.py` enforces a capital-deployed floor/comfort/cap but nothing bounds `max_drawdown_pct`, and the curve-shape search bounds don't reach far enough into aggressive medium-dip selling to find a lower-drawdown shape even if a gate existed.
5. **Crash response is too slow** — the composite only de-risked "end of February" during the Feb-2020 COVID crash; `crash_override` exists in code (`crash_override.py`, wired into `curve_sim.py`/`nautilus_evaluator.py`) but has never been turned on.

This is diagnostic/research work per the standing accept gate — nothing here writes `settings.json` or promotes a candidate in `RESEARCH_STATE.md`. Results are reported to Chris for explicit accept/reject, same as `run_ablation_best_round_full_resolution.py`.

## 2. Root causes and fixes

### 2.1 Indicator breadth + weight floor (Phase 1)

`EXTRA_INDICATOR_NAMES` (`indicator_catalog.py`) is already the correct, previously-validated 11-name pool (it excludes the 4 empirically-rejected indicators: adx, stochastic, vol_regime, halving_cycle) — no new indicator list needed. What's missing is a search that (a) considers all 11 plus `power_law` together and (b) forbids any enabled indicator from being floored to near-zero weight, via `optimize_stage_a_weights_combined_multi_ratio`'s existing `min_weight_floor` parameter (`stage_a.py`). `scripts/run_full_pool_floored_search.py` runs this 12-name, floor=0.1 search.

### 2.2 M2 spikiness — root cause: sparse source, not the blend

M2 is monthly FRED data, forward-filled to daily then rolling-z'd over a 90-day window that contains only ~3 distinct real print values (`m2_liquidity_z`, `indicator_catalog.py`) — so the rolling-z is a literal step function, one jump per monthly print. The composite-level `smoothing_window` already in `compute_composite_risk` (`composite_risk.py`) is the wrong place to fix this: it's uniform across every indicator and isn't exercised by the search path at all today. Fix: a new, narrowly-scoped helper `causal_ema_smooth` (`composite_risk.py`, next to `causal_rolling_z`) applied only inside `m2_liquidity_z`, with a short halflife (`_M2_SMOOTHING_HALFLIFE_DAYS = 5.0`) — enough to turn each monthly step into a few-day ramp without adding meaningful lag to an inherently slow signal.

### 2.3 RSI spikiness — root cause: quartic curve × confluence amplification

`rsi_continuous_z` (`price_oscillators.py`) maps RSI onto `[-3, 3]` through a power curve (`_RSI_CURVE_POWER`), deliberately raised from linear to quartic (4.0) on 2026-09-07 specifically to stop a *different* problem: a linear map pegged an entire bull market at the z floor (regression-guarded by `test_mid_bull_rsi_does_not_sit_at_floor_for_entire_bull`). Quartic's near-zero output through ordinary 55-75 RSI followed by a steep run-up near the extremes, compounded with `agreement_scaled_blend`'s up-to-1.5x same-sign amplification (`weekly_monthly_rsi_confluence_z`), reads as a flatline-then-spike rather than a ramp — the flip side of the same fix.

Moderating the power (not downstream-smoothing, which would blunt the fast response Phase 3's drawdown target needs) is the source-level fix, but the 2026-09-07 regression guard is the actual empirical boundary, not the originally-guessed 2.5-3.0 range: on the guard's own synthetic mid-bull fixture, power ≤3.25 already pushes mean mid-bull `|z|` back over the guard's 1.25 threshold — i.e. the old pegging problem starts returning before reaching 3.0. `_RSI_CURVE_POWER = 3.5` is the lowest value that stays clear of that guard (mean `|z|` 1.20 vs. the 1.25 cutoff) while still measurably softening the ordinary-range flatline (RSI=70 maps to -0.32 at power 4.0 vs. -0.42 at 3.5) and verified against the real 2023-2024 BTC bull run (only ~4% of days pegged at the floor there, vs. the whole run for the original linear map).

### 2.4 Curve aggressiveness + drawdown cap + crash override (Phase 3)

Three changes, one search:

- **Drawdown cap.** `curve_optimize_feasibility.py`'s `score_shape_on_index_feasibility_aware` already computes `base.max_drawdown_pct` as part of its internal `score_shape_on_index` call (no extra backtest needed). Add a soft-then-hard gate mirroring the existing capital-deployed pattern — `MAX_DRAWDOWN_CAP_PCT` (hard reject above), `MAX_DRAWDOWN_COMFORT_PCT` (soft penalty zone below the cap) — so the search itself refuses shapes that blow through the drawdown target instead of reporting them as merely low-scoring.
- **Wider search bounds.** `WIDE_KNEE_SEARCH_BOUNDS`/`WIDE_KNEE_COARSE_GRID` (`curve_optimize.py`) don't currently reach far enough into front-loaded, aggressive medium-dip selling (lower `sell_knee_risk`, lower `sell_curvature`) to let the search find a materially lower-drawdown shape even with the new gate in place. Widened on the sell side; the new drawdown gate rejects anything that doesn't actually help, so erring toward wider is safe.
- **Crash override.** `crash_override.py` is fully built and wired into both evaluators but disabled by default. Enabled with starting params tuned against the Feb-2020 COVID crash specifically (Chris's complaint: the composite only spiked "end of February," too late).

### 2.5 Combined re-run (Phase 4)

`scripts/run_recalibration_v1_full_resolution.py` chains 2.1's floored weight search → 2.4's widened, drawdown-capped, crash-override-enabled curve search → the standard `run_sdca_walk_forward_vs_baseline` comparison (duration-weighted, with sensitivity check), then iterates the drawdown cap / crash-override params / curve bounds toward "best risk-adjusted return with a drawdown around 30%, not exactly 30%" — not chasing the last points of drawdown reduction at large cost to return.

## 3. Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Floored 12-name weight search | **done** — `scripts/run_full_pool_floored_search.py`; first run used wrong (default) Stage 1 oscillator/extra windows, fixed and re-run; primary (3:1) winner: power_law=1.0, m2/rs_eth/dxy/onchain_mvrv/onchain_asopr/onchain_puell/onchain_rhodl/onchain_addr_ratio/fear_greed/weekly_monthly_rsi=0.1 (floor), weekly_monthly_macd=0.5; every extra indicator sits at or above floor, ratio-stable (2:1/3:1/5:1 pick the same weights) |
| 2 | M2 EMA smoothing + RSI curve power | **done** — `composite_risk.py`, `indicator_catalog.py`, `price_oscillators.py`; tests added/extended, `pytest tests/dq/strategies/sdca/` green |
| 3 | Drawdown cap + wider curve bounds + crash override | **done** — `curve_optimize_feasibility.py`, `curve_optimize.py`; crash override verified against real 2020-03-12 COVID crash data, no new wiring needed; tests added, `pytest tests/dq/strategies/sdca/` green (585 passed) |
| 4 | Combined search + calibration loop | planned |

## 4. Gate

Never writes `settings.json` or `RESEARCH_STATE.md`'s "Current best validated candidate" section. Diagnostic scripts write only under `.scratch/`. Reported to Chris as a walk-forward table (`beats_flat_dca_oos`, `sensitivity_stable`, realized max drawdown) for explicit accept/reject, same protocol as every prior ablation round.
