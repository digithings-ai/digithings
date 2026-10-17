"""Golden-path driver: research -> backtest -> optimize -> tearsheet.

Every stage of the strategy pipeline already existed as its own function, and
nothing sequenced them. This module is the sequencing, not a second
implementation: each stage calls the lab function that owns the work and hands
its output to the next one.

The four stages, and what each actually does here:

``research``
    Resolve market data (from disk through :func:`load_sdca_ohlcv`, or from an
    in-memory series the caller already holds), resolve the risk model, build
    the composite risk index, and compute the technical series. The head of the
    series is trimmed to the first row whose risk is non-null, because every
    downstream stage requires a finite risk and the composite is undefined
    through indicator warmup.

``backtest``
    :func:`run_backtest` over the risk index and an accumulation/distribution
    curve resolved from a :class:`SdcaPreset`.

``optimize``
    :func:`run_sdca_walk_forward` over caller-supplied shape trials with the two
    collaborators it requires, a ``rails_fitter`` and a trial ``evaluator``.
    Both stay caller-supplied on purpose: the rail fit must not be reused across
    the full history inside the optimizer (#3173 truncated quadratic log-time
    fits do not extrapolate), and a driver that invented either one would be
    choosing a research method, not sequencing an existing one.

``tearsheet``
    :func:`tearsheet_overlays` over the backtest frame, producing the diagnostic
    series the published ``TearsheetData`` schema renders.

Three rules are encoded rather than documented elsewhere, because each one has
already cost a wrong number:

1. **The backtest stage is not authoritative.** :class:`SdcaBacktestReport` says
   of itself that it is "never the authoritative backtest result" and that
   PnL/Sharpe/drawdown surfaced to users must come from a completed Nautilus
   ``BacktestResult``/``OptimizeResult``. This driver therefore marks every
   backtest stage ``authoritative=False`` and writes that caveat into the
   manifest beside the numbers, so an artifact cannot be read as a published
   backtest later.
2. **Feasibility gates on ``capital_deployed_peak_pct``.**
   ``capital_deployed_pct`` is an endpoint snapshot that goes negative after
   take-profit sells; it must never be read as participation or feasibility.
3. **Artifacts are local only.** ``AGENTS.md`` forbids publishing
   ``btc_optimized`` / composite variants to digiquant.io from this WP, so
   nothing here writes to Supabase or to the site. ``persist_golden_path``
   writes files under a directory the caller names.

Nothing in this module is asset-specific: the risk model, the curve and the
trials all arrive as arguments, which is what makes the same path usable for any
asset or idea.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from digiquant.strategies.lab.asset_profile import technicals_from_ohlcv
from digiquant.strategies.lab.backtest import SdcaBacktestReport, run_backtest
from digiquant.strategies.lab.composite_risk import IndicatorWeight
from digiquant.strategies.lab.curve import AccumDistCurve
from digiquant.strategies.lab.curve_sim import DEFAULT_TRIAL_CASH, evaluate_sdca_trial_curve_sim
from digiquant.strategies.lab.dca_metrics import tearsheet_overlays
from digiquant.strategies.lab.optimize import (
    SdcaWalkForwardResult,
    btc_power_law_rails_fitter,
    load_sdca_ohlcv,
    run_sdca_walk_forward,
)
from digiquant.strategies.lab.presets import SdcaPreset, load_preset
from digiquant.strategies.lab.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.lab.providers import (
    KNOWN_SDCA_RISK_MODELS,
    resolve_sdca_risk_model,
)
from digiquant.strategies.lab.risk_index import build_risk_index
from digiquant.strategies.lab.risk_model import RiskModel
from digiquant.strategies.lab.walk_forward import RailsFitter, SdcaTrialEvaluator

STAGES: tuple[str, ...] = ("research", "backtest", "optimize", "tearsheet")

BACKTEST_CAVEAT = (
    "The backtest stage is the curve simulator, not a Nautilus BacktestResult. "
    "SdcaBacktestReport describes itself as 'never the authoritative backtest "
    "result'; PnL, Sharpe and drawdown surfaced to users must come from a "
    "completed Nautilus run. Treat these figures as a trial simulation."
)

FEASIBILITY_RULE = (
    "Feasibility gates on capital_deployed_peak_pct. capital_deployed_pct is an "
    "endpoint snapshot that goes negative after take-profit sells and must never "
    "be used as a participation or feasibility measure."
)

PUBLISH_RULE = (
    "Artifacts are written locally only. Nothing here pushes to Supabase or to "
    "digiquant.io: AGENTS.md forbids publishing btc_optimized / composite "
    "variants from this WP."
)


# --------------------------------------------------------------------------- #
# Stage results
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ResearchStage:
    """Market data plus the composite risk index built from it.

    ``dates`` and ``prices`` are the *trimmed* series: the head that predates a
    usable risk value has already been dropped, so every row here has a finite
    risk and the two series stay aligned with ``risk_index``.
    """

    dates: pl.Series
    prices: pl.Series
    risk_index: pl.DataFrame
    indicators: dict[str, list[float | None]]
    risk_model: RiskModel
    dropped_warmup_rows: int = 0

    @property
    def row_count(self) -> int:
        return len(self.dates)

    @property
    def start(self) -> date:
        return self.dates.to_list()[0]

    @property
    def end(self) -> date:
        return self.dates.to_list()[-1]

    def risk_values(self) -> pl.Series:
        """The ``risk`` column, asserted finite — the input every stage needs."""
        column = self.risk_index["risk"]
        nulls = column.null_count()
        if nulls:
            raise ValueError(
                f"risk index has {nulls} null row(s) after warmup trim; "
                "drop the extras that are missing sources "
                "(see optimize.drop_extras_missing_sources) before running the path"
            )
        return column.cast(pl.Float64)


@dataclass(frozen=True)
class BacktestStage:
    """A curve-simulation backtest. Never the authoritative result — see module docstring."""

    report: SdcaBacktestReport
    frame: pl.DataFrame
    initial_cash: float
    authoritative: bool = False
    caveat: str = BACKTEST_CAVEAT


@dataclass(frozen=True)
class GoldenPathVerdict:
    """Whether the path cleared its gate, and on what evidence.

    ``cleared`` requires both halves of the published bar: the walk-forward must
    beat flat DCA out of sample *and* the sensitivity neighbourhood must be
    stable. When the optimize stage did not run neither can be evaluated, so
    ``cleared`` is False and ``reason`` says so rather than implying a pass.
    """

    cleared: bool
    beats_flat_dca_oos: bool | None = None
    sensitivity_stable: bool | None = None
    mean_oos_vs_flat_dca_pct: float | None = None
    max_abs_delta_oos_pct: float | None = None
    reason: str = "not evaluated"

    def describe(self) -> str:
        return (
            f"cleared={self.cleared} beats_flat_dca_oos={self.beats_flat_dca_oos} "
            f"sensitivity_stable={self.sensitivity_stable} "
            f"mean_oos_vs_flat_dca_pct={self.mean_oos_vs_flat_dca_pct} "
            f"max_abs_delta_oos_pct={self.max_abs_delta_oos_pct} :: {self.reason}"
        )


@dataclass(frozen=True)
class GoldenPathResult:
    """Everything one run produced, plus the verdict it earned."""

    research: ResearchStage
    backtest: BacktestStage
    optimize: SdcaWalkForwardResult | None
    tearsheet: dict[str, object] | None
    verdict: GoldenPathVerdict
    stages: tuple[str, ...] = STAGES
    preset_name: str | None = None


# --------------------------------------------------------------------------- #
# Coercion and validation
# --------------------------------------------------------------------------- #


def _as_date_series(values: Any) -> pl.Series:
    if isinstance(values, pl.Series):
        return values if values.dtype == pl.Date else values.cast(pl.Date)
    return pl.Series(list(values), dtype=pl.Date)


def _as_float_series(values: Any) -> pl.Series:
    if isinstance(values, pl.Series):
        return values if values.dtype == pl.Float64 else values.cast(pl.Float64)
    return pl.Series([float(v) for v in values], dtype=pl.Float64)


def _validate_market_data(dates: pl.Series, prices: pl.Series) -> None:
    """Fail loudly on the shapes every downstream stage assumes."""
    if len(dates) != len(prices):
        raise ValueError(f"dates and prices differ in length: {len(dates)} vs {len(prices)}")
    if len(dates) < 2:
        raise ValueError(f"a backtest needs at least 2 rows, got {len(dates)}")
    if dates.null_count():
        raise ValueError(f"dates contain {dates.null_count()} null row(s)")
    if prices.null_count():
        raise ValueError(f"prices contain {prices.null_count()} null row(s)")
    date_list = dates.to_list()
    if any(b <= a for a, b in zip(date_list, date_list[1:])):
        raise ValueError("dates must be strictly increasing with no duplicates")
    price_list = prices.to_list()
    if any(p <= 0.0 for p in price_list):
        raise ValueError("prices must be strictly positive")


def _trim_to_first_usable_risk(
    dates: pl.Series, prices: pl.Series, risk_index: pl.DataFrame
) -> tuple[pl.Series, pl.Series, pl.DataFrame, int]:
    """Drop the warmup head, where the composite risk is undefined.

    Every stage downstream requires a finite risk, and the composite is null
    until its slowest input has warmed up. Trimming here keeps one boundary
    instead of scattering null handling through the path.
    """
    risk = risk_index["risk"].to_list()
    first = next((i for i, value in enumerate(risk) if value is not None), None)
    if first is None:
        raise ValueError(
            "risk index has no usable row: every risk value is null, so the "
            "inputs never warmed up over this date range"
        )
    if first == 0:
        return dates, prices, risk_index, 0
    trimmed = risk_index.slice(first)
    if len(trimmed) < 2:
        raise ValueError(
            f"only {len(trimmed)} row(s) survive the warmup trim (dropped {first}); "
            "the date range is too short for this risk model"
        )
    return dates.slice(first), prices.slice(first), trimmed, first


def _resolve_curve(
    *, curve: AccumDistCurve | Sequence[float] | None, preset: str | SdcaPreset | None
) -> tuple[AccumDistCurve, str | None]:
    """A curve comes from a preset (by name or object) or is passed directly."""
    if curve is not None and preset is not None:
        raise ValueError("pass curve or preset, not both")
    if curve is not None:
        resolved = curve if isinstance(curve, AccumDistCurve) else AccumDistCurve(tuple(curve))
        return resolved, None
    if preset is None:
        raise ValueError(
            "a curve is required: pass preset (a name from list_presets() or an "
            "SdcaPreset) or an explicit curve"
        )
    if isinstance(preset, str):
        resolved_preset = load_preset(preset)
        name = preset
    else:
        resolved_preset = preset
        name = None
    return AccumDistCurve(resolved_preset.curve_nodes), name


# --------------------------------------------------------------------------- #
# Stage 1 — research
# --------------------------------------------------------------------------- #


def research_asset(
    *,
    dates: Sequence[date] | pl.Series | None = None,
    prices: Sequence[float] | pl.Series | None = None,
    symbols: Sequence[str] | None = None,
    data_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    risk_model: RiskModel | None = None,
    risk_model_name: str | None = None,
    valuation_weight: float = 1.0,
    extra_indicators: Sequence[IndicatorWeight] | None = None,
    oscillators: SdcaOscillatorSpec | None = None,
    include_indicators: bool = True,
    coefficients_path: Path | None = None,
) -> ResearchStage:
    """Stage 1: market data in, a validated risk index out.

    Market data arrives one of two ways and never both: an in-memory
    ``dates``/``prices`` pair (for a caller holding its own series, e.g. from
    :func:`daily_closes_from_cache`), or ``symbols`` plus ``data_path`` /
    ``data_dir``, which is read through :func:`load_sdca_ohlcv`.

    The risk model is either an object satisfying :class:`RiskModel` or one of
    :data:`KNOWN_SDCA_RISK_MODELS`, resolved through
    :func:`resolve_sdca_risk_model` against the same series.
    """
    explicit = dates is not None or prices is not None
    loaded = symbols is not None or data_path is not None or data_dir is not None
    if explicit and loaded:
        raise ValueError("pass either dates/prices or symbols with data_path/data_dir, not both")
    if explicit:
        if dates is None or prices is None:
            raise ValueError("dates and prices must be supplied together")
        date_series = _as_date_series(dates)
        price_series = _as_float_series(prices)
    elif loaded:
        if symbols is None:
            raise ValueError("symbols is required when reading market data from disk")
        loaded_dates, loaded_prices = load_sdca_ohlcv(
            symbols=list(symbols), data_path=data_path, data_dir=data_dir
        )
        date_series = pl.Series(loaded_dates, dtype=pl.Date)
        price_series = pl.Series(loaded_prices, dtype=pl.Float64)
    else:
        raise ValueError("no market data: pass dates/prices, or symbols with data_path/data_dir")
    _validate_market_data(date_series, price_series)

    if risk_model is not None and risk_model_name is not None:
        raise ValueError("pass risk_model or risk_model_name, not both")
    if risk_model is None:
        if risk_model_name is None:
            raise ValueError(
                "a risk model is required: pass risk_model, or risk_model_name "
                f"from {sorted(KNOWN_SDCA_RISK_MODELS)}"
            )
        risk_model = resolve_sdca_risk_model(
            risk_model_name,
            dates=date_series,
            price=price_series,
            coefficients_path=coefficients_path,
        )

    risk_index = build_risk_index(
        date_series,
        price_series,
        risk_model,
        extra_indicators=list(extra_indicators) if extra_indicators is not None else None,
        valuation_weight=valuation_weight,
    )
    date_series, price_series, risk_index, dropped = _trim_to_first_usable_risk(
        date_series, price_series, risk_index
    )
    indicators = (
        technicals_from_ohlcv(date_series, price_series, oscillators) if include_indicators else {}
    )
    stage = ResearchStage(
        dates=date_series,
        prices=price_series,
        risk_index=risk_index,
        indicators=indicators,
        risk_model=risk_model,
        dropped_warmup_rows=dropped,
    )
    stage.risk_values()  # fail here, not three stages later
    return stage


# --------------------------------------------------------------------------- #
# Stage 2 — backtest
# --------------------------------------------------------------------------- #


def backtest_asset(
    research: ResearchStage,
    *,
    curve: AccumDistCurve | Sequence[float] | None = None,
    preset: str | SdcaPreset | None = None,
    initial_cash: float = DEFAULT_TRIAL_CASH,
    sell_dates: set[date] | None = None,
) -> BacktestStage:
    """Stage 2: run the accumulation/distribution curve over the risk index."""
    resolved_curve, _ = _resolve_curve(curve=curve, preset=preset)
    if initial_cash <= 0.0:
        raise ValueError(f"initial_cash must be positive, got {initial_cash}")
    report, frame = run_backtest(
        research.dates,
        research.prices,
        research.risk_values(),
        resolved_curve,
        initial_cash,
        sell_dates=sell_dates,
    )
    return BacktestStage(report=report, frame=frame, initial_cash=initial_cash)


# --------------------------------------------------------------------------- #
# Stage 3 — optimize
# --------------------------------------------------------------------------- #


def optimize_asset(
    research: ResearchStage,
    *,
    trials: Sequence[Mapping[str, float | int | str]],
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator | None = None,
    evaluator_label: str | None = None,
    objective: Any | None = None,
    n_folds: int = 3,
    holdout_frac: float = 0.2,
    oos_frac: float = 0.25,
    sensitivity_frac: float = 0.05,
    extra_z: Mapping[str, Sequence[float | None]] | None = None,
    fold_weighting: str = "unweighted",
) -> SdcaWalkForwardResult:
    """Stage 3: walk-forward search over shape trials on the same series.

    ``rails_fitter`` and ``evaluator`` are caller-supplied collaborators, as
    :func:`run_sdca_walk_forward` requires. The default evaluator is
    :func:`evaluate_sdca_trial_curve_sim`, whose recorded label in the rest of
    the engine is ``"curve_simulator"``; a custom evaluator contributes its own
    name so provenance cannot claim a simulator that did not run.
    """
    trial_list = [dict(trial) for trial in trials]
    if not trial_list:
        raise ValueError("trials must contain at least one shape-parameter mapping")
    resolved_evaluator = evaluator if evaluator is not None else evaluate_sdca_trial_curve_sim
    if evaluator_label is not None:
        label = evaluator_label
    elif resolved_evaluator is evaluate_sdca_trial_curve_sim:
        label = "curve_simulator"
    else:
        label = getattr(resolved_evaluator, "__name__", "custom_evaluator")
    return run_sdca_walk_forward(
        research.dates.to_list(),
        [float(price) for price in research.prices.to_list()],
        trial_list,
        rails_fitter=rails_fitter,
        evaluator=resolved_evaluator,
        evaluator_label=label,
        objective=objective,
        n_folds=n_folds,
        holdout_frac=holdout_frac,
        oos_frac=oos_frac,
        sensitivity_frac=sensitivity_frac,
        extra_z=dict(extra_z) if extra_z is not None else None,
        fold_weighting=fold_weighting,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- #
# Named rails fitters
# --------------------------------------------------------------------------- #


def rails_fitter_for(name: str) -> RailsFitter:
    """Map a known SDCA risk-model name to a walk-forward ``RailsFitter``.

    :func:`run_sdca_walk_forward` hands its fitter the in-sample window of each
    fold, and nothing wider on purpose: ``walk_forward`` records that a
    full-history rail fit must not be reused inside the optimizer because
    truncated quadratic log-time fits do not extrapolate (#3173). So the
    mapping has to respect what each named model actually does when called.

    ``btc_power_law`` maps to :func:`btc_power_law_rails_fitter`, **not** to
    :func:`resolve_sdca_risk_model`. The resolver constructs
    ``BtcPowerLawRiskModel`` from *stored coefficients*, which is a full-history
    fit by definition; on a window shorter than the 730-observation floor it
    succeeds while the real fitter refuses, so wiring the resolver here would
    inject exactly the leak the fold protocol exists to prevent.

    ``generic_valuation`` and ``rolling_z`` are fitted from the series they are
    handed, so they can go through the resolver as long as coefficients are not
    loaded — hence ``coefficients_path=None``.

    Raises ``ValueError`` for an unknown name, naming the models it accepts.
    """
    if name == "btc_power_law":
        return btc_power_law_rails_fitter

    if name not in ("generic_valuation", "rolling_z"):
        raise ValueError(
            f"unknown SDCA risk model {name!r} for a walk-forward rails fitter; "
            f"expected one of {sorted(KNOWN_SDCA_RISK_MODELS)}"
        )

    def _fitter(dates: Sequence[date], prices: Sequence[float]) -> RiskModel:
        return resolve_sdca_risk_model(
            name,
            dates=pl.Series("date", list(dates), dtype=pl.Date),
            price=pl.Series("close", [float(price) for price in prices]),
            coefficients_path=None,
        )

    # Name the closure after the model it wraps, so a provenance record reading
    # the fitter's ``__name__`` says which model produced the rails.
    _fitter.__name__ = f"{name}_rails_fitter"
    return _fitter


# --------------------------------------------------------------------------- #
# Stage 4 — tearsheet
# --------------------------------------------------------------------------- #


def tearsheet_payload(
    research: ResearchStage,
    backtest: BacktestStage,
    *,
    preset_name: str | None = None,
    weights: object | None = None,
    indicator_z: Mapping[str, Sequence[float | None]] | None = None,
) -> dict[str, object]:
    """Stage 4: the diagnostic series the published tearsheet schema renders.

    ``research.indicators`` is deliberately *not* forwarded as ``indicator_z``.
    The technical series are raw indicator values and ``indicator_z`` expects
    z-scores; passing one as the other would mislabel a chart axis. A caller
    that wants indicator curves computes the z form and passes it explicitly.
    """
    frame = backtest.frame
    rails_frame = research.risk_model.rails(research.dates)
    rails = list(
        zip(
            rails_frame["low"].to_list(),
            rails_frame["median"].to_list(),
            rails_frame["high"].to_list(),
            strict=True,
        )
    )
    risk = research.risk_values().to_list()
    return tearsheet_overlays(
        dates=[day.isoformat() for day in research.dates.to_list()],
        prices=[float(price) for price in research.prices.to_list()],
        daily_trade_usd=frame["daily_trade_usd"].to_list(),
        net_deployed=frame["net_deployed"].to_list(),
        initial_cash=backtest.initial_cash,
        rails=rails,
        risk=risk,
        asset_units=frame["asset_units"].to_list(),
        indicator_z=dict(indicator_z) if indicator_z is not None else None,
        weights=weights,
        preset_name=preset_name,
    )


# --------------------------------------------------------------------------- #
# The driver
# --------------------------------------------------------------------------- #


def _verdict(optimize: SdcaWalkForwardResult | None) -> GoldenPathVerdict:
    if optimize is None:
        return GoldenPathVerdict(
            cleared=False,
            reason=(
                "the optimize stage did not run, so neither half of the gate "
                "(positive OOS versus flat DCA, and a stable sensitivity "
                "neighbourhood) was evaluated"
            ),
        )
    beats = bool(optimize.beats_flat_dca_oos)
    stable = bool(optimize.sensitivity.stable)
    if beats and stable:
        reason = "beats flat DCA out of sample and the sensitivity neighbourhood is stable"
    elif beats and not stable:
        reason = "beats flat DCA out of sample but the sensitivity neighbourhood is unstable"
    elif stable:
        reason = "sensitivity is stable but it does not beat flat DCA out of sample"
    else:
        reason = "neither half of the gate is met"
    return GoldenPathVerdict(
        cleared=beats and stable,
        beats_flat_dca_oos=beats,
        sensitivity_stable=stable,
        mean_oos_vs_flat_dca_pct=float(optimize.mean_oos_vs_flat_dca_pct),
        max_abs_delta_oos_pct=float(optimize.sensitivity.max_abs_delta_oos_pct),
        reason=reason,
    )


def run_golden_path(
    *,
    dates: Sequence[date] | pl.Series | None = None,
    prices: Sequence[float] | pl.Series | None = None,
    symbols: Sequence[str] | None = None,
    data_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    risk_model: RiskModel | None = None,
    risk_model_name: str | None = None,
    valuation_weight: float = 1.0,
    extra_indicators: Sequence[IndicatorWeight] | None = None,
    oscillators: SdcaOscillatorSpec | None = None,
    include_indicators: bool = True,
    coefficients_path: Path | None = None,
    preset: str | SdcaPreset | None = None,
    curve: AccumDistCurve | Sequence[float] | None = None,
    initial_cash: float = DEFAULT_TRIAL_CASH,
    sell_dates: set[date] | None = None,
    trials: Sequence[Mapping[str, float | int | str]] | None = None,
    rails_fitter: RailsFitter | None = None,
    evaluator: SdcaTrialEvaluator | None = None,
    evaluator_label: str | None = None,
    objective: Any | None = None,
    n_folds: int = 3,
    holdout_frac: float = 0.2,
    oos_frac: float = 0.25,
    sensitivity_frac: float = 0.05,
    extra_z: Mapping[str, Sequence[float | None]] | None = None,
    fold_weighting: str = "unweighted",
    with_tearsheet: bool = True,
    weights: object | None = None,
    indicator_z: Mapping[str, Sequence[float | None]] | None = None,
) -> GoldenPathResult:
    """Run research -> backtest -> optimize -> tearsheet over one series.

    The optimize stage runs only when both ``trials`` and ``rails_fitter`` are
    supplied; with either missing the path stops after the tearsheet and the
    verdict records that the gate was not evaluated. That is deliberate: a
    driver that invented a rail fit would be choosing a research method, and
    #3173 is explicit that a full-history fit must not be reused inside the
    optimizer.

    Nothing is written to disk here and nothing is pushed anywhere. Call
    :func:`persist_golden_path` for the artifacts.
    """
    research = research_asset(
        dates=dates,
        prices=prices,
        symbols=symbols,
        data_path=data_path,
        data_dir=data_dir,
        risk_model=risk_model,
        risk_model_name=risk_model_name,
        valuation_weight=valuation_weight,
        extra_indicators=extra_indicators,
        oscillators=oscillators,
        include_indicators=include_indicators,
        coefficients_path=coefficients_path,
    )
    resolved_curve, preset_name = _resolve_curve(curve=curve, preset=preset)
    backtest = backtest_asset(
        research,
        curve=resolved_curve,
        initial_cash=initial_cash,
        sell_dates=sell_dates,
    )
    optimize: SdcaWalkForwardResult | None = None
    if (trials is None) != (rails_fitter is None):
        raise ValueError(
            "the optimize stage needs both trials and rails_fitter; pass both "
            "or neither. Running with only one would silently skip the stage."
        )
    if trials is not None and rails_fitter is not None:
        optimize = optimize_asset(
            research,
            trials=trials,
            rails_fitter=rails_fitter,
            evaluator=evaluator,
            evaluator_label=evaluator_label,
            objective=objective,
            n_folds=n_folds,
            holdout_frac=holdout_frac,
            oos_frac=oos_frac,
            sensitivity_frac=sensitivity_frac,
            extra_z=extra_z,
            fold_weighting=fold_weighting,
        )
    tearsheet = (
        tearsheet_payload(
            research,
            backtest,
            preset_name=preset_name,
            weights=weights,
            indicator_z=indicator_z,
        )
        if with_tearsheet
        else None
    )
    return GoldenPathResult(
        research=research,
        backtest=backtest,
        optimize=optimize,
        tearsheet=tearsheet,
        verdict=_verdict(optimize),
        stages=STAGES,
        preset_name=preset_name,
    )


# --------------------------------------------------------------------------- #
# Persistence (local files only)
# --------------------------------------------------------------------------- #


def persist_golden_path(
    result: GoldenPathResult, dest_dir: Path | str, *, stem: str = "golden_path"
) -> dict[str, Path]:
    """Write the run's artifacts as local files and return their paths.

    The manifest is the load-bearing file: it carries the non-authoritative
    caveat, the feasibility rule and the local-only rule beside the numbers, so
    an artifact read months later cannot be mistaken for a published backtest or
    for a cleared gate.
    """
    directory = Path(dest_dir)
    directory.mkdir(parents=True, exist_ok=True)

    risk_path = directory / f"{stem}_risk_index.parquet"
    result.research.risk_index.write_parquet(risk_path)

    frame_path = directory / f"{stem}_backtest_frame.parquet"
    result.backtest.frame.write_parquet(frame_path)

    paths: dict[str, Path] = {"risk_index": risk_path, "backtest_frame": frame_path}

    if result.tearsheet is not None:
        tearsheet_path = directory / f"{stem}_tearsheet.json"
        tearsheet_path.write_text(
            json.dumps(result.tearsheet, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        paths["tearsheet"] = tearsheet_path

    manifest: dict[str, Any] = {
        "stem": stem,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "stages": list(result.stages),
        "optimize_ran": result.optimize is not None,
        "tearsheet_written": result.tearsheet is not None,
        "preset_name": result.preset_name,
        "range": {
            "start": result.research.start.isoformat(),
            "end": result.research.end.isoformat(),
            "rows": result.research.row_count,
            "dropped_warmup_rows": result.research.dropped_warmup_rows,
        },
        "verdict": asdict(result.verdict),
        "backtest": {
            "authoritative": result.backtest.authoritative,
            "caveat": result.backtest.caveat,
            "initial_cash": result.backtest.initial_cash,
            "report": result.backtest.report.model_dump(mode="json"),
        },
        "optimize": (
            result.optimize.model_dump(mode="json") if result.optimize is not None else None
        ),
        "rules": {
            "feasibility": FEASIBILITY_RULE,
            "publish": PUBLISH_RULE,
        },
    }
    manifest_path = directory / f"{stem}_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    paths["manifest"] = manifest_path
    return paths


__all__ = [
    "BACKTEST_CAVEAT",
    "FEASIBILITY_RULE",
    "PUBLISH_RULE",
    "STAGES",
    "BacktestStage",
    "GoldenPathResult",
    "GoldenPathVerdict",
    "ResearchStage",
    "backtest_asset",
    "optimize_asset",
    "persist_golden_path",
    "rails_fitter_for",
    "research_asset",
    "run_golden_path",
    "tearsheet_payload",
]
