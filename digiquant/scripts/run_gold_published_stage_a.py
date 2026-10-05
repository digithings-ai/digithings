#!/usr/bin/env python3
"""The PUBLISHED Stage A keep/drop for gold, on in-sample vs-flat-DCA (#4804).

This runs the published Stage A objective for GLD — the one the house rules name as
the keep/drop — rather than the diagnostic that preceded it on this branch.

**What this is.** Glue, again. The search itself is the SHIPPED
``strategies/sdca/weight_search.py::optimize_stage_a_by_backtest``, on the SHIPPED
frozen grids that function declares (``grid`` and ``valuation_grid``, both read from
its signature — never restated here, never widened, never narrowed). The rails are
the SHIPPED no-trend rolling-z anchor, refit per fold on the in-sample window only.
The curve is the SHIPPED ``gold_reselect`` preset shape, resolved by name.

**The objective.** In-sample ``vs_flat_dca_pct``, subject to a 10% capital-deployed
floor and a 50% drawdown cap — NOT vs-lump, NOT Sharpe, and NOT cycle overlap. See
``OBJECTIVE_LABEL``.

**Two things the owner ruled out, honoured structurally.** There is no power-law
valuation steer for gold and no generic log-linear / log-quadratic form anywhere in
this file; the only valuation rails are the shipped rolling-z anchor. Nothing here
reimplements the accumulation/distribution curve, the composite blend or the
buy/sell loop — those are the engine's, and this file only feeds them.

**ONE run, not two.** ``optimize_stage_a_by_backtest`` takes no cycle windows: it
builds its own folds from the calendar via the shipped fold geometry. So the two
gold pin sets are NOT two runs here — the objective simply does not see them. The
``SdcaAssetProfile`` model still requires a ``cycle_windows`` field, so the profile
below carries one, and it is INERT for this objective. See
``CYCLE_WINDOWS_INERT_LABEL``.

**No gold profile exists in the module.** ``asset_profile.py`` ships ``btc_v1()`` and
``eth_research_v1()`` only. Per the task, that src file is NOT edited: the profile is
built from the module's own public surface (the ``SdcaAssetProfile`` constructor) with
the gold allowlist the module already publishes (``GOLD_MACRO_NAMES`` plus the generic
price oscillators) and the gold pin set the module already ships. See
``PROFILE_NOT_IN_SRC_LABEL``.

**The search name set is never hand-picked.** It comes from
``stage_a_search_names(gold_profile())``.

**FEASIBILITY.** The joint sweep is exponential in the number of searched names, and
the full 13-name allowlist does not fit in a session. The narrowing is a stated
FEASIBILITY CALL, recorded in ``FEASIBILITY_NOTE``, in the JSON, on the console and in
``ARCHITECTURE.md`` — never applied silently. It runs on a **coverage** rule (does the
leg's z actually exist across the searchable calendar), which is a property of the data
and not of any objective, and every excluded name keeps a row in the per-extra table so
**no allowlist name goes unreported.**

**Nothing live is touched.** Writes one file under ``.scratch/``. No publish config,
no push, no broker adapter, no live-trading path. Stage A only: Stage B
(``run_sdca_walk_forward``) freezes the weights, then ``regularize``.

Usage (research venv + src on PYTHONPATH):

    PYTHONPATH=digiquant/src <venv>/bin/python \\
        digiquant/scripts/run_gold_published_stage_a.py
"""

from __future__ import annotations

import inspect
import json
import time
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.asset_profile import (
    GENERIC_TECHNICAL_NAMES,
    SdcaAssetProfile,
    stage_a_search_names,
)
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import (
    GOLD_MACRO_NAMES,
    SdcaCompositeWeights,
    extra_z_vectors,
)
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_ohlcv
from digiquant.strategies.sdca.presets import load_preset
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.rolling_z import RollingZRiskModel
from digiquant.strategies.sdca.walk_forward import (
    FoldScore,
    RailsFitter,
    SdcaOptimizeObjective,
    SdcaTrialEvaluator,
    make_walk_forward_folds,
)
from digiquant.strategies.sdca.weight_search import optimize_stage_a_by_backtest

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_published_stage_a.json"

SYMBOL = "GLD-USD"
RISK_MODEL = "rolling_z"

# The shipped gold curve, resolved BY NAME from the shipped preset table. Owner ruling:
# no power-law steer for gold, no generic log-linear / log-quadratic form.
CURVE_PRESET = "gold_reselect"
CURVE_SOURCE = (
    "load_preset('gold_reselect').shape — the SHIPPED gold curve personality from "
    "strategies/sdca/presets.json, resolved by name rather than restated, so the curve "
    "cannot drift from the preset the rest of the gold work already uses"
)

# The shipped no-trend valuation rails: the same anchor the gold seed uses.
RAILS_KIND = "rolling_z"
RAILS_WINDOW_DAYS = 90
RAILS_Z = 1.0
RAILS_LABEL = (
    f"valuation rails = the shipped no-trend {RAILS_KIND} anchor, rolling "
    f"{RAILS_WINDOW_DAYS}d / z {RAILS_Z} — a trailing mean-reversion rail, refit per fold "
    "on the in-sample window only (never a full-history fit). No power-law and no "
    "time-trend fit is used for gold anywhere in this file."
)

