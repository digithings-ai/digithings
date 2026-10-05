"""Gold Stage A variable-weight calibration against BOTH approved pin sets (#4804).

``digiquant/scripts/run_gold_stage_a_weights.py`` is the **glue** between two engine
halves that already exist and are already tested: the per-indicator fits (read from
``.scratch/gold_pin_set_fits.json``; the grid sweep is NOT re-run here) and the
shipped variable-weight aggregate (``strategies/sdca/stage_a.py``). It builds each
leg's z at its best-fitted params and hands the vectors to
``optimize_stage_a_weights``, four times: both pin sets x both ``require_extras``
settings.

The script is loaded by FILE PATH (the local script-import pattern this directory
already uses in ``test_gold_pin_set_fits.py``) rather than imported as a module,
because it lives under ``digiquant/scripts/`` and not on ``src``'s package path.

What is pinned here, and how each pin can fail:

1. **The grid the optimizer sweeps is re-implemented independently and MUST agree.**
   The test enumerates ``valuation_grid x grid**len(names)`` itself, scores every
   combo with the shipped ``cycle_overlap_score``, and asserts the runner's winner is
   the argmax. A silently-narrowed grid (a dropped name, a skipped combo class, a
   ``require_extras`` filter leaking) changes which row wins or drops the evaluation
   count, so the disagreement shows up rather than passing quietly.
2. **``require_extras=True`` never returns zero enabled extras.** The whole reason the
   second setting exists: without it the "aggregate" can be a single leg wearing a
   composite's name.
3. **A leg with no non-degenerate fit is EXCLUDED AND RECORDED**, never passed as a
   missing series — ``risk_from_weighted_z`` raises on a positive weight with no
   series, so the wiring has to drop the name up front and say so.
4. **``require_extras=False`` DOES allow the valuation-only result.** Without this pin
   the two settings could be accidentally identical (or the False one accidentally
   filtered), and the difference between them would be assumed rather than proven.
5. **Determinism: two identical runs give byte-identical JSON.** The artifact is a
   research record the owner reads; a run that reshuffles key order or float
   formatting between invocations cannot be diffed against itself.
6. **A genuine failure surfaces as a clean ``ValueError``**, never a bare ``assert``
   in the script and never an ``IndexError`` from a mis-indexed lookup.

Nothing here reads the price history or the fits artifact: every read is synthetic,
so these pins are about the WIRING RULES, not about the numbers GLD happens to
produce. (Pin 1 is deliberately run on a synthetic z/window fixture for that reason.)
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import itertools
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from digiquant.strategies.sdca.cycle_windows import CycleKind, CycleWindow, SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.stage_a import (
    ACCUMULATE_RISK_MAX,
    DISTRIBUTE_RISK_MIN,
    cycle_overlap_score,
    risk_from_weighted_z,
)

REPO = Path(__file__).resolve().parents[4]
RUNNER_PATH = REPO / "digiquant" / "scripts" / "run_gold_stage_a_weights.py"

pytestmark = pytest.mark.unit

GRID = (0.0, 0.5, 1.0)
VALUATION_GRID = (0.0, 0.5, 1.0)


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner() -> Any:
    return _load(RUNNER_PATH, "run_gold_stage_a_weights")


# --------------------------------------------------------------------------- #
# Synthetic fixtures
# --------------------------------------------------------------------------- #


def _dates(n: int, start: date = date(2020, 1, 1)) -> list[date]:
    return [start + _dt.timedelta(days=i) for i in range(n)]


def _windows() -> SdcaCycleWindows:
    """A trough window early and a peak window late, with quiet days between."""
    return SdcaCycleWindows(
        windows=(
            CycleWindow(
                name="t", kind=CycleKind.TROUGH, start=date(2020, 1, 1), end=date(2020, 1, 20)
            ),
            CycleWindow(
                name="p", kind=CycleKind.PEAK, start=date(2020, 2, 10), end=date(2020, 2, 25)
            ),
        )
    )


def _cheap_at_bottoms(dates: list[date], *, trough_end: date, peak_start: date) -> list[float]:
    """A z that votes CHEAP (+z) at bottoms and RICH (-z) at peaks, zero in between."""
    return [3.0 if d <= trough_end else (-3.0 if d >= peak_start else 0.0) for d in dates]


def _inverted(dates: list[date], *, trough_end: date, peak_start: date) -> list[float]:
    """A z that votes the WRONG way: rich at bottoms, cheap at peaks."""
    return [-v for v in _cheap_at_bottoms(dates, trough_end=trough_end, peak_start=peak_start)]


def _plan(runner: Any, names: tuple[str, ...]) -> Any:
    extras = tuple(
        runner.ExtraSelection(
            name=name,
            params={"window": 90},
            window_days=90,
            separation=1.0,
            direction=1,
            captures=True,
            degenerate=False,
            verdict="keep",
        )
        for name in names
    )
    return runner.SearchPlan(search_names=names, extras=extras, exclusions=())


# --------------------------------------------------------------------------- #
# 1. The grid is swept in full — an independent argmax must agree
# --------------------------------------------------------------------------- #


def _independent_argmax(
    dates: list[date],
    valuation_z: list[float | None],
    extra_z: dict[str, list[float | None]],
    windows: SdcaCycleWindows,
    names: tuple[str, ...],
    *,
    require_extras: bool,
) -> tuple[SdcaCompositeWeights, float, int]:
    """Sweep ``valuation_grid x grid**len(names)`` here, independently of the runner.

    Deliberately re-implemented rather than delegated: the point is that a narrowed
    grid in the runner cannot agree with a full sweep done from the spec. Returns the
    best weights, its objective and how many combos were evaluated.
    """
    best: SdcaCompositeWeights | None = None
    best_objective = float("-inf")
    evaluated = 0
    for value in VALUATION_GRID:
        for combo in itertools.product(GRID, repeat=len(names)):
            payload = {name: float(weight) for name, weight in zip(names, combo, strict=True)}
            try:
                weights = SdcaCompositeWeights(valuation=float(value), **payload)
            except ValueError:
                continue
            if require_extras and not weights.enabled_extras():
                continue
            if any(name not in extra_z for name in weights.enabled_extras()):
                continue
            evaluated += 1
            try:
                risk = risk_from_weighted_z(dates, valuation_z, extra_z, weights)
                score = cycle_overlap_score(dates, risk, windows)
            except ValueError:
                continue
            # Same tie-break the shipped optimizer uses: higher objective, then fewer
            # enabled extras, then higher valuation.
            better = score.objective > best_objective
            if score.objective == best_objective and best is not None:
                complexity = (len(weights.enabled_extras()), -weights.valuation)
                incumbent = (len(best.enabled_extras()), -best.valuation)
                better = complexity < incumbent
            if better:
                best, best_objective = weights, score.objective
    assert best is not None
    return best, best_objective, evaluated


@pytest.mark.parametrize("require_extras", [False, True])
def test_the_winner_is_the_argmax_of_an_independently_swept_full_grid(
    runner: Any, require_extras: bool
) -> None:
    """The pin that would catch a silently-narrowed grid."""
    dates = _dates(60)
    windows = _windows()
    names = ("weekly_rsi", "sma_band", "weekly_macd")
    valuation_z = _cheap_at_bottoms(
        dates, trough_end=date(2020, 1, 20), peak_start=date(2020, 2, 10)
    )
    extra_z = {
        "weekly_rsi": _cheap_at_bottoms(
            dates, trough_end=date(2020, 1, 20), peak_start=date(2020, 2, 10)
        ),
        # A second, weaker copy of the same vote, so the winner is not a uniqueness
        # artefact of one leg.
        "sma_band": [
            2.0 if d <= date(2020, 1, 20) else (-2.0 if d >= date(2020, 2, 10) else 0.0)
            for d in dates
        ],
        # An INVERTED leg: a positive weight on it must hurt, so a grid that quietly
        # skipped it would pick different weights.
        "weekly_macd": _inverted(dates, trough_end=date(2020, 1, 20), peak_start=date(2020, 2, 10)),
    }
    plan = _plan(runner, names)

    run = runner.run_stage_a(
        dates,
        valuation_z=valuation_z,
        extra_z=extra_z,
        windows=windows,
        plan=plan,
        pin_set="gold_v1",
        require_extras=require_extras,
    )

    expected, expected_objective, expected_evaluations = _independent_argmax(
        dates, valuation_z, extra_z, windows, names, require_extras=require_extras
    )
    assert run.weights == expected, "the winner must be the full-grid argmax"
    assert run.score.objective == pytest.approx(expected_objective)
    assert run.num_evaluations == expected_evaluations, (
        "the evaluation count is the grid's width; a narrowed sweep shows up here"
    )
    # The full grid over three names is 3 * 3**3 = 81 rows; only the all-zero and the
    # require_extras-filtered rows are legitimately dropped.
    assert run.num_evaluations >= len(VALUATION_GRID) * len(GRID) ** 3 - len(VALUATION_GRID)


def test_the_search_names_actually_reach_the_sweep(runner: Any) -> None:
    """A name in the plan is searched; a name absent from ``extra_z`` is not invented."""
    dates = _dates(60)
    windows = _windows()
    plan = _plan(runner, ("weekly_rsi",))
    result = runner.run_stage_a(
        dates,
        valuation_z=[1.0] * len(dates),
        extra_z={"weekly_rsi": [0.0] * len(dates)},
        windows=windows,
        plan=plan,
        pin_set="gold_v2",
        require_extras=False,
    )
    assert result.search_names == ("weekly_rsi",)
    # A plan that CLAIMS a name it carries no series for must be refused by the wiring
    # rather than handed to the sweep, where it would raise deep inside the grid.
    unbacked = runner.SearchPlan(
        search_names=("weekly_rsi",),
        extras=(),
        exclusions=(),
    )
    with pytest.raises(ValueError, match="without a built z series"):
        runner.build_extra_z(
            date_s=None,  # type: ignore[arg-type]
            price_s=None,  # type: ignore[arg-type]
            sources=None,
            plan=unbacked,
        )


# --------------------------------------------------------------------------- #
# 2. require_extras=True never returns a composite with no legs
# --------------------------------------------------------------------------- #


def test_require_extras_true_never_returns_zero_enabled_extras(runner: Any) -> None:
    dates = _dates(60)
    windows = _windows()
    names = ("weekly_rsi", "sma_band")
    # Valuation-only is the BEST combo here: the one extra is uninformative, so a
    # False-setting run would pick valuation 1.0 and nothing else.
    valuation_z = _cheap_at_bottoms(
        dates, trough_end=date(2020, 1, 20), peak_start=date(2020, 2, 10)
    )
    extra_z = {"weekly_rsi": [0.0] * len(dates), "sma_band": [0.0] * len(dates)}
    plan = _plan(runner, names)
    run = runner.run_stage_a(
        dates,
        valuation_z=valuation_z,
        extra_z=extra_z,
        windows=windows,
        plan=plan,
        pin_set="gold_v1",
        require_extras=True,
    )
    assert run.require_extras is True
    assert run.weights.enabled_extras(), "require_extras=True must leave at least one leg on"
    assert sum(run.weights.enabled_extras().values()) > 0.0


# --------------------------------------------------------------------------- #
# 3. A leg with no non-degenerate fit is excluded AND recorded
# --------------------------------------------------------------------------- #


def _set_payload(*, keep: str, degenerate: str) -> dict[str, Any]:
    """A fits-artifact set payload with one kept leg, one degenerate-only leg."""
    return {
        "indicator_reads": {
            keep: {
                "name": keep,
                "params": {"window": 378},
                "window_days": 378,
                "separation": 1.2345,
                "direction": 1,
                "captures": True,
                "degenerate": False,
                "status": "scored",
                "reason": None,
            },
            degenerate: {
                "name": degenerate,
                "params": {"rsi_length": 14},
                "window_days": 105,
                "separation": 0.7183,
                "direction": 1,
                "captures": False,
                "degenerate": True,
                "status": "scored",
                "reason": None,
            },
        },
        "fits": {
            "indicators": {
                keep: {
                    "name": keep,
                    "verdict": "keep",
                    "rows": [
                        {
                            "params": {"window": 378},
                            "window_days": 378,
                            "separation": 1.2345,
                            "degenerate": False,
                        }
                    ],
                },
                degenerate: {
                    "name": degenerate,
                    "verdict": "degenerate_pass",
                    "rows": [
                        {
                            "params": {"rsi_length": 14},
                            "window_days": 105,
                            "separation": 0.7183,
                            "degenerate": True,
                        },
                        {
                            "params": {"rsi_length": 21},
                            "window_days": 105,
                            "separation": 0.6,
                            "degenerate": True,
                        },
                    ],
                },
            }
        },
    }


def test_a_leg_with_no_non_degenerate_fit_is_excluded_and_recorded(runner: Any) -> None:
    plan = runner.select_extras(
        _set_payload(keep="real_rate", degenerate="weekly_rsi"), pin_set="gold_v1"
    )
    assert plan.search_names == ("real_rate",)
    assert plan.extras[0].name == "real_rate"
    reasons = {e.name: e.reason for e in plan.exclusions}
    assert reasons == {"weekly_rsi": "no non-degenerate grid row"}, (
        "the exclusion must be recorded with a reason, not applied silently"
    )
    detail = next(e.detail for e in plan.exclusions if e.name == "weekly_rsi")
    assert "2 scored row(s), every one degenerate" in detail


def test_an_excluded_leg_is_never_passed_as_a_missing_series(runner: Any) -> None:
    """``risk_from_weighted_z`` raises on a positive weight with no series — so the
    excluded name must not reach the sweep at all."""
    from digiquant.strategies.sdca.stage_a import risk_from_weighted_z

    dates = _dates(3)
    with pytest.raises(ValueError, match="no extra_z series"):
        risk_from_weighted_z(
            dates,
            valuation_z=[0.0, 0.0, 0.0],
            extra_z={},  # the excluded leg's series is absent
            weights=SdcaCompositeWeights(valuation=0.0, weekly_rsi=1.0),
        )

    plan = runner.select_extras(
        _set_payload(keep="real_rate", degenerate="weekly_rsi"), pin_set="gold_v1"
    )
    assert "weekly_rsi" not in plan.search_names


# --------------------------------------------------------------------------- #
# 4. require_extras=False DOES allow the valuation-only result
# --------------------------------------------------------------------------- #


def test_require_extras_false_allows_the_valuation_only_result(runner: Any) -> None:
    dates = _dates(60)
    windows = _windows()
    names = ("weekly_rsi", "sma_band")
    valuation_z = _cheap_at_bottoms(
        dates, trough_end=date(2020, 1, 20), peak_start=date(2020, 2, 10)
    )
    extra_z = {"weekly_rsi": [0.0] * len(dates), "sma_band": [0.0] * len(dates)}
    plan = _plan(runner, names)
    run = runner.run_stage_a(
        dates,
        valuation_z=valuation_z,
        extra_z=extra_z,
        windows=windows,
        plan=plan,
        pin_set="gold_v1",
        require_extras=False,
    )
    assert run.require_extras is False
    assert run.weights.enabled_extras() == {}, (
        "the False setting must be free to return valuation-only — that is the finding "
        "the True setting exists to sit beside"
    )
    assert run.weights.valuation == pytest.approx(1.0)


def test_the_two_settings_are_genuinely_different_runs_not_one_result_twice(
    runner: Any,
) -> None:
    """Both settings always run, both get recorded, and the owner sees each."""
    assert runner.REQUIRE_EXTRAS_SETTINGS == (False, True), (
        "reporting only the flattering setting is the dishonest version of this experiment"
    )
    dates = _dates(60)
    windows = _windows()
    names = ("weekly_rsi", "sma_band")
    valuation_z = _cheap_at_bottoms(
        dates, trough_end=date(2020, 1, 20), peak_start=date(2020, 2, 10)
    )
    extra_z = {"weekly_rsi": [0.0] * len(dates), "sma_band": [0.0] * len(dates)}
    plan = _plan(runner, names)
    free = runner.run_stage_a(
        dates,
        valuation_z=valuation_z,
        extra_z=extra_z,
        windows=windows,
        plan=plan,
        pin_set="gold_v1",
        require_extras=False,
    )
    forced = runner.run_stage_a(
        dates,
        valuation_z=valuation_z,
        extra_z=extra_z,
        windows=windows,
        plan=plan,
        pin_set="gold_v1",
        require_extras=True,
    )
    assert free.weights != forced.weights, "the settings must not collapse onto one row"


# --------------------------------------------------------------------------- #
# 5. Determinism — two identical runs, byte-identical JSON
# --------------------------------------------------------------------------- #


def _synthetic_runs(runner: Any) -> tuple[Any, ...]:
    """Four synthetic runs (both pin sets x both settings), no price history needed."""
    return tuple(
        runner.StageARun(
            pin_set=label,
            require_extras=require_extras,
            weights=SdcaCompositeWeights(valuation=1.0, weekly_rsi=0.5),
            score=cycle_overlap_score(
                _dates(60),
                risk_from_weighted_z(
                    _dates(60),
                    [1.0] * 60,
                    {"weekly_rsi": [0.5] * 60},
                    SdcaCompositeWeights(valuation=1.0, weekly_rsi=0.5),
                ),
                _windows(),
            ),
            num_evaluations=17,
            search_names=("weekly_rsi",),
            exclusions=(
                runner.Exclusion(
                    name="sma_band",
                    reason="no non-degenerate grid row",
                    detail="2 scored row(s), every one degenerate",
                ),
            ),
            risk=tuple([0.5] * 60),
        )
        for label in ("gold_v1", "gold_v2")
        for require_extras in runner.REQUIRE_EXTRAS_SETTINGS
    )


def test_two_identical_runs_serialize_byte_identically(runner: Any) -> None:
    artifact = {"metric": "synthetic"}
    first = json.dumps(runner.payload(_synthetic_runs(runner), artifact), indent=2) + "\n"
    second = json.dumps(runner.payload(_synthetic_runs(runner), artifact), indent=2) + "\n"
    assert first == second, "the artifact is a research record the owner diffs against itself"


def test_the_artifact_carries_weights_as_plain_data_and_the_exclusions(runner: Any) -> None:
    body = runner.payload(_synthetic_runs(runner), {"metric": "synthetic"})
    assert len(body["runs"]) == 4, "two pin sets x two require_extras settings"
    assert [run["pin_set"] for run in body["runs"]] == ["gold_v1", "gold_v1", "gold_v2", "gold_v2"]
    assert [run["require_extras"] for run in body["runs"]] == [False, True, False, True]
    for run in body["runs"]:
        assert isinstance(run["weights"], dict)
        assert run["weights"]["weekly_rsi"] == pytest.approx(0.5)
        assert set(run["score"]) >= {"objective", "spread", "trough_in_accumulate_frac"}
        assert run["num_evaluations"] == 17
        assert run["search_names"] == ["weekly_rsi"]
        assert [e["name"] for e in run["exclusions"]] == ["sma_band"]
    assert body["btc_sdca_reference_shape"] == dict(runner.BTC_SDCA_REFERENCE)
    assert body["bands"]["accumulate_risk_max"] == ACCUMULATE_RISK_MAX
    assert body["bands"]["distribute_risk_min"] == DISTRIBUTE_RISK_MIN


# --------------------------------------------------------------------------- #
# 6. Genuine failures are clean ValueErrors
# --------------------------------------------------------------------------- #


def test_a_missing_fits_artifact_is_a_clean_refusal_not_a_re_derivation(runner: Any) -> None:
    """The wiring reads best-fitted params; it never re-runs the indicator sweep."""
    with pytest.raises(ValueError, match="run_gold_pin_set_fits"):
        runner.load_fits_artifact(REPO / "digiquant" / ".scratch" / "does_not_exist.json")


def test_a_set_payload_without_the_reads_block_is_an_error_not_a_blank_cell(runner: Any) -> None:
    with pytest.raises(ValueError, match="indicator_reads"):
        runner.select_extras({"fits": {"indicators": {}}}, pin_set="gold_v1")


def test_an_unapproved_pin_set_label_is_refused(runner: Any) -> None:
    with pytest.raises(ValueError, match="not an approved gold pin set"):
        runner.pin_set_windows("gold_v3")


def test_windows_that_never_overlap_the_risk_series_raise_value_error(runner: Any) -> None:
    """A risk series that misses every window is a clean ValueError from the shipped
    scorer, surfaced through the runner — never an IndexError, never a blank cell."""
    dates = _dates(60)
    windows_outside = SdcaCycleWindows(
        windows=(
            CycleWindow(
                name="far",
                kind=CycleKind.TROUGH,
                start=date(1990, 1, 1),
                end=date(1990, 2, 1),
            ),
        )
    )
    plan = _plan(runner, ())
    with pytest.raises(ValueError):
        runner.run_stage_a(
            dates,
            valuation_z=[1.0] * len(dates),
            extra_z={},
            windows=windows_outside,
            plan=plan,
            pin_set="gold_v1",
            require_extras=False,
        )


def test_the_runner_has_no_bare_assert_statements() -> None:
    """A research script that asserts is a script that dies on ``python -O`` and hides
    a real failure behind an AssertionError nobody recognises."""
    source = RUNNER_PATH.read_text()
    assert "assert " not in source.replace("  # assert ", "")


# --------------------------------------------------------------------------- #
# The frozen anchors and the reported reference shape
# --------------------------------------------------------------------------- #


def test_the_bands_are_the_shipped_ones_not_restated(runner: Any) -> None:
    assert runner.ACCUMULATE_RISK_MAX == ACCUMULATE_RISK_MAX
    assert runner.DISTRIBUTE_RISK_MIN == DISTRIBUTE_RISK_MIN
    assert runner.OBJECTIVE_LABEL.find("25.0") != -1, "the band bonus must be named in the label"


def test_the_reported_btc_sdca_shape_is_the_published_composite(runner: Any) -> None:
    assert dict(runner.BTC_SDCA_REFERENCE) == {
        "valuation": 1.0,
        "m2": 0.5,
        "dxy": 0.5,
        "weekly_macd": 0.5,
        "weekly_rsi": 0.25,
    }
    assert "shape" in runner.BTC_REFERENCE_LABEL.lower()
    assert "for shape comparison only" in runner.BTC_REFERENCE_LABEL


def test_the_anchor_is_the_shipped_rolling_z_rails(runner: Any) -> None:
    assert runner.ANCHOR_FORM == "rolling_z"
    assert runner.ANCHOR_ROLLING_WINDOW == 90
    assert runner.ANCHOR_ROLLING_Z == 1.0
    assert runner.ANCHOR_NAME == "valuation"


def test_the_registry_is_exactly_the_two_approved_gold_pin_sets(runner: Any) -> None:
    assert runner.PIN_SETS == (
        ("gold_v1", "SdcaCycleWindows.gold_v1()"),
        ("gold_v2", "SdcaCycleWindows.gold_v2()"),
    )
    for label, _factory in runner.PIN_SETS:
        windows = runner.pin_set_windows(label)
        assert windows.windows, f"{label} resolved to an empty window set"


def test_the_report_states_it_is_diagnostic_and_not_the_published_keep_drop(
    runner: Any,
) -> None:
    assert "DIAGNOSTIC, NOT THE PUBLISHED KEEP/DROP" in runner.DIAGNOSTIC_NOT_KEEP_DROP
    assert "vs_flat_dca_pct" in runner.DIAGNOSTIC_NOT_KEEP_DROP
    assert "IN-SAMPLE" in runner.IN_SAMPLE_LABEL
