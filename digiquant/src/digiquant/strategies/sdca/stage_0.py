"""Stage 0: solo-indicator remaining-book books, gated on walk-forward OOS.

Each catalog extra and power law (code id ``valuation``, user-facing
**power law**) gets its own risk index — unused members are omitted, not
passed as weight 0. A remaining-book curve search then asks whether that
series, on its own, accumulates when cheap and distributes when rich.

Keep/drop is mean OOS vs-flat-DCA versus the named ``power_law_solo``
baseline on the same folds. IS vs-flat is diagnostic. Never-sell (dump)
solos are dropped even when IS looks good. ``beats_flat_dca_oos`` stays
false here — Stage 0 is not a combined-book claim.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.composite_risk import IndicatorWeight
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import (
    EXTRA_INDICATOR_NAMES,
    SdcaCompositeWeights,
    extra_indicators_for_window,
    indicator_display_name,
    missing_extra_names,
)
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    SdcaWalkForwardResult,
    btc_power_law_rails_fitter,
    load_sdca_extra_z,
    load_sdca_ohlcv,
)
from digiquant.strategies.sdca.risk_index import build_risk_index
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.two_stage import (
    persist_two_stage,
    run_stage_b_frozen,
    stage_b_trials,
)
from digiquant.strategies.sdca.walk_forward import (
    FoldScore,
    RailsFitter,
    SdcaOptimizeObjective,
    SdcaTrialEvaluator,
    WalkForwardFold,
    is_feasible,
    shape_from_params,
    window_slice,
)
from digiquant.strategies.sdca.weight_search import (
    optimize_stage_1_survivor_weights,
    search_names_with_data,
)

POWER_LAW_CODE_ID = "valuation"
NAMED_BASELINE = "power_law_solo"
DEFAULT_EVALUATOR_LABEL = "curve_simulator"
_PROVENANCE_DIR = Path(__file__).resolve().parent
_PUBLISHED_PROVENANCE = _PROVENANCE_DIR / "btc_optimized_provenance.json"
_SETTINGS_PATH = Path(__file__).resolve().parents[1] / "settings.json"

DEFAULT_STAGE0_SHAPE_TRIALS: tuple[dict[str, float | int | str], ...] = (
    {
        **SDCA_SHAPE_DEFAULTS,
        "buy_max_rate": 3.0,
        "buy_knee_risk": 25.0,
        "sell_knee_risk": 70.0,
        "sell_max_rate": 3.0,
    },
    {
        **SDCA_SHAPE_DEFAULTS,
        "buy_max_rate": 5.0,
        "buy_knee_risk": 30.0,
        "sell_knee_risk": 75.0,
        "sell_max_rate": 5.0,
    },
)

_STAGE1_FROZEN_SHAPE = SdcaCurveShape(
    buy_max_rate=3.0,
    buy_knee_risk=25.0,
    sell_knee_risk=70.0,
    sell_max_rate=3.0,
    buy_curvature=1.0,
    sell_curvature=2.0,
)


class Stage0Cadence(BaseModel):
    """Buy/sell day counts from a remaining-book pass (fill-based cadence)."""

    model_config = ConfigDict(frozen=True, strict=True)

    buy_days: int = Field(ge=0)
    sell_days: int = Field(ge=0)
    capital_deployed_pct: float
    max_drawdown_pct: float


CadenceFn = Callable[..., Stage0Cadence]


class Stage0SoloResult(BaseModel):
    """One solo book: power law or a catalog extra."""

    model_config = ConfigDict(frozen=True, strict=True)

    code_id: str
    display_name: str
    evaluator: str
    mean_is_vs_flat_dca_pct: float
    mean_oos_vs_flat_dca_pct: float
    beats_named_baseline_oos: bool
    baseline_name: str
    baseline_oos_vs_flat_dca_pct: float
    feasible_oos: bool
    buy_days: int = Field(ge=0)
    sell_days: int = Field(ge=0)
    capital_deployed_pct: float
    max_drawdown_pct: float
    keep: bool
    drop_reason: str | None
    best_params: dict[str, float | int | str]
    num_evaluations: int = Field(ge=0)
    fold_scores: list[FoldScore]


class Stage0Report(BaseModel):
    """Per-indicator IS/OOS plus keep/drop. Not a combined-book OOS claim."""

    model_config = ConfigDict(frozen=True, strict=True)

    evaluator: str
    baseline_name: str = NAMED_BASELINE
    survivors: tuple[str, ...]
    solos: list[Stage0SoloResult]
    beats_flat_dca_oos: bool = False
    notes: str
    folds: list[WalkForwardFold] = Field(default_factory=list)


class SoloThenCombineResult(BaseModel):
    """Stage 0 → optional Stage 1 weights → Stage B. Persist is explicit."""

    model_config = ConfigDict(frozen=True, strict=True)

    stage0: Stage0Report
    stage1_weights: dict[str, float] | None
    stage_b_mean_oos_vs_flat_dca_pct: float | None
    beats_flat_dca_oos: bool
    persist_settings: bool
    notes: str


def solo_weights(code_id: str) -> SdcaCompositeWeights:
    """One-hot weights. Unused members are 0 (omitted from the blend)."""
    payload = {name: 0.0 for name in SdcaCompositeWeights.model_fields}
    if code_id == POWER_LAW_CODE_ID:
        payload["valuation"] = 1.0
    elif code_id in payload:
        payload[code_id] = 1.0
    else:
        raise ValueError(f"unknown SDCA indicator {code_id!r}")
    return SdcaCompositeWeights(**payload)


def cached_rails_fitter(fitter: RailsFitter) -> RailsFitter:
    """Memoize QuantReg rails per IS window so Stage 0 does not refit per trial."""
    cache: dict[tuple[date, date, int], RiskModel] = {}

    def wrapped(dates: Sequence[date], prices: Sequence[float]) -> RiskModel:
        key = (dates[0], dates[-1], len(dates))
        hit = cache.get(key)
        if hit is None:
            hit = fitter(dates, prices)
            cache[key] = hit
        return hit

    return wrapped


def cadence_from_curve_sim(
    dates: Sequence[date],
    prices: Sequence[float],
    risk_model: RiskModel,
    shape: SdcaCurveShape,
    valuation_weight: float,
    extra_indicators: Sequence[IndicatorWeight] | None = None,
    *,
    initial_cash: float = 100_000.0,
) -> Stage0Cadence:
    """Remaining-book cadence via ``run_backtest`` (evaluator=curve_simulator)."""
    date_s = pl.Series("date", list(dates), dtype=pl.Date)
    price_s = pl.Series("price", list(prices), dtype=pl.Float64)
    index = build_risk_index(
        date_s,
        price_s,
        risk_model,
        extra_indicators=list(extra_indicators) if extra_indicators is not None else None,
        valuation_weight=valuation_weight,
    )
    report, _frame = run_backtest(
        date_s,
        price_s,
        index["risk"],
        AccumDistCurve(shape.to_nodes()),
        initial_cash,
    )
    return Stage0Cadence(
        buy_days=report.buy_days,
        sell_days=report.sell_days,
        capital_deployed_pct=report.capital_deployed_pct,
        max_drawdown_pct=abs(report.dca_max_drawdown_pct) * 100.0,
    )


def _mean_is(scores: Sequence[FoldScore]) -> float:
    if not scores:
        return float("-inf")
    return sum(s.in_sample.vs_flat_dca_pct for s in scores) / len(scores)


def _mean_oos(scores: Sequence[FoldScore]) -> float:
    if not scores:
        return float("-inf")
    return sum(s.out_of_sample.vs_flat_dca_pct for s in scores) / len(scores)


def _drop_reason(
    *,
    code_id: str,
    mean_oos: float,
    baseline_oos: float,
    feasible_oos: bool,
    sell_days: int,
) -> str | None:
    if code_id == POWER_LAW_CODE_ID:
        return None
    if sell_days <= 0:
        return "never-sell (long-only dump); cadence diagnostic is not an OOS substitute"
    if not feasible_oos:
        return "no OOS fold passed Stage B capital floor / drawdown cap"
    if mean_oos <= baseline_oos:
        return f"OOS vs-flat {mean_oos:.4f} did not beat {NAMED_BASELINE} {baseline_oos:.4f}"
    return None


def _cadence_last_oos(
    dates: Sequence[date],
    prices: Sequence[float],
    extra_z: Mapping[str, Sequence[float | None]],
    weights: SdcaCompositeWeights,
    wf: SdcaWalkForwardResult,
    rails_fitter: RailsFitter,
) -> Stage0Cadence:
    last = wf.fold_scores[-1].fold
    is_dates, is_prices = window_slice(dates, prices, last.is_start, last.is_end)
    oos_dates, oos_prices = window_slice(dates, prices, last.oos_start, last.oos_end)
    model = rails_fitter(is_dates, is_prices)
    shape = shape_from_params(dict(wf.best_params))
    extras = extra_indicators_for_window(oos_dates, dates, extra_z, weights)
    return cadence_from_curve_sim(oos_dates, oos_prices, model, shape, weights.valuation, extras)


def run_stage_0(
    dates: Sequence[date],
    prices: Sequence[float],
    *,
    extra_z: Mapping[str, Sequence[float | None]],
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
    evaluator_label: str = DEFAULT_EVALUATOR_LABEL,
    search_names: Sequence[str] | None = None,
    shape_trials: Sequence[Mapping[str, float | int | str]] | None = None,
    objective: SdcaOptimizeObjective | None = None,
    cadence_fn: CadenceFn | None = None,
) -> Stage0Report:
    """Solo curve search per indicator. Gate extras on OOS vs power-law solo."""
    obj = objective or SdcaOptimizeObjective()
    trials = list(shape_trials) if shape_trials is not None else list(DEFAULT_STAGE0_SHAPE_TRIALS)
    extra_names = search_names_with_data(search_names or EXTRA_INDICATOR_NAMES, extra_z)
    catalog = (POWER_LAW_CODE_ID, *extra_names)
    date_list = list(dates)
    price_list = list(prices)
    fitter = cached_rails_fitter(rails_fitter)
    raw: list[tuple[str, SdcaWalkForwardResult, SdcaCompositeWeights, Stage0Cadence]] = []
    for code_id in catalog:
        weights = solo_weights(code_id)
        if missing_extra_names(weights, extra_z):
            continue
        wf = run_stage_b_frozen(
            date_list,
            price_list,
            stage_b_trials(weights, trials),
            rails_fitter=fitter,
            evaluator=evaluator,
            evaluator_label=evaluator_label,
            extra_z=extra_z,
        )
        if cadence_fn is not None:
            cadence = cadence_fn(code_id)
        else:
            cadence = _cadence_last_oos(date_list, price_list, extra_z, weights, wf, fitter)
        raw.append((code_id, wf, weights, cadence))
    if not raw or raw[0][0] != POWER_LAW_CODE_ID:
        raise ValueError("Stage 0 requires a power-law (valuation) solo as the named baseline")
    baseline_oos = _mean_oos(raw[0][1].fold_scores)
    solos: list[Stage0SoloResult] = []
    for code_id, wf, _weights, cadence in raw:
        mean_is = _mean_is(wf.fold_scores)
        mean_oos = _mean_oos(wf.fold_scores)
        feasible = any(is_feasible(s.out_of_sample, obj) for s in wf.fold_scores)
        reason = _drop_reason(
            code_id=code_id,
            mean_oos=mean_oos,
            baseline_oos=baseline_oos,
            feasible_oos=feasible,
            sell_days=cadence.sell_days,
        )
        keep = reason is None
        if code_id == POWER_LAW_CODE_ID:
            keep = True
            reason = None
        solos.append(
            Stage0SoloResult(
                code_id=code_id,
                display_name=indicator_display_name(code_id),
                evaluator=evaluator_label,
                mean_is_vs_flat_dca_pct=mean_is,
                mean_oos_vs_flat_dca_pct=mean_oos,
                beats_named_baseline_oos=mean_oos > baseline_oos,
                baseline_name=NAMED_BASELINE,
                baseline_oos_vs_flat_dca_pct=baseline_oos,
                feasible_oos=feasible,
                buy_days=cadence.buy_days,
                sell_days=cadence.sell_days,
                capital_deployed_pct=cadence.capital_deployed_pct,
                max_drawdown_pct=cadence.max_drawdown_pct,
                keep=keep,
                drop_reason=reason,
                best_params=dict(wf.best_params),
                num_evaluations=wf.num_evaluations,
                fold_scores=list(wf.fold_scores),
            )
        )
    survivors = tuple(row.code_id for row in solos if row.keep)
    extra_kept = [row.code_id for row in solos if row.keep and row.code_id != POWER_LAW_CODE_ID]
    notes = (
        f"Stage 0 solo books; evaluator={evaluator_label}; "
        f"gate={NAMED_BASELINE} OOS vs-flat plus Stage B capital/drawdown; "
        f"IS vs-flat is diagnostic. kept extras={extra_kept or '{}'}. "
        "beats_flat_dca_oos is not a combined-book claim. "
        "Do not --push-supabase."
    )
    return Stage0Report(
        evaluator=evaluator_label,
        baseline_name=NAMED_BASELINE,
        survivors=survivors,
        solos=solos,
        beats_flat_dca_oos=False,
        notes=notes,
        folds=list(raw[0][1].folds) if raw else [],
    )


def persist_stage_0(report: Stage0Report, path: Path | str) -> Path:
    """Write Stage 0 provenance JSON (evaluator, per-indicator IS/OOS, keep/drop)."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(report.model_dump_json(indent=2) + "\n")
    return dest


