"""Generic sensitivity consolidation: how finely can pins be before indicators stop seeing them?

Plan 22 Engine 2 (#4804). Engine 1 shipped the paired turn detector
(``turn_detect.py``); its ``min_move_pct`` knob is *monotone* in turn count
(pinned in ``tests/dq/strategies/sdca/test_turn_detect.py``), so "how sensitive
should the calibration be" is not a question the detector can answer — it can
always go finer. This module answers the other half: **at what point do the
fitted indicators stop being able to see the turns?**

The move is deliberate and generic. Detection reads prices; capture reads
indicators. A finer ``min_move_pct`` yields more, smaller turns, so a pin set
sharpened that way is a *harder* scoring target: an indicator that voted on 20
big swings may have no opinion on 63 small ones. Choosing pins finer than the
evidence supports would calibrate indicator windows against structure no
indicator can see. So the sensitivity is chosen by the indicators, not by taste —
"the most sensitive granularity the indicators can still capture".

**Windows are a scoring target, not execution periods.** Everything here consumes
``SdcaCycleWindows`` the way ``cycle_windows.py`` documents them — an object
whose only job is to be scored against. This module adds **no exposure floor**,
no period-of-execution semantics, and no perfect-strategy oracle: a window set
can be recognised as captured or missed, never traded around.

**Pure and asset-agnostic.** ``select_sensitivity_level`` takes rows of numbers
and returns a decision. It reads no files, no price series, no asset name and no
calendar, so the same rule consolidates any asset's ladder. There is no
``nautilus_trader`` import (SDCA core rule) and no pandas.

**The rule, exactly as ruled.**

1. **Selection — maximise ``|separation|``.** For one indicator at one level, the
   row that speaks for it is the grid row with the largest ``abs(separation)``
   (ties to the shorter window: the harness parsimony rule). Polarity is NOT a
   selection constraint any more. The caller hands over the whole frozen grid for
   each indicator and this module picks, so "best row" is one rule in one place.
2. **Capture — the bar, on ``|separation|``.** The selected row captures a level
   iff ``abs(separation) >= capture_bar`` (inclusive; ``CAPTURE_BAR`` = 0.5
   z-units is the frozen default and the bar every count below is read at unless
   the caller supplies another) AND it is **not degenerate** (one window side's
   mean never leaves the +/-``DEGENERATE_MEAN_ABS`` dead zone). An unscoreable
   leg never captures.
   ``abs()`` IS applied to the bar. **This reverses the earlier "abs() is
   forbidden" rule, on purpose:** that rule only made sense while the polarity
   was *imposed*. With direction fitted (below) a mirrored leg is a leg that
   sees the turns the other way round, and refusing it was throwing away
   evidence — a leg voting rich at the bottoms is exactly the macro-led reading
   the owner wants to see, so it is now recorded, not rejected.
3. **Fitted direction.** The selected row's direction is FITTED and RECORDED as
   ``+1`` (trough-high / peak-low, the expected polarity) or ``-1`` (inverted),
   read off the sign of its own separation. It appears on the per-indicator row,
   on every level summary, on the choice, and in the sign mix.
4. **Direction stability (a veto, and a new conjunct).** An indicator that
   captures at MORE THAN ONE level must carry the SAME fitted direction at every
   level where it captures. If it flips sign between levels it is flagged
   ``direction_unstable``, captures **nowhere**, and the flip is recorded as
   evidence. A single-level capture carries no stability obligation.
5. **Qualification.** A level QUALIFIES iff its settled capture count is at least
   as large as at *every* coarser level — it loses no indicator relative to the
   coarser calibrations. The coarsest level therefore always qualifies, so a
   ladder is never undecidable.
6. **Choice — DEPTH, not headcount.** Among qualifiers take the LARGEST
   ``capture_depth``: the SUM of the capturing indicators' ``|separation|`` at
   that level. The capture count is still reported, on the choice and on every
   level summary, but it is no longer the ranking key. Headcount ranking let one
   knife-edge indicator — a leg clearing the bar by 0.0042 z-units — hand the
   decision to a different granularity, because a barely-clearing leg and a
   deeply-separating leg each counted as exactly one vote. Depth does not have
   that failure mode. Tied ``capture_depth`` resolves to the **coarser** level
   (fewer turns, more robust).
7. **Finer cost.** For every level FINER than the chosen one, the indicators that
   captured at the chosen level and fail there are reported with both separations
   and the reason. That table is the evidence for the choice: it names exactly
   which votes the finer granularity costs.

**Two views of a level, on purpose.** ``SensitivityLevelRow`` carries the raw
grid and answers *per row*: does THIS row clear the bar? The cross-level
conjuncts — direction stability — cannot be answered by one row in isolation, so
they live in ``LevelSummary``, one per rung, built by
:func:`select_sensitivity_level` and reported on the choice. A level row's own
``capture_count`` / ``capture_depth`` are therefore the PROVISIONAL, frozen-bar
read (bar only, stability not yet applied); ``choice.level_summaries`` holds the
settled numbers the ranking key is built from. Both are named for what they are
and the pair is pinned side by side.

The degenerate rule is Plan-19 Ruling 1, whose dead-zone width (0.06) is restated
here as a plain constant: the harness that owns it
(``digiquant/scripts/fit_gold_indicators.py``) is a research script, not an
importable package module, so the two cannot share a definition. Both are frozen;
change one and you must change the other.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The frozen capture bar, in z-units (owner ruling, Plan 22): a separation this
# large is an indicator making a statement about the pin set, not drifting.
CAPTURE_BAR = 0.5

# Plan-19 Ruling 1's dead-zone width, restated (see the module docstring). A
# window-side mean inside +/- this band means the z has no opinion on that side,
# so a separation resting on it is one-sided and is not a capture.
DEGENERATE_MEAN_ABS = 0.06


def _capture_rule_at(capture_bar: float) -> str:
    """The capture rule as it reads at ``capture_bar``.

    A ``SensitivityChoice`` states the rule it actually applied, so a choice made
    at a caller-supplied bar cannot ship the frozen 0.5 text it was not decided
    under. At the frozen default this returns exactly ``CAPTURE_RULE``.
    """
    return (
        "An indicator's row is the grid row maximising |separation|. It CAPTURES a "
        f"level iff |separation| >= {capture_bar} z-units AND is not degenerate "
        f"(neither window side's mean inside +/-{DEGENERATE_MEAN_ABS}). abs() IS "
        "applied to the bar — this REVERSES the earlier 'abs() is forbidden' rule, "
        "because direction is now FITTED per indicator and recorded as +1 "
        "(trough-high / peak-low) or -1 (inverted) rather than imposed. DIRECTION "
        "STABILITY: an indicator capturing at more than one level must carry the "
        "SAME fitted direction at every level where it captures; a flip is flagged "
        "direction_unstable, captures nowhere, and the flip is recorded. An "
        "unscoreable leg never captures."
    )


CAPTURE_RULE = _capture_rule_at(CAPTURE_BAR)

CHOICE_RULE = (
    "Sensitivity crank: a lower min_move_pct yields MORE turns, so a smaller "
    "min_move_pct is the MORE SENSITIVE (finer) calibration. A level QUALIFIES "
    "iff its capture count is at least as large as at every COARSER level (it "
    "loses no indicator relative to the coarser calibrations); the coarsest level "
    "therefore always qualifies. Among qualifiers take the one with the LARGEST "
    "capture_depth — the SUM of the capturing indicators' |separation| at that "
    "level. The ranking key is DEPTH, NOT HEADCOUNT: a knife-edge indicator that "
    "clears the bar by 0.0042 must not be able to hand the decision to a "
    "different granularity, and under headcount it counts as one vote exactly like "
    "a deeply-separating leg. Capture count is still reported, it just does not "
    "rank. Where two qualifiers reach the SAME capture_depth prefer the COARSER "
    "one (fewer turns, more robust)."
)

RATIONALE = (
    "the most sensitive granularity the indicators can still capture: finer pin "
    "sets are harder scoring targets, so sensitivity is taken as far as the "
    "indicator evidence carries it and no further. Among the levels the "
    "indicators do carry, the one they carry DEEPLY wins, because headcount "
    "cannot tell a vote held from conviction from one held by 0.0042"
)


def fitted_direction(separation: float | None) -> int | None:
    """The direction an indicator's best row votes: ``+1`` expected, ``-1`` inverted.

    Read off the SIGN of the scored separation, never imposed by the rule: a leg
    that votes rich at the bottoms is recorded as inverted rather than refused,
    which is what makes the sign mix per level readable at all. ``None`` when the
    row never reached both window sides (there is nothing to fit); ``0`` when the
    separation is exactly ``0.0`` (no sign at all — it can never clear a positive
    bar, so the value never reaches a verdict).
    """
    if separation is None:
        return None
    if separation > 0.0:
        return 1
    if separation < 0.0:
        return -1
    return 0


class IndicatorCaptureRow(BaseModel):
    """One scored grid row of one indicator at one level.

    A level hands over the whole frozen grid it scored for each indicator; the
    row that speaks for the indicator is picked by :func:`best_grid_row`
    (largest ``|separation|``, ties to the shorter window). Keeping every row —
    rather than only the winner — is what makes the selection auditable: the
    choice of winner is visible in the evidence, not buried in the caller.

    ``status`` / ``reason`` carry the caller's own unscoreability reporting, so a
    leg that could not be measured is listed rather than silently absent. The
    ``degenerate`` flag is cross-checked against the frozen dead-zone rule below:
    a caller cannot pass a one-sided row by mislabelling it.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    name: str = Field(..., min_length=1, description="Indicator name, as the caller registered it")
    params: dict[str, int] = Field(
        default_factory=dict,
        description="The grid cell that produced this row, e.g. {'window': 378}",
    )
    params_note: str | None = Field(
        default=None,
        description=(
            "Free-text note for parameters that are not integers (an anchor's rolling z is a "
            "float, for instance); None when params already says everything"
        ),
    )
    window_days: int = Field(..., ge=1, description="Calendar footprint the row was read at")
    separation: float | None = Field(
        ...,
        description=(
            "mean(z | trough windows) - mean(z | peak windows), positive = the z votes cheap "
            "at the bottoms, negative = rich. None when the row could not reach both window sides"
        ),
    )
    mean_peak_z: float | None = Field(..., description="Mean z inside peak windows, or None")
    mean_trough_z: float | None = Field(..., description="Mean z inside trough windows, or None")
    peak_negative_share: float | None = Field(
        ..., description="Share of peak window days with z < 0, or None when unscored"
    )
    trough_positive_share: float | None = Field(
        ..., description="Share of trough window days with z > 0, or None when unscored"
    )
    zero_z_share: float | None = Field(
        ..., description="Share of scored window days with z exactly 0.0, or None when unscored"
    )
    degenerate: bool = Field(
        ...,
        description=(
            "As scored by the caller; must agree with the frozen dead-zone rule, else the "
            "model is refused"
        ),
    )
    coverage: float = Field(..., ge=0.0, le=1.0, description="Scored window days / window days")
    scored_days: int = Field(..., ge=0, description="Window days with a valid z")
    status: str = Field(
        ..., min_length=1, description="Caller's status, e.g. 'scored' or 'unscoreable'"
    )
    reason: str | None = Field(
        default=None, description="Why the row is unscoreable, or an extra caveat"
    )

    @model_validator(mode="after")
    def _degenerate_agrees(self) -> IndicatorCaptureRow:
        """Refuse a ``degenerate`` flag the frozen rule contradicts."""
        recomputed = row_is_degenerate(
            separation=self.separation,
            mean_peak_z=self.mean_peak_z,
            mean_trough_z=self.mean_trough_z,
        )
        if recomputed != self.degenerate:
            raise ValueError(
                f"{self.name}: degenerate={self.degenerate} contradicts the frozen dead-zone "
                f"rule (+/-{DEGENERATE_MEAN_ABS} on a window-side mean), which gives "
                f"{recomputed} for separation={self.separation}, mean_peak_z={self.mean_peak_z}, "
                f"mean_trough_z={self.mean_trough_z}"
            )
        return self

    @property
    def direction(self) -> int | None:
        """The FITTED direction of this row: ``+1`` expected, ``-1`` inverted, 0 or None.

        See :func:`fitted_direction`. Recorded, not imposed: a negative
        separation is a leg that reads the turns the other way round, and under
        the current rule it can capture on its magnitude.
        """
        return fitted_direction(self.separation)

    @property
    def captures(self) -> bool:
        """Does this row clear the bar at the FROZEN bar? (the 0.5 default view)

        This is a per-ROW fact: the bar, the dead zone, nothing else. The
        direction-stability conjunct is cross-level and therefore cannot be
        answered here — ``choice.level_summaries`` is the settled view. A
        decision made at another bar must use :meth:`captures_at` instead.
        """
        return self.captures_at(CAPTURE_BAR)

    def captures_at(self, capture_bar: float) -> bool:
        """Does this row clear the bar at ``capture_bar``?"""
        return captures_level(self, capture_bar=capture_bar)


