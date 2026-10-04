"""Tests for the generic sensitivity-consolidation rule (#4804, Plan 22, Engine 2).

The owner's Engine-2 objective: *find the most sensitive granularity the fitted
indicators can still capture*. The sensitivity crank is ``min_move_pct`` — a
lower threshold yields more turns, hence a finer pin set and a harder scoring
target. Engine 1 already proved the crank is monotone in turn count
(``test_turn_detect.py``); what this module settles is **where the indicators
stop being able to see the turns**, so the pins are not chosen finer than the
evidence supports.

Pins that matter here, in order of importance:

- **Grid-row selection (a).** The row that speaks for an indicator at a level is
  the one maximising ``|separation|`` — polarity is not a selection constraint.
  Selection belongs to the module, not the caller.
- **The capture bar, and its two conjuncts** (b). Capture is
  ``abs(separation) >= 0.5`` AND not degenerate. The bar boundary is inclusive at
  exactly 0.5; a one-sided pass (one window mean inside the +/-0.06 dead zone)
  never captures, however high its separation; an unscoreable leg never captures.
  0.5 is the FROZEN DEFAULT, not a hard-wired constant: a bar the caller supplies
  must decide the verdict, the count, the choice and the drop reasons — never
  merely label them.
  **``abs()`` IS applied to the bar.** This REVERSES the earlier "``abs()`` is
  forbidden" rule and its pin below is inverted accordingly: that rule only made
  sense while the polarity was *imposed*, and with direction fitted a mirrored
  leg is evidence about the pin set rather than a mistake in it.
- **Fitted direction, per indicator** (c). ``direction`` is ``+1`` (expected
  polarity) or ``-1`` (inverted), read off the sign of the selected row, and it
  is RECORDED: on the row, on every level summary and on the choice, plus a
  per-level sign mix (how many captures are inverted vs expected), because that
  mix is the owner's read on whether a level is macro-led.
- **Direction stability** (d). An indicator capturing at MORE THAN ONE level must
  carry the SAME fitted direction at every level where it captures. A flip is
  flagged ``direction_unstable``, captures NOWHERE, and the flip is recorded as
  evidence. A single-level capture has no stability obligation. All three cases
  are pinned.
- **The choice: the finest that does not lose, ranked by DEPTH** (e). A level
  qualifies when its capture count is at least as large as at EVERY coarser
  level; among qualifiers the LARGEST ``capture_depth`` (the sum of the
  capturing indicators' ``|separation|``) wins. The capture count is reported
  but is **no longer the ranking key** — headcount cannot tell a vote held from
  conviction from one held by 0.0042, and a knife-edge indicator must not be
  able to hand the decision to a different granularity.
- **The coarser tie-break** (c/e) — equal ``capture_depth`` resolves to the
  coarser level: fewer turns, more robust.
- **The dropped table** (f) — the owner's evidence. For each level FINER than the
  chosen one, every indicator that captured at the chosen level and fails there
  is reported with both separations and the reason it fails.
- **Refusals** (g): an empty ladder, two levels sharing a ``min_move_pct``
  ("coarser" would be ambiguous), a duplicated grid cell in one level, and a
  ``degenerate`` flag that disagrees with the frozen dead-zone rule (a caller
  cannot smuggle a one-sided pass past the bar by mislabelling it).
- **Zero Nautilus** (h): the module is importable and pure, so the rule is
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
    best_grid_row,
    captures_level,
    fitted_direction,
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
    params: dict[str, int] | None = None,
) -> IndicatorCaptureRow:
    """One scored grid row of one indicator at one level.

    By default the two window means split ``separation`` evenly, so the row is a
    clean pass consistent with its own numbers. A test that wants a dead side or
    a specific boundary passes the means explicitly; the model does not re-derive
    the separation from them.

    ``window_days`` is also the parsimony tie-break for grid-row selection, so a
    fixture with several rows per indicator gives them distinct windows.
    """
    if separation is not None:
        # Fill only the means the caller did not pin, so an override of one side
        # leaves the other a live value rather than None.
        mean_peak_z = -separation / 2.0 if mean_peak_z is None else mean_peak_z
        mean_trough_z = separation / 2.0 if mean_trough_z is None else mean_trough_z
    scored = separation is not None
    return IndicatorCaptureRow(
        name=name,
        params={"window": window_days} if params is None else params,
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
# (a) grid-row selection: maximise |separation|, in the module
# --------------------------------------------------------------------------- #


def test_grid_row_selection_maximises_absolute_separation() -> None:
    """The speaking row is the deepest one, not the most positive one.

    This is the reversal that opens the whole fitted-direction ruling up: a leg
    whose grid contains both a +0.70 row and a -1.20 row speaks through the
    -1.20 one, because the ruling keys selection on magnitude and reads the
    polarity off the winner afterwards. Selecting on the signed separation would
    hand the leg a shallower row and record a different direction for the same
    indicator.
    """
    rows = [_row("macro", 0.70, window_days=252), _row("macro", -1.20, window_days=756)]
    assert best_grid_row(rows).separation == -1.20
    assert best_grid_row(rows).window_days == 756
    assert best_grid_row(rows).direction == -1
    # Order of the input cannot matter: selection is on the number, not on
    # whichever row the caller happened to list first.
    assert best_grid_row(list(reversed(rows))).window_days == 756


def test_grid_row_selection_breaks_a_magnitude_tie_to_the_shorter_window() -> None:
    """The harness parsimony rule survives into the selection: shorter window wins a tie."""
    rows = [_row("macro", 1.0, window_days=756), _row("macro", -1.0, window_days=378)]
    # A magnitude tie between an expected-polarity and an inverted row still
    # resolves to the shorter window — the direction is a consequence of the
    # selection, never a constraint on it.
    assert best_grid_row(rows).window_days == 378
    assert best_grid_row(rows).direction == -1


def test_a_level_reads_each_indicator_through_its_selected_row() -> None:
    """The level's selected rows are what every count on it is built from."""
    level = _level(
        15.0,
        [
            _row("macro", 0.70, window_days=252),
            _row("macro", -1.20, window_days=756),
            _row("value", 0.60, window_days=378),
        ],
    )
    assert [row.name for row in level.best_rows] == ["macro", "value"]
    assert level.row_for("macro").separation == -1.20
    assert level.row_for("absent") is None
    # -1.20 clears the bar on magnitude, so the inverted leg captures.
    assert level.capture_count == 2
    assert level.capturing == ("macro", "value")