def published_oos_vs_flat(path: Path | str | None = None) -> float:
    """Mean OOS vs-flat from the checked-in ``btc_optimized`` sidecar."""
    payload = json.loads(Path(path or _PUBLISHED_PROVENANCE).read_text())
    return float(payload["mean_oos_vs_flat_dca_pct"])


def should_persist_settings(combined_oos: float, published_oos: float) -> bool:
    """Overwrite ``settings.json`` only when combined OOS is not worse."""
    return combined_oos >= published_oos


def _write_settings_weights(weights: SdcaCompositeWeights, *, path: Path) -> None:
    payload = json.loads(path.read_text())
    sdca = payload["strategies"]["btc_sdca"]["sdca"]
    sdca["indicator_weights"] = weights.model_dump()
    path.write_text(json.dumps(payload, indent=2) + "\n")


def run_solo_then_combine(
    dates: Sequence[date],
    prices: Sequence[float],
    *,
    extra_z: Mapping[str, Sequence[float | None]],
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
    evaluator_label: str = DEFAULT_EVALUATOR_LABEL,
    search_names: Sequence[str] | None = None,
    shape_trials: Sequence[Mapping[str, float | int | str]] | None = None,
    objective: SdcaOptimizeObjective | None = None,
    published_oos: float | None = None,
    persist_dir: Path | str | None = None,
    persist_settings_path: Path | str | None = None,
    cycle_windows: SdcaCycleWindows | None = None,
) -> SoloThenCombineResult:
    """Stage 0 gate, then Stage 1 weights among survivors, then Stage B."""
    trials = list(shape_trials) if shape_trials is not None else list(DEFAULT_STAGE0_SHAPE_TRIALS)
    stage0 = run_stage_0(
        dates,
        prices,
        extra_z=extra_z,
        rails_fitter=rails_fitter,
        evaluator=evaluator,
        evaluator_label=evaluator_label,
        search_names=search_names,
        shape_trials=trials,
        objective=objective,
    )
    dest = Path(persist_dir) if persist_dir is not None else None
    if dest is not None:
        persist_stage_0(stage0, dest / "btc_stage0.json")
    extra_survivors = [name for name in stage0.survivors if name != POWER_LAW_CODE_ID]
    incumbent_oos = published_oos if published_oos is not None else published_oos_vs_flat()
    if not extra_survivors:
        notes = (
            "no extra beat power_law_solo OOS; published power-law-only weights unchanged. "
            + stage0.notes
        )
        return SoloThenCombineResult(
            stage0=stage0,
            stage1_weights=None,
            stage_b_mean_oos_vs_flat_dca_pct=None,
            beats_flat_dca_oos=False,
            persist_settings=False,
            notes=notes,
        )
    stage1 = optimize_stage_1_survivor_weights(
        list(dates),
        list(prices),
        extra_z=extra_z,
        rails_fitter=cached_rails_fitter(rails_fitter),
        evaluator=evaluator,
        shape=_STAGE1_FROZEN_SHAPE,
        survivor_names=stage0.survivors,
        objective=objective,
    )
    stage_b = run_stage_b_frozen(
        list(dates),
        list(prices),
        stage_b_trials(stage1.weights, trials),
        rails_fitter=cached_rails_fitter(rails_fitter),
        evaluator=evaluator,
        evaluator_label=evaluator_label,
        extra_z=extra_z,
    )
    write_settings = should_persist_settings(stage_b.mean_oos_vs_flat_dca_pct, incumbent_oos)
    beats = bool(stage_b.beats_flat_dca_oos and stage_b.mean_oos_vs_flat_dca_pct > 0.0)
    notes = (
        f"Stage 1 survivors={list(stage0.survivors)}; "
        f"combined OOS vs-flat={stage_b.mean_oos_vs_flat_dca_pct:.4f} "
        f"(published {incumbent_oos:.4f}); persist_settings={write_settings}. "
        f"beats_flat_dca_oos={beats}. Do not --push-supabase."
    )
    if dest is not None:
        persist_two_stage(
            stage_a_weights=stage1.weights,
            stage_b=stage_b,
            windows=cycle_windows or SdcaCycleWindows.btc_v1(),
            dest_dir=dest,
            notes=notes,
        )
        (dest / "btc_stage1_weights.json").write_text(
            json.dumps(
                {
                    "weights": stage1.weights.model_dump(),
                    "search_names": list(stage1.search_names),
                    "mean_is_vs_flat_dca_pct": stage1.mean_is_vs_flat_dca_pct,
                    "mean_oos_vs_flat_dca_pct": stage1.mean_oos_vs_flat_dca_pct,
                    "num_evaluations": stage1.num_evaluations,
                    "evaluator": evaluator_label,
                    "notes": notes,
                },
                indent=2,
            )
            + "\n"
        )
        if write_settings:
            _write_settings_weights(
                stage1.weights,
                path=Path(persist_settings_path) if persist_settings_path else _SETTINGS_PATH,
            )
    return SoloThenCombineResult(
        stage0=stage0,
        stage1_weights=stage1.weights.model_dump(),
        stage_b_mean_oos_vs_flat_dca_pct=stage_b.mean_oos_vs_flat_dca_pct,
        beats_flat_dca_oos=beats,
        persist_settings=write_settings,
        notes=notes,
    )


