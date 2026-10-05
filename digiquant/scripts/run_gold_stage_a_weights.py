#!/usr/bin/env python3
"""Calibrate the Stage A variable weights for GLD against BOTH approved pin sets (#4804).

This is the **glue**, not a third calibration. Both engine halves already exist and
are tested, and neither is modified or restated here:

* per-indicator calibration ran first — ``fit_gold_indicators.py`` via
  ``run_gold_pin_set_fits.py`` wrote ``.scratch/gold_pin_set_fits.json``, and this
  script **READS that artifact**. The indicator grid sweep is NOT re-run and the
  indicator params are NOT re-derived: each extra is handed the exact
  ``best_grid_row`` params the fits artifact recorded for it.
* the variable-weight aggregate is ``strategies/sdca/stage_a.py`` —
  ``optimize_stage_a_weights`` sweeps the full
  ``valuation_grid x grid**len(names)`` product and scores every combo with
  ``cycle_overlap_score``. ``risk_from_weighted_z`` CONSUMES already-built z
  vectors; it does not calibrate anything. So the wiring job is exactly this:
  build each indicator's z at its best-fitted params, then hand the vectors to
  the shipped optimizer.

The anchor is the same no-trend anchor the frozen harness uses —
``anchor_z(date_s, price_s)``, i.e. the SHIPPED ``rolling_z`` rails at
rolling 90d / z 1.0. Zero production edits.

**Four runs, all reported — both ``require_extras`` settings, both pin sets.**

``require_extras=False`` can legitimately return a **valuation-only** composite.
That is a real finding and it is reported, not buried. But it is not the owner's
aggregate, so ``require_extras=True`` is run beside it, forcing at least one extra
so a real blend has to win on the same objective. Reporting only the flattering
row would be the dishonest version of this experiment, so the console table always
carries both.

**Search names: the frozen ``keep`` pool, and every exclusion is recorded.** The
artifact already made a per-indicator keep/drop verdict; Stage A then searches
weights over the legs that verdict kept. Two exclusion reasons are recorded, never
applied silently:

* ``no non-degenerate grid row`` — the hard rule. Passing such a name would hand
  ``optimize_stage_a_weights`` a series it cannot build, and
  ``risk_from_weighted_z`` raises on a missing one.
* ``frozen verdict != keep`` — feasibility, stated rather than hidden. The
  full ``product`` sweep is exponential in the number of search names: 12
  non-degenerate names is ``3^12 x 3 = 1,594,323`` evaluations at the measured
  ~5.6 ms each, i.e. ~2.5 h PER RUN and ~10 h for the four runs. The frozen
  ``verdict == "keep"`` pool is the harness's OWN candidate filter
  (``candidate_pool`` in ``fit_gold_indicators.py``), so this narrows along an
  already-ruled line rather than inventing a new one. It is a feasibility
  decision, and it is reported as one.

**IN-SAMPLE, and the objective is DIAGNOSTIC.** Every number here is fitted on the
same GLD history it is scored against: each leg's params are a max over a frozen
grid, scored against cycle windows derived from that same series, and the winning
weights are a max over the weight grid against those same windows. The objective
here is ``spread + 25 * (trough_frac + peak_frac)`` — cycle-window OVERLAP, a
shape diagnostic. **This is NOT the published keep/drop**, which is
``optimize_stage_a_by_backtest`` on in-sample ``vs_flat_dca_pct`` subject to a 10%
deployed floor and a 50% drawdown cap. Nothing in this script is a backtest
result and no return, Sharpe, drawdown or trade count is claimed anywhere. We are
at Stage A only; Stage B (``run_sdca_walk_forward``) freezes weights, then
``regularize``. Research-only: touches nothing outside ``.scratch/``, never
``settings.json``, never ``--push-supabase``, no live-trading path.

Usage (research venv + src on PYTHONPATH):

    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/run_gold_stage_a_weights.py

Writes ``digiquant/.scratch/gold_stage_a_weights.json`` (UNTRACKED). Requires the
fits artifact to exist first (``run_gold_pin_set_fits.py``); this script refuses
with a clean ``ValueError`` rather than re-deriving params.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_ohlcv
from digiquant.strategies.sdca.stage_a import (
    ACCUMULATE_RISK_MAX,
    DISTRIBUTE_RISK_MIN,
    CycleOverlapScore,
    StageAResult,
    optimize_stage_a_weights,
)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = DIGIQUANT_ROOT / "scripts" / "fit_gold_indicators.py"
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
FITS_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_pin_set_fits.json"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_stage_a_weights.json"

SYMBOL = "GLD-USD"

# The two approved gold pin sets, in report order. Resolved from the SHIPPED
# factories below, never from restated dates.
PIN_SETS: tuple[tuple[str, str], ...] = (
    ("gold_v1", "SdcaCycleWindows.gold_v1()"),
    ("gold_v2", "SdcaCycleWindows.gold_v2()"),
)

# Both settings, always. Never one alone.
REQUIRE_EXTRAS_SETTINGS: tuple[bool, ...] = (False, True)

# The published btc_sdca composite, as the SHAPE precedent for "what a real
# multi-leg blend looks like" — NOT as an input here and NOT as a target to beat.
# Reported so the owner can see whether gold's winner has the same shape (several
# partial-weight legs) or collapses onto one.
BTC_SDCA_REFERENCE: Mapping[str, float] = {
    "valuation": 1.0,
    "m2": 0.5,
    "dxy": 0.5,
    "weekly_macd": 0.5,
    "weekly_rsi": 0.25,
}
BTC_REFERENCE_LABEL = (
    "published btc_sdca reference shape: valuation=1.0, m2=0.5, dxy=0.5, "
    "weekly_macd=0.5, weekly_rsi=0.25 (SMA band and BTC/ETH RS at 0) — the "
    "precedent for what a real composite looks like. It is reported for shape "
    "comparison only: nothing here is copied from it, tuned toward it, or "
    "benchmarked against it."
)

OBJECTIVE_LABEL = (
    "objective = cycle_overlap_score.objective = spread + 25.0 * "
    "(trough_in_accumulate_frac + peak_in_distribute_frac), where spread = mean risk "
    "in peak windows minus mean risk in trough windows, accumulate band <= "
    f"{ACCUMULATE_RISK_MAX} and distribute band >= {DISTRIBUTE_RISK_MIN}. Higher is "
    "better. This is a SHAPE diagnostic — how well composite risk lines up with the "
    "pinned cycle windows."
)

DIAGNOSTIC_NOT_KEEP_DROP = (
    "DIAGNOSTIC, NOT THE PUBLISHED KEEP/DROP. The published Stage A keep/drop is "
    "optimize_stage_a_by_backtest on in-sample vs_flat_dca_pct subject to a 10% "
    "capital-deployed floor and a 50% drawdown cap — NOT cycle overlap, NOT vs-lump, "
    "NOT Sharpe. This run used the cycle-overlap objective, so it does not constitute "
    "the published keep/drop and no weight here is promoted on its strength. Stage A "
    "only: Stage B (run_sdca_walk_forward) freezes weights, then regularize."
)

IN_SAMPLE_LABEL = (
    "IN-SAMPLE, AND PARTLY A SELECTED UPPER BOUND. Every leg's params are a MAX over "
    "the frozen indicator grid, and the winning weights are a MAX over the weight "
    "grid, both scored against cycle windows derived from the SAME GLD history the "
    "z-series are built from. The maximums are chosen knowing the scores. Read the "
    "results as 'the best this grid can do on its own history', never as "
    "out-of-sample predictive skill. The pin-set windows are a SCORING TARGET, not "
    "execution periods: they carry no exposure floor and say nothing about time in "
    "market. No return, Sharpe, drawdown or trade count is claimed anywhere here."
)

SEARCH_POOL_NOTE = (
    "search_names = the frozen verdict == 'keep' pool of the fits artifact (the same "
    "filter candidate_pool() applies in fit_gold_indicators.py). Exclusions are "
    "recorded per name with a reason and never applied silently. The 'no "
    "non-degenerate grid row' exclusion is a hard rule — passing such a name would "
    "raise in risk_from_weighted_z. The 'frozen verdict != keep' exclusion is a "
    "FEASIBILITY decision: the shipped optimizer sweeps the full itertools.product, "
    "so 12 non-degenerate names is 3**12 * 3 = 1,594,323 evaluations at the measured "
    "~5.6 ms each (~2.5 h per run, ~10 h for four runs). Narrowing along an "
    "already-ruled keep/drop line is preferable to a sweep that never finishes."
)

_HARNESS_MODULE: ModuleType | None = None


def load_harness() -> ModuleType:
    """Load the frozen Plan-19 harness by file path. No module-level execution.

    Same by-path pattern as ``run_gold_pin_set_fits.py`` — a research script, not a
    package module. Cached so the re-exports below name one instance.
    """
    global _HARNESS_MODULE
    if _HARNESS_MODULE is not None:
        return _HARNESS_MODULE
    spec = importlib.util.spec_from_file_location("fit_gold_indicators", HARNESS_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover — loader contract
        raise ImportError(f"cannot load the frozen harness at {HARNESS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("fit_gold_indicators", module)
    spec.loader.exec_module(module)
    _HARNESS_MODULE = module
    return module


_HARNESS = load_harness()

# Re-exported BY REFERENCE from the frozen harness — an alias, never a second copy.
ANCHOR_NAME = _HARNESS.ANCHOR_NAME
ANCHOR_FORM = _HARNESS.ANCHOR_FORM
ANCHOR_ROLLING_WINDOW = _HARNESS.ANCHOR_ROLLING_WINDOW
ANCHOR_ROLLING_Z = _HARNESS.ANCHOR_ROLLING_Z
EQUAL_WEIGHT = _HARNESS.EQUAL_WEIGHT
ANCHOR_LABEL = _HARNESS.ANCHOR_LABEL


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


class ExtraSelection(BaseModel):
    """One extra as the fits artifact handed it over: best-fitted params, not re-derived."""

    model_config = ConfigDict(frozen=True, strict=True)

    name: str = Field(..., min_length=1)
    params: dict[str, int]
    window_days: int = Field(ge=2)
    separation: float
    direction: int = Field(ge=-1, le=1)
    captures: bool
    degenerate: bool
    verdict: str


class Exclusion(BaseModel):
    """One name kept OUT of search_names, with the reason it was kept out."""

    model_config = ConfigDict(frozen=True, strict=True)

    name: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    detail: str = Field(..., min_length=1)


class SearchPlan(BaseModel):
    """What Stage A actually searched, and what it refused to search and why."""

    model_config = ConfigDict(frozen=True, strict=True)

    search_names: tuple[str, ...]
    extras: tuple[ExtraSelection, ...]
    exclusions: tuple[Exclusion, ...]


class StageARun(BaseModel):
    """One (pin set, require_extras) run: the winning weights and their overlap score."""

    model_config = ConfigDict(frozen=True, strict=True)

    pin_set: str
    require_extras: bool
    weights: SdcaCompositeWeights
    score: CycleOverlapScore
    num_evaluations: int = Field(ge=0)
    search_names: tuple[str, ...]
    exclusions: tuple[Exclusion, ...]
    # The composite risk curve over the calendar, for the chart. Held on the record but
    # NOT serialized into the JSON artifact (it is 5,499 floats per run).
    risk: tuple[float | None, ...]


# --------------------------------------------------------------------------- #
# Reading the fits artifact
# --------------------------------------------------------------------------- #


def load_fits_artifact(path: Path = FITS_PATH) -> dict[str, Any]:
    """The per-indicator calibration artifact, or a clean refusal.

    This script does not re-run the indicator grid sweep and does not re-derive a
    single indicator param, so a missing artifact is a stop rather than a fallback.
    """
    if not path.exists():
        raise ValueError(
            f"missing fits artifact {path}; run "
            "digiquant/scripts/run_gold_pin_set_fits.py first (this script reads "
            "best-fitted indicator params from it and never re-derives them)"
        )
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict) or "sets" not in payload:
        raise ValueError(f"{path} is not a gold pin-set fits artifact (no 'sets' key)")
    return payload


def select_extras(set_payload: Mapping[str, Any], *, pin_set: str) -> SearchPlan:
    """The searched extras for one pin set, plus every exclusion and its reason.

    Two rules, in order:

    1. **No non-degenerate grid row -> exclude.** A leg whose every scored grid row
       is degenerate passes on a dead side only, and passing its name would also ask
       ``risk_from_weighted_z`` for a series built from a pass the frozen harness
       refuses to keep. Recorded, never passed as a missing series.
    2. **Frozen ``verdict != keep`` -> exclude**, on feasibility (see
       ``SEARCH_POOL_NOTE``). Also recorded.
    """
    reads = set_payload.get("indicator_reads")
    fits = set_payload.get("fits")
    if not isinstance(reads, Mapping) or not isinstance(fits, Mapping):
        raise ValueError(f"{pin_set} fits payload has no indicator_reads / fits block")
    indicators = fits.get("indicators")
    if not isinstance(indicators, Mapping):
        raise ValueError(f"{pin_set} fits payload has no fits.indicators block")

    extras: list[ExtraSelection] = []
    exclusions: list[Exclusion] = []
    for name, read in reads.items():
        if not isinstance(read, Mapping):
            raise ValueError(f"{pin_set} indicator_reads[{name!r}] is not an object")
        rows = (
            indicators.get(name, {}).get("rows")
            if isinstance(indicators.get(name), Mapping)
            else None
        )
        scored = [row for row in (rows or []) if row.get("separation") is not None]
        non_degenerate = [row for row in scored if not row.get("degenerate")]
        verdict = str(indicators.get(name, {}).get("verdict", "unknown"))
        if not non_degenerate:
            exclusions.append(
                Exclusion(
                    name=name,
                    reason="no non-degenerate grid row",
                    detail=(
                        f"{len(scored)} scored row(s), every one degenerate (a pass resting "
                        "on a dead side); the frozen verdict is "
                        f"{verdict!r}. Excluded rather than passed as a missing series."
                    ),
                )
            )
            continue
        if verdict != "keep":
            exclusions.append(
                Exclusion(
                    name=name,
                    reason="frozen verdict != keep",
                    detail=(
                        f"verdict {verdict!r} on best separation "
                        f"{float(read['separation']):+.4f} at {read.get('params')}; "
                        "outside the frozen keep pool Stage A searches (feasibility, see "
                        "SEARCH_POOL_NOTE)."
                    ),
                )
            )
            continue
        extras.append(
            ExtraSelection(
                name=name,
                params={str(k): int(v) for k, v in dict(read["params"]).items()},
                window_days=int(read["window_days"]),
                separation=float(read["separation"]),
                direction=int(read["direction"]),
                captures=bool(read["captures"]),
                degenerate=bool(read["degenerate"]),
                verdict=verdict,
            )
        )
    return SearchPlan(
        search_names=tuple(extra.name for extra in extras),
        extras=tuple(extras),
        exclusions=tuple(exclusions),
    )


# --------------------------------------------------------------------------- #
# Building the z vectors and running the shipped optimizer
# --------------------------------------------------------------------------- #


def build_extra_z(
    date_s: pl.Series,
    price_s: pl.Series,
    sources: Any,
    plan: SearchPlan,
) -> dict[str, list[float | None]]:
    """One z vector per SEARCHED extra, at the params the fits artifact recorded.

    ``build_z`` is the harness's own dispatcher into the SHIPPED z-functions, so no
    leg is reimplemented here. A name in ``plan.search_names`` that cannot be built
    raises — loudly, never as a silent null series.
    """
    extra_z: dict[str, list[float | None]] = {}
    for extra in plan.extras:
        extra_z[extra.name] = _HARNESS.build_z(extra.name, extra.params, date_s, price_s, sources)
    missing = [name for name in plan.search_names if name not in extra_z]
    if missing:
        raise ValueError(f"search_names without a built z series: {missing}")
    return extra_z


def run_stage_a(
    dates: Sequence[date],
    *,
    valuation_z: Sequence[float | None],
    extra_z: Mapping[str, Sequence[float | None]],
    windows: SdcaCycleWindows,
    plan: SearchPlan,
    pin_set: str,
    require_extras: bool,
) -> StageARun:
    """Hand the built z vectors to the SHIPPED variable-weight optimizer.

    ``optimize_stage_a_weights`` does the grid sweep and the overlap scoring; this
    wrapper only records what it was given and what it returned. A failure inside it
    (empty grid, windows that never overlap the risk series) propagates as a
    ``ValueError`` — never swallowed into a blank cell and never an ``IndexError``.
    """
    result: StageAResult = optimize_stage_a_weights(
        dates,
        valuation_z=valuation_z,
        extra_z=extra_z,
        windows=windows,
        search_names=plan.search_names,
        require_extras=require_extras,
    )
    risk = _risk_for_report(dates, valuation_z, extra_z, result.weights)
    return StageARun(
        pin_set=pin_set,
        require_extras=require_extras,
        weights=result.weights,
        score=result.score,
        num_evaluations=result.num_evaluations,
        search_names=plan.search_names,
        exclusions=plan.exclusions,
        risk=tuple(risk),
    )


def _risk_for_report(
    dates: Sequence[date],
    valuation_z: Sequence[float | None],
    extra_z: Mapping[str, Sequence[float | None]],
    weights: SdcaCompositeWeights,
) -> list[float | None]:
    from digiquant.strategies.sdca.stage_a import risk_from_weighted_z

    return list(risk_from_weighted_z(dates, valuation_z, extra_z, weights))


def pin_set_windows(label: str) -> SdcaCycleWindows:
    """Resolve an approved gold pin set from the SHIPPED factory."""
    factories = {
        "gold_v1": SdcaCycleWindows.gold_v1,
        "gold_v2": SdcaCycleWindows.gold_v2,
    }
    factory = factories.get(label)
    if factory is None:
        raise ValueError(f"{label!r} is not an approved gold pin set ({sorted(factories)})")
    return factory()


def run_all(
    dates: Sequence[date],
    date_s: pl.Series,
    price_s: pl.Series,
    sources: Any,
    artifact: Mapping[str, Any],
    *,
    valuation_z: Sequence[float | None] | None = None,
    set_labels: Sequence[str] = tuple(label for label, _factory in PIN_SETS),
) -> tuple[StageARun, ...]:
    """The four runs: both pin sets x both ``require_extras`` settings."""
    anchor = list(valuation_z) if valuation_z is not None else _HARNESS.anchor_z(date_s, price_s)
    sets = artifact.get("sets")
    if not isinstance(sets, Mapping):
        raise ValueError("fits artifact has no 'sets' block")
    runs: list[StageARun] = []
    for label in set_labels:
        set_payload = sets.get(label)
        if not isinstance(set_payload, Mapping):
            raise ValueError(f"fits artifact has no {label!r} set")
        plan = select_extras(set_payload, pin_set=label)
        extra_z = build_extra_z(date_s, price_s, sources, plan)
        windows = pin_set_windows(label)
        for require_extras in REQUIRE_EXTRAS_SETTINGS:
            runs.append(
                run_stage_a(
                    dates,
                    valuation_z=anchor,
                    extra_z=extra_z,
                    windows=windows,
                    plan=plan,
                    pin_set=label,
                    require_extras=require_extras,
                )
            )
    return tuple(runs)


# --------------------------------------------------------------------------- #
# Artifact + console table
# --------------------------------------------------------------------------- #


def _weights_text(run: StageARun) -> str:
    enabled = run.weights.enabled_extras()
    head = f"val={run.weights.valuation:g}"
    if not enabled:
        return f"{head} (valuation-only)"
    return head + " " + " ".join(f"{name}={weight:g}" for name, weight in enabled.items())


def print_table(runs: Sequence[StageARun]) -> None:
    """The owner's table: one row per run, both require_extras settings side by side."""
    print("")
    print("GOLD STAGE A VARIABLE-WEIGHT CALIBRATION — BOTH PIN SETS, BOTH require_extras")
    header = (
        f"{'pin set':<10} {'req_extras':>10} {'objective':>10} {'spread':>9} "
        f"{'trough_f':>9} {'peak_f':>8} {'evals':>7}  weights"
    )
    print(header)
    print("-" * len(header))
    for run in runs:
        score = run.score
        print(
            f"{run.pin_set:<10} {str(run.require_extras):>10} "
            f"{score.objective:>10.4f} {score.spread:>9.4f} "
            f"{score.trough_in_accumulate_frac:>9.4f} {score.peak_in_distribute_frac:>8.4f} "
            f"{run.num_evaluations:>7}  {_weights_text(run)}"
        )
    print("")
    for label in dict.fromkeys(run.pin_set for run in runs):
        rows = [run for run in runs if run.pin_set == label]
        first = rows[0]
        print(f"{label}: searched {list(first.search_names)}")
        for exclusion in first.exclusions:
            print(f"  EXCLUDED {exclusion.name}: {exclusion.reason} — {exclusion.detail}")
    print("")
    print(BTC_REFERENCE_LABEL)
    print("")
    print(OBJECTIVE_LABEL)
    print("")
    print(DIAGNOSTIC_NOT_KEEP_DROP)
    print("")
    print(SEARCH_POOL_NOTE)
    print("")
    print(IN_SAMPLE_LABEL)