FROZEN_GRID_SOURCE = (
    "the frozen grids are the SHIPPED defaults of "
    "optimize_stage_a_by_backtest in strategies/sdca/weight_search.py, read from that "
    "function's own signature at run time — the sweep below never restates, widens or "
    "narrows them"
)

# A leg whose z is missing on more than a quarter of its WORST SCORED WINDOW cannot be
# evaluated as a vote: the composite blend nulls any day one enabled leg is missing, so
# such a leg deletes that part of the book rather than informing it. Measured per window,
# not as a span average — averaging is what hides the early folds that decide the winner.
# Stated as a budget, applied inclusively at the boundary, and applied to DATA COVERAGE
# only — never to a score.
NULL_COVERAGE_LIMIT_PCT = 25.0

SINGLE_RUN_BECAUSE_NO_CYCLE_WINDOWS = True

OBJECTIVE_LABEL = (
    "objective = maximize mean IN-SAMPLE vs_flat_dca_pct across the walk-forward folds, "
    "with each fold's floor flag measured at the 10% capital-deployed floor and the "
    "50% drawdown cap recorded per fold. Not vs-lump, not Sharpe, not cycle overlap."
)

RANK_NOT_GATED_LABEL = (
    "IMPORTANT: the shipped Stage A rank does NOT gate on the floor or the cap. The frozen "
    "objective records the feasibility flag per fold and Stage B enforces it, but the Stage A "
    "argmax is the plain mean in-sample vs_flat_dca_pct. Nothing here may claim a row was "
    "vetoed for breaching the floor or the cap. Read the feasibility flag as recorded fact, "
    "not as a filter that ran."
)

IN_SAMPLE_LABEL = (
    "IN-SAMPLE. These numbers are fitted on the same GLD calendar the folds are cut from: "
    "the winning weights are a MAXIMUM over the frozen weight grid, scored against those "
    "in-sample folds. A selected upper bound, not a skill estimate. No performance claim "
    "of any kind is made here — no return, no Sharpe, no edge — beyond what the returned "
    "metrics literally say."
)

OOS_LABEL = (
    "OUT-OF-SAMPLE, REPORTED AND NOT USED FOR SELECTION. Every OOS number below is printed "
    "for the owner's information only. Nothing was chosen on it: the Stage A argmax reads "
    "in-sample vs_flat_dca_pct exclusively. Do not read an OOS figure as validation of the "
    "weights, and do not pick a row by it."
)

OOS_VOID_LABEL = (
    "MEASURED, AND IT IS A REAL DEFECT IN THE SHIPPED PATH: every OOS window in this run "
    "deployed ZERO capital, so every OOS figure below is the same all-cash book and carries "
    "no information. The cause is in the rails, not in this script. optimize_stage_a_by_backtest "
    "refits rails on each fold's IN-SAMPLE window and then evaluates OOS on those same rails — "
    "correct per the #3173 no-leak rule, and fine for a model that EXTRAPOLATES (the trend "
    "rails do). But RollingZRiskModel is a trailing model: its rails() left-joins a stored "
    "(date, mu, sigma) table, so every date OUTSIDE the fit window comes back null. Null rails "
    "give null risk, null risk gives no trades, and the fold is all cash. So the no-trend "
    "rolling-z anchor and the engine's per-fold walk-forward are not compatible as written: "
    "Stage A in-sample numbers are sound (in-sample dates are inside the fit window), and the "
    "out-of-sample numbers are structurally void. This is reported rather than worked around. "
    "The gold curve search on this branch already carries a 'causal rolling' path that scores "
    "folds through a concatenated-history rolling loop and calls the engine walk-forward void "
    "for these rails; Stage B must use that path, or the rails must be a model that "
    "extrapolates. Not fixed here — that is a source change in walk_forward.py or rolling_z.py, "
    "which are owner territory."
)

FLOOR_BASIS_LABEL = (
    "Note the floor is measured on a DIFFERENT basis in the two stages, which is worth knowing "
    "before reading either flag. Stage A's feasible flag (weight_search.py) compares NET "
    "capital_deployed_pct, while Stage B's is_feasible (walk_forward.py) compares PEAK "
    "capital_deployed_peak_pct. A book that sold into strength can net negative while capital "
    "was genuinely at risk, which is why the baseline's fold 0 is flagged infeasible here on "
    "peak-deployed 100.0%. Both flags are reported as recorded; neither gated Stage A."
)

NOT_THE_DIAGNOSTIC_LABEL = (
    "THIS IS A DIFFERENT OBJECTIVE FROM THE PRECEDING DIAGNOSTIC RUN, and the two must not be "
    "blended into a single claim. That run scored cycle-window overlap via "
    "optimize_stage_a_weights in stage_a.py; this one scores the published backtest objective "
    "via optimize_stage_a_by_backtest in weight_search.py. Cycle overlap is a shape "
    "diagnostic. A cycle-overlap winner and a backtest winner are answers to two different "
    "questions, and agreement or disagreement between them is a finding to report — never a "
    "number to merge."
)