def operator_stage_0(
    *,
    data_path: Path | str,
    out_dir: Path | str,
    evaluator_label: str = DEFAULT_EVALUATOR_LABEL,
    combine: bool = True,
) -> SoloThenCombineResult | Stage0Report:
    """Load BTC cache + FRED/ETH siblings; run Stage 0 (and Stage 1 if survivors)."""
    if evaluator_label != DEFAULT_EVALUATOR_LABEL:
        raise ValueError(
            f"operator Stage 0 default is {DEFAULT_EVALUATOR_LABEL}, got {evaluator_label}"
        )
    path = Path(data_path)
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=path, data_dir=None)
    extra_z = load_sdca_extra_z(dates, prices, data_path=path, data_dir=path.parent)
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    fitter = cached_rails_fitter(btc_power_law_rails_fitter)
    if combine:
        return run_solo_then_combine(
            dates,
            prices,
            extra_z=extra_z,
            rails_fitter=fitter,
            evaluator=evaluate_sdca_trial_curve_sim,
            evaluator_label=DEFAULT_EVALUATOR_LABEL,
            persist_dir=dest,
        )
    report = run_stage_0(
        dates,
        prices,
        extra_z=extra_z,
        rails_fitter=fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        evaluator_label=DEFAULT_EVALUATOR_LABEL,
    )
    persist_stage_0(report, dest / "btc_stage0.json")
    return report