def test_an_indicator_with_no_scored_row_stays_listed_as_unscoreable() -> None:
    level = _level(15.0, [_row("dead_source", None, window_days=252)])
    (best,) = level.best_rows
    assert best.name == "dead_source"
    assert best.separation is None
    assert best.direction is None
    assert level.capturing == ()
    assert level.capture_count == 0


# --------------------------------------------------------------------------- #
# (b) the capture bar and its two conjuncts
# --------------------------------------------------------------------------- #


def test_capture_needs_the_bar_and_a_live_side() -> None:
    level = _level(
        15.0,
        [
            _row("at_bar", CAPTURE_BAR),  # inclusive boundary
            _row("just_under", 0.4999),
            _row("high_but_dead_side", 0.9, mean_peak_z=0.0),
            _row("inverted_at_bar", -CAPTURE_BAR),  # |separation| clears the bar
            _row("unscoreable", None),
        ],
    )
    assert level.capture_count == 2
    assert level.capturing == ("at_bar", "inverted_at_bar")


def test_magnitude_may_rescue_an_inverted_leg_and_the_direction_is_recorded() -> None:
    """The reversed pin: ``abs()`` is now applied to the bar, and the polarity is recorded.

    The earlier pin here asserted the opposite — that a mirrored leg "scores its
    exact negation; ``abs()`` would reward it". That was correct only while the
    polarity was *imposed*, and the owner has since ruled that direction is
    FITTED per indicator rather than required. So the mirrored leg now captures on
    its magnitude, and the honest replacement for "refuse it" is "say which way
    it votes": a shallow mirrored leg still fails, and a deep one is recorded as
    inverted.
    """
    deep_mirrored = _row("mirrored", -0.90)
    assert deep_mirrored.captures is True
    assert deep_mirrored.direction == -1
    # Magnitude is still the bar: a mirrored leg that is merely shallow fails.
    shallow_mirrored = _row("shallow_mirrored", -0.49)
    assert shallow_mirrored.captures is False
    assert shallow_mirrored.direction == -1
    # And the rule string says so, so the artifact cannot ship the old wording.
    assert "abs() IS applied to the bar" in CAPTURE_RULE
    assert "REVERSES" in CAPTURE_RULE