class SensitivityLevelRow(BaseModel):
    """One rung of the sensitivity ladder: a turn count and every indicator's grid at it.

    ``min_move_pct`` is the detector's magnitude filter, so a SMALLER value is
    the more sensitive calibration and yields more turns.

    ``indicators`` is every grid row scored at this level, so an indicator may
    appear more than once (one row per grid cell). Exactly one row per grid cell
    is enforced; the row that speaks for an indicator is
    :attr:`best_rows`, chosen by ``|separation``. All the derived properties on
    this model read those selected rows and are the **provisional** read — the
    bar applied, the direction-stability veto not yet applied — so they are the
    per-row/per-bar fact and not the settled count the choice is ranked by.

    ``n_peaks + n_troughs`` must equal ``n_turns`` — the pairing invariant means
    every turn is one or the other. The one accommodation is an **unpaired**
    level: one reporting no peaks AND no troughs has no side to reconcile, so its
    turn count is taken as reported (a caller's split is not derivable when it
    reports no pins at all).
    """

    model_config = ConfigDict(frozen=True, strict=True)

    min_move_pct: float = Field(
        ...,
        ge=0.0,
        description="The level's magnitude filter; smaller = more sensitive, more turns",
    )
    n_turns: int = Field(..., ge=0, description="Turns the detector found at this level")
    n_peaks: int = Field(..., ge=0, description="Of those, how many were peaks")
    n_troughs: int = Field(..., ge=0, description="Of those, how many were troughs")
    window_day_share: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Share of the calendar the level's windows cover, as the detector reports it",
    )
    indicators: tuple[IndicatorCaptureRow, ...] = Field(
        ...,
        description=(
            "Every grid row scored at this level; one or more rows per indicator. The row that "
            "speaks for an indicator is the one maximising |separation| (see best_rows)"
        ),
    )

    @model_validator(mode="after")
    def _consistent(self) -> SensitivityLevelRow:
        if self.n_peaks + self.n_troughs != self.n_turns and not (
            self.n_peaks == 0 and self.n_troughs == 0
        ):
            raise ValueError(
                f"n_peaks ({self.n_peaks}) + n_troughs ({self.n_troughs}) must equal n_turns "
                f"({self.n_turns}) — the pairing invariant means every turn is one or the other "
                "(only an unpaired level, reporting no peaks and no troughs, is exempt)"
            )
        cells: dict[tuple[str, tuple[tuple[str, int], ...], int], str] = {}
        for row in self.indicators:
            key = (row.name, tuple(sorted(row.params.items())), row.window_days)
            if key in cells:
                raise ValueError(
                    f"duplicate grid cell at min_move_pct={self.min_move_pct}: {row.name} "
                    f"{dict(row.params)} @ {row.window_days}d is listed twice — one row per "
                    "grid cell, or the capture depth double-counts"
                )
            cells[key] = row.name
        return self

    @property
    def best_rows(self) -> tuple[IndicatorCaptureRow, ...]:
        """The row that speaks for each indicator: largest ``|separation|``, caller order.

        The selection is the module's, not the caller's, because the ruling keys
        it on magnitude and a caller picking by signed separation would be
        quietly picking a different rule. An indicator with NO scored row is
        still listed once (its first row, ``separation is None``) so it is
        reported as unscoreable rather than silently absent.
        """
        seen: set[str] = set()
        out: list[IndicatorCaptureRow] = []
        for row in self.indicators:
            if row.name in seen:
                continue
            out.append(best_grid_row([r for r in self.indicators if r.name == row.name]))
            seen.add(row.name)
        return tuple(out)

    def row_for(self, name: str) -> IndicatorCaptureRow | None:
        """This indicator's selected row here, or ``None`` when the level never scored it."""
        return next((row for row in self.best_rows if row.name == name), None)

    @property
    def capturing(self) -> tuple[str, ...]:
        """Provisional capturing names at the FROZEN bar (caller order, stability not applied)."""
        return self.capturing_at(CAPTURE_BAR)

    def capturing_at(self, capture_bar: float) -> tuple[str, ...]:
        """Provisional capturing names at ``capture_bar``, before the stability veto."""
        return tuple(row.name for row in self.best_rows if row.captures_at(capture_bar))

    @property
    def capture_count(self) -> int:
        """Provisional capture count at the FROZEN bar (stability veto NOT applied)."""
        return self.capture_count_at(CAPTURE_BAR)

    def capture_count_at(self, capture_bar: float) -> int:
        """Provisional capture count at ``capture_bar``, before the stability veto."""
        return sum(1 for row in self.best_rows if row.captures_at(capture_bar))

    @property
    def capture_depth(self) -> float:
        """Provisional summed ``|separation|`` of the capturing indicators at the FROZEN bar.

        Sign-blind by construction — depth sums magnitude regardless of the fitted
        direction, which is what the ranking key wants. Read ``choice.capture_depth``
        for the settled, stability-applied figure the choice was actually made on.
        """
        return self.capture_depth_at(CAPTURE_BAR)

    def capture_depth_at(self, capture_bar: float) -> float:
        """Provisional summed ``|separation|`` of the capturing indicators at ``capture_bar``."""
        return sum(
            abs(row.separation)
            for row in self.best_rows
            if row.separation is not None and row.captures_at(capture_bar)
        )

    def sign_mix_at(self, capture_bar: float = CAPTURE_BAR) -> tuple[int, int]:
        """``(expected, inverted)`` provisional capturing counts at ``capture_bar``.

        The owner's read on whether a level is macro-led: a level whose capturing
        legs are mostly inverted is being held up by legs that see the turns the
        other way round, and that is a different claim about the pin set than a
        level held by expected-polarity legs.
        """
        expected = sum(
            1 for row in self.best_rows if row.captures_at(capture_bar) and row.direction == 1
        )
        inverted = sum(
            1 for row in self.best_rows if row.captures_at(capture_bar) and row.direction == -1
        )
        return (expected, inverted)


