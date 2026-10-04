"""Gold indicator weights fitted against BOTH approved gold pin sets (#4804).

Plan 22's last piece. ``digiquant/scripts/run_gold_pin_set_fits.py`` runs the
**frozen** Plan-19 harness (``fit_gold_indicators.py``: every grid, the
``mean(trough) - mean(peak)`` separation, the 0.06 dead zone, the ±45d windows,
the greedy equal-weight selection) twice — once against ``gold_v1()`` (Set A's
six hand-approved pins) and once against ``gold_v2()`` (the 20 algorithmic turns
at 15%) — and compares them.

What is pinned here, and why each pin can fail:

1. **The frozen harness is imported, not restated, and not re-run on import.**
   The grids, the 0.5 capture bar and the 0.06 dead zone are the *objects* the
   runner re-exports (identity, not equality: a restated literal that happens to
   match today would drift the day a knob moves), and loading the harness by file
   path must write nothing.
2. **The pin-set registry is exactly the two approved gold factories**, resolved
   from the shipped ``SdcaCycleWindows`` — and the set-inclusion the report
   leans on (``gold_v1`` ⊆ ``gold_v2``, same turns AND same kinds) is asserted
   here, so "v2 is a strict refinement, not a rival target" cannot rot silently.
3. **Window-day share counts a day inside ANY window once.** ``gold_v2()`` has
   two overlapping window pairs, so a share that double-counts overlaps would
   report a set bigger than the calendar; the overlap is in the fixture rather
   than assumed away.
4. **The capture read follows Engine 2b Ruling 2**: the row that speaks for an
   indicator is the largest ``|separation|`` in the grid, direction is FITTED from
   its sign, and capture is ``|separation| >= CAPTURE_BAR`` (inclusive) and not
   degenerate. Each conjunct is pinned separately — including that a 3.0-deep
   DEGENERATE row still does not capture, and that an unscoreable leg carries no
   direction rather than a defaulted one.
5. **Depth, not headcount, decides which set the indicators fit better** (the
   owner's frozen ranking key, applied across pin sets instead of across
   granularities), with the coarser pin set taking a depth tie — the same
   robustness tie-break Engine 2b uses across ``min_move_pct``.
6. **Only a change of VERDICT counts as a flip.** An indicator whose separation
   moved a lot but still votes the same way and captures (or still does not) is
   not a flip, and one that loses capture is named — so the report's flip list
   cannot be inflated by noise.

The comparison table is built for every fitted indicator against both sets and
must line up key-for-key; a missing or extra indicator is an error, not a blank
cell. Nothing here reads the price history: every read is a synthetic row, so
the pins are about the RULES.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from digiquant.strategies.sdca.cycle_windows import CycleKind, CycleWindow, SdcaCycleWindows
from digiquant.strategies.sdca.sensitivity_consolidate import (
    CAPTURE_BAR,
    IndicatorCaptureRow,
)

REPO = Path(__file__).resolve().parents[4]
RUNNER_PATH = REPO / "digiquant" / "scripts" / "run_gold_pin_set_fits.py"
HARNESS_PATH = REPO / "digiquant" / "scripts" / "fit_gold_indicators.py"
FITS_JSON = REPO / "digiquant" / ".scratch" / "gold_indicator_fits.json"


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner() -> Any:
    return _load(RUNNER_PATH, "run_gold_pin_set_fits")


def _row(
    name: str,
    separation: float | None,
    *,
    window_days: int = 378,
    mean_peak_z: float | None = -0.5,
    mean_trough_z: float | None = 0.5,
    coverage: float = 1.0,
    scored_days: int = 100,
    status: str = "scored",
    reason: str | None = None,
) -> IndicatorCaptureRow:
    return IndicatorCaptureRow(
        name=name,
        params={"window": window_days},
        window_days=window_days,
        separation=separation,
        mean_peak_z=mean_peak_z,
        mean_trough_z=mean_trough_z,
        peak_negative_share=0.5 if separation is not None else None,
        trough_positive_share=0.5 if separation is not None else None,
        zero_z_share=0.0 if separation is not None else None,
        # The model refuses a degenerate flag the frozen rule contradicts, so the
        # dead-side cases are built by their MEANS, never by passing True.
        degenerate=(False if separation is None else abs(0.5) <= 0.06 or abs(-0.5) <= 0.06),
        coverage=coverage,
        scored_days=scored_days,
        status=status,
        reason=reason,
    )


def _dead_row(name: str, separation: float, *, window_days: int = 378) -> IndicatorCaptureRow:
    """A deep row whose PEAK side sits inside the frozen dead zone."""
    return IndicatorCaptureRow(
        name=name,
        params={"window": window_days},
        window_days=window_days,
        separation=separation,
        mean_peak_z=0.0,
        mean_trough_z=1.0,
        peak_negative_share=0.0,
        trough_positive_share=1.0,
        zero_z_share=0.0,
        degenerate=True,
        coverage=1.0,
        scored_days=100,
        status="scored",
    )


# --------------------------------------------------------------------------- #
# 1. The frozen harness is imported, not restated
# --------------------------------------------------------------------------- #


def test_the_frozen_knobs_are_the_harness_objects_not_a_restatement(runner: Any) -> None:
    # The runner's OWN harness instance — the one its re-exports came from.
    harness = runner.load_harness()
    assert harness is sys.modules["fit_gold_indicators"], "one harness instance, not a second"
    assert runner.CAPTURE_BAR == 0.5
    assert runner.CAPTURE_BAR == CAPTURE_BAR
    # The two frozen modules each own a DEGENERATE_MEAN_ABS literal; they must AGREE.
    assert runner.DEGENERATE_MEAN_ABS == harness.DEGENERATE_MEAN_ABS == 0.06
    # Identity, not equality: a restated literal would be a second thing to forget.
    assert runner.LEVEL_WINDOWS is harness.LEVEL_WINDOWS
    assert runner.ROC_DAYS is harness.ROC_DAYS
    assert runner.ROC_WINDOWS is harness.ROC_WINDOWS
    assert runner.RSI_LENGTHS is harness.RSI_LENGTHS
    assert runner.MACD_SPANS is harness.MACD_SPANS
    assert runner.MACD_Z_WINDOWS is harness.MACD_Z_WINDOWS
    assert runner.SMA_BAND_WINDOWS is harness.SMA_BAND_WINDOWS
    assert runner.SMA_BAND_MIN_SAMPLES is harness.SMA_BAND_MIN_SAMPLES
    assert runner.MEDIUM_WINDOW_MAX == harness.MEDIUM_WINDOW_MAX
    assert runner.LONG_WINDOW_MIN == harness.LONG_WINDOW_MIN
    assert runner.ANCHOR_NAME == harness.ANCHOR_NAME
    assert runner.EQUAL_WEIGHT == harness.EQUAL_WEIGHT


def test_loading_the_frozen_harness_runs_nothing_at_module_level(runner: Any) -> None:
    """The single-set run must stay reproducible, so the harness must not run on import."""
    module = runner.load_harness()
    assert callable(module.run_fit) and callable(module.run_selection)
    if not FITS_JSON.exists():
        pytest.skip("no fits artifact present; the side-effect probe has nothing to watch")
    digest = hashlib.sha256(FITS_JSON.read_bytes()).hexdigest()
    _load(HARNESS_PATH, "fit_gold_indicators_side_effect_probe")
    assert hashlib.sha256(FITS_JSON.read_bytes()).hexdigest() == digest


# --------------------------------------------------------------------------- #
# 2. The pin-set registry
# --------------------------------------------------------------------------- #


def test_the_registry_is_exactly_the_two_approved_gold_factories(runner: Any) -> None:
    assert [label for label, _ in runner.PIN_SETS] == ["gold_v1", "gold_v2"]
    assert runner.pin_set("gold_v1").windows == SdcaCycleWindows.gold_v1().windows
    assert runner.pin_set("gold_v2").windows == SdcaCycleWindows.gold_v2().windows
    with pytest.raises(KeyError):
        runner.pin_set("gold_v3")


def test_set_a_is_a_subset_of_the_algorithmic_set_with_the_same_kind(runner: Any) -> None:
    """The relation the comparison rests on: v2 REFINES v1, it does not rival it."""
    v1 = {(w.start, w.end, w.kind) for w in runner.pin_set("gold_v1").windows}
    v2 = {(w.start, w.end, w.kind) for w in runner.pin_set("gold_v2").windows}
    assert v1 < v2, "gold_v1 must be a PROPER subset: every Set A turn, same kind, plus extras"
    assert len(v1) == 6  # Set A is six pins, and the strictness must be real
    assert len(v2) == 20


# --------------------------------------------------------------------------- #
# 3. Window-day share
# --------------------------------------------------------------------------- #


def _windows(*spans: tuple[str, str, CycleKind]) -> SdcaCycleWindows:
    return SdcaCycleWindows(
        windows=tuple(
            CycleWindow(
                name=name, kind=kind, start=date.fromisoformat(a), end=date.fromisoformat(b)
            )
            for name, a, b, kind in spans
        )
    )


def test_window_day_share_counts_an_overlapping_day_once(runner: Any) -> None:
    windows = _windows(
        ("early", "2020-01-01", "2020-03-01", CycleKind.PEAK),
        ("late", "2020-02-01", "2020-04-01", CycleKind.TROUGH),
    )
    days = [date(2020, 1, 1) + timedelta(days=offset) for offset in range(92)]  # 2020-01-01..04-01
    share = runner.window_day_share(days, windows)
    # Jan 1..Apr 1 inclusive = 92 days. The Feb overlap is 29 days and is counted ONCE.
    assert share.window_days == 92
    assert share.calendar_days == 92
    assert share.overlap_days == 30, "Feb 1 .. Mar 1 inclusive is 30 days, counted ONCE"
    assert share.share == pytest.approx(1.0)


def test_window_day_share_excludes_days_outside_every_window(runner: Any) -> None:
    windows = _windows(("only", "2020-01-10", "2020-01-20", CycleKind.PEAK))
    days = [date(2020, 1, 1) + timedelta(days=offset) for offset in range(31)]
    share = runner.window_day_share(days, windows)
    assert share.window_days == 11  # Jan 10..20 inclusive
    assert share.calendar_days == 31
    assert share.overlap_days == 0
    assert share.share == pytest.approx(11 / 31)


# --------------------------------------------------------------------------- #
# 4. The capture read (Engine 2b Ruling 2, unchanged)
# --------------------------------------------------------------------------- #


def test_the_speaking_row_is_the_largest_magnitude_and_its_direction_is_fitted(
    runner: Any,
) -> None:
    rows = [
        _row("uup", 0.6, window_days=378),
        _row("uup", -1.2, window_days=90),
        _row("uup", -0.9, window_days=756),
    ]
    read = runner.capture_read("uup", rows)
    assert read.window_days == 90
    assert read.separation == pytest.approx(-1.2)
    assert read.direction == -1, "the sign of the winning row is the FITTED direction"
    assert read.captures is True
    assert read.abs_separation == pytest.approx(1.2)
    assert read.degenerate is False


def test_the_bar_is_inclusive_at_exactly_the_frozen_value(runner: Any) -> None:
    at_bar = runner.capture_read("edge", [_row("edge", 0.5)])
    under = runner.capture_read("edge", [_row("edge", 0.4999)])
    assert at_bar.captures is True
    assert under.captures is False


def test_a_deep_but_one_sided_row_does_not_capture_however_deep(runner: Any) -> None:
    read = runner.capture_read("walcl", [_dead_row("walcl", -3.0)])
    assert read.abs_separation == pytest.approx(3.0)
    assert read.degenerate is True
    assert read.captures is False, "a pass resting on a dead side is not a pass"


def test_an_unscoreable_indicator_has_no_direction_and_no_capture(runner: Any) -> None:
    read = runner.capture_read(
        "hy_oas",
        [_row("hy_oas", None, status="unscoreable", reason="starts after every window")],
    )
    assert read.separation is None
    assert read.direction is None, "nothing was scored, so no direction is fitted"
    assert read.captures is False
    assert read.reason == "starts after every window"


def test_a_magnitude_tie_resolves_to_the_shorter_window(runner: Any) -> None:
    read = runner.capture_read(
        "nfci", [_row("nfci", 1.0, window_days=756), _row("nfci", -1.0, window_days=180)]
    )
    assert read.window_days == 180


# --------------------------------------------------------------------------- #
# 5. The capture summary and which set fits better
# --------------------------------------------------------------------------- #


def test_capture_summary_sums_depth_over_capturing_legs_only_and_counts_the_sign_mix(
    runner: Any,
) -> None:
    reads = [
        runner.capture_read("real_rate", [_row("real_rate", 3.0)]),
        runner.capture_read("uup", [_row("uup", -1.1, window_days=90)]),
        runner.capture_read("walcl", [_row("walcl", 0.2)]),
        runner.capture_read("gvz", [_dead_row("gvz", 2.0)]),
    ]
    summary = runner.capture_summary(reads)
    assert summary.capture_count == 2
    assert summary.capture_depth == pytest.approx(3.0 + 1.1)
    assert (summary.expected_sign_count, summary.inverted_sign_count) == (1, 1)
    assert summary.non_capturing == ("walcl", "gvz"), "input order, never re-sorted"


def test_depth_beats_headcount_when_choosing_the_set_that_fits_better(runner: Any) -> None:
    """The owner's ranking key: fewer but deeper captures wins over more but shallow."""
    few_deep = runner.capture_summary(
        [
            runner.capture_read("a", [_row("a", 3.0)]),
            runner.capture_read("b", [_row("b", -2.0)]),
        ]
    )
    many_shallow = runner.capture_summary(
        [
            runner.capture_read("a", [_row("a", 0.6)]),
            runner.capture_read("b", [_row("b", 0.6)]),
            runner.capture_read("c", [_row("c", 0.6)]),
            runner.capture_read("d", [_row("d", 0.6)]),
        ]
    )
    # second is the challenger, so the margin is signed second - first.
    verdict = runner.fits_better(("gold_v2", few_deep), ("gold_v1", many_shallow))
    assert verdict.better_label == "gold_v2"
    assert "capture_depth 2.4000 < 5.0000 (-2.6000)" in verdict.reason
    assert verdict.depth_margin == pytest.approx(2.4 - 5.0)
    assert verdict.count_margin == 4 - 2
    assert verdict.tied is False