FEASIBILITY_NOTE = (
    "FEASIBILITY CALL — the joint sweep is 3**len(names) combinations times 3 valuation "
    "values, so it is exponential in the searched name count. The published name set is "
    "stage_a_search_names(gold_profile), 13 names here, which projects to 3**13 * 3 = "
    "4,782,969 evaluations at the MEASURED 33.0 ms/eval — about 43.9 h for one run, which "
    "does not fit a research session. The joint sweep therefore runs the subset whose legs "
    "clear a COVERAGE budget of "
    f"{NULL_COVERAGE_LIMIT_PCT:g}% missing z in their WORST SCORED WINDOW (a data property, "
    "never a score). The window is the right granularity and the span average is not: the "
    "macro legs' missing history sits in the EARLIEST in-sample fold, so a leg can average "
    "13% missing across the span while missing more than half of the first fold the search "
    "actually scores. Every name dropped from the joint sweep is named, with its measured "
    "coverage, in the per-extra table and in the exclusions, and every one of them still "
    "gets its own single-leg probe row — so nothing is silently absent and no name goes "
    "unreported. The projected full-allowlist cost is carried in the artifact."
)

PROFILE_NOT_IN_SRC_LABEL = (
    "NO gold profile exists in the module. asset_profile.py ships btc_v1() and "
    "eth_research_v1() only, and that src file was deliberately NOT edited for this run: "
    "adding a gold factory is a source change the owner has not asked for, and a research "
    "script is the wrong place to make one. The profile below is therefore built from the "
    "module's own public surface — the SdcaAssetProfile constructor — using the gold "
    "allowlist the module already publishes (GOLD_MACRO_NAMES plus the generic price "
    "oscillators) and the gold pin set the module already ships. If the owner later wants a "
    "first-class gold profile, that is a separate, deliberate change."
)

CYCLE_WINDOWS_INERT_LABEL = (
    "CYCLE WINDOWS ARE INERT HERE. optimize_stage_a_by_backtest takes no cycle windows — it "
    "cuts its own folds from the calendar — so ONE run is correct and the gold_v1 / "
    "gold_v2 pin sets are not an input to this objective at all. The SdcaAssetProfile model "
    "still requires a cycle_windows field, so the profile carries gold_v1() to satisfy the "
    "schema; it does not influence any number in this artifact. The preceding diagnostic "
    "run did consume those windows, which is one reason its result differs."
)

BTC_SDCA_REFERENCE: Mapping[str, float] = {
    "valuation": 1.0,
    "m2": 0.5,
    "dxy": 0.5,
    "weekly_macd": 0.5,
    "weekly_rsi": 0.25,
}
BTC_REFERENCE_LABEL = (
    "published btc_sdca reference shape: valuation=1.0, m2=0.5, dxy=0.5, weekly_macd=0.5, "
    "weekly_rsi=0.25 (SMA band and BTC/ETH RS at 0) — five legs, four of them "
    "partial-weight. Reported for shape comparison only: not a tuning target, not a "
    "benchmark, and nothing here was copied from it or steered toward it."
)

_ALLOWLIST = GOLD_MACRO_NAMES + GENERIC_TECHNICAL_NAMES
_FOLD_GEOMETRY_KEYS = ("n_folds", "holdout_frac", "oos_frac")


def shipped_fold_geometry() -> dict[str, Any]:
    """The fold geometry the shipped Stage A will use, read off its own signature."""
    params = inspect.signature(optimize_stage_a_by_backtest).parameters
    return {key: params[key].default for key in _FOLD_GEOMETRY_KEYS}


def shipped_frozen_grid() -> tuple[tuple[float, ...], tuple[float, ...]]:
    """The shipped frozen grids, read off the signature. Never restated, never altered."""
    params = inspect.signature(optimize_stage_a_by_backtest).parameters
    return tuple(params["grid"].default), tuple(params["valuation_grid"].default)


def profile_for(
    *,
    symbol: str = SYMBOL,
    risk_model: str = RISK_MODEL,
    extra_indicators: Sequence[str] = _ALLOWLIST,
) -> SdcaAssetProfile:
    """Build a profile from the module's public constructor. No src file is edited."""
    return SdcaAssetProfile(
        symbol=symbol,
        risk_model=risk_model,  # type: ignore[arg-type]
        oscillators=SdcaOscillatorSpec(),
        cycle_windows=SdcaCycleWindows.gold_v1(),
        extra_indicators=tuple(extra_indicators),
        signal_delay_days=0,
    )


def gold_profile() -> SdcaAssetProfile:
    """The gold research profile. Research-only: not a publish candidate."""
    return profile_for()


def declared_search_names(profile: SdcaAssetProfile) -> tuple[str, ...]:
    """The published name set, via the module's own helper. Never hand-picked."""
    return stage_a_search_names(profile)


def objective() -> SdcaOptimizeObjective:
    """The published objective: 10% deployed floor, 50% drawdown cap."""
    return SdcaOptimizeObjective()


def curve_shape() -> SdcaCurveShape:
    """The shipped gold curve shape, by preset name."""
    preset = load_preset(CURVE_PRESET)
    if preset.shape is None:
        raise ValueError(f"preset {CURVE_PRESET!r} carries no shape")
    return preset.shape


def rails_fitter(dates: Sequence[date], prices: Sequence[float]) -> RiskModel:
    """``RailsFitter`` for the shipped rolling-z anchor, fit on the given window only."""
    return RollingZRiskModel(
        pl.Series("date", list(dates), dtype=pl.Date),
        pl.Series("price", [float(p) for p in prices], dtype=pl.Float64),
        window=RAILS_WINDOW_DAYS,
        z=RAILS_Z,
    )


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