class FittedDirection(BaseModel):
    """One indicator's fitted direction at one level it clears the bar at."""

    model_config = ConfigDict(frozen=True, strict=True)

    min_move_pct: float = Field(..., ge=0.0, description="The level this direction was fitted at")
    separation: float = Field(..., description="The signed separation the direction was read from")
    direction: int = Field(
        ..., ge=-1, le=1, description="+1 expected (trough-high / peak-low), -1 inverted, 0 no sign"
    )
    window_days: int = Field(..., ge=1, description="Window footprint the row was read at")


class IndicatorDirectionCheck(BaseModel):
    """One indicator's fitted direction at every level it clears the bar at.

    This is the cross-level conjunct's whole evidence: a leg that clears the bar
    at two levels with opposite signs is not a leg with two readings, it is a leg
    whose fitted direction is not a property of the indicator — so it is flagged
    ``stable: False``, vetoed everywhere, and the flip is spelled out in ``note``.
    An indicator that clears the bar at one level has nothing to be stable
    against and is always ``stable: True``.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    name: str = Field(..., min_length=1, description="Indicator name")
    entries: tuple[FittedDirection, ...] = Field(
        ...,
        min_length=1,
        description="Every level this indicator clears the bar at, coarsest first",
    )
    stable: bool = Field(
        ...,
        description=(
            "True when every level carries the SAME fitted direction. False means the leg was "
            "flagged direction_unstable and captures nowhere"
        ),
    )
    note: str = Field(..., min_length=1, description="The reading, or the flip, in words")


class LevelSummary(BaseModel):
    """One rung's SETTLED capture read — the numbers the ranking key is built from.

    The level row holds the grid and answers per-row questions; the two
    cross-level conjuncts (direction stability, qualification) cannot be answered
    there, so the settled per-rung numbers live here, built once by
    :func:`select_sensitivity_level` and reported on the choice. Every count here
    has already had the direction-stability veto applied.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    min_move_pct: float = Field(..., ge=0.0, description="The level's magnitude filter")
    n_turns: int = Field(..., ge=0, description="Turns the detector found at this level")
    window_day_share: float = Field(
        ..., ge=0.0, le=1.0, description="Calendar share the windows cover"
    )
    capture_count: int = Field(
        ..., ge=0, description="How many indicators capture this level, after the stability veto"
    )
    capture_depth: float = Field(
        ...,
        ge=0.0,
        description=(
            "SUM of the capturing indicators' |separation| at this level — the ranking key. "
            "Sign-blind: a level's depth is the same whether its captures vote the expected way "
            "or inverted, and the sign mix below is what distinguishes them"
        ),
    )
    expected_direction_count: int = Field(
        ...,
        ge=0,
        description="Capturing legs whose fitted direction is +1 (trough-high / peak-low)",
    )
    inverted_direction_count: int = Field(
        ..., ge=0, description="Capturing legs whose fitted direction is -1 (rich at the bottoms)"
    )
    capturing: tuple[str, ...] = Field(..., description="Capturing indicator names, level order")
    unstable_here: tuple[str, ...] = Field(
        ...,
        description=(
            "Indicators whose best row clears the bar HERE but were vetoed for flipping "
            "direction between levels; they capture nowhere, so they are named here instead of "
            "being silently absent"
        ),
    )
    qualifies: bool = Field(
        ...,
        description=(
            "Whether this level loses no indicator against every COARSER level. False is the "
            "evidence that the chosen level is the finest one the indicators can still carry"
        ),
    )