def test_dead_zone_means_a_one_sided_pass_never_captures() -> None:
    dead = _row("dead_side", 3.0, mean_peak_z=0.0)
    assert dead.degenerate is True
    assert dead.captures is False
    # An inverted leg is no exemption from the dead zone: whichever way it votes,
    # a pass resting on a silent side is one-sided.
    dead_inverted = _row("dead_inverted", -3.0, mean_peak_z=0.0)
    assert dead_inverted.captures is False
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

    # At the frozen bar: all three legs clear 0.5 at both rungs, so the choice is
    # settled on depth (2.25 vs 2.05) and the finer rung costs nothing.
    at_frozen_bar = select_sensitivity_level(ladder)
    assert at_frozen_bar.capture_bar == CAPTURE_BAR
    assert at_frozen_bar.chosen_min_move_pct == 15.0
    assert at_frozen_bar.capture_count == 3
    assert at_frozen_bar.capture_depth == pytest.approx(0.9 + 0.75 + 0.6)
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
    assert raised.capture_depth == pytest.approx(0.9 + 0.75)
    assert raised.capturing_indicators == ("high", "edge")
    assert raised.non_capturing_indicators == ("mid",)

    # (iii) The evidence table is scored at the same bar, and its numbers are
    # consistent with it: `edge` is reported as dropped for falling short of 0.7,
    # never for falling short of a 0.5 it was never held to.
    (cost,) = raised.dropped_at_finer_levels
    assert cost.min_move_pct == 5.0
    assert cost.capture_count == 1
    assert cost.capture_depth == pytest.approx(0.9)
    assert [drop.name for drop in cost.dropped] == ["edge"]
    below = cost.dropped[0]
    assert below.separation_at_chosen_level == 0.75
    assert below.separation_at_finer_level == 0.6
    # The bar is compared on |separation| now, with the signed read and the fitted
    # direction printed alongside so the polarity is never lost from the evidence.
    assert "0.6000 < 0.7" in below.reason
    assert "+0.6000" in below.reason
    assert "0.5" not in below.reason
    # The rule the artifact carries names the bar it was decided at, and the
    # frozen text is still what a frozen-bar choice records.
    assert "0.7" in raised.capture_rule
    assert at_frozen_bar.capture_rule == CAPTURE_RULE


# --------------------------------------------------------------------------- #
# (c) fitted direction, recorded per indicator and per level
# --------------------------------------------------------------------------- #


def test_direction_is_fitted_from_the_sign_and_recorded_on_the_row() -> None:
    assert fitted_direction(1.4) == 1
    assert fitted_direction(-1.4) == -1
    assert fitted_direction(None) is None
    # Exactly zero has no sign to fit. It can never clear a positive bar, so the
    # value never reaches a verdict — it is reported, not smuggled into one.
    assert fitted_direction(0.0) == 0
    assert _row("zero", 0.0).direction == 0
    assert _row("zero", 0.0).captures is False
    assert _row("unscoreable", None).direction is None


def test_the_chosen_level_reports_its_depth_count_and_sign_mix() -> None:
    ladder = [
        _level(15.0, [_row("expected_a", 0.6), _row("expected_b", 0.9), _row("inverted", -0.8)]),
        _level(5.0, [_row("expected_a", 0.6), _row("expected_b", 0.5), _row("inverted", -0.4)]),
    ]
    choice = select_sensitivity_level(ladder)
    assert choice.chosen_min_move_pct == 15.0
    # The sign mix is reported because it is the owner's read on whether a level
    # is macro-led: one of three captures votes the other way round.
    assert choice.expected_direction_count == 2
    assert choice.inverted_direction_count == 1
    assert choice.capture_depth == pytest.approx(0.6 + 0.9 + 0.8)
    assert choice.direction_unstable == ()
    for check in choice.direction_checks:
        assert check.stable is True
        assert check.note.startswith("direction ")