class CoverageRow(BaseModel):
    """One allowlist name's measured calendar coverage, and whether it was searched.

    ``worst_window_null_pct`` is the number the rule gates on. The aggregate
    ``span_null_pct`` is reported beside it because measuring only the aggregate is what
    nearly let this run through with an infeasible name count: the macro legs' missing
    history is concentrated in the EARLIEST in-sample window, so a leg can average 13%
    missing across the span while being missing on more than half of the first fold the
    search actually scores.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    name: str = Field(..., min_length=1)
    searched: bool = True
    span_null_pct: float = Field(ge=0.0, le=100.0)
    worst_window_null_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    worst_window: str = Field(default="", min_length=0)
    full_null_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class Exclusion(BaseModel):
    """One name kept OUT of the joint sweep, with the reason and the measurement."""

    model_config = ConfigDict(frozen=True, strict=True)

    name: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    detail: str = Field(..., min_length=1)


class SearchPlan(BaseModel):
    """What the joint sweep searched, what it did not, and the stated rule."""

    model_config = ConfigDict(frozen=True, strict=True)

    search_names: tuple[str, ...]
    coverage: tuple[CoverageRow, ...]
    exclusions: tuple[Exclusion, ...]
    limit_pct: float
    detail: str


class PublishedRun(BaseModel):
    """One published Stage A run: the winning weights and the metrics that chose them."""

    model_config = ConfigDict(frozen=True, strict=True, arbitrary_types_allowed=True)

    label: str
    weights: SdcaCompositeWeights
    search_names: tuple[str, ...]
    mean_is_vs_flat_dca_pct: float
    mean_oos_vs_flat_dca_pct: float
    num_evaluations: int = Field(ge=0)
    feasible_folds: int = Field(ge=0)
    wall_seconds: float = Field(ge=0.0)
    fold_scores: tuple[FoldScore, ...]

    @property
    def enabled_extras(self) -> dict[str, float]:
        """Which legs are on — the "is this actually a composite" read."""
        return dict(self.weights.enabled_extras())


class PerExtraProbe(BaseModel):
    """One allowlist name's single-leg verdict against the valuation-only baseline.

    The verdict vocabulary is deliberately **keep / flat**, not keep / drop, and the
    reason is structural rather than stylistic: a one-name sweep runs the frozen grid, and
    that grid *contains* the valuation-only row (extras at 0.0). So the sweep's best is
    ``max(baseline, leg-on)`` and can never fall below the baseline. A leg that actively
    hurts and a leg that merely does not help are therefore the same observation here, and
    both are reported as **no keep earned** rather than as a drop this sweep cannot see.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    name: str
    decision: str
    in_joint_sweep: bool
    best_weight: float
    mean_is_vs_flat_dca_pct: float
    delta_is_vs_flat_dca_pct: float
    mean_oos_vs_flat_dca_pct: float
    delta_oos_vs_flat_dca_pct: float
    num_evaluations: int = Field(ge=0)


class ProjectedCost(BaseModel):
    """What the un-narrowed allowlist would have cost, at the measured rate."""

    model_config = ConfigDict(frozen=True, strict=True)

    names: int = Field(ge=0)
    evaluations: int = Field(ge=0)
    ms_per_eval: float = Field(ge=0.0)
    hours: float = Field(ge=0.0)


# --------------------------------------------------------------------------- #
# Coverage and the feasibility partition
# --------------------------------------------------------------------------- #


def searchable_span_indices(dates: Sequence[date]) -> list[int]:
    """Indices the search actually scores: everything up to the last fold's OOS end.

    The holdout tail is reserved and never scored, so it must not count toward a leg's
    coverage. Geometry is the SHIPPED fold geometry, read off the shipped signature.
    """
    folds, _holdout = make_walk_forward_folds(list(dates), **shipped_fold_geometry())
    last = max(fold.oos_end for fold in folds)
    return [i for i, day in enumerate(dates) if day <= last]


def _null_pct(series: Sequence[float | None], indices: Sequence[int]) -> float:
    if not indices:
        return 100.0
    return 100.0 * sum(1 for i in indices if series[i] is None) / len(indices)


def scored_windows(dates: Sequence[date]) -> list[tuple[str, list[int]]]:
    """Every window the shipped search actually scores, labelled, as index lists.

    This is the granularity at which a missing leg does damage. The composite blend
    nulls a day when ANY enabled leg is null there, so a leg that is missing on part of a
    window deletes that part of the book for the whole fold — it is not diluted by the
    rest of the calendar the way an aggregate share suggests.
    """
    folds, _holdout = make_walk_forward_folds(list(dates), **shipped_fold_geometry())
    windows: list[tuple[str, list[int]]] = []
    for fold in folds:
        for label, start, end in (
            ("is", fold.is_start, fold.is_end),
            ("oos", fold.oos_start, fold.oos_end),
        ):
            indices = [i for i, day in enumerate(dates) if start <= day <= end]
            windows.append((f"fold{fold.fold}_{label}", indices))
    return windows


