"""Remaining-book curve search with a frozen composite index.

Index members stay at published ``settings.json`` weights (power law 1.0 +
M2 0.5 + DXY 0.5). Search is over ``SdcaCurveShape`` only. Objective is
``total_return_pct`` (highest backtest return). vs-flat-DCA is logged, never
the headline, and never used to set ``beats_flat_dca_oos``.

Concentration uses fixed published cheap/rich bands (risk < 25 / risk > 70)
plus deeper bands (risk < 15 / risk > 85) and dollar-weighted mean risk:
remaining-book already only buys below the trial's own buy knee, so that
fraction is tautological unless the band is independent of the trial.
"""

from __future__ import annotations

import itertools
import json
import logging
import random
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.data.prices.history_cache import load_cached
from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights, build_extra_indicators
from digiquant.strategies.sdca.optimize import drop_extras_missing_sources, load_sdca_extra_sources
from digiquant.strategies.sdca.presets import load_preset
from digiquant.strategies.sdca.risk_index import build_risk_index

logger = logging.getLogger(__name__)

_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"
_PRESETS_PATH = Path(__file__).parent / "presets.json"
_SIDECAR_PATH = Path(__file__).parent / "btc_curve_optimize_provenance.json"

PUBLISHED_BUY_KNEE = 25.0
PUBLISHED_SELL_KNEE = 70.0
DEEP_CHEAP_RISK = 15.0
DEEP_RICH_RISK = 85.0

CURVE_SEARCH_BOUNDS: dict[str, tuple[float, float]] = {
    "buy_max_rate": (3.0, 40.0),
    "buy_knee_risk": (8.0, 25.0),
    "sell_knee_risk": (70.0, 92.0),
    "sell_max_rate": (3.0, 40.0),
    "buy_curvature": (1.0, 5.0),
    "sell_curvature": (1.0, 5.0),
}

# Coarse grid: widened vs the published 3% / 25 / 70 / curv 1+2 clip.
DEFAULT_COARSE_GRID: dict[str, tuple[float, ...]] = {
    "buy_max_rate": (8.0, 15.0, 25.0, 35.0),
    "buy_knee_risk": (10.0, 15.0, 20.0, 25.0),
    "sell_knee_risk": (70.0, 80.0, 88.0),
    "sell_max_rate": (8.0, 15.0, 25.0, 35.0),
    "buy_curvature": (1.0, 2.0, 3.5),
    "sell_curvature": (2.0, 3.5),
}

_SHAPE_KEYS = (
    "buy_max_rate",
    "buy_knee_risk",
    "sell_knee_risk",
    "sell_max_rate",
    "buy_curvature",
    "sell_curvature",
)


class CurveOptimizeGates(BaseModel):
    """Hard gates. Return is maximized only among trials that pass."""

    model_config = ConfigDict(frozen=True, strict=True)

    min_buy_frac_cheap: float = Field(0.99, ge=0.0, le=1.0)
    min_sell_frac_rich: float = Field(0.99, ge=0.0, le=1.0)
    require_2025_sells: bool = True
    require_sells: bool = True
    min_sell_max_rate: float = Field(1.0, gt=0.0)


class FillConcentration(BaseModel):
    """Dollar-weighted fill location vs the frozen 0–100 index."""

    model_config = ConfigDict(frozen=True, strict=True)

    buy_notional: float = Field(ge=0.0)
    sell_notional: float = Field(ge=0.0)
    buy_frac_cheap: float = Field(ge=0.0, le=1.0)
    sell_frac_rich: float = Field(ge=0.0, le=1.0)
    buy_frac_deep: float = Field(ge=0.0, le=1.0)
    sell_frac_deep: float = Field(ge=0.0, le=1.0)
    buy_mean_risk: float | None = None
    sell_mean_risk: float | None = None
    sell_notional_2025: float = Field(ge=0.0)
    sell_days_2025: int = Field(ge=0)
    min_cash: float
    min_units: float


class CurveTrialScore(BaseModel):
    """One curve on the frozen index. vs-flat is logged, not the objective."""

    model_config = ConfigDict(frozen=True, strict=True)

    shape: SdcaCurveShape
    total_return_pct: float
    vs_lump_pct: float
    vs_flat_dca_pct: float
    concentration: FillConcentration
    feasible: bool
    reject_reasons: tuple[str, ...] = ()