def test_a_depth_tie_prefers_the_coarser_pin_set(runner: Any) -> None:
    reads = [runner.capture_read("a", [_row("a", 1.0)])]
    v1 = runner.capture_summary(reads)
    v2 = runner.capture_summary(reads)
    verdict = runner.fits_better(("gold_v2", v2), ("gold_v1", v1))
    assert verdict.tied is True
    assert verdict.better_label == "gold_v1", "a tie goes to the FEWER pins (more robust)"
    assert verdict.depth_margin == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# 6. The comparison table and the flip list
# --------------------------------------------------------------------------- #


def _both_sets(runner: Any, *, uup_v1: float, uup_v2: float) -> dict[str, dict[str, Any]]:
    """uup's two separations move; nfci captures in BOTH sets so it is never a flip."""
    return {
        "gold_v1": {
            "uup": runner.capture_read("uup", [_row("uup", uup_v1, window_days=90)]),
            "nfci": runner.capture_read("nfci", [_row("nfci", 1.4)]),
        },
        "gold_v2": {
            "uup": runner.capture_read("uup", [_row("uup", uup_v2, window_days=756)]),
            "nfci": runner.capture_read("nfci", [_row("nfci", 0.6)]),
        },
    }


def test_the_comparison_table_lines_up_key_for_key_and_names_every_indicator(
    runner: Any,
) -> None:
    sets = _both_sets(runner, uup_v1=-1.2, uup_v2=-0.9)
    rows = runner.comparison_rows(sets)
    assert [row.name for row in rows] == ["uup", "nfci"], "frozen indicator order, not dict order"
    for row in rows:
        assert row.by_set["gold_v1"] is not None and row.by_set["gold_v2"] is not None
    uup = next(row for row in rows if row.name == "uup")
    assert uup.by_set["gold_v1"].captures and uup.by_set["gold_v2"].captures