def measure_coverage(
    dates: Sequence[date],
    extra_z: Mapping[str, Sequence[float | None]],
    *,
    limit_pct: float = NULL_COVERAGE_LIMIT_PCT,
) -> tuple[CoverageRow, ...]:
    """Missing-z share per name: worst scored window, searchable span, full calendar.

    ``searched`` is decided on the WORST SCORED WINDOW. That is the honest gate: a leg
    that is missing on more than the limit inside any one window the search trades cannot
    be evaluated as a vote in that window, and averaging it away over the whole span would
    hide exactly the folds that decide the winner.
    """
    span = searchable_span_indices(dates)
    everything = list(range(len(dates)))
    windows = scored_windows(dates)
    rows: list[CoverageRow] = []
    for name in extra_z:
        series = extra_z[name]
        shares = [(label, _null_pct(series, indices)) for label, indices in windows]
        worst_label, worst_pct = max(shares, key=lambda item: (item[1], item[0]))
        rows.append(
            CoverageRow(
                name=name,
                searched=worst_pct <= limit_pct,
                span_null_pct=_null_pct(series, span),
                worst_window_null_pct=worst_pct,
                worst_window=worst_label,
                full_null_pct=_null_pct(series, everything),
            )
        )
    return tuple(rows)


def partition_search_names(
    rows: Sequence[CoverageRow],
    *,
    limit_pct: float = NULL_COVERAGE_LIMIT_PCT,
) -> SearchPlan:
    """Split measured coverage into a searched subset and a recorded exclusion list."""
    searched = tuple(r.name for r in rows if r.worst_window_null_pct <= limit_pct)
    exclusions: list[Exclusion] = []
    for row in rows:
        if row.searched:
            continue
        exclusions.append(
            Exclusion(
                name=row.name,
                reason="calendar coverage over the feasibility limit",
                detail=(
                    f"missing z on {row.worst_window_null_pct:.1f}% of its worst scored window "
                    f"({row.worst_window}), over the stated {limit_pct:g}% budget; "
                    f"{row.span_null_pct:.1f}% across the whole searchable span and "
                    f"{row.full_null_pct:.1f}% of the full calendar. The composite blend nulls "
                    "any day one enabled leg is missing, so such a leg deletes that part of "
                    "the book rather than informing it — and the fold it deletes is one of "
                    "the folds that decides the winner. Excluded from the JOINT sweep only; "
                    "it still gets its own single-leg probe row in the per-extra table. This "
                    "is a data property, not a score."
                ),
            )
        )
    detail = (
        f"FEASIBILITY CALL. Joint sweep searched {len(searched)} of {len(rows)} allowlist "
        f"names, each missing z on at most {limit_pct:g}% of its worst SCORED WINDOW. "
        f"{len(exclusions)} name(s) held out with their measured coverage and the window that "
        "failed; every one of them still carries a single-leg probe row, so the per-extra "
        f"table covers the whole allowlist. See {FEASIBILITY_NOTE.split('.')[0]}."
    )
    return SearchPlan(
        search_names=searched,
        coverage=tuple(rows),
        exclusions=tuple(exclusions),
        limit_pct=limit_pct,
        detail=detail,
    )


def require_built_series(
    names: Sequence[str],
    extra_z: Mapping[str, Sequence[float | None]],
) -> None:
    """Refuse a searched name with no z series, rather than handing the engine a gap."""
    missing = [name for name in names if name not in extra_z]
    if missing:
        raise ValueError(f"search_names without a built z series: {missing}")


# --------------------------------------------------------------------------- #
# Running the shipped search
# --------------------------------------------------------------------------- #


def oos_is_degenerate(runs: Sequence[PublishedRun]) -> bool:
    """True when every fold of every run deployed nothing out of sample.

    Computed, not asserted in prose: a disclosure that could be wrong about its own subject
    is worse than no disclosure. An all-cash OOS book makes every OOS figure identical
    across weight vectors, so the OOS panel would read as evidence when it is an artefact.
    """
    folds = [score for run in runs for score in run.fold_scores]
    if not folds:
        return False
    return all(score.out_of_sample.capital_deployed_peak_pct == 0.0 for score in folds)