class IndicatorDrop(BaseModel):
    """One indicator that captured at the chosen level and fails at a finer one."""

    model_config = ConfigDict(frozen=True, strict=True)

    name: str = Field(..., min_length=1, description="Indicator that dropped")
    separation_at_chosen_level: float | None = Field(
        ..., description="Its separation at the chosen level, where it captured"
    )
    separation_at_finer_level: float | None = Field(
        ..., description="Its separation at this finer level, or None when unscoreable there"
    )
    reason: str = Field(
        ...,
        min_length=1,
        description=(
            "Why it fails here, most fundamental first: not scored, unscoreable, degenerate "
            "(one side dead), below the capture bar on |separation|. Every comparison is at the "
            "bar this choice was made at, so the number printed is the number applied"
        ),
    )


class FinerLevelDrops(BaseModel):
    """What the finer calibration costs: the drops at one level below the chosen one."""

    model_config = ConfigDict(frozen=True, strict=True)

    min_move_pct: float = Field(..., ge=0.0, description="The finer level in question")
    n_turns: int = Field(..., ge=0, description="Turns found at that finer level")
    capture_count: int = Field(
        ...,
        ge=0,
        description=(
            "How many indicators capture the finer level, after the stability veto, at the bar "
            "this choice was made at"
        ),
    )
    capture_depth: float = Field(
        ...,
        ge=0.0,
        description="Summed |separation| of that level's captures, at the bar this choice was made at",
    )
    qualifies: bool = Field(
        ...,
        description=(
            "Whether the finer level qualifies under the choice rule at the bar this choice "
            "was made at; False is exactly the evidence that the chosen level is the finest "
            "one the indicators can still capture"
        ),
    )
    dropped: tuple[IndicatorDrop, ...] = Field(
        ..., description="Indicators captured at the chosen level and failing here, by name"
    )