def test_the_sign_mix_is_reported_on_every_level_summary() -> None:
    ladder = [
        _level(15.0, [_row("macro", -1.2), _row("value", 0.6)]),
        _level(5.0, [_row("macro", -0.6), _row("value", 0.6), _row("extra", 0.6)]),
    ]
    choice = select_sensitivity_level(ladder)
    summaries = {summary.min_move_pct: summary for summary in choice.level_summaries}
    # 15% holds one inverted leg and one expected one; 5% holds one inverted and
    # two expected. macro clears the bar at both levels with the SAME sign, so it
    # is stable and captures at both.
    assert summaries[15.0].expected_direction_count == 1
    assert summaries[15.0].inverted_direction_count == 1
    assert summaries[5.0].expected_direction_count == 2
    assert summaries[5.0].inverted_direction_count == 1
    assert summaries[15.0].capturing == ("macro", "value")
    assert summaries[5.0].capturing == ("macro", "value", "extra")


# --------------------------------------------------------------------------- #
# (d) direction stability — stable, flipping, single-level
# --------------------------------------------------------------------------- #


def test_a_direction_stable_indicator_captures_at_every_level_it_clears() -> None:
    ladder = [
        _level(15.0, [_row("macro", -1.20), _row("value", 0.60)]),
        _level(10.0, [_row("macro", -0.90), _row("value", 0.55)]),
        _level(5.0, [_row("macro", -0.70), _row("value", 0.45)]),
    ]
    choice = select_sensitivity_level(ladder)
    summaries = {summary.min_move_pct: summary for summary in choice.level_summaries}
    # macro is inverted at every level it clears, so it captures at all three and
    # is never vetoed. value falls short of the bar at 5% only.
    assert summaries[15.0].capturing == ("macro", "value")
    assert summaries[10.0].capturing == ("macro", "value")
    assert summaries[5.0].capturing == ("macro",)
    assert choice.direction_unstable == ()
    checks = {check.name: check for check in choice.direction_checks}
    assert checks["macro"].stable is True
    assert [entry.direction for entry in checks["macro"].entries] == [-1, -1, -1]
    assert [entry.min_move_pct for entry in checks["macro"].entries] == [15.0, 10.0, 5.0]


def test_a_direction_flip_between_levels_is_refused_and_flagged() -> None:
    """The veto: a leg whose fitted direction is not its own is not trusted anywhere.

    ``flipper`` clears the bar at two levels with opposite signs. Under the
    conjunct it captures NOWHERE — not at the level where it happens to agree with
    its usual reading — and the flip is recorded as the evidence for refusing it.
    """
    ladder = [
        _level(15.0, [_row("steady", 0.9), _row("flipper", 1.10)]),
        _level(5.0, [_row("steady", 0.9), _row("flipper", -1.10)]),
    ]
    choice = select_sensitivity_level(ladder)
    assert choice.direction_unstable == ("flipper",)
    # Refused everywhere: not at 15%, where its separation is the deepest on the
    # level, and not at 5%, where its sign agrees with nothing it did before.
    summaries = {summary.min_move_pct: summary for summary in choice.level_summaries}
    assert summaries[15.0].capturing == ("steady",)
    assert summaries[5.0].capturing == ("steady",)
    assert summaries[15.0].unstable_here == ("flipper",)
    assert summaries[5.0].unstable_here == ("flipper",)
    # Named, not silently absent: at the chosen level it is a non-capturing
    # indicator with the evidence attached.
    assert choice.chosen_min_move_pct == 15.0
    assert choice.non_capturing_indicators == ("flipper",)
    (check,) = [c for c in choice.direction_checks if c.name == "flipper"]
    assert check.stable is False
    assert "direction_unstable" in check.note
    assert "captures nowhere" in check.note
    # The flip is spelled out level by level, signed, so it can be argued with.
    assert "+1 at min_move_pct=15 (separation +1.1000)" in check.note
    assert "-1 at min_move_pct=5 (separation -1.1000)" in check.note


