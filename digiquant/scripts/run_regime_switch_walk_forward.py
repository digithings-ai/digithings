#!/usr/bin/env python3
"""Stage 3/4: OOS walk-forward for the regime-conditional weight-switch candidate.

Context (see project memory, "FIRST improvement found 2026-09-18" +
"small-sample caveat investigated and largely resolved" same day): splicing
power_law-only risk on high-vol days with the fixed baseline
(power_law=1.0, m2=0.5, dxy=0.5) on low-vol days beat the fixed baseline by
+30.71 combined in-sample cycle-overlap objective, and the improvement was
shown to be present in both the long-term and medium-term cycle-window
components independently -- not just an artifact of the two dominant
historical peaks. That is still in-sample evidence. This script is the real
robustness test: walk-forward OOS validation with a sensitivity check.

Why a new script instead of ``run_sdca_walk_forward``: that function (and
everything under it -- ``score_trial_on_folds``,
``extra_indicators_for_window``) assumes ONE fixed composite-weight vector
for the whole trial. A regime-conditional switch needs a *different* risk
series depending on the day's trailing-volatility regime, which no existing
entry point supports. Investigation found the fix needs no core-plumbing
changes: ``run_backtest`` (``backtest.py``) accepts a precomputed risk
series directly rather than reconstructing it from indicator weights, so
this script computes the regime-switched risk series per fold (reusing
``run_regime_conditional_reweight_experiment.py``'s
``trailing_realized_vol``/``causal_expanding_median_split``/``splice``/
``risk_from_weighted_z`` primitives) and feeds it straight into
``run_backtest``, entirely bypassing the single-fixed-weight-vector
limitation -- fully diagnostic, no production code touched.

Design, mirroring ``score_trial_on_folds``'s no-lookahead discipline:
  - Regime signal (trailing realized vol + causal expanding-median split) is
    computed ONCE over the full historical series, not restarted per fold --
    matches how ``extra_z`` (m2, dxy) is already treated elsewhere in this
    codebase, and avoids fold-boundary cold-start artifacts in the trailing
    window and the expanding median.
  - Rails ARE refit per fold, IS-only, via ``btc_power_law_rails_fitter`` --
    the #3173 "rails leakage" rule (truncated quadratic log-time fits do not
    extrapolate safely) means OOS must reuse the IS-fitted model, never a
    fresh OOS-inclusive fit. power_law_confluence_z is computed separately
    for the IS and OOS date ranges from that same IS-fitted model.
  - Curve shape is the published ``btc_optimized`` preset
    (buy_max_rate=35.5, buy_knee_risk=24.1, sell_knee_risk=71.9,
    sell_max_rate=21.0, buy_curvature=1.3, sell_curvature=4.0) -- frozen as a
    pragmatic first pass rather than re-searched per fold, consistent with
    "index then curve" but prioritizing getting a real OOS read on the
    regime-switch *index* mechanism first.

Never touches settings.json/RESEARCH_STATE.md per the standing gate: do not
touch settings.json or RESEARCH_STATE.md until this table shows
beats_flat_dca_oos=True with a stable sensitivity check -- report the full
table to Chris for explicit accept first.

Usage:
    uv run python -m scripts.run_regime_switch_walk_forward
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

import polars as pl

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
sys.path.insert(0, str(DIGIQUANT_ROOT / "scripts"))

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z
from digiquant.strategies.sdca.walk_forward import (
    make_walk_forward_folds,
    window_slice,
)
from digiquant.strategies.sdca.optimize import btc_power_law_rails_fitter

from run_regime_conditional_reweight_experiment import (  # noqa: E402
    VOL_WINDOW,
    BASELINE,
    causal_expanding_median_split,
    splice,
    trailing_realized_vol,
)

HIGH_VOL_WEIGHTS = SdcaCompositeWeights(power_law=1.0, m2=0.0, dxy=0.0)

# Published btc_optimized preset shape -- frozen as this pass's curve.
SHAPE = SdcaCurveShape(
    buy_max_rate=35.5,
    buy_knee_risk=24.1,
    sell_knee_risk=71.9,
    sell_max_rate=21.0,
    buy_curvature=1.3,
    sell_curvature=4.0,
)
INITIAL_CASH = 1000.0


def regime_switched_risk_series(
    dates: list, prices: list[float], extra_z: dict, is_high_vol_full: list[bool]
) -> list[float | None]:
    """Rebuild power_law z on this window's IS-fitted rails and splice."""
    rails_model = btc_power_law_rails_fitter(dates, prices)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    rails = rails_model.rails(date_s)
    power_law_z = power_law_confluence_z(date_s, price_s, rails["low"], rails["median"], rails["high"]).to_list()

    baseline_risk = risk_from_weighted_z(dates, power_law_z, extra_z, BASELINE)
    high_vol_risk = risk_from_weighted_z(dates, power_law_z, extra_z, HIGH_VOL_WEIGHTS)
    return splice(baseline_risk, high_vol_risk, is_high_vol_full)