class SensitivityChoice(BaseModel):
    """The consolidation verdict: which level, how deep, and what finer costs."""

    model_config = ConfigDict(frozen=True, strict=True)

    capture_bar: float = Field(
        ...,
        gt=0.0,
        description=(
            "The capture bar in z-units this choice was made at. It is the bar every "
            "verdict, count, qualifies flag and drop reason below was decided at, not a "
            "label: CAPTURE_BAR when the caller did not supply one"
        ),
    )
    chosen_min_move_pct: float = Field(
        ..., ge=0.0, description="The chosen level's magnitude filter"
    )
    chosen_n_turns: int = Field(..., ge=0, description="Turns the chosen level produced")
    capture_count: int = Field(
        ...,
        ge=0,
        description=(
            "How many indicators capture the chosen level. Reported, but NOT the ranking "
            "key — capture_depth is"
        ),
    )
    capture_depth: float = Field(
        ...,
        ge=0.0,
        description=(
            "The chosen level's capture depth: the SUM of its capturing indicators' "
            "|separation|. This is the ranking key the choice was made on"
        ),
    )
    expected_direction_count: int = Field(
        ..., ge=0, description="Chosen level's captures whose fitted direction is +1"
    )
    inverted_direction_count: int = Field(
        ..., ge=0, description="Chosen level's captures whose fitted direction is -1"
    )
    capturing_indicators: tuple[str, ...] = Field(
        ..., description="Indicators capturing the chosen level, in level order"
    )
    non_capturing_indicators: tuple[str, ...] = Field(
        ...,
        description=(
            "Indicators scored at the chosen level that do not capture it — which includes any "
            "leg vetoed for flipping direction between levels"
        ),
    )
    direction_unstable: tuple[str, ...] = Field(
        ...,
        description=(
            "Indicators flagged direction_unstable: they cleared the bar at more than one level "
            "with opposite fitted directions, so they capture nowhere. Empty when every fitting "
            "leg reads the same way at every level it clears the bar at"
        ),
    )
    direction_checks: tuple[IndicatorDirectionCheck, ...] = Field(
        ...,
        description=(
            "Every indicator that clears the bar at at least one level, with its fitted "
            "direction at each — the evidence behind the veto"
        ),
    )
    level_summaries: tuple[LevelSummary, ...] = Field(
        ..., description="Every level's settled capture read, ordered coarsest first"
    )
    level_rows: tuple[SensitivityLevelRow, ...] = Field(
        ..., description="Every level with its full grid, ordered coarsest first"
    )
    dropped_at_finer_levels: tuple[FinerLevelDrops, ...] = Field(
        ...,
        description=(
            "One row per level FINER than the chosen one, coarsest finer level first: the "
            "owner-facing evidence table. A direction_unstable leg is absent from it by "
            "construction — it captures nowhere, the chosen level included — and is reported "
            "through direction_unstable / direction_checks instead"
        ),
    )
    capture_rule: str = Field(..., description="The capture rule this choice applied")
    choice_rule: str = Field(..., description="The choice rule this choice applied")
    rationale: str = Field(..., description="Why the rule reads the way it does")


