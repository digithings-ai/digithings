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
  its separation; an unscoreable leg never captures. 0.5 is the FROZEN DEFAULT,
  not a hard-wired constant: a bar the caller supplies must decide the verdict,
  the count, the choice and the drop reasons — never merely label them.
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
    CAPTURE_RULE,
    DEGENERATE_MEAN_ABS,
    IndicatorCaptureRow,
    SensitivityLevelRow,
    captures_level,
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


def test_the_caller_supplied_capture_bar_is_the_bar_the_choice_is_made_at() -> None:
    """``capture_bar`` decides; it is not just a label on a frozen 0.5 decision.

    The ladder's two rungs agree at the frozen bar — every leg clears 0.5 at both,
    so nothing is dropped — but they disagree at a caller-supplied 0.7: ``mid``
    (0.60) falls out of both levels and ``edge`` falls out of the finer one. So a
    choice made at 0.7 must (i) move a capture verdict, (ii) move the counts the
    choice is built from, and (iii) print the bar it actually used in the evidence
    it attaches — while the frozen default still decides at 0.5 and says so.
    """
    ladder = [
        _level(15.0, [_row("high", 0.9), _row("edge", 0.75), _row("mid", 0.6)]),
        _level(5.0, [_row("high", 0.9), _row("edge", 0.6), _row("mid", 0.55)]),
    ]
    coarse, fine = ladder

    # At the frozen bar: all three legs clear 0.5 at both rungs, so the choice ties
    # and the coarser tie-break takes 15% — and the finer rung costs nothing.
    at_frozen_bar = select_sensitivity_level(ladder)
    assert at_frozen_bar.capture_bar == CAPTURE_BAR
    assert at_frozen_bar.chosen_min_move_pct == 15.0
    assert at_frozen_bar.capture_count == 3
    assert at_frozen_bar.capturing_indicators == ("high", "edge", "mid")
    assert at_frozen_bar.dropped_at_finer_levels[0].capture_count == 3
    assert at_frozen_bar.dropped_at_finer_levels[0].dropped == ()

    # (i) The verdict is evaluated at the bar the caller asked for, not at the
    # frozen one. A level's own ``capturing`` stays the frozen-bar view; the
    # bar-aware view is what a choice at 0.7 is allowed to read.
    assert captures_level(_row("mid", 0.6)) is True  # clears the frozen 0.5
    assert captures_level(_row("mid", 0.6), capture_bar=0.7) is False
    assert coarse.capturing == ("high", "edge", "mid")
    assert coarse.capturing_at(0.7) == ("high", "edge")
    assert fine.capturing == ("high", "edge", "mid")
    assert fine.capturing_at(0.7) == ("high",)
    assert coarse.capture_count_at(0.7) == 2

    raised = select_sensitivity_level(ladder, capture_bar=0.7)
    # (ii) The count the choice is built from, and the sets behind it, are the
    # caller-supplied bar's — three captures become two, so the choice cannot be
    # 0.5's verdict wearing a 0.7 label.
    assert raised.capture_bar == 0.7
    assert raised.chosen_min_move_pct == 15.0
    assert raised.capture_count == 2
    assert raised.capturing_indicators == ("high", "edge")
    assert raised.non_capturing_indicators == ("mid",)

    # (iii) The evidence table is scored at the same bar, and its numbers are
    # consistent with it: `edge` is reported as dropped for falling short of 0.7,
    # never for falling short of a 0.5 it was never held to.
    (cost,) = raised.dropped_at_finer_levels
    assert cost.min_move_pct == 5.0
    assert cost.capture_count == 1
    assert [drop.name for drop in cost.dropped] == ["edge"]
    below = cost.dropped[0]
    assert below.separation_at_chosen_level == 0.75
    assert below.separation_at_finer_level == 0.6
    assert "+0.6000 < 0.7" in below.reason
    assert "0.5" not in below.reason
    # The rule the artifact carries names the bar it was decided at, and the
    # frozen text is still what a frozen-bar choice records.
    assert "0.7" in raised.capture_rule
    assert at_frozen_bar.capture_rule == CAPTURE_RULE


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
    # The counts are NOT monotone across the ladder — [4, 1, 3] — and 5% recovers
    # most of what 10% lost. That is what makes this fixture the ONLY one that can
    # tell "at least as many captures as at EVERY coarser level" from the weaker
    # "at least as many as at the immediately preceding level": 5% beats its direct
    # predecessor (3 > 1) but still loses to the coarsest rung (3 < 4). Both rungs
    # finer than the choice are therefore reported as NON-qualifying, and neither
    # `chosen` nor `capture_count` above can see the difference — only the flags
    # the ladder's finer rows carry.
    ten, five = choice.dropped_at_finer_levels
    assert ten.min_move_pct == 10.0
    assert ten.qualifies is False  # 1 capture against the coarsest rung's 4
    assert five.min_move_pct == 5.0
    assert five.qualifies is False  # 3 captures — above 10%'s 1, below 15%'s 4


