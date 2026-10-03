"""Tests for the generic sensitivity-consolidation rule (#4804, Plan 22, Engine 2).

The owner's Engine-2 objective: *find the most sensitive granularity the fitted
indicators can still capture*. The sensitivity crank is ``min_move_pct`` — a
lower threshold yields more turns, hence a finer pin set and a harder scoring
target. Engine 1 already proved the crank is monotone in turn count
(``test_turn_detect.py``); what this module settles is **where the indicators
stop being able to see the turns**, so the pins are not chosen finer than the
evidence supports.

Pins that matter here, in order of importance:

- **The capture bar, and all three of its conjuncts** (a). Capture is
  ``separation >= 0.5`` AND sign-correct AND not degenerate. The bar boundary is
  inclusive at exactly 0.5; a negative separation never captures (``abs()`` is
  forbidden — that would reward a leg voting backwards); a one-sided pass
  (one window mean inside the +/-0.06 dead zone) never captures, however high
  its separation; an unscoreable leg never captures.
- **The choice: finest that does not lose** (b). A level qualifies when its
  capture count is at least as large as at EVERY coarser level, and the rule
  takes the most sensitive qualifier.
- **The coarser tie-break** (c). Two qualifying levels with the SAME capture
  count resolve to the coarser one — fewer turns, more robust. This is a real
  decision, not a formality: the gold ladder has three levels and equal counts
  are the likely case.
- **The dropped table** (d) — the owner's evidence. For each level FINER than the
  chosen one, every indicator that captured at the chosen level and fails there
  is reported with both separations and the reason it fails.
- **Refusals** (e): an empty ladder, two levels sharing a ``min_move_pct``
  ("coarser" would be ambiguous), and a ``degenerate`` flag that disagrees with
  the frozen dead-zone rule (a caller cannot smuggle a one-sided pass past the
  bar by mislabelling it).
- **Zero Nautilus** (f): the module is importable and pure, so the rule is
  reusable for any asset without the engine.

Every number below is synthetic and hand-built; nothing is copied from a run.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from digiquant.strategies.sdca.sensitivity_consolidate import (
    CAPTURE_BAR,
    DEGENERATE_MEAN_ABS,
    IndicatorCaptureRow,
    SensitivityLevelRow,
    row_is_degenerate,
    select_sensitivity_level,
)

pytestmark = pytest.mark.unit

MODULE_PATH = (
    Path(__file__).resolve().parents[4]
    / "digiquant"
    / "src"
    / "digiquant"
    / "strategies"
    / "sdca"
    / "sensitivity_consolidate.py"
)


def _row(
    name: str,
    separation: float | None,
    *,
    mean_peak_z: float | None = None,
    mean_trough_z: float | None = None,
    window_days: int = 378,
) -> IndicatorCaptureRow:
    """One indicator's best grid row at one level.

    By default the two window means split ``separation`` evenly, so the row is a
    clean pass consistent with its own numbers. A test that wants a dead side or
    a specific boundary passes the means explicitly; the model does not re-derive
    the separation from them.
    """
    if separation is not None:
        # Fill only the means the caller did not pin, so an override of one side
        # leaves the other a live value rather than None.
        mean_peak_z = -separation / 2.0 if mean_peak_z is None else mean_peak_z
        mean_trough_z = separation / 2.0 if mean_trough_z is None else mean_trough_z
    scored = separation is not None
    return IndicatorCaptureRow(
        name=name,
        params={"window": window_days},
        window_days=window_days,
        separation=separation,
        mean_peak_z=mean_peak_z,
        mean_trough_z=mean_trough_z,
        peak_negative_share=0.8 if scored else None,
        trough_positive_share=0.8 if scored else None,
        zero_z_share=0.0 if scored else None,
        degenerate=row_is_degenerate(
            separation=separation, mean_peak_z=mean_peak_z, mean_trough_z=mean_trough_z
        ),
        coverage=0.9 if scored else 0.0,
        scored_days=180 if scored else 0,
        status="scored" if scored else "unscoreable",
        reason=None if scored else "series starts after every window at this level",
    )


def _level(min_move_pct: float, rows: list[IndicatorCaptureRow]) -> SensitivityLevelRow:
    return SensitivityLevelRow(
        min_move_pct=min_move_pct,
        n_turns=int(20 / min_move_pct),
        n_peaks=int(10 / min_move_pct),
        n_troughs=int(10 / min_move_pct),
        window_day_share=0.2 * (20.0 / min_move_pct),
        indicators=tuple(rows),
    )


# --------------------------------------------------------------------------- #
# (a) the capture bar and its three conjuncts
# --------------------------------------------------------------------------- #


def test_capture_needs_the_bar_the_sign_and_a_live_side() -> None:
    level = _level(
        15.0,
        [
            _row("at_bar", CAPTURE_BAR),  # inclusive boundary
            _row("just_under", 0.4999),
            _row("high_but_dead_side", 0.9, mean_peak_z=0.0),
            _row("backwards", -0.9),
            _row("unscoreable", None),
        ],
    )
    assert level.capture_count == 1
    assert level.capturing == ("at_bar",)


def test_sign_correctness_is_never_replaced_by_magnitude() -> None:
    """A mirrored leg scores its exact negation; ``abs()`` would reward it."""
    row = _row("mirrored", -0.9)
    assert row.captures is False


def test_dead_zone_means_a_one_sided_pass_never_captures() -> None:
    dead = _row("dead_side", 3.0, mean_peak_z=0.0)
    assert dead.degenerate is True
    assert dead.captures is False
    # The dead-zone test is inclusive: a mean exactly at the edge is inside it.
    at_edge = _row("at_edge", 0.6, mean_peak_z=-DEGENERATE_MEAN_ABS, mean_trough_z=0.5)
    assert at_edge.degenerate is True
    assert at_edge.captures is False
    just_outside = _row(
        "just_outside",
        0.6,
        mean_peak_z=-DEGENERATE_MEAN_ABS - 1e-6,
        mean_trough_z=0.5,
    )
    assert just_outside.degenerate is False
    assert just_outside.captures is True


# --------------------------------------------------------------------------- #
# (b) the choice: the finest level that does not lose capture count
# --------------------------------------------------------------------------- #


def test_chooses_the_most_sensitive_level_when_every_finer_level_captures_more() -> None:
    ladder = [
        _level(15.0, [_row("a", 0.6), _row("b", -0.6)]),
        _level(10.0, [_row("a", 0.6), _row("b", 0.6)]),
        _level(5.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6), _row("d", 0.6)]),
    ]
    choice = select_sensitivity_level(ladder)
    assert choice.chosen_min_move_pct == 5.0
    assert choice.capture_count == 4
    assert choice.capturing_indicators == ("a", "b", "c", "d")


def test_refuses_a_finer_level_that_loses_capture_count() -> None:
    ladder = [
        _level(15.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6), _row("d", 0.6)]),
        _level(10.0, [_row("a", 0.6), _row("b", -0.6)]),
        _level(5.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6)]),
    ]
    choice = select_sensitivity_level(ladder)
    assert choice.chosen_min_move_pct == 15.0
    assert choice.capture_count == 4


def test_the_coarsest_level_always_qualifies() -> None:
    """It has nothing coarser to compare against, so a ladder is never undecidable."""
    ladder = [_level(15.0, [_row("a", 0.0)]), _level(5.0, [_row("a", 0.6)])]
    assert select_sensitivity_level(ladder).chosen_min_move_pct == 15.0


# --------------------------------------------------------------------------- #
# (c) the coarser tie-break
# --------------------------------------------------------------------------- #


def test_equal_capture_counts_resolve_to_the_coarser_level() -> None:
    ladder = [
        _level(15.0, [_row("a", 0.6), _row("b", 0.6)]),
        _level(10.0, [_row("a", 0.6), _row("b", 0.9)]),
        _level(5.0, [_row("a", 0.6), _row("b", 0.9), _row("c", -0.6)]),
    ]
    choice = select_sensitivity_level(ladder)
    # All three qualify (nothing loses) and all three capture 2, so the coarser
    # tie-break decides — the finest qualifying level is NOT taken.
    assert choice.chosen_min_move_pct == 15.0
    assert choice.capture_count == 2
    assert [entry.min_move_pct for entry in choice.dropped_at_finer_levels] == [10.0, 5.0]
    assert all(entry.qualifies for entry in choice.dropped_at_finer_levels)


# --------------------------------------------------------------------------- #
# (d) the dropped-at-finer table — the owner's evidence
# --------------------------------------------------------------------------- #


def test_reports_each_indicator_that_drops_at_a_finer_level() -> None:
    ladder = [
        _level(15.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6)]),
        _level(10.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6)]),
        _level(5.0, [_row("a", 0.6), _row("b", 0.21), _row("c", -0.8)]),
    ]
    choice = select_sensitivity_level(ladder)
    assert choice.chosen_min_move_pct == 15.0
    (finer,) = choice.dropped_at_finer_levels
    assert finer.min_move_pct == 10.0
    assert [drop.name for drop in finer.dropped] == []
    # 5% is only reported once 10% has already lost b and c.
    finests = choice.dropped_at_finer_levels[-1]
    assert finests.min_move_pct == 5.0
    assert [drop.name for drop in finests.dropped] == ["b", "c"]
    below = next(drop for drop in finests.dropped if drop.name == "b")
    assert below.separation_at_chosen_level == 0.6
    assert below.separation_at_finer_level == 0.21
    assert "0.5" in below.reason
    flipped = next(drop for drop in finests.dropped if drop.name == "c")
    assert flipped.separation_at_finer_level == -0.8
    assert "negative" in flipped.reason


def test_a_dead_side_drop_is_named_as_such() -> None:
    ladder = [
        _level(15.0, [_row("a", 0.6)]),
        _level(5.0, [_row("a", 0.6, mean_peak_z=0.0)]),
    ]
    choice = select_sensitivity_level(ladder)
    (drop,) = [d for entry in choice.dropped_at_finer_levels for d in entry.dropped]
    assert "degenerate" in drop.reason


def test_levels_are_ordered_coarse_to_fine_regardless_of_input_order() -> None:
    ladder = [
        _level(5.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6)]),
        _level(15.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6)]),
        _level(10.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6)]),
    ]
    choice = select_sensitivity_level(ladder)
    assert [row.min_move_pct for row in choice.level_rows] == [15.0, 10.0, 5.0]
    assert choice.chosen_min_move_pct == 15.0


# --------------------------------------------------------------------------- #
# (e) refusals
# --------------------------------------------------------------------------- #


def test_an_empty_ladder_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one level"):
        select_sensitivity_level([])


def test_two_levels_at_the_same_min_move_pct_are_refused() -> None:
    ladder = [_level(10.0, [_row("a", 0.6)]), _level(10.0, [_row("a", 0.6)])]
    with pytest.raises(ValueError, match="min_move_pct"):
        select_sensitivity_level(ladder)


def test_a_mislabelled_degenerate_flag_is_refused() -> None:
    """A caller cannot smuggle a one-sided pass past the bar by flagging it live."""
    fields = _row("honest", 0.9, mean_peak_z=0.0)
    assert fields.degenerate is True
    with pytest.raises(ValueError, match="degenerate"):
        IndicatorCaptureRow(
            **{
                **fields.model_dump(),
                "params": dict(fields.params),
                "degenerate": False,
            }
        )


def test_duplicate_indicator_names_in_one_level_are_refused() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        _level(15.0, [_row("a", 0.6), _row("a", 0.9)])


def test_peak_and_trough_counts_must_sum_to_the_turn_count() -> None:
    with pytest.raises(ValueError, match="n_turns"):
        SensitivityLevelRow(
            min_move_pct=15.0,
            n_turns=7,
            n_peaks=3,
            n_troughs=3,
            window_day_share=0.2,
            indicators=(_row("a", 0.6),),
        )


# --------------------------------------------------------------------------- #
# (f) zero Nautilus, zero pandas — the rule is pure and asset-agnostic
# --------------------------------------------------------------------------- #


def test_module_imports_no_engine_and_no_pandas() -> None:
    source = MODULE_PATH.read_text()
    banned = re.findall(r"^\s*(?:import|from)\s+(nautilus_trader|pandas)\b", source, re.MULTILINE)
    assert banned == []
    # Asset knowledge would make the rule non-generic.
    assert not re.search(r"\bGLD\b|\bgold\b|\bBTC\b", source, re.IGNORECASE)