class CurveOptimizeResult(BaseModel):
    """Search outcome. ``beats_flat_dca_oos`` is always false here (in-sample)."""

    model_config = ConfigDict(frozen=True, strict=True)

    best: CurveTrialScore
    baseline: CurveTrialScore
    beats_baseline_return: bool
    beats_baseline_concentration: bool
    persist_ok: bool
    num_evaluations: int = Field(ge=0)
    num_feasible: int = Field(ge=0)
    frozen_weights: dict[str, float]
    evaluator: str = "curve_simulator"
    beats_flat_dca_oos: bool = False
    notes: str = ""


def published_indicator_weights(
    settings_path: Path | None = None,
) -> SdcaCompositeWeights:
    """Freeze composite members from ``settings.json`` (do not re-search extras)."""
    path = settings_path or _SETTINGS_PATH
    raw = json.loads(path.read_text())
    block = raw["strategies"]["btc_sdca"]["sdca"]["indicator_weights"]
    return SdcaCompositeWeights(
        valuation=float(block.get("valuation", 1.0)),
        m2=float(block.get("m2", 0.0)),
        rs_eth=float(block.get("rs_eth", 0.0)),
        dxy=float(block.get("dxy", 0.0)),
        weekly_rsi=float(block.get("weekly_rsi", 0.0)),
        weekly_macd=float(block.get("weekly_macd", 0.0)),
        sma_band=float(block.get("sma_band", 0.0)),
    )


def published_curve_shape() -> SdcaCurveShape:
    """Current ``btc_optimized`` shape (the public remaining-book curve)."""
    preset = load_preset("btc_optimized")
    if preset.shape is None:
        raise ValueError("btc_optimized preset has no shape")
    return preset.shape


def shape_from_bounds_ok(params: dict[str, float | int | str]) -> bool:
    """True when params form a valid shape inside ``CURVE_SEARCH_BOUNDS``."""
    try:
        shape = SdcaCurveShape(
            buy_max_rate=float(params["buy_max_rate"]),
            buy_knee_risk=float(params["buy_knee_risk"]),
            sell_knee_risk=float(params["sell_knee_risk"]),
            sell_max_rate=float(params["sell_max_rate"]),
            buy_curvature=float(params["buy_curvature"]),
            sell_curvature=float(params["sell_curvature"]),
        )
    except (KeyError, TypeError, ValueError):
        return False
    for key, (lo, hi) in CURVE_SEARCH_BOUNDS.items():
        value = float(getattr(shape, key))
        if value < lo - 1e-9 or value > hi + 1e-9:
            return False
    return shape.sell_max_rate > 0.0


def params_from_shape(shape: SdcaCurveShape) -> dict[str, float]:
    return {key: float(getattr(shape, key)) for key in _SHAPE_KEYS}


def sample_curve_trials(
    *,
    n_random: int = 0,
    seed: int = 42,
    include_grid: bool = True,
    include_published: bool = True,
) -> list[dict[str, float]]:
    """Rerunnable trial list: published shape + coarse grid + seeded random."""
    seen: set[tuple[float, ...]] = set()
    out: list[dict[str, float]] = []

    def _add(params: dict[str, float]) -> None:
        if not shape_from_bounds_ok(params):
            return
        key = tuple(round(params[k], 6) for k in _SHAPE_KEYS)
        if key in seen:
            return
        seen.add(key)
        out.append(params)

    if include_published:
        _add(params_from_shape(published_curve_shape()))
    if include_grid:
        names = list(DEFAULT_COARSE_GRID)
        for combo in itertools.product(*(DEFAULT_COARSE_GRID[n] for n in names)):
            _add(dict(zip(names, combo, strict=True)))
    rng = random.Random(seed)
    for _ in range(max(0, n_random)):
        drawn: dict[str, float] = {}
        for name, (lo, hi) in CURVE_SEARCH_BOUNDS.items():
            drawn[name] = round(rng.uniform(lo, hi), 4)
        _add(drawn)
    return out