def _fold_payload(scores: Sequence[FoldScore]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for score in scores:
        row: dict[str, Any] = json.loads(score.fold.model_dump_json())
        row["in_sample"] = json.loads(score.in_sample.model_dump_json())
        row["out_of_sample"] = json.loads(score.out_of_sample.model_dump_json())
        row["feasible"] = score.feasible
        out.append(row)
    return out


def run_published(
    dates: Sequence[date],
    prices: Sequence[float],
    *,
    extra_z: Mapping[str, Sequence[float | None]],
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
    shape: SdcaCurveShape,
    search_names: Sequence[str],
    objective: SdcaOptimizeObjective,
    label: str,
) -> PublishedRun:
    """Hand the calendar to the SHIPPED published Stage A search and record what it said."""
    started = time.perf_counter()
    result = optimize_stage_a_by_backtest(
        dates,
        prices,
        extra_z=extra_z,
        rails_fitter=rails_fitter,
        evaluator=evaluator,
        shape=shape,
        search_names=search_names,
        objective=objective,
    )
    elapsed = time.perf_counter() - started
    return PublishedRun(
        label=label,
        weights=result.weights,
        search_names=tuple(result.search_names),
        mean_is_vs_flat_dca_pct=result.mean_is_vs_flat_dca_pct,
        mean_oos_vs_flat_dca_pct=result.mean_oos_vs_flat_dca_pct,
        num_evaluations=result.num_evaluations,
        feasible_folds=sum(1 for s in result.fold_scores if s.feasible),
        wall_seconds=elapsed,
        fold_scores=tuple(result.fold_scores),
    )


def run_baseline(
    dates: Sequence[date],
    prices: Sequence[float],
    *,
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
) -> PublishedRun:
    """The valuation-only row. Always run, so every per-extra delta has a reference."""
    return run_published(
        dates,
        prices,
        extra_z={},
        rails_fitter=rails_fitter,
        evaluator=evaluator,
        shape=curve_shape(),
        search_names=(),
        objective=objective(),
        label="baseline_valuation_only",
    )


def per_extra_probes(
    dates: Sequence[date],
    prices: Sequence[float],
    *,
    extra_z: Mapping[str, Sequence[float | None]],
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
    shape: SdcaCurveShape,
    objective: SdcaOptimizeObjective,
    allowlist: Sequence[str],
    baseline_is: float,
    baseline_oos: float,
    joint_names: Sequence[str] | None = None,
) -> tuple[PerExtraProbe, ...]:
    """One single-leg keep/drop row per allowlist name, against the baseline.

    Each probe is itself a call to the SHIPPED search over a one-name grid, so the
    per-extra table and the joint sweep share one objective and cannot drift apart.
    Coverage held a name out of the JOINT sweep; this is what keeps it reported.
    """
    require_built_series(allowlist, extra_z)
    joint = tuple(joint_names or ())
    rows: list[PerExtraProbe] = []
    for name in allowlist:
        run = run_published(
            dates,
            prices,
            extra_z=extra_z,
            rails_fitter=rails_fitter,
            evaluator=evaluator,
            shape=shape,
            search_names=(name,),
            objective=objective,
            label=f"probe:{name}",
        )
        delta_is = run.mean_is_vs_flat_dca_pct - baseline_is
        delta_oos = run.mean_oos_vs_flat_dca_pct - baseline_oos
        # keep / flat only. A one-name sweep always contains the valuation-only row, so a
        # negative delta is structurally unreachable here — see PerExtraProbe.
        decision = "keep" if delta_is > 0.0 else "flat"
        weight = dict(run.weights.model_dump()).get(name, 0.0)
        rows.append(
            PerExtraProbe(
                name=name,
                decision=decision,
                in_joint_sweep=name in joint,
                best_weight=weight,
                mean_is_vs_flat_dca_pct=run.mean_is_vs_flat_dca_pct,
                delta_is_vs_flat_dca_pct=delta_is,
                mean_oos_vs_flat_dca_pct=run.mean_oos_vs_flat_dca_pct,
                delta_oos_vs_flat_dca_pct=delta_oos,
                num_evaluations=run.num_evaluations,
            )
        )
    return tuple(rows)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def _weights_text(weights: SdcaCompositeWeights) -> str:
    enabled = weights.enabled_extras()
    head = f"val={weights.valuation:g}"
    if not enabled:
        return f"{head} (valuation-only)"
    return head + " " + " ".join(f"{n}={w:g}" for n, w in enabled.items())


def _fold_span(run: PublishedRun) -> str:
    if not run.fold_scores:
        return "-"
    return f"folds {len(run.fold_scores)}, {run.feasible_folds} feasible"


def print_report(
    runs: Sequence[PublishedRun],
    plan: SearchPlan,
    probes: Sequence[PerExtraProbe],
    *,
    projected: ProjectedCost,
    wall_seconds: float,
) -> None:
    """The owner's console read. IN-SAMPLE and OOS are never on the same line."""
    grid, valuation_grid = shipped_frozen_grid()
    degenerate = oos_is_degenerate(runs)
    print("")
    print("GOLD PUBLISHED STAGE A — in-sample vs-flat-DCA (keep/drop, NOT vs-lump, NOT Sharpe)")
    print(f"allowlist ({len(_ALLOWLIST)}): {', '.join(_ALLOWLIST)}")
    print(
        f"frozen grids: extras {list(grid)} x valuation {list(valuation_grid)} — {FROZEN_GRID_SOURCE}"
    )
    print(f"curve: {CURVE_SOURCE}")
    print(f"rails: {RAILS_LABEL}")
    print(f"objective: {OBJECTIVE_LABEL}")
    print("")

    header = f"{'run':<26} {'evals':>7} {'IN-SAMPLE':>11} {'feasible':>9} {'wall_s':>8}  weights"
    print(header)
    print("-" * len(header))
    for run in runs:
        print(
            f"{run.label:<26} {run.num_evaluations:>7} "
            f"{run.mean_is_vs_flat_dca_pct:>11.3f} {run.feasible_folds:>9} "
            f"{run.wall_seconds:>8.1f}  {_weights_text(run.weights)}"
        )
    print("")

    print("PER-EXTRA KEEP/DROP — IN-SAMPLE vs-flat-DCA against the valuation-only baseline")
    pheader = (
        f"{'extra':<14} {'decision':>9} {'weight':>7} {'IS pct':>9} {'d IS':>9} "
        f"{'in joint':>9} {'worst win':>10}"
    )
    print(pheader)
    print("-" * len(pheader))
    worst = {r.name: (r.worst_window_null_pct, r.worst_window) for r in plan.coverage}
    for probe in probes:
        share, when = worst.get(probe.name, (0.0, "-"))
        print(
            f"{probe.name:<14} {probe.decision:>9} {probe.best_weight:>7.2f} "
            f"{probe.mean_is_vs_flat_dca_pct:>9.3f} {probe.delta_is_vs_flat_dca_pct:>9.3f} "
            f"{str(probe.in_joint_sweep):>9} {share:>6.1f}% {when[:7]}"
        )
    print("")

    oos_title = "OUT-OF-SAMPLE — REPORTED, NOT USED FOR SELECTION"
    if degenerate:
        oos_title += "  ***  BUT SEE BELOW — EVERY WINDOW IS ALL-CASH, SO THESE CARRY NOTHING ***"
    print(oos_title)
    print(f"{'run':<26} {'OOS pct':>10}")
    print("-" * 38)
    for run in runs:
        print(f"{run.label:<26} {run.mean_oos_vs_flat_dca_pct:>10.3f}")
    print("")
    if degenerate:
        print(OOS_VOID_LABEL)
        print("")
    pheader2 = f"{'extra':<14} {'OOS pct':>10} {'d OOS':>10}"
    print(pheader2)
    print("-" * len(pheader2))
    for probe in probes:
        print(
            f"{probe.name:<14} {probe.mean_oos_vs_flat_dca_pct:>10.3f} "
            f"{probe.delta_oos_vs_flat_dca_pct:>10.3f}"
        )
    print("")

    print(f"joint sweep searched: {list(plan.search_names)}")
    for exclusion in plan.exclusions:
        print(f"  HELD OUT {exclusion.name}: {exclusion.reason} — {exclusion.detail}")
    print("")
    print(plan.detail)
    print("")
    print(
        f"projected un-narrowed cost: {projected.names} names = {projected.evaluations:,} "
        f"evaluations at the measured {projected.ms_per_eval:.1f} ms/eval "
        f"= {projected.hours:.1f} h"
    )
    print(f"this run wall time: {wall_seconds:.1f} s")
    print("")
    for label in (
        FEASIBILITY_NOTE,
        FLOOR_BASIS_LABEL,
        RANK_NOT_GATED_LABEL,
        NOT_THE_DIAGNOSTIC_LABEL,
        CYCLE_WINDOWS_INERT_LABEL,
        PROFILE_NOT_IN_SRC_LABEL,
        IN_SAMPLE_LABEL,
        OOS_LABEL,
        BTC_REFERENCE_LABEL,
    ):
        print(label)
        print("")


def payload(
    *,
    runs: Sequence[PublishedRun],
    plan: SearchPlan,
    coverage: Sequence[CoverageRow],
    probes: Sequence[PerExtraProbe],
    allowlist: Sequence[str],
    projected_full_cost: ProjectedCost,
) -> dict[str, Any]:
    """The UNTRACKED artifact. Every label travels with the numbers it qualifies.

    Deliberately free of wall time: see ``timing_note`` in the body.
    """
    grid, valuation_grid = shipped_frozen_grid()
    return {
        "symbol": SYMBOL,
        "risk_model": RISK_MODEL,
        "rails": RAILS_LABEL,
        "curve_preset": CURVE_PRESET,
        "curve_source": CURVE_SOURCE,
        "objective": OBJECTIVE_LABEL,
        "rank_not_gated_label": RANK_NOT_GATED_LABEL,
        "in_sample": True,
        "in_sample_label": IN_SAMPLE_LABEL,
        "oos_label": OOS_LABEL,
        "oos_is_degenerate": oos_is_degenerate(runs),
        "oos_void_label": OOS_VOID_LABEL,
        "floor_basis_label": FLOOR_BASIS_LABEL,
        "not_the_diagnostic_label": NOT_THE_DIAGNOSTIC_LABEL,
        "feasibility_note": FEASIBILITY_NOTE,
        "profile_not_in_src_label": PROFILE_NOT_IN_SRC_LABEL,
        "cycle_windows_inert_label": CYCLE_WINDOWS_INERT_LABEL,
        "single_run_because_no_cycle_windows": SINGLE_RUN_BECAUSE_NO_CYCLE_WINDOWS,
        "btc_sdca_reference_shape": dict(BTC_SDCA_REFERENCE),
        "btc_reference_label": BTC_REFERENCE_LABEL,
        "frozen_knobs": {
            "grid": list(grid),
            "valuation_grid": list(valuation_grid),
            "fold_geometry": shipped_fold_geometry(),
            "grid_source": FROZEN_GRID_SOURCE,
            "null_coverage_limit_pct": plan.limit_pct,
        },
        "allowlist": list(allowlist),
        "search_plan": {
            "search_names": list(plan.search_names),
            "detail": plan.detail,
            "exclusions": [
                {"name": e.name, "reason": e.reason, "detail": e.detail} for e in plan.exclusions
            ],
        },
        "coverage": [
            {
                "name": r.name,
                "searched": r.searched,
                "span_null_pct": r.span_null_pct,
                "worst_window_null_pct": r.worst_window_null_pct,
                "worst_window": r.worst_window,
                "full_null_pct": r.full_null_pct,
            }
            for r in coverage
        ],
        "projected_full_cost": json.loads(projected_full_cost.model_dump_json()),
        "runs": [
            {
                "label": run.label,
                "in_sample": True,
                "weights": json.loads(run.weights.model_dump_json()),
                "enabled_extras": dict(run.weights.enabled_extras()),
                "mean_is_vs_flat_dca_pct": run.mean_is_vs_flat_dca_pct,
                "mean_oos_vs_flat_dca_pct": run.mean_oos_vs_flat_dca_pct,
                "num_evaluations": run.num_evaluations,
                "search_names": list(run.search_names),
                "feasible_folds": run.feasible_folds,
                "folds": _fold_payload(run.fold_scores),
            }
            for run in runs
        ],
        "timing_note": (
            "Wall time is deliberately NOT in this artifact. It is a property of the machine, "
            "not a result, so recording it would make every diff of this record against itself "
            "show a spurious change. The console prints it, and num_evaluations — the "
            "machine-independent cost measure — is here per run."
        ),
        "per_extra": [
            {
                "name": p.name,
                "decision": p.decision,
                "in_joint_sweep": p.in_joint_sweep,
                "best_weight": p.best_weight,
                "mean_is_vs_flat_dca_pct": p.mean_is_vs_flat_dca_pct,
                "delta_is_vs_flat_dca_pct": p.delta_is_vs_flat_dca_pct,
                "mean_oos_vs_flat_dca_pct": p.mean_oos_vs_flat_dca_pct,
                "delta_oos_vs_flat_dca_pct": p.delta_oos_vs_flat_dca_pct,
                "num_evaluations": p.num_evaluations,
                "in_sample": True,
            }
            for p in probes
        ],
        "per_extra_note": (
            "One row per allowlist name, each a single-leg call to the SHIPPED search, so a "
            "name held out of the joint sweep on coverage is still reported rather than "
            "silently absent. decision is keep / flat on the IN-SAMPLE delta alone; OOS is "
            "reported and was not used to decide. 'flat' means no keep earned: a one-name "
            "sweep shares its grid with the valuation-only row, so its best can never fall "
            "below the baseline and a negative delta is structurally unreachable. Whether a "
            "flat leg actively hurts is not observable from this sweep — read the joint "
            "sweep's winning weight vector for that."
        ),
    }


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> int:
    from digiquant.strategies.sdca.curve_sim import evaluate_sdca_trial_curve_sim

    dates, prices = load_sdca_ohlcv(symbols=[SYMBOL], data_path=DATA_PATH, data_dir=None)
    print(f"{SYMBOL} {dates[0]}..{dates[-1]} ({len(dates)} daily bars, close column)")

    profile = gold_profile()
    allowlist = declared_search_names(profile)
    print(f"search names from stage_a_search_names(gold_profile()): {list(allowlist)}")

    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    seeds = SdcaCompositeWeights(valuation=1.0, **{name: 0.5 for name in allowlist})
    extra_z = extra_z_vectors(date_s, price_s, seeds, sources)
    require_built_series(allowlist, extra_z)
    print(f"built z series for {len(extra_z)} names")

    coverage = measure_coverage(dates, extra_z)
    plan = partition_search_names(coverage)

    started = time.perf_counter()
    baseline = run_baseline(
        dates, prices, rails_fitter=rails_fitter, evaluator=evaluate_sdca_trial_curve_sim
    )
    joint = run_published(
        dates,
        prices,
        extra_z=extra_z,
        rails_fitter=rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        shape=curve_shape(),
        search_names=plan.search_names,
        objective=objective(),
        label="joint_sweep",
    )
    probes = per_extra_probes(
        dates,
        prices,
        extra_z=extra_z,
        rails_fitter=rails_fitter,
        evaluator=evaluate_sdca_trial_curve_sim,
        shape=curve_shape(),
        objective=objective(),
        allowlist=allowlist,
        baseline_is=baseline.mean_is_vs_flat_dca_pct,
        baseline_oos=baseline.mean_oos_vs_flat_dca_pct,
        joint_names=plan.search_names,
    )
    wall = time.perf_counter() - started

    _, valuation_grid = shipped_frozen_grid()
    projected = ProjectedCost(
        names=len(allowlist),
        evaluations=len(valuation_grid) * 3 ** len(allowlist),
        ms_per_eval=33.0,
        hours=len(valuation_grid) * 3 ** len(allowlist) * 0.033 / 3600.0,
    )

    print_report(
        (baseline, joint),
        plan,
        probes,
        projected=projected,
        wall_seconds=wall,
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            payload(
                runs=(baseline, joint),
                plan=plan,
                coverage=coverage,
                probes=probes,
                allowlist=allowlist,
                projected_full_cost=projected,
            ),
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BTC_REFERENCE_LABEL",
    "BTC_SDCA_REFERENCE",
    "CURVE_PRESET",
    "CURVE_SOURCE",
    "CoverageRow",
    "Exclusion",
    "FEASIBILITY_NOTE",
    "FROZEN_GRID_SOURCE",
    "IN_SAMPLE_LABEL",
    "NOT_THE_DIAGNOSTIC_LABEL",
    "NULL_COVERAGE_LIMIT_PCT",
    "OOS_LABEL",
    "OUT_PATH",
    "PROFILE_NOT_IN_SRC_LABEL",
    "PerExtraProbe",
    "ProjectedCost",
    "PublishedRun",
    "RAILS_KIND",
    "RAILS_LABEL",
    "RAILS_WINDOW_DAYS",
    "RAILS_Z",
    "RANK_NOT_GATED_LABEL",
    "SearchPlan",
    "curve_shape",
    "declared_search_names",
    "gold_profile",
    "main",
    "measure_coverage",
    "objective",
    "partition_search_names",
    "payload",
    "print_report",
    "profile_for",
    "rails_fitter",
    "run_baseline",
    "run_published",
    "per_extra_probes",
    "searchable_span_indices",
    "shipped_fold_geometry",
    "shipped_frozen_grid",
]