def test_a_single_level_capture_has_no_stability_obligation() -> None:
    """A leg that clears the bar once cannot be inconsistent with anything."""
    ladder = [
        # `lonely` is inverted where it clears the bar and far short of it at 15%.
        _level(15.0, [_row("steady", 0.9), _row("lonely", 0.30)]),
        _level(5.0, [_row("steady", 0.9), _row("lonely", -1.10)]),
    ]
    choice = select_sensitivity_level(ladder)
    assert choice.direction_unstable == ()
    summaries = {summary.min_move_pct: summary for summary in choice.level_summaries}
    assert summaries[15.0].capturing == ("steady",)
    assert summaries[5.0].capturing == ("steady", "lonely")
    (check,) = [c for c in choice.direction_checks if c.name == "lonely"]
    assert check.stable is True
    assert "single level, so no stability obligation" in check.note
    assert choice.chosen_min_move_pct == 5.0
    assert choice.inverted_direction_count == 1


def test_a_leg_below_the_bar_at_a_coarser_level_is_not_part_of_its_stability_read() -> None:
    """Stability is judged only over the levels where the leg captures.

    ``thin`` is inverted at 5% and deep enough to clear the bar only there; at
    15% it reads +0.20. The +0.20 is not a second direction to be inconsistent
    with — it is not a capture, so it is not in the check at all. This is what
    keeps the conjunct from vetoing legs for a disagreement it invented.
    """
    ladder = [
        _level(15.0, [_row("steady", 0.9), _row("thin", 0.20)]),
        _level(5.0, [_row("steady", 0.9), _row("thin", -1.10)]),
    ]
    choice = select_sensitivity_level(ladder)
    assert choice.direction_unstable == ()
    (check,) = [c for c in choice.direction_checks if c.name == "thin"]
    assert [entry.direction for entry in check.entries] == [-1]
    assert choice.capturing_indicators == ("steady", "thin")


# --------------------------------------------------------------------------- #
# (e) the choice: the finest level that does not lose, ranked by DEPTH
# --------------------------------------------------------------------------- #


def test_more_capturing_indicators_with_less_depth_loses_to_fewer_deeper_captures() -> None:
    """Ruling 1's whole point: depth ranks, headcount does not.

    The 5% rung carries MORE capturing indicators (3 against 2) and LESS summed
    depth (1.8 against 3.3). Under the previous headcount rule the 5% rung won
    outright; under the ruled rule the coarse rung wins because its captures are
    deep. Both halves are asserted, so the fixture is non-vacuous in both
    directions: a headcount key would give 5.0 and this test would fail.
    """
    ladder = [
        _level(15.0, [_row("deep_a", 2.4), _row("deep_b", 0.9)]),
        _level(5.0, [_row("shallow_a", 0.6), _row("shallow_b", 0.6), _row("shallow_c", 0.6)]),
    ]
    choice = select_sensitivity_level(ladder)
    summaries = {summary.min_move_pct: summary for summary in choice.level_summaries}
    # The fixture really is the shape the ruling is about.
    assert summaries[5.0].capture_count == 3 > summaries[15.0].capture_count == 2
    assert summaries[5.0].capture_depth == pytest.approx(1.8)
    assert summaries[15.0].capture_depth > summaries[5.0].capture_depth
    # …and the decision follows the depth, not the count.
    assert choice.chosen_min_move_pct == 15.0
    assert choice.capture_count == 2
    assert choice.capture_depth == pytest.approx(2.4 + 0.9)
    assert choice.capturing_indicators == ("deep_a", "deep_b")


def test_a_knife_edge_capture_cannot_hand_the_choice_to_a_finer_level() -> None:
    """The ruling's stated why: a leg clearing the bar by 0.0042 must not decide.

    This is the shape the gold ladder actually had — one leg at +0.5042 against
    a 0.5 bar — where under headcount that leg's single vote was worth exactly as
    much as a deeply-separating one, so its presence flipped the chosen level.
    Here the deeper rung is chosen even though the coarse rung has one MORE
    capturing indicator and one of them is the knife-edge leg.
    """
    ladder = [
        _level(15.0, [_row("macro", 3.0), _row("knife_edge", 0.5042)]),
        _level(5.0, [_row("macro", 3.0)]),
    ]
    choice = select_sensitivity_level(ladder)
    assert choice.chosen_min_move_pct == 15.0
    assert choice.capture_count == 2
    assert choice.capture_depth == pytest.approx(3.0 + 0.5042)
    summaries = {summary.min_move_pct: summary for summary in choice.level_summaries}
    # 5% qualifies (it loses nothing: 1 capture against 2 is a loss, so it does
    # not) — the count is what refuses it here, and the depth agrees.
    assert summaries[5.0].capture_count == 1
    assert summaries[5.0].qualifies is False