def test_only_a_changed_capture_or_direction_counts_as_a_flip(runner: Any) -> None:
    # uup keeps its direction but drops under the bar; nfci keeps capturing with
    # a much smaller separation. Neither is a verdict flip.
    quiet = runner.verdict_flips(_both_sets(runner, uup_v1=-1.2, uup_v2=-0.9))
    assert quiet == []

    # Now uup flips direction (inverted at v1, expected at v2): a real flip.
    flipped = runner.verdict_flips(
        {
            "gold_v1": {
                "uup": runner.capture_read("uup", [_row("uup", -1.2, window_days=90)]),
                "nfci": runner.capture_read("nfci", [_row("nfci", 1.4)]),
            },
            "gold_v2": {
                "uup": runner.capture_read("uup", [_row("uup", 0.9, window_days=756)]),
                "nfci": runner.capture_read("nfci", [_row("nfci", 0.6)]),
            },
        }
    )
    assert [entry["name"] for entry in flipped] == ["uup"]
    assert "direction" in flipped[0]["changes"]
    assert flipped[0]["gold_v1_direction"] == -1
    assert flipped[0]["gold_v2_direction"] == 1


def test_a_lost_capture_is_named_as_a_flip_too(runner: Any) -> None:
    flips = runner.verdict_flips(_both_sets(runner, uup_v1=-1.2, uup_v2=-0.3))
    assert [entry["name"] for entry in flips] == ["uup"]
    assert "captures" in flips[0]["changes"]
    assert (flips[0]["gold_v1_captures"], flips[0]["gold_v2_captures"]) == (True, False)


def test_an_indicator_missing_from_one_set_is_an_error_not_a_blank_cell(runner: Any) -> None:
    sets = _both_sets(runner, uup_v1=-1.2, uup_v2=-0.9)
    del sets["gold_v2"]["uup"]
    with pytest.raises(ValueError, match="uup"):
        runner.comparison_rows(sets)