def slice_extra_z(extra_z: dict, all_dates: list, window_dates: list) -> dict:
    idx_by_date = {d: i for i, d in enumerate(all_dates)}
    idxs = [idx_by_date[d] for d in window_dates]
    return {name: [series[i] for i in idxs] for name, series in extra_z.items()}


def run_backtest_metrics(dates: list, prices: list[float], risk: list[float | None]) -> dict:
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    risk_s = pl.Series("risk", risk, dtype=pl.Float64)
    report, _frame = run_backtest(date_s, price_s, risk_s, AccumDistCurve(SHAPE.to_nodes()), INITIAL_CASH)
    return {
        "vs_flat_dca_pct": report.vs_flat_dca_pct,
        "vs_lump_pct": report.vs_lump_pct,
        "capital_deployed_pct": report.capital_deployed_pct,
        "max_drawdown_pct": abs(report.dca_max_drawdown_pct) * 100.0,
    }


def score_fold(
    dates: list,
    prices: list,
    extra_z: dict,
    is_high_vol_full: list[bool],
    is_start,
    is_end,
    oos_start,
    oos_end,
) -> dict:
    is_dates, is_prices = window_slice(dates, prices, is_start, is_end)
    oos_dates, oos_prices = window_slice(dates, prices, oos_start, oos_end)

    is_extra_z = slice_extra_z(extra_z, dates, is_dates)
    oos_extra_z = slice_extra_z(extra_z, dates, oos_dates)
    idx_by_date = {d: i for i, d in enumerate(dates)}
    is_flags = [is_high_vol_full[idx_by_date[d]] for d in is_dates]
    oos_flags = [is_high_vol_full[idx_by_date[d]] for d in oos_dates]

    # Rails fit ONCE on the IS window; OOS z is computed from that same
    # IS-fitted model (never refit on OOS -- #3173 rails-leakage rule).
    rails_model = btc_power_law_rails_fitter(is_dates, is_prices)

    def risk_from_model(win_dates, win_prices, win_extra_z, win_flags):
        date_s = pl.Series("date", win_dates, dtype=pl.Date)
        price_s = pl.Series("price", win_prices, dtype=pl.Float64)
        rails = rails_model.rails(date_s)
        pl_z = power_law_confluence_z(date_s, price_s, rails["low"], rails["median"], rails["high"]).to_list()
        baseline_risk = risk_from_weighted_z(win_dates, pl_z, win_extra_z, BASELINE)
        high_vol_risk = risk_from_weighted_z(win_dates, pl_z, win_extra_z, HIGH_VOL_WEIGHTS)
        return splice(baseline_risk, high_vol_risk, win_flags)

    is_risk = risk_from_model(is_dates, is_prices, is_extra_z, is_flags)
    oos_risk = risk_from_model(oos_dates, oos_prices, oos_extra_z, oos_flags)

    is_metrics = run_backtest_metrics(is_dates, is_prices, is_risk)
    oos_metrics = run_backtest_metrics(oos_dates, oos_prices, oos_risk)
    feasible = oos_metrics["capital_deployed_pct"] > 1.0
    return {"in_sample": is_metrics, "out_of_sample": oos_metrics, "feasible": feasible}


def print_wf_row(label: str, fold_scores: list[dict], holdout_metrics: dict | None) -> None:
    print(f"\n=== {label} ===")
    for i, fs in enumerate(fold_scores):
        is_m, oos_m = fs["in_sample"], fs["out_of_sample"]
        print(
            f"  fold {i}: IS vs_flat_dca={is_m['vs_flat_dca_pct']:+.2f}%  "
            f"OOS vs_flat_dca={oos_m['vs_flat_dca_pct']:+.2f}%  "
            f"gap={oos_m['vs_flat_dca_pct'] - is_m['vs_flat_dca_pct']:+.2f}  "
            f"OOS vs_lump={oos_m['vs_lump_pct']:+.2f}%  "
            f"OOS capital_deployed={oos_m['capital_deployed_pct']:.1f}%  "
            f"OOS max_dd={oos_m['max_drawdown_pct']:.1f}%  "
            f"feasible={fs['feasible']}"
        )
    mean_is = statistics.mean(fs["in_sample"]["vs_flat_dca_pct"] for fs in fold_scores)
    mean_oos = statistics.mean(fs["out_of_sample"]["vs_flat_dca_pct"] for fs in fold_scores)
    beats_flat_dca_oos = mean_oos > 0.0
    print(f"  mean IS vs_flat_dca={mean_is:+.2f}%  mean OOS vs_flat_dca={mean_oos:+.2f}%")
    print(f"  beats_flat_dca_oos={beats_flat_dca_oos}")
    if holdout_metrics is not None:
        print(
            f"  holdout: vs_flat_dca={holdout_metrics['vs_flat_dca_pct']:+.2f}%  "
            f"vs_lump={holdout_metrics['vs_lump_pct']:+.2f}%  "
            f"capital_deployed={holdout_metrics['capital_deployed_pct']:.1f}%  "
            f"max_dd={holdout_metrics['max_drawdown_pct']:.1f}%"
        )
    return beats_flat_dca_oos


