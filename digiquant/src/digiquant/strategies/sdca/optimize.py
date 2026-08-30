"""Walk-forward search over SDCA curve-shape parameters (#3174).

Fitness is injected (``SdcaTrialEvaluator``). Production dispatch uses the
Nautilus evaluator; tests inject a fake. ``SdcaBacktestReport`` is never the
score. Rails are refit per fold on the IS window only (#3173).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.data.loader import load_ohlcv_csv
from digiquant.models import OptimizeResult
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, fit_btc_power_law
from digiquant.strategies.sdca.indicator_catalog import (
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    composite_weights_from_params,
    extra_indicators_for_window,
    extra_z_vectors,
    load_date_value_frame,
    missing_extra_names,
)
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.walk_forward import (
    SENSITIVITY_SPIKE_PCT,
    FoldScore,
    RailsFitter,
    SdcaOptimizeObjective,
    SdcaTrialEvaluator,
    SdcaTrialMetrics,
    WalkForwardFold,
    make_walk_forward_folds,
    objective_score,
    params_are_valid,
    score_trial_on_folds,
    sensitivity_neighbors,
    shape_from_params,
    window_slice,
)

logger = logging.getLogger(__name__)

RAILS_PROTOCOL = (
    "refit per fold on the in-sample window only; never a full-history fit. "
    "Truncated quadratic log-time rails do not extrapolate (#3173)."
)

_PRESETS_PATH = Path(__file__).parent / "presets.json"
_PROVENANCE_PATH = Path(__file__).parent / "btc_optimized_provenance.json"

SDCA_SHAPE_DEFAULTS: dict[str, float] = {
    "buy_max_rate": 10.0,
    "buy_knee_risk": 35.0,
    "sell_knee_risk": 80.0,
    "sell_max_rate": 10.0,
    "buy_curvature": 1.0,
    "sell_curvature": 2.0,
    "valuation_weight": 1.0,
    "m2_weight": 0.0,
    "rs_eth_weight": 0.0,
    "dxy_weight": 0.0,
}


class SensitivityReport(BaseModel):
    """5% perturbation of the winner. A spike is not a plateau."""

    model_config = ConfigDict(frozen=True, strict=True)

    frac: float = Field(0.05, gt=0.0, lt=1.0)
    spike_threshold_pct: float = Field(SENSITIVITY_SPIKE_PCT, gt=0.0)
    max_abs_delta_oos_pct: float
    stable: bool
    neighbor_count: int = Field(ge=0)


class SdcaWalkForwardResult(BaseModel):
    """Search outcome: winner, per-fold scores, holdout, sensitivity, provenance."""

    model_config = ConfigDict(frozen=True, strict=True)

    best_params: dict[str, float | int | str]
    folds: list[WalkForwardFold]
    holdout: tuple[date, date]
    fold_scores: list[FoldScore]
    mean_is_vs_flat_dca_pct: float
    mean_oos_vs_flat_dca_pct: float
    is_oos_gap_pct: float
    holdout_metrics: SdcaTrialMetrics | None
    sensitivity: SensitivityReport
    num_evaluations: int = Field(ge=0)
    objective: SdcaOptimizeObjective
    rails_protocol: str = RAILS_PROTOCOL
    evaluator_label: str
    beats_flat_dca_oos: bool


class SdcaOptimizeProvenance(BaseModel):
    """Checked-in sidecar for ``btc_optimized``. Honest even when OOS is negative."""

    model_config = ConfigDict(frozen=True, strict=True)

    preset: str = "btc_optimized"
    evaluator: str
    objective: SdcaOptimizeObjective
    fit_window: tuple[date, date]
    folds: list[WalkForwardFold]
    holdout: tuple[date, date]
    best_params: dict[str, float | int | str]
    mean_is_vs_flat_dca_pct: float
    mean_oos_vs_flat_dca_pct: float
    is_oos_gap_pct: float
    holdout_vs_flat_dca_pct: float | None
    beats_flat_dca_oos: bool
    sensitivity_stable: bool
    rails_protocol: str
    notes: str


def btc_power_law_rails_fitter(dates: list[date], prices: list[float]) -> RiskModel:
    """Production ``RailsFitter``: QuantReg on the IS window only."""
    coeffs = fit_btc_power_law(
        pl.Series("date", list(dates), dtype=pl.Date),
        pl.Series("price", list(prices), dtype=pl.Float64),
        notes="walk-forward fold IS window (#3174); not full-history",
    )
    return BtcPowerLawRiskModel(coeffs)


def load_sdca_ohlcv(
    *,
    symbols: list[str],
    data_path: str | Path | None,
    data_dir: str | Path | None,
) -> tuple[list[date], list[float]]:
    """Daily close series for walk-forward. One symbol."""
    if data_path is not None:
        path = Path(data_path)
    elif data_dir is not None and symbols:
        path = Path(data_dir) / f"{symbols[0]}.csv"
    else:
        raise ValueError("SDCA optimize requires data_path or data_dir with symbols")
    df = load_ohlcv_csv(path)
    if "timestamp" not in df.columns:
        raise ValueError(f"OHLCV at {path} has no timestamp column")
    ts = df["timestamp"]
    if ts.dtype != pl.Date:
        ts = ts.dt.date()
    dates = ts.to_list()
    prices = [float(p) for p in df["close"].to_list()]
    if len(dates) != len(prices) or not dates:
        raise ValueError("SDCA optimize needs a non-empty aligned date/close series")
    return dates, prices


def _first_existing(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def load_sdca_extra_z(
    dates: list[date],
    prices: list[float],
    *,
    data_path: str | Path | None,
    data_dir: str | Path | None,
) -> dict[str, list[float | None]]:
    """Load independent extras from sibling files next to the BTC OHLCV CSV.

    Looks for ``M2SL.csv``/``M2.csv``, ``ETH-USD.csv``, ``DTWEXBGS.csv``/``DXY.csv``.
    Missing files omit that extra (trials that need it are skipped).
    """
    root = Path(data_path).parent if data_path is not None else None
    if root is None and data_dir is not None:
        root = Path(data_dir)
    if root is None:
        return {}
    m2_path = _first_existing(root, ("M2SL.csv", "M2.csv", "M2SL.parquet"))
    eth_path = _first_existing(root, ("ETH-USD.csv", "ETH-USD.parquet"))
    dxy_path = _first_existing(root, ("DTWEXBGS.csv", "DXY.csv", "DTWEXBGS.parquet"))
    m2_dates, m2_values = load_date_value_frame(m2_path) if m2_path else (None, None)
    eth_dates, eth_close = load_date_value_frame(eth_path) if eth_path else (None, None)
    dxy_dates, dxy_values = load_date_value_frame(dxy_path) if dxy_path else (None, None)
    weights = SdcaCompositeWeights(
        valuation=1.0,
        m2=1.0 if m2_dates is not None else 0.0,
        rs_eth=1.0 if eth_dates is not None else 0.0,
        dxy=1.0 if dxy_dates is not None else 0.0,
    )
    if not weights.enabled_extras():
        return {}
    return extra_z_vectors(
        pl.Series("date", list(dates), dtype=pl.Date),
        pl.Series("price", list(prices), dtype=pl.Float64),
        weights,
        ExtraIndicatorSources(
            m2_dates=m2_dates,
            m2_values=m2_values,
            eth_dates=eth_dates,
            eth_close=eth_close,
            dxy_dates=dxy_dates,
            dxy_values=dxy_values,
        ),
    )


def _mean_oos(scores: list[FoldScore]) -> float:
    if not scores:
        return float("-inf")
    return sum(s.out_of_sample.vs_flat_dca_pct for s in scores) / len(scores)


def _mean_is(scores: list[FoldScore]) -> float:
    if not scores:
        return float("-inf")
    return sum(s.in_sample.vs_flat_dca_pct for s in scores) / len(scores)


def _trial_oos_objective(scores: list[FoldScore], objective: SdcaOptimizeObjective) -> float:
    feasible = [s for s in scores if s.feasible]
    if not feasible:
        return float("-inf")
    return sum(objective_score(s.out_of_sample, objective) for s in feasible) / len(feasible)


def run_sdca_walk_forward(
    dates: list[date],
    prices: list[float],
    trials: list[dict[str, float | int | str]],
    *,
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
    evaluator_label: str,
    objective: SdcaOptimizeObjective | None = None,
    n_folds: int = 3,
    holdout_frac: float = 0.2,
    oos_frac: float = 0.25,
    sensitivity_frac: float = 0.05,
    extra_z: dict[str, list[float | None]] | None = None,
) -> SdcaWalkForwardResult:
    """Search ``trials`` under walk-forward; score the winner on the held-out tail."""
    obj = objective or SdcaOptimizeObjective()
    folds, holdout = make_walk_forward_folds(
        dates, n_folds=n_folds, holdout_frac=holdout_frac, oos_frac=oos_frac
    )
    ranked: list[tuple[float, dict[str, float | int | str], list[FoldScore]]] = []
    evaluated = 0
    for params in trials:
        merged = {**SDCA_SHAPE_DEFAULTS, **params}
        if not params_are_valid(merged):
            continue
        if missing_extra_names(composite_weights_from_params(merged), extra_z):
            continue
        evaluated += 1
        scores = score_trial_on_folds(
            merged, dates, prices, folds, rails_fitter, evaluator, obj, extra_z=extra_z
        )
        ranked.append((_trial_oos_objective(scores, obj), merged, scores))
    if not ranked:
        raise ValueError("no valid SDCA trials to evaluate")
    ranked.sort(key=lambda row: row[0], reverse=True)
    best_score, best_params, best_folds = ranked[0]
    if best_score == float("-inf"):
        logger.warning("all SDCA trials infeasible under capital/drawdown rails")

    mean_is = _mean_is(best_folds)
    mean_oos = _mean_oos(best_folds)
    sensitivity = _sensitivity_of(
        best_params,
        mean_oos,
        dates,
        prices,
        folds,
        rails_fitter,
        evaluator,
        obj,
        sensitivity_frac,
        extra_z,
    )
    holdout_metrics = _holdout_metrics(
        best_params, dates, prices, folds, holdout, rails_fitter, evaluator, extra_z
    )
    return SdcaWalkForwardResult(
        best_params=best_params,
        folds=folds,
        holdout=holdout,
        fold_scores=best_folds,
        mean_is_vs_flat_dca_pct=mean_is,
        mean_oos_vs_flat_dca_pct=mean_oos,
        is_oos_gap_pct=mean_is - mean_oos,
        holdout_metrics=holdout_metrics,
        sensitivity=sensitivity,
        num_evaluations=evaluated,
        objective=obj,
        evaluator_label=evaluator_label,
        beats_flat_dca_oos=mean_oos > 0.0,
    )


def _sensitivity_of(
    best_params: dict[str, float | int | str],
    mean_oos: float,
    dates: list[date],
    prices: list[float],
    folds: list[WalkForwardFold],
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
    objective: SdcaOptimizeObjective,
    frac: float,
    extra_z: dict[str, list[float | None]] | None,
) -> SensitivityReport:
    deltas: list[float] = []
    neighbors = sensitivity_neighbors(best_params, frac=frac)
    for neighbor in neighbors:
        if missing_extra_names(composite_weights_from_params(neighbor), extra_z):
            continue
        scores = score_trial_on_folds(
            neighbor,
            dates,
            prices,
            folds,
            rails_fitter,
            evaluator,
            objective,
            extra_z=extra_z,
        )
        deltas.append(abs(_mean_oos(scores) - mean_oos))
    max_delta = max(deltas) if deltas else 0.0
    return SensitivityReport(
        frac=frac,
        spike_threshold_pct=SENSITIVITY_SPIKE_PCT,
        max_abs_delta_oos_pct=max_delta,
        stable=max_delta <= SENSITIVITY_SPIKE_PCT,
        neighbor_count=len(neighbors),
    )


def _holdout_metrics(
    params: dict[str, float | int | str],
    dates: list[date],
    prices: list[float],
    folds: list[WalkForwardFold],
    holdout: tuple[date, date],
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
    extra_z: dict[str, list[float | None]] | None,
) -> SdcaTrialMetrics:
    """Fit rails on the searchable span (everything before holdout), score the tail."""
    search_end = folds[-1].oos_end
    search_dates, search_prices = window_slice(dates, prices, dates[0], search_end)
    hold_dates, hold_prices = window_slice(dates, prices, holdout[0], holdout[1])
    model = rails_fitter(search_dates, search_prices)
    shape = shape_from_params(params)
    weights = composite_weights_from_params(params)
    extras = extra_indicators_for_window(hold_dates, dates, extra_z or {}, weights)
    return evaluator(hold_dates, hold_prices, model, shape, weights.valuation, extras)


def persist_btc_optimized(
    result: SdcaWalkForwardResult,
    *,
    presets_path: Path | None = None,
    provenance_path: Path | None = None,
    notes: str = "",
) -> SdcaOptimizeProvenance:
    """Write ``btc_optimized`` into presets.json and a provenance sidecar."""
    shape = shape_from_params(result.best_params)
    dest = presets_path or _PRESETS_PATH
    raw = json.loads(dest.read_text())
    raw["btc_optimized"] = {
        "description": (
            "Walk-forward winner (#3174). Not a published digiquant.io number. "
            "Re-run with the Nautilus evaluator on real BTC when new history lands. " + notes
        ).strip(),
        "long_only": shape.sell_max_rate == 0.0,
        "shape": {
            "buy_max_rate": shape.buy_max_rate,
            "buy_knee_risk": shape.buy_knee_risk,
            "sell_knee_risk": shape.sell_knee_risk,
            "sell_max_rate": shape.sell_max_rate,
            "buy_curvature": shape.buy_curvature,
            "sell_curvature": shape.sell_curvature,
        },
    }
    dest.write_text(json.dumps(raw, indent=2) + "\n")
    hold_vs = result.holdout_metrics.vs_flat_dca_pct if result.holdout_metrics is not None else None
    provenance = SdcaOptimizeProvenance(
        evaluator=result.evaluator_label,
        objective=result.objective,
        fit_window=(result.folds[0].is_start, result.folds[-1].oos_end),
        folds=result.folds,
        holdout=result.holdout,
        best_params=result.best_params,
        mean_is_vs_flat_dca_pct=result.mean_is_vs_flat_dca_pct,
        mean_oos_vs_flat_dca_pct=result.mean_oos_vs_flat_dca_pct,
        is_oos_gap_pct=result.is_oos_gap_pct,
        holdout_vs_flat_dca_pct=hold_vs,
        beats_flat_dca_oos=result.beats_flat_dca_oos,
        sensitivity_stable=result.sensitivity.stable,
        rails_protocol=result.rails_protocol,
        notes=notes,
    )
    (provenance_path or _PROVENANCE_PATH).write_text(provenance.model_dump_json(indent=2) + "\n")
    return provenance


def walk_forward_to_optimize_result(
    result: SdcaWalkForwardResult,
    *,
    strategy_name: str,
    symbols: list[str],
) -> OptimizeResult:
    """Map SDCA walk-forward onto the shared ``OptimizeResult`` envelope."""
    status = "ok" if result.best_params else "error"
    if result.mean_oos_vs_flat_dca_pct == float("-inf"):
        status = "partial"
    hold = result.holdout_metrics
    hold_txt = "n/a" if hold is None else f"{hold.vs_flat_dca_pct:.4f}"
    message = (
        f"sdca walk-forward evaluator={result.evaluator_label} "
        f"evals={result.num_evaluations} mean_oos_vs_flat_dca_pct="
        f"{result.mean_oos_vs_flat_dca_pct:.4f} mean_is_vs_flat_dca_pct="
        f"{result.mean_is_vs_flat_dca_pct:.4f} gap={result.is_oos_gap_pct:.4f} "
        f"holdout_vs_flat_dca_pct={hold_txt} beats_flat_dca_oos="
        f"{result.beats_flat_dca_oos} sensitivity_stable={result.sensitivity.stable}"
    )
    return OptimizeResult(
        run_id=f"optimize-{uuid.uuid4().hex[:8]}",
        strategy_name=strategy_name,
        symbols=symbols,
        best_params=result.best_params,
        best_backtest=None,
        num_evaluations=result.num_evaluations,
        status=status,
        message=message,
    )


__all__ = [
    "RAILS_PROTOCOL",
    "SDCA_SHAPE_DEFAULTS",
    "SdcaOptimizeProvenance",
    "SdcaWalkForwardResult",
    "SensitivityReport",
    "btc_power_law_rails_fitter",
    "load_sdca_extra_z",
    "load_sdca_ohlcv",
    "persist_btc_optimized",
    "run_sdca_walk_forward",
    "walk_forward_to_optimize_result",
]