def row_is_degenerate(
    *,
    separation: float | None,
    mean_peak_z: float | None,
    mean_trough_z: float | None,
) -> bool:
    """True when ONE window side's mean never leaves the dead zone.

    A pass that rests on a side sitting inside +/-``DEGENERATE_MEAN_ABS`` is
    one-sided — the z has no opinion there at all, so the separation is really
    the other side alone. An unscored row has no pass to rest on and is never
    degenerate.
    """
    if separation is None or mean_peak_z is None or mean_trough_z is None:
        return False
    return abs(mean_peak_z) <= DEGENERATE_MEAN_ABS or abs(mean_trough_z) <= DEGENERATE_MEAN_ABS


def best_grid_row(rows: Sequence[IndicatorCaptureRow]) -> IndicatorCaptureRow:
    """The row that speaks for an indicator at a level: largest ``|separation|``.

    Ties break to the SHORTER window (the harness parsimony rule), then to the
    caller's first row so the read is deterministic. Selection is on the
    MAGNITUDE, never on the signed separation: the polarity is fitted and
    recorded afterwards, from the sign of whichever row wins here.

    An indicator with no scored row has no winner — the caller's first row is
    returned instead, so the leg stays listed as unscoreable rather than
    disappearing from the ladder.
    """
    if not rows:
        raise ValueError("best_grid_row needs at least one row to choose between")
    scored = [row for row in rows if row.separation is not None]
    if not scored:
        return rows[0]
    return min(scored, key=lambda row: (-abs(row.separation), row.window_days))


def captures_level(row: IndicatorCaptureRow, *, capture_bar: float = CAPTURE_BAR) -> bool:
    """The frozen capture test, evaluated AT ``capture_bar``.

    Two conjuncts: the row's ``|separation|`` reaches the bar (inclusive), and
    neither window side is dead. ``capture_bar`` is a real input, not a label —
    callers that consolidate at another bar get that bar's verdicts.

    **``abs()`` is applied here, reversing the earlier "abs() is forbidden"
    rule.** That rule existed to stop magnitude rescuing a backwards vote; it
    only made sense while the polarity was imposed on the indicator. With
    ``direction`` fitted and recorded (see :func:`fitted_direction`) a mirrored
    leg is evidence about the pin set rather than a mistake in it, so it is
    scored on its magnitude and reported in the per-level sign mix instead of
    being refused. The polarity conjunct itself is gone; what survives is the
    degenerate one, because a pass resting on a dead side is not a pass at all
    whichever way it votes.
    """
    if row.separation is None or capture_bar <= 0.0:
        return False
    return abs(row.separation) >= capture_bar and not row.degenerate


def _drop_reason(row: IndicatorCaptureRow | None, capture_bar: float, min_move_pct: float) -> str:
    """Why this indicator fails to capture the finer level, most fundamental failure first.

    Absent, then unscoreable, then degenerate (one side dead), then simply short
    of the bar. ``row is None`` is a finer level that never scored the indicator
    at all.

    There is deliberately NO "negative separation" branch any more: under the
    fitted-direction rule a backwards vote can capture, so it is a direction,
    not a failure. ``row`` here is the indicator's SELECTED row at this level,
    which is the row the verdict was taken on.
    """
    if row is None:
        return (
            f"not scored at this level: no capture row for this indicator at "
            f"min_move_pct={min_move_pct}, so it cannot capture here"
        )
    if row.separation is None:
        return f"unscoreable at this level: {row.reason or 'no valid z reached both window sides'}"
    if row.degenerate:
        return (
            f"degenerate: |separation| {abs(row.separation):.4f} rests on a dead side (one "
            f"window mean inside +/-{DEGENERATE_MEAN_ABS}), so the pass is one-sided"
        )
    return (
        f"below the capture bar: |separation| {abs(row.separation):.4f} < {capture_bar} "
        f"(scored {row.separation:+.4f}, fitted direction {row.direction:+d})"
    )


@dataclass(frozen=True)
class _Resolved:
    """The settled cross-level verdict: who captures where, after the veto.

    ``by_level`` is keyed by ``(min_move_pct, indicator name)`` and holds only
    the rows that survived BOTH conjuncts — the bar (applied in
    ``select_sensitivity_level``'s call site) and the direction-stability veto.
    It is never mutated after construction.
    """

    checks: tuple[IndicatorDirectionCheck, ...]
    unstable: frozenset[str]
    by_level: Mapping[tuple[float, str], IndicatorCaptureRow]