def test_equal_capture_depth_resolves_to_the_coarser_level() -> None:
    ladder = [
        _level(15.0, [_row("a", 0.6), _row("b", 0.6)]),
        _level(10.0, [_row("a", 0.5), _row("b", 0.7)]),
        _level(5.0, [_row("a", 0.5), _row("b", 0.7), _row("c", 0.4)]),
    ]
    choice = select_sensitivity_level(ladder)
    summaries = {summary.min_move_pct: summary for summary in choice.level_summaries}
    # Every rung reaches the SAME depth, so the ranking key cannot separate them
    # and the coarser tie-break decides — the finest qualifying level is not taken.
    assert summaries[15.0].capture_depth == pytest.approx(1.2)
    assert summaries[10.0].capture_depth == pytest.approx(1.2)
    assert summaries[5.0].capture_depth == pytest.approx(1.2)
    assert choice.chosen_min_move_pct == 15.0
    assert choice.capture_count == 2
    assert choice.capture_depth == pytest.approx(1.2)
    assert [entry.min_move_pct for entry in choice.dropped_at_finer_levels] == [10.0, 5.0]
    assert all(entry.qualifies for entry in choice.dropped_at_finer_levels)


def test_capture_depth_is_reported_on_the_choice_and_on_every_level_summary() -> None:
    """The ranking key is on the record at both places the owner reads it."""
    ladder = [
        _level(15.0, [_row("a", 1.2), _row("b", 0.8)]),
        _level(5.0, [_row("a", 1.0), _row("c", 0.6)]),
    ]
    choice = select_sensitivity_level(ladder)
    assert [summary.min_move_pct for summary in choice.level_summaries] == [15.0, 5.0]
    assert choice.level_summaries[0].capture_depth == pytest.approx(2.0)
    assert choice.level_summaries[1].capture_depth == pytest.approx(1.6)
    # The choice carries the CHOSEN level's depth — the number the key was read
    # from — and never a sum over some other rung.
    assert choice.chosen_min_move_pct == 15.0
    assert choice.capture_depth == choice.level_summaries[0].capture_depth
    # …and it is not simply the capture count wearing a float: the count and the
    # depth are separate numbers and this fixture's counts tie.
    assert choice.capture_count == 2
    assert choice.capture_depth == pytest.approx(2.0)


def test_qualification_still_requires_no_loss_against_every_coarser_level() -> None:
    """Depth ranks the qualifiers; the COUNT still decides who qualifies, against ALL coarser.

    The counts are deliberately NOT monotone across the ladder — [4, 1, 3] — so a
    5% that beats its direct predecessor (3 > 1) but loses to the coarsest rung
    (3 < 4) still fails. Both finer rungs are asserted non-qualifying: only a rule
    that compares against every coarser level can produce that.
    """
    ladder = [
        _level(15.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6), _row("d", 0.6)]),
        _level(10.0, [_row("a", 0.6), _row("b", 0.21), _row("c", 0.21), _row("d", 0.21)]),
        _level(5.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6), _row("d", 0.21)]),
    ]
    choice = select_sensitivity_level(ladder)
    summaries = {summary.min_move_pct: summary for summary in choice.level_summaries}
    assert summaries[15.0].capture_count == 4
    assert summaries[10.0].capture_count == 1
    assert summaries[5.0].capture_count == 3
    assert choice.chosen_min_move_pct == 15.0
    assert choice.capture_count == 4
    ten, five = choice.dropped_at_finer_levels
    assert ten.min_move_pct == 10.0
    assert ten.qualifies is False  # 1 capture against the coarsest rung's 4
    assert five.min_move_pct == 5.0
    assert five.qualifies is False  # 3 captures — above 10%'s 1, below 15%'s 4