def _cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "SDCA Stage 0 solo-indicator curve search (curve_simulator). "
            "Gate extras on OOS vs power-law solo. Digi names lowercase."
        )
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        default=Path("data/price-history/BTC-USD.csv"),
        help="BTC OHLCV CSV; FRED/ETH siblings load from the same directory",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("digiquant/src/digiquant/strategies/sdca"),
        help="Provenance sidecar directory",
    )
    parser.add_argument(
        "--stage0-only",
        action="store_true",
        help="Skip Stage 1 / Stage B even if extras survive",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = operator_stage_0(
        data_path=args.data_path,
        out_dir=args.out_dir,
        combine=not args.stage0_only,
    )
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())


__all__ = [
    "DEFAULT_EVALUATOR_LABEL",
    "DEFAULT_STAGE0_SHAPE_TRIALS",
    "NAMED_BASELINE",
    "POWER_LAW_CODE_ID",
    "SoloThenCombineResult",
    "Stage0Cadence",
    "Stage0Report",
    "Stage0SoloResult",
    "cached_rails_fitter",
    "cadence_from_curve_sim",
    "operator_stage_0",
    "persist_stage_0",
    "published_oos_vs_flat",
    "run_solo_then_combine",
    "run_stage_0",
    "should_persist_settings",
    "solo_weights",
]