def payload(runs: Sequence[StageARun], artifact: Mapping[str, Any]) -> dict[str, Any]:
    """The UNTRACKED artifact: weights as plain data, full score, names, exclusions."""
    return {
        "symbol": SYMBOL,
        "source_artifact": str(FITS_PATH.name),
        "anchor": ANCHOR_LABEL,
        "objective": OBJECTIVE_LABEL,
        "bands": {
            "accumulate_risk_max": ACCUMULATE_RISK_MAX,
            "distribute_risk_min": DISTRIBUTE_RISK_MIN,
        },
        "in_sample": True,
        "in_sample_label": IN_SAMPLE_LABEL,
        "diagnostic_not_keep_drop": DIAGNOSTIC_NOT_KEEP_DROP,
        "search_pool_note": SEARCH_POOL_NOTE,
        "btc_sdca_reference_shape": dict(BTC_SDCA_REFERENCE),
        "btc_reference_label": BTC_REFERENCE_LABEL,
        "require_extras_rationale": (
            "Both settings are reported for both pin sets, always. require_extras=False "
            "can return a valuation-only composite — a legitimate finding, and not the "
            "owner's aggregate. require_extras=True forces at least one extra so a real "
            "blend must win on the same objective. Reporting only the flattering row "
            "would make this experiment dishonest."
        ),
        "frozen_knobs": {
            "grid": [0.0, 0.5, 1.0],
            "valuation_grid": [0.0, 0.5, 1.0],
            "accumulate_risk_max": ACCUMULATE_RISK_MAX,
            "distribute_risk_min": DISTRIBUTE_RISK_MIN,
            "band_bonus": 25.0,
            "grid_source": (
                "stage_a.optimize_stage_a_weights defaults, re-exported by value here "
                "for the record only — the sweep itself is the shipped function's"
            ),
        },
        "pin_sets": {label: factory for label, factory in PIN_SETS},
        "comparator": {
            "name": "btc_sdca (published)",
            "weights": dict(BTC_SDCA_REFERENCE),
            "role": ("shape comparison only — not an input, not a tuning target, not a benchmark"),
        },
        "runs": [
            {
                "pin_set": run.pin_set,
                "require_extras": run.require_extras,
                # weights as PLAIN DATA: the model dumped to JSON scalars.
                "weights": json.loads(run.weights.model_dump_json()),
                "enabled_extras": dict(run.weights.enabled_extras()),
                "score": json.loads(run.score.model_dump_json()),
                "num_evaluations": run.num_evaluations,
                "search_names": list(run.search_names),
                "exclusions": [
                    {"name": e.name, "reason": e.reason, "detail": e.detail} for e in run.exclusions
                ],
                "risk_points": len(run.risk),
            }
            for run in runs
        ],
        "runs_note": (
            "The composite risk curve itself is deliberately NOT serialized (5,499 "
            "floats per run); recompute it with risk_from_weighted_z at these weights."
        ),
        "source_fits_metric": artifact.get("metric"),
    }


def main() -> int:
    artifact = load_fits_artifact()
    dates, prices = load_sdca_ohlcv(symbols=[SYMBOL], data_path=DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    print(f"{SYMBOL} {dates[0]}..{dates[-1]} ({len(dates)} daily bars, close column)")
    print(f"anchor: {ANCHOR_LABEL}")
    print(f"bands: accumulate <= {ACCUMULATE_RISK_MAX}, distribute >= {DISTRIBUTE_RISK_MIN}")

    runs = run_all(dates, date_s, price_s, sources, artifact)
    print_table(runs)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload(runs, artifact), indent=2) + "\n")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ANCHOR_LABEL",
    "BTC_SDCA_REFERENCE",
    "DIAGNOSTIC_NOT_KEEP_DROP",
    "ExtraSelection",
    "Exclusion",
    "IN_SAMPLE_LABEL",
    "OBJECTIVE_LABEL",
    "PIN_SETS",
    "REQUIRE_EXTRAS_SETTINGS",
    "SEARCH_POOL_NOTE",
    "SearchPlan",
    "StageARun",
    "build_extra_z",
    "load_fits_artifact",
    "main",
    "payload",
    "pin_set_windows",
    "print_table",
    "run_all",
    "run_stage_a",
    "select_extras",
]