def test_chooses_the_most_sensitive_level_when_every_finer_level_captures_more() -> None:
    ladder = [
        _level(15.0, [_row("a", 0.6), _row("b", -0.6)]),
        _level(10.0, [_row("a", 0.6), _row("b", -0.6)]),
        _level(5.0, [_row("a", 0.6), _row("b", -0.6), _row("c", 0.6), _row("d", 0.6)]),
    ]
    choice = select_sensitivity_level(ladder)
    assert choice.chosen_min_move_pct == 5.0
    assert choice.capture_count == 4
    assert choice.capture_depth == pytest.approx(2.4)
    assert choice.capturing_indicators == ("a", "b", "c", "d")
    # `b` votes the other way round at every rung, which is now stable and legal.
    assert choice.inverted_direction_count == 1


def test_the_coarsest_level_does_not_win_when_a_finer_level_captures_more() -> None:
    """The coarsest rung always QUALIFIES; it does not always WIN.

    The fixture keeps STRICTLY UNEQUAL depths (0 captures at 15%, 1 at 5%), so no
    tie-break is in play and the choice must be the finer qualifier.
    """
    ladder = [_level(15.0, [_row("a", 0.0)]), _level(5.0, [_row("a", 0.6)])]
    choice = select_sensitivity_level(ladder)
    # Both rungs are read, coarsest first — the coarsest is weighed, not discarded.
    assert [level.min_move_pct for level in choice.level_rows] == [15.0, 5.0]
    # 5% captures strictly more (1 vs 0), so the most sensitive qualifier wins and
    # the coarsest rung does not get the choice by default.
    assert choice.chosen_min_move_pct == 5.0
    assert choice.capture_count == 1
    assert choice.capture_depth == pytest.approx(0.6)
    assert choice.capturing_indicators == ("a",)
    # Nothing is finer than the chosen rung, so no finer level is charged for it.
    assert choice.dropped_at_finer_levels == ()


# --------------------------------------------------------------------------- #
# (f) the dropped-at-finer table — the owner's evidence
# --------------------------------------------------------------------------- #


def test_reports_each_indicator_that_drops_at_a_finer_level() -> None:
    """One row per level FINER than the chosen one; each drop names its indicator."""
    ladder = [
        _level(15.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6)]),
        _level(10.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6)]),
        _level(
            5.0,
            [_row("a", 0.6), _row("b", 0.21), _row("c", 0.0, mean_peak_z=-0.9, mean_trough_z=0.9)],
        ),
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
    assert finer_qualifier.capture_depth == pytest.approx(1.8)
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
    # The polarity is no longer a failure, so there is no "negative" reason any
    # more: the bar is read on |separation| and the signed read is printed with it.
    assert all("negative separation" not in drop.reason for drop in finer_cost.dropped)
    flat = next(drop for drop in finer_cost.dropped if drop.name == "c")
    assert flat.separation_at_finer_level == 0.0
    assert "0.0000 < 0.5" in flat.reason


def test_a_dead_side_drop_is_named_as_such() -> None:
    ladder = [
        _level(15.0, [_row("a", 0.6)]),
        _level(5.0, [_row("a", 0.6, mean_peak_z=0.0)]),
    ]
    choice = select_sensitivity_level(ladder)
    (drop,) = [d for entry in choice.dropped_at_finer_levels for d in entry.dropped]
    assert "degenerate" in drop.reason


def test_an_unscored_leg_is_reported_as_a_drop_with_a_reason() -> None:
    ladder = [
        _level(15.0, [_row("a", 0.6), _row("b", 0.6)]),
        _level(5.0, [_row("a", 0.6), _row("b", None)]),
    ]
    choice = select_sensitivity_level(ladder)
    (drop,) = [d for entry in choice.dropped_at_finer_levels for d in entry.dropped]
    assert drop.name == "b"
    assert drop.separation_at_finer_level is None
    assert "unscoreable" in drop.reason


def test_a_level_that_never_scored_a_leg_reports_it_as_a_drop() -> None:
    ladder = [
        _level(15.0, [_row("a", 0.6), _row("b", 0.6)]),
        _level(5.0, [_row("a", 0.6)]),
    ]
    choice = select_sensitivity_level(ladder)
    (drop,) = [d for entry in choice.dropped_at_finer_levels for d in entry.dropped]
    assert drop.name == "b"
    assert "not scored at this level" in drop.reason