def _resolve_directions(ordered: Sequence[SensitivityLevelRow], *, capture_bar: float) -> _Resolved:
    """Fit every indicator's direction at every level it clears the bar at, then veto flips.

    Walked coarsest-first, so the finest level an indicator fits is the one whose
    direction the others are compared against. The conjunct is deliberately
    narrow: it only speaks about an indicator that clears the bar at MORE THAN
    ONE level, because a single-level capture has no second reading to be
    inconsistent with. A flip is not repaired, it is refused — the leg captures
    nowhere and the flip is spelled out in the check's note, so the owner can see
    the evidence rather than inherit a silent choice.
    """
    per_indicator: dict[str, list[tuple[float, IndicatorCaptureRow]]] = {}
    for level in ordered:
        for row in level.best_rows:
            if row.captures_at(capture_bar):
                per_indicator.setdefault(row.name, []).append((level.min_move_pct, row))

    checks: list[IndicatorDirectionCheck] = []
    unstable: set[str] = set()
    by_level: dict[tuple[float, str], IndicatorCaptureRow] = {}
    for name in sorted(per_indicator):
        found = per_indicator[name]
        entries = tuple(
            FittedDirection(
                min_move_pct=min_move_pct,
                separation=float(row.separation),
                direction=int(row.direction or 0),
                window_days=row.window_days,
            )
            for min_move_pct, row in found
        )
        directions = {entry.direction for entry in entries}
        stable = len(directions) <= 1
        if stable:
            reading = f"direction {entries[0].direction:+d} at every level it clears the bar at"
            if len(entries) == 1:
                reading += " (single level, so no stability obligation)"
        else:
            unstable.add(name)
            reading = (
                "direction_unstable: flips fitted direction between levels ("
                + ", ".join(
                    f"{entry.direction:+d} at min_move_pct={entry.min_move_pct:g} "
                    f"(separation {entry.separation:+.4f})"
                    for entry in entries
                )
                + ") — captures nowhere, recorded as evidence"
            )
        checks.append(
            IndicatorDirectionCheck(name=name, entries=entries, stable=stable, note=reading)
        )
        if stable:
            for min_move_pct, row in found:
                by_level[(min_move_pct, name)] = row
    return _Resolved(checks=tuple(checks), unstable=frozenset(unstable), by_level=by_level)


def _settled_captures(
    level: SensitivityLevelRow, resolved: _Resolved
) -> tuple[tuple[str, IndicatorCaptureRow], ...]:
    """``(name, selected row)`` for every indicator capturing this level after the veto."""
    return tuple(
        (row.name, row)
        for row in level.best_rows
        if (level.min_move_pct, row.name) in resolved.by_level
    )


def _settled_depth(level: SensitivityLevelRow, resolved: _Resolved) -> float:
    """The level's capture depth: the SUM of its capturing indicators' ``|separation|``.

    Sign-blind by construction — depth measures how DEEPLY the captures read,
    not which way round they vote, which is what keeps the ranking key a measure
    of conviction rather than of agreement. The per-level sign mix is what
    carries the direction read.
    """
    return sum(abs(row.separation) for _name, row in _settled_captures(level, resolved))


def _qualifying(
    ordered: Sequence[SensitivityLevelRow], resolved: _Resolved
) -> tuple[SensitivityLevelRow, ...]:
    """Levels whose capture count loses nothing against every coarser level.

    Walked coarsest-first, which is what makes "less sensitive" mean "already
    visited": the running best is the max capture count strictly coarser than the
    level under test, and the coarsest level has none, so it always qualifies.

    The running max is over EVERY coarser level, not just the one before it. A
    ladder may dip and recover (counts [4, 1, 3]), and a recovered level must not
    be admitted by beating only the rung it recovered from — it still has to hold
    the best count any coarser level reached.

    The counts come from ``resolved``, i.e. the bar has been applied AND the
    direction-stability veto has already been enforced, so this walk cannot read
    a provisional capture the choice itself would refuse.
    """
    qualifying: list[SensitivityLevelRow] = []
    best_coarser = -1
    for level in ordered:
        count = len(_settled_captures(level, resolved))
        if count >= best_coarser:
            qualifying.append(level)
        best_coarser = max(best_coarser, count)
    return tuple(qualifying)


def _summarize(
    level: SensitivityLevelRow,
    resolved: _Resolved,
    *,
    qualifies: bool,
) -> LevelSummary:
    """One rung's settled read: count, depth, sign mix, vetoed legs, qualification."""
    settled = _settled_captures(level, resolved)
    expected = sum(1 for _name, row in settled if row.direction == 1)
    inverted = sum(1 for _name, row in settled if row.direction == -1)
    unstable_here = tuple(
        check.name
        for check in resolved.checks
        if not check.stable
        and any(entry.min_move_pct == level.min_move_pct for entry in check.entries)
    )
    return LevelSummary(
        min_move_pct=level.min_move_pct,
        n_turns=level.n_turns,
        window_day_share=level.window_day_share,
        capture_count=len(settled),
        capture_depth=sum(abs(row.separation) for _name, row in settled),
        expected_direction_count=expected,
        inverted_direction_count=inverted,
        capturing=tuple(name for name, _row in settled),
        unstable_here=unstable_here,
        qualifies=qualifies,
    )


def _drop(
    name: str,
    *,
    chosen: SensitivityLevelRow,
    finer: SensitivityLevelRow,
    capture_bar: float,
) -> IndicatorDrop:
    """One captured-at-the-chosen-level leg that fails at a finer level.

    Both separations come from each level's SELECTED row for this leg, so the
    evidence is the number the verdict was taken on. ``None`` on the finer side
    means the finer level never scored the leg at all.
    """
    finer_row = finer.row_for(name)
    return IndicatorDrop(
        name=name,
        separation_at_chosen_level=chosen.row_for(name).separation,  # type: ignore[union-attr]
        separation_at_finer_level=None if finer_row is None else finer_row.separation,
        reason=_drop_reason(finer_row, capture_bar, finer.min_move_pct),
    )