def fill_concentration(frame: pl.DataFrame) -> FillConcentration:
    """Dollar-weighted fill location. Buys > 0, sells < 0 in ``daily_trade_usd``."""
    required = {"date", "risk", "daily_trade_usd", "cash", "asset_units"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"fill_concentration missing columns: {sorted(missing)}")
    buy_usd = 0.0
    sell_usd = 0.0
    buy_cheap = 0.0
    sell_rich = 0.0
    buy_deep = 0.0
    sell_deep = 0.0
    buy_risk_sum = 0.0
    sell_risk_sum = 0.0
    sell_2025 = 0.0
    sell_days_2025 = 0
    for row in frame.iter_rows(named=True):
        traded = float(row["daily_trade_usd"])
        risk_raw = row["risk"]
        day = row["date"]
        if traded > 0.0 and risk_raw is not None:
            risk = float(risk_raw)
            buy_usd += traded
            buy_risk_sum += traded * risk
            if risk < PUBLISHED_BUY_KNEE:
                buy_cheap += traded
            if risk < DEEP_CHEAP_RISK:
                buy_deep += traded
        elif traded < 0.0 and risk_raw is not None:
            risk = float(risk_raw)
            notional = -traded
            sell_usd += notional
            sell_risk_sum += notional * risk
            if risk > PUBLISHED_SELL_KNEE:
                sell_rich += notional
            if risk > DEEP_RICH_RISK:
                sell_deep += notional
            year = day.year if isinstance(day, date) else int(str(day)[:4])
            if year == 2025:
                sell_2025 += notional
                sell_days_2025 += 1
    cash_vals = frame["cash"].to_list()
    unit_vals = frame["asset_units"].to_list()
    return FillConcentration(
        buy_notional=buy_usd,
        sell_notional=sell_usd,
        buy_frac_cheap=(buy_cheap / buy_usd) if buy_usd > 0.0 else 0.0,
        sell_frac_rich=(sell_rich / sell_usd) if sell_usd > 0.0 else 0.0,
        buy_frac_deep=(buy_deep / buy_usd) if buy_usd > 0.0 else 0.0,
        sell_frac_deep=(sell_deep / sell_usd) if sell_usd > 0.0 else 0.0,
        buy_mean_risk=(buy_risk_sum / buy_usd) if buy_usd > 0.0 else None,
        sell_mean_risk=(sell_risk_sum / sell_usd) if sell_usd > 0.0 else None,
        sell_notional_2025=sell_2025,
        sell_days_2025=sell_days_2025,
        min_cash=min(float(v) for v in cash_vals) if cash_vals else 0.0,
        min_units=min(float(v) for v in unit_vals) if unit_vals else 0.0,
    )


def _reject_reasons(
    shape: SdcaCurveShape,
    conc: FillConcentration,
    gates: CurveOptimizeGates,
) -> list[str]:
    reasons: list[str] = []
    if shape.sell_max_rate < gates.min_sell_max_rate:
        reasons.append("long_only")
    if gates.require_sells and conc.sell_notional <= 0.0:
        reasons.append("no_sells")
    if gates.require_2025_sells and conc.sell_days_2025 < 1:
        reasons.append("no_2025_sells")
    if conc.min_cash < -1e-9:
        reasons.append("negative_cash")
    if conc.min_units < -1e-9:
        reasons.append("negative_units")
    if conc.buy_notional > 0.0 and conc.buy_frac_cheap < gates.min_buy_frac_cheap:
        reasons.append("buys_outside_cheap_zone")
    if conc.sell_notional > 0.0 and conc.sell_frac_rich < gates.min_sell_frac_rich:
        reasons.append("sells_outside_rich_zone")
    return reasons


def score_shape_on_index(
    dates: pl.Series,
    prices: pl.Series,
    risk: pl.Series,
    shape: SdcaCurveShape,
    initial_cash: float,
    *,
    gates: CurveOptimizeGates | None = None,
) -> CurveTrialScore:
    """Linux-safe ``run_backtest`` evaluator (no NautilusTrader)."""
    g = gates or CurveOptimizeGates()
    report, frame = run_backtest(
        dates, prices, risk, AccumDistCurve(shape.to_nodes()), initial_cash
    )
    conc = fill_concentration(frame)
    reasons = _reject_reasons(shape, conc, g)
    return CurveTrialScore(
        shape=shape,
        total_return_pct=report.total_return_pct,
        vs_lump_pct=report.vs_lump_pct,
        vs_flat_dca_pct=report.vs_flat_dca_pct,
        concentration=conc,
        feasible=not reasons,
        reject_reasons=tuple(reasons),
    )