def test_levels_are_ordered_coarse_to_fine_regardless_of_input_order() -> None:
    ladder = [
        _level(5.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6)]),
        _level(15.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6)]),
        _level(10.0, [_row("a", 0.6), _row("b", 0.6), _row("c", 0.6)]),
    ]
    choice = select_sensitivity_level(ladder)
    assert [row.min_move_pct for row in choice.level_rows] == [15.0, 10.0, 5.0]
    assert [summary.min_move_pct for summary in choice.level_summaries] == [15.0, 10.0, 5.0]
    assert choice.chosen_min_move_pct == 15.0  # three identical depths -> coarser


def test_the_level_row_view_is_provisional_and_the_summary_is_settled() -> None:
    """Two named views, so neither can quietly be read as the other.

    A level row answers a per-row question (does THIS row clear the bar); the
    cross-level conjuncts cannot be answered there. So ``capture_count`` /
    ``capture_depth`` on the row are provisional — the veto not applied — while
    ``choice.level_summaries`` holds the settled numbers the choice was ranked
    by. On a ladder with a flipping leg those two views genuinely differ, which is
    exactly when conflating them would misreport the verdict.
    """
    ladder = [
        _level(15.0, [_row("steady", 0.9), _row("flipper", 1.10)]),
        _level(5.0, [_row("steady", 0.9), _row("flipper", -1.10)]),
    ]
    coarse, _fine = ladder
    # Provisional: both legs clear the bar at 15%, so the row counts 2 and sums
    # 2.0 — the flip has not been considered, because a row cannot consider it.
    assert coarse.capture_count == 2
    assert coarse.capture_depth == pytest.approx(2.0)
    assert coarse.capturing == ("steady", "flipper")
    # Settled: the flip vetoes `flipper`, so the summary counts 1 and sums 0.9.
    # The choice is built from THESE numbers.
    choice = select_sensitivity_level(ladder)
    summary = next(s for s in choice.level_summaries if s.min_move_pct == 15.0)
    assert summary.capture_count == 1
    assert summary.capture_depth == pytest.approx(0.9)
    assert summary.capturing == ("steady",)
    assert choice.capture_count == summary.capture_count == 1
    assert choice.capture_depth == pytest.approx(0.9)
    # The bar is still threaded: the provisional view moves with a supplied bar,
    # and the settled view is built from that same bar.
    coarse_at_2 = coarse.capture_count_at(2.0)
    assert coarse_at_2 == 0
    assert summary.capture_depth == pytest.approx(0.9)


# --------------------------------------------------------------------------- #
# (g) refusals
# --------------------------------------------------------------------------- #


def test_an_empty_ladder_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one level"):
        select_sensitivity_level([])


def test_two_levels_at_the_same_min_move_pct_are_refused() -> None:
    ladder = [_level(10.0, [_row("a", 0.6)]), _level(10.0, [_row("a", 0.6)])]
    with pytest.raises(ValueError, match="min_move_pct"):
        select_sensitivity_level(ladder)


def test_a_non_positive_capture_bar_is_refused() -> None:
    with pytest.raises(ValueError, match="capture_bar"):
        select_sensitivity_level([_level(15.0, [_row("a", 0.6)])], capture_bar=0.0)


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


def test_a_duplicated_grid_cell_in_one_level_is_refused() -> None:
    """One row per grid cell. A repeated NAME is now legal (that is the frozen grid).

    What cannot be repeated is the same cell, because the capture depth sums
    rows: a cell listed twice would be worth two votes it did not earn.
    """
    _level(15.0, [_row("a", 0.6, window_days=378), _row("a", 0.6, window_days=756)])
    with pytest.raises(ValueError, match="duplicate grid cell"):
        _level(15.0, [_row("a", 0.6, window_days=378), _row("a", 0.6, window_days=378)])


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
# (h) zero Nautilus, zero pandas — the rule is pure and asset-agnostic
# --------------------------------------------------------------------------- #


def test_module_imports_no_engine_and_no_pandas() -> None:
    source = MODULE_PATH.read_text()
    banned = re.findall(r"^\s*(?:import|from)\s+(nautilus_trader|pandas)\b", source, re.MULTILINE)
    assert banned == []
    # Asset knowledge would make the rule non-generic.
    assert not re.search(r"\bGLD\b|\bgold\b|\bBTC\b", source, re.IGNORECASE)