def select_sensitivity_level(
    level_rows: Sequence[SensitivityLevelRow],
    *,
    capture_bar: float = CAPTURE_BAR,
) -> SensitivityChoice:
    """Consolidate a sensitivity ladder into one level, with the evidence attached.

    ``level_rows`` may arrive in any order; it is read coarsest-first. Raises
    ``ValueError`` on an empty ladder, on two levels sharing a ``min_move_pct``
    (which would make "coarser than" ambiguous), or on a non-positive
    ``capture_bar``.

    ``capture_bar`` is threaded through the whole decision — every capture
    verdict, every capture count, the stability veto, the qualifying set, the
    chosen level and every drop reason is evaluated AT that bar, and the returned
    choice records the bar it was actually made at. ``CAPTURE_BAR`` (0.5) remains
    the frozen default; a bar supplied here overrides it rather than merely
    annotating a 0.5 decision.

    The decision is made on ``capture_depth`` — the summed ``|separation|`` of a
    level's captures — and never on the capture count, which is reported but does
    not rank. Pure: no I/O, no series, no asset. The caller supplies the numbers
    it scored, and this module selects the winning grid row of each indicator.
    """
    rows = tuple(level_rows)
    if not rows:
        raise ValueError("select_sensitivity_level needs at least one level to choose between")
    if capture_bar <= 0.0:
        raise ValueError(f"capture_bar must be positive, got {capture_bar}")
    ordered = tuple(sorted(rows, key=lambda level: -level.min_move_pct))
    seen: set[float] = set()
    for level in ordered:
        if level.min_move_pct in seen:
            raise ValueError(
                f"two levels share min_move_pct={level.min_move_pct}: 'coarser than' would be "
                "ambiguous, so the choice rule cannot be applied — merge them or re-label"
            )
        seen.add(level.min_move_pct)

    resolved = _resolve_directions(ordered, capture_bar=capture_bar)
    qualifying = _qualifying(ordered, resolved)
    if not qualifying:  # unreachable: the coarsest level always qualifies
        raise ValueError(
            "no level qualifies: the coarsest level has no coarser level to lose against, so "
            "an empty qualifying set means the ladder is malformed"
        )
    # Among qualifiers: the largest capture DEPTH wins, and the coarser level
    # whenever the depths tie — the pair sorts depth first, magnitude second.
    # The capture count is deliberately absent from the key: it is reported on
    # every summary and cannot steer the choice.
    chosen = max(
        qualifying,
        key=lambda level: (_settled_depth(level, resolved), level.min_move_pct),
    )
    chosen_names = tuple(name for name, _row in _settled_captures(chosen, resolved))
    chosen_name_set = set(chosen_names)

    summaries = tuple(
        _summarize(
            level, resolved, qualifies=level.min_move_pct in {q.min_move_pct for q in qualifying}
        )
        for level in ordered
    )
    by_pct = {summary.min_move_pct: summary for summary in summaries}

    finer_rows = tuple(level for level in ordered if level.min_move_pct < chosen.min_move_pct)
    dropped_by_level: list[FinerLevelDrops] = []
    for level in finer_rows:
        finer_names = {name for name, _row in _settled_captures(level, resolved)}
        summary = by_pct[level.min_move_pct]
        # A finer level that never scored a leg at all is still a drop — the leg
        # is named with ``separation_at_finer_level: None`` and the "not scored"
        # reason, because hiding it would understate what the finer level costs.
        drops = tuple(
            _drop(name, chosen=chosen, finer=level, capture_bar=capture_bar)
            for name in sorted(chosen_name_set - finer_names)
        )
        dropped_by_level.append(
            FinerLevelDrops(
                min_move_pct=level.min_move_pct,
                n_turns=level.n_turns,
                capture_count=summary.capture_count,
                capture_depth=summary.capture_depth,
                qualifies=summary.qualifies,
                dropped=drops,
            )
        )

    chosen_summary = by_pct[chosen.min_move_pct]
    return SensitivityChoice(
        capture_bar=capture_bar,
        chosen_min_move_pct=chosen.min_move_pct,
        chosen_n_turns=chosen.n_turns,
        capture_count=chosen_summary.capture_count,
        capture_depth=chosen_summary.capture_depth,
        expected_direction_count=chosen_summary.expected_direction_count,
        inverted_direction_count=chosen_summary.inverted_direction_count,
        capturing_indicators=chosen_names,
        non_capturing_indicators=tuple(
            row.name for row in chosen.best_rows if row.name not in chosen_name_set
        ),
        direction_unstable=tuple(sorted(resolved.unstable)),
        direction_checks=resolved.checks,
        level_summaries=summaries,
        level_rows=ordered,
        dropped_at_finer_levels=tuple(dropped_by_level),
        capture_rule=_capture_rule_at(capture_bar),
        choice_rule=CHOICE_RULE,
        rationale=RATIONALE,
    )


__all__ = [
    "CAPTURE_BAR",
    "CAPTURE_RULE",
    "CHOICE_RULE",
    "DEGENERATE_MEAN_ABS",
    "RATIONALE",
    "FinerLevelDrops",
    "FittedDirection",
    "IndicatorCaptureRow",
    "IndicatorDirectionCheck",
    "IndicatorDrop",
    "LevelSummary",
    "SensitivityChoice",
    "SensitivityLevelRow",
    "best_grid_row",
    "captures_level",
    "fitted_direction",
    "row_is_degenerate",
    "select_sensitivity_level",
]