def beats_baseline_concentration(candidate: FillConcentration, baseline: FillConcentration) -> bool:
    """True when buys sit cheaper and sells sit richer than the published curve."""
    if candidate.buy_mean_risk is None or baseline.buy_mean_risk is None:
        return False
    if candidate.sell_mean_risk is None or baseline.sell_mean_risk is None:
        return False
    if candidate.buy_mean_risk > baseline.buy_mean_risk + 1e-9:
        return False
    if candidate.sell_mean_risk < baseline.sell_mean_risk - 1e-9:
        return False
    if candidate.buy_frac_deep + 1e-12 < baseline.buy_frac_deep:
        return False
    if candidate.sell_frac_deep + 1e-12 < baseline.sell_frac_deep:
        return False
    return True


def search_curve(
    dates: pl.Series,
    prices: pl.Series,
    risk: pl.Series,
    trials: Sequence[dict[str, float | int | str]],
    *,
    initial_cash: float,
    baseline: SdcaCurveShape,
    frozen_weights: SdcaCompositeWeights,
    gates: CurveOptimizeGates | None = None,
    evaluator: str = "curve_simulator",
) -> CurveOptimizeResult:
    """Score ``trials`` on a precomputed frozen index; pick max feasible return."""
    g = gates or CurveOptimizeGates()
    baseline_score = score_shape_on_index(dates, prices, risk, baseline, initial_cash, gates=g)
    ranked: list[CurveTrialScore] = []
    for params in trials:
        try:
            shape = SdcaCurveShape(
                buy_max_rate=float(params["buy_max_rate"]),
                buy_knee_risk=float(params["buy_knee_risk"]),
                sell_knee_risk=float(params["sell_knee_risk"]),
                sell_max_rate=float(params["sell_max_rate"]),
                buy_curvature=float(params["buy_curvature"]),
                sell_curvature=float(params["sell_curvature"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        ranked.append(score_shape_on_index(dates, prices, risk, shape, initial_cash, gates=g))
    if not ranked:
        raise ValueError("no valid curve trials to evaluate")
    feasible = [s for s in ranked if s.feasible]
    pool = feasible or ranked
    best = max(pool, key=lambda s: s.total_return_pct)
    beat_ret = best.total_return_pct > baseline_score.total_return_pct + 1e-9
    beat_conc = beats_baseline_concentration(best.concentration, baseline_score.concentration)
    persist_ok = bool(best.feasible and beat_ret and beat_conc)
    notes = (
        f"Frozen index weights {frozen_weights.model_dump()}. "
        f"Objective=total_return_pct evaluator={evaluator}. "
        f"vs-flat-DCA logged only (best={best.vs_flat_dca_pct:.4f}). "
        "beats_flat_dca_oos is not set from this in-sample search. "
        "Do not --push-supabase from this command."
    )
    return CurveOptimizeResult(
        best=best,
        baseline=baseline_score,
        beats_baseline_return=beat_ret,
        beats_baseline_concentration=beat_conc,
        persist_ok=persist_ok,
        num_evaluations=len(ranked),
        num_feasible=len(feasible),
        frozen_weights=frozen_weights.model_dump(),
        evaluator=evaluator,
        beats_flat_dca_oos=False,
        notes=notes,
    )


def persist_curve_winner(
    result: CurveOptimizeResult,
    *,
    presets_path: Path | None = None,
    sidecar_path: Path | None = None,
    persist: bool = False,
) -> bool:
    """Always write the sidecar. Update ``btc_optimized`` only when ``persist_ok``."""
    dest_side = sidecar_path or _SIDECAR_PATH
    dest_side.write_text(result.model_dump_json(indent=2) + "\n")
    if not persist or not result.persist_ok:
        logger.info(
            "curve search sidecar at %s persist_ok=%s (presets unchanged)",
            dest_side,
            result.persist_ok,
        )
        return False
    dest = presets_path or _PRESETS_PATH
    raw = json.loads(dest.read_text())
    shape = result.best.shape
    raw["btc_optimized"] = {
        "description": (
            "Remaining-book curve search on the frozen published composite "
            "(power law 1.0 + M2 0.5 + DXY 0.5). Objective is total return with "
            "fill-concentration gates (cheap buys, rich sells, 2025 distribute). "
            "beats_flat_dca_oos stays false — this search is in-sample on today's "
            "index, not a walk-forward OOS claim. Re-run: digiquant sdca-optimize-curve. "
            "Do not --push-supabase from the agent environment."
        ),
        "long_only": False,
        "shape": params_from_shape(shape),
    }
    dest.write_text(json.dumps(raw, indent=2) + "\n")
    logger.info("persisted btc_optimized curve into %s", dest)
    return True


def apply_calendar_delay(ohlcv: pl.DataFrame, signal_delay_days: int) -> pl.DataFrame:
    """Truncate so the run ends ``signal_delay_days`` before the freshest bar."""
    if signal_delay_days < 0:
        raise ValueError(f"signal_delay_days must be >= 0, got {signal_delay_days}")
    if signal_delay_days == 0 or ohlcv.is_empty():
        return ohlcv
    ts_col = "timestamp" if "timestamp" in ohlcv.columns else ohlcv.columns[0]
    cutoff = ohlcv[ts_col].max() - timedelta(days=signal_delay_days)
    return ohlcv.filter(pl.col(ts_col) <= cutoff)


def load_frozen_index(
    cache_dir: Path,
    *,
    signal_delay_days: int = 3,
    trade_start: str = "2018-01-01",
    ticker: str = "BTC-USD",
) -> tuple[pl.Series, pl.Series, pl.Series, SdcaCompositeWeights]:
    """Published composite risk on the delayed cache, sliced from ``trade_start``."""
    ohlcv = load_cached(ticker, cache_dir)
    if ohlcv is None or ohlcv.is_empty():
        raise FileNotFoundError(f"no cached {ticker} under {cache_dir}")
    ohlcv = apply_calendar_delay(ohlcv, signal_delay_days)
    ts_col = "timestamp" if "timestamp" in ohlcv.columns else ohlcv.columns[0]
    dates = ohlcv[ts_col]
    if dates.dtype != pl.Date:
        dates = dates.cast(pl.Date)
    published = published_indicator_weights()
    sources = load_sdca_extra_sources(cache_dir)
    weights = drop_extras_missing_sources(published, sources)
    extras = build_extra_indicators(dates, ohlcv["close"], weights, sources)
    index = build_risk_index(
        dates,
        ohlcv["close"],
        BtcPowerLawRiskModel(load_coefficients()),
        extra_indicators=extras or None,
        valuation_weight=weights.valuation,
    )
    cutoff = date.fromisoformat(trade_start)
    window = index.filter(pl.col("date") >= cutoff)
    if window.is_empty():
        raise ValueError(f"frozen index empty after trade_start={trade_start}")
    return window["date"], window["price"], window["risk"], weights


def run_published_curve_search(
    cache_dir: Path,
    *,
    signal_delay_days: int = 3,
    trade_start: str = "2018-01-01",
    initial_cash: float = 1000.0,
    n_random: int = 400,
    seed: int = 42,
    include_grid: bool = True,
) -> CurveOptimizeResult:
    """Operator entry: freeze index, search remaining-book curve, do not push."""
    dates, prices, risk, weights = load_frozen_index(
        cache_dir, signal_delay_days=signal_delay_days, trade_start=trade_start
    )
    trials = sample_curve_trials(n_random=n_random, seed=seed, include_grid=include_grid)
    logger.info(
        "sdca curve search: %d trials on frozen index %s→%s weights=%s",
        len(trials),
        dates[0],
        dates[-1],
        weights.model_dump(),
    )
    return search_curve(
        dates,
        prices,
        risk,
        trials,
        initial_cash=initial_cash,
        baseline=published_curve_shape(),
        frozen_weights=weights,
    )


__all__ = [
    "CURVE_SEARCH_BOUNDS",
    "DEEP_CHEAP_RISK",
    "DEEP_RICH_RISK",
    "DEFAULT_COARSE_GRID",
    "PUBLISHED_BUY_KNEE",
    "PUBLISHED_SELL_KNEE",
    "CurveOptimizeGates",
    "CurveOptimizeResult",
    "CurveTrialScore",
    "FillConcentration",
    "apply_calendar_delay",
    "beats_baseline_concentration",
    "fill_concentration",
    "load_frozen_index",
    "params_from_shape",
    "persist_curve_winner",
    "published_curve_shape",
    "published_indicator_weights",
    "run_published_curve_search",
    "sample_curve_trials",
    "score_shape_on_index",
    "search_curve",
    "shape_from_bounds_ok",
]