def test_the_coarsest_level_does_not_win_when_a_finer_level_captures_more() -> None:
    """The coarsest rung always QUALIFIES; it does not always WIN.

    Corrected as unsatisfiable (2026-10-03, #4804). This pin used to read
    ``assert select_sensitivity_level(ladder).chosen_min_move_pct == 15.0`` against
    capture counts ``[0, 1]`` — that is not the owner-ruled choice, which takes the
    most sensitive QUALIFIER: a strictly larger count at a finer level must beat
    the coarsest, exactly as pins (b) and (c) do. So the pin now asserts what the
    rule actually decides, and the coarsest rung's real property stays in the
    prose: it has nothing coarser to lose against, so it is always a candidate and
    a ladder is therefore never undecidable.

    The fixture deliberately keeps STRICTLY UNEQUAL counts (0 captures at 15%, 1 at
    5%), so no tie-break is in play and the choice must be the finer qualifier.
    """
    ladder = [_level(15.0, [_row("a", 0.0)]), _level(5.0, [_row("a", 0.6)])]
    choice = select_sensitivity_level(ladder)
    # Both rungs are read, coarsest first — the coarsest is weighed, not discarded.
    assert [level.min_move_pct for level in choice.level_rows] == [15.0, 5.0]
    # 5% captures strictly more (1 vs 0), so the most sensitive qualifier wins and
    # the coarsest rung does not get the choice by default.
    assert choice.chosen_min_move_pct == 5.0
    assert choice.capture_count == 1
    assert choice.capturing_indicators == ("a",)
    # Nothing is finer than the chosen rung, so no finer level is charged for it.
    assert choice.dropped_at_finer_levels == ()


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
    """One row per level FINER than the chosen one; each drop names its indicator.

    Corrected as unsatisfiable (2026-10-03, #4804). The pin used to unpack a single
    row — ``(finer,) = choice.dropped_at_finer_levels`` — assert that same object was
    ``min_move_pct == 10.0``, and then take ``choice.dropped_at_finer_levels[-1]``,
    i.e. the SAME object again, and assert ``min_move_pct == 5.0``. One object cannot
    be both, and the unpack also pinned a table length of 1 while this ladder has two
    levels finer than the chosen 15%. The table has one row per finer level, coarsest
    finer first, which is what this pin now reads.
    """
    ladder = [
        _level(15.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6)]),
        _level(10.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6)]),
        _level(5.0, [_row("a", 0.6), _row("b", 0.21), _row("c", -0.8)]),
    ]
    choice = select_sensitivity_level(ladder)
    assert choice.chosen_min_move_pct == 15.0
    # Every level FINER than the chosen one is reported, coarsest finer first — the
    # chosen 15% itself is not a row of its own cost.
    table = choice.dropped_at_finer_levels
    assert [entry.min_move_pct for entry in table] == [10.0, 5.0]
    assert all(entry.min_move_pct < choice.chosen_min_move_pct for entry in table)
    finer_qualifier, finer_cost = table
    # 10% still captures all three and loses nothing, so it qualifies and its drop
    # list is empty: being finer than the choice is not by itself a drop.
    assert finer_qualifier.capture_count == 3
    assert finer_qualifier.qualifies is True
    assert [drop.name for drop in finer_qualifier.dropped] == []
    # 5% is where the evidence runs out: b and c captured at the chosen 15% and fail
    # here, so naming them is what this level costs. a still captures, so it is not
    # reported as a drop.
    assert finer_cost.capture_count == 1
    assert finer_cost.qualifies is False
    assert [drop.name for drop in finer_cost.dropped] == ["b", "c"]
    below = next(drop for drop in finer_cost.dropped if drop.name == "b")
    # Both separations are the fixture's own numbers: 0.6 is where b captured at the
    # chosen level, 0.21 is the same leg at this finer one — short of the bar.
    assert below.separation_at_chosen_level == 0.6
    assert below.separation_at_finer_level == 0.21
    assert "0.5" in below.reason
    flipped = next(drop for drop in finer_cost.dropped if drop.name == "c")
    # c's chosen-level separation is the 0.6 it captured at; here the vote flipped,
    # and the reason says so rather than crediting the magnitude.
    assert flipped.separation_at_chosen_level == 0.6
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