def run(data_path: Path = DEFAULT_DATA_PATH) -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=data_path, data_dir=None)
    print(f"BTC-USD {dates[0]}..{dates[-1]} ({len(dates)} daily bars)\n")

    extra_z = load_sdca_extra_z(dates, prices, data_path=data_path, data_dir=None)
    missing = [name for name in ("m2", "dxy") if name not in extra_z]
    if missing:
        print(f"Missing required extras {missing} -- cannot run.")
        return

    folds, holdout = make_walk_forward_folds(dates, n_folds=3, holdout_frac=0.2, oos_frac=0.25)
    print(f"{len(folds)} folds, holdout tail {holdout[0]}..{holdout[1]}\n")

    def run_full(vol_window: int) -> tuple[list[dict], dict]:
        vol = trailing_realized_vol(prices, vol_window)
        is_high_vol_full = causal_expanding_median_split(vol)
        fold_scores = [
            score_fold(dates, prices, extra_z, is_high_vol_full, f.is_start, f.is_end, f.oos_start, f.oos_end)
            for f in folds
        ]
        holdout_dates, holdout_prices = window_slice(dates, prices, holdout[0], holdout[1])
        # Holdout rails refit on everything before the holdout tail (never on the holdout itself).
        search_dates, search_prices = window_slice(dates, prices, dates[0], holdout[0])
        holdout_extra_z = slice_extra_z(extra_z, dates, holdout_dates)
        idx_by_date = {d: i for i, d in enumerate(dates)}
        holdout_flags = [is_high_vol_full[idx_by_date[d]] for d in holdout_dates]
        rails_model = btc_power_law_rails_fitter(search_dates, search_prices)
        date_s = pl.Series("date", holdout_dates, dtype=pl.Date)
        price_s = pl.Series("price", holdout_prices, dtype=pl.Float64)
        rails = rails_model.rails(date_s)
        pl_z = power_law_confluence_z(date_s, price_s, rails["low"], rails["median"], rails["high"]).to_list()
        baseline_risk = risk_from_weighted_z(holdout_dates, pl_z, holdout_extra_z, BASELINE)
        high_vol_risk = risk_from_weighted_z(holdout_dates, pl_z, holdout_extra_z, HIGH_VOL_WEIGHTS)
        holdout_risk = splice(baseline_risk, high_vol_risk, holdout_flags)
        holdout_metrics = run_backtest_metrics(holdout_dates, holdout_prices, holdout_risk)
        return fold_scores, holdout_metrics

    fold_scores, holdout_metrics = run_full(VOL_WINDOW)
    beats_flat_dca_oos = print_wf_row(
        f"regime-switch walk-forward (vol_window={VOL_WINDOW}d, curve=btc_optimized published)",
        fold_scores,
        holdout_metrics,
    )

    print("\n=== sensitivity check: vol-detection window varied (widened grid) ===")
    sensitivity_oos = {}
    for vw in (45, 60, 75, 90, 120, 150, 180):
        fs, _ = run_full(vw)
        mean_oos = statistics.mean(f["out_of_sample"]["vs_flat_dca_pct"] for f in fs)
        sensitivity_oos[vw] = mean_oos
        print(f"  vol_window={vw:>3}d  mean OOS vs_flat_dca={mean_oos:+.2f}%")
    max_abs_delta_oos_pct = max(sensitivity_oos.values()) - min(sensitivity_oos.values())
    stable = max_abs_delta_oos_pct < 5.0 and all(v > 0.0 for v in sensitivity_oos.values())
    print(f"  max_abs_delta_oos_pct={max_abs_delta_oos_pct:.2f}  all_positive={all(v > 0.0 for v in sensitivity_oos.values())}")
    print(f"  sensitivity stable={stable}")

    print(f"\nOVERALL: beats_flat_dca_oos={beats_flat_dca_oos}  sensitivity_stable={stable}")
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
