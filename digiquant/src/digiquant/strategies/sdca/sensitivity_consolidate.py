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

1. An indicator **captures** a level iff its best grid row has
   ``separation >= capture_bar`` (``CAPTURE_BAR`` = 0.5 z-units is the frozen
   default and the bar every count below is read at unless the caller supplies
   another), is **sign-correct** (``separation > 0``) and is **not degenerate**
   (one window side's mean never leaves the +/-``DEGENERATE_MEAN_ABS`` dead zone).
   ``abs()`` is never applied to the metric: a leg that votes rich at the bottoms
   must not be rewarded for doing so loudly. The bar is inclusive at exactly
   ``capture_bar``.
2. A level **qualifies** iff its capture count is at least as large as at *every*
   coarser level — it loses nothing relative to the coarser calibrations. The
   coarsest level therefore always qualifies, so a ladder is never undecidable.
3. The chosen level is the **most sensitive qualifier** (the smallest
   ``min_move_pct``, i.e. the most turns) and, among qualifiers, the one with the
   **largest capture count**; where two qualifiers capture the *same* count the
   **coarser** one wins: fewer turns is the more robust pin set. That tie-break
   is a real decision rather than a formality — a ladder can easily have two
   levels that tie.
4. For every level **finer** than the chosen one, the indicators that captured at
   the chosen level and fail there are reported with both separations and the
   reason. That table is the evidence for the choice: it names exactly which
   votes the finer granularity costs.

The degenerate rule is Plan-19 Ruling 1, whose dead-zone width (0.06) is restated
here as a plain constant: the harness that owns it
(``digiquant/scripts/fit_gold_indicators.py``) is a research script, not an
importable package module, so the two cannot share a definition. Both are frozen;
change one and you must change the other.
"""

from __future__ import annotations

from collections.abc import Sequence

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
        "An indicator CAPTURES a level iff its best grid row has separation >= "
        f"{capture_bar} z-units AND is sign-correct (separation > 0, abs() never "
        f"applied) AND is not degenerate (neither window side's mean inside "
        f"+/-{DEGENERATE_MEAN_ABS}). An unscoreable leg never captures."
    )


CAPTURE_RULE = _capture_rule_at(CAPTURE_BAR)

CHOICE_RULE = (
    "Sensitivity crank: a lower min_move_pct yields MORE turns, so a smaller "
    "min_move_pct is the MORE SENSITIVE (finer) calibration. A level QUALIFIES "
    "iff its capture count is at least as large as at every COARSER level (it "
    "loses no indicator relative to the coarser calibrations); the coarsest "
    "level therefore always qualifies. Among qualifiers take the one with the "
    "largest capture count, and where two qualifiers capture the SAME count "
    "prefer the COARSER one (fewer turns, more robust)."
)

RATIONALE = (
    "the most sensitive granularity the indicators can still capture: finer pin "
    "sets are harder scoring targets, so sensitivity is taken as far as the "
    "indicator evidence carries it and no further"
)


class IndicatorCaptureRow(BaseModel):
    """One indicator's BEST grid row at one level, scored against that level's windows.

    "Best" is the caller's highest ``separation`` row (ties to the shorter
    window, the harness parsimony rule), so if this row misses the capture bar no
    other row of the same indicator can reach it.

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
            "at the bottoms. None when the row could not reach both window sides"
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
    def captures(self) -> bool:
        """Does this row capture its level at the FROZEN bar? (the 0.5 default view)

        This is the frozen default's own reading of the row. A decision made at
        another bar must use :meth:`captures_at` instead — otherwise the count,
        the choice and the evidence table would be decided at one bar and labelled
        with another.
        """
        return self.captures_at(CAPTURE_BAR)

    def captures_at(self, capture_bar: float) -> bool:
        """Does this row capture its level at ``capture_bar``?"""
        return captures_level(self, capture_bar=capture_bar)


class SensitivityLevelRow(BaseModel):
    """One rung of the sensitivity ladder: a turn count and every indicator's read on it.

    ``min_move_pct`` is the detector's magnitude filter, so a SMALLER value is
    the more sensitive calibration and yields more turns. The capture count is
    derived (never stored) so it can never disagree with the rows it summarises.

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
        ..., description="Every indicator scored at this level, each with its best grid row"
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
        names = [row.name for row in self.indicators]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise ValueError(
                f"duplicate indicator names at min_move_pct={self.min_move_pct}: {repeated} — "
                "one row per indicator, or the capture count double-counts"
            )
        return self

    @property
    def capturing(self) -> tuple[str, ...]:
        """Names capturing at the FROZEN bar (the 0.5 default view); caller order."""
        return self.capturing_at(CAPTURE_BAR)

    def capturing_at(self, capture_bar: float) -> tuple[str, ...]:
        """Names of the indicators that capture this level at ``capture_bar``."""
        return tuple(row.name for row in self.indicators if row.captures_at(capture_bar))

    @property
    def capture_count(self) -> int:
        """How many indicators capture this level at the FROZEN bar."""
        return self.capture_count_at(CAPTURE_BAR)

    def capture_count_at(self, capture_bar: float) -> int:
        """How many indicators capture this level at ``capture_bar``.

        The bar-aware form is what :func:`select_sensitivity_level` reads, so a
        choice made at a caller-supplied bar reports that bar's counts. The
        ``capture_count`` property above stays the frozen 0.5 view.
        """
        return sum(1 for row in self.indicators if row.captures_at(capture_bar))


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
            "Why it fails here, most fundamental first: unscoreable, negative (sign-flipped), "
            "degenerate (one side dead), below the capture bar. Every comparison is at the "
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
            "How many indicators capture the finer level, at the bar this choice was made at"
        ),
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
    """The consolidation verdict: which level, how many captures, and what finer costs."""

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
        ..., ge=0, description="How many indicators capture the chosen level"
    )
    capturing_indicators: tuple[str, ...] = Field(
        ..., description="Indicators capturing the chosen level, in level order"
    )
    non_capturing_indicators: tuple[str, ...] = Field(
        ..., description="Indicators scored at the chosen level that do not capture it"
    )
    level_rows: tuple[SensitivityLevelRow, ...] = Field(
        ..., description="Every level, ordered coarsest first"
    )
    dropped_at_finer_levels: tuple[FinerLevelDrops, ...] = Field(
        ...,
        description=(
            "One row per level FINER than the chosen one, coarsest finer level first: the "
            "owner-facing evidence table"
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


def captures_level(row: IndicatorCaptureRow, *, capture_bar: float = CAPTURE_BAR) -> bool:
    """The frozen capture test, evaluated AT ``capture_bar``.

    Three conjuncts, each the owner's own wording: the separation reaches the bar
    (inclusive), the vote runs the right way, and neither window side is dead.
    ``capture_bar`` is a real input, not a label — callers that consolidate at
    another bar get that bar's verdicts.
    """
    if row.separation is None or capture_bar <= 0.0:
        return False
    # `separation > 0.0` is the sign-correctness conjunct. It is provably implied by
    # the bar conjunct above for every positive bar (separation >= capture_bar > 0),
    # so it carries no verdict today and will read as dead code to the next reader.
    # It is retained deliberately: it is the one line in this body that says a vote
    # which runs backwards is NOT rescued by magnitude, which is the failure mode
    # `abs()` would introduce. Delete it as redundant and the next edit that lowers
    # or symmetrises the bar (`abs(separation) >= capture_bar`) admits every mirrored
    # leg with no remaining trace of the rule that forbade it.
    return row.separation >= capture_bar and row.separation > 0.0 and not row.degenerate


def _drop_reason(row: IndicatorCaptureRow | None, capture_bar: float, min_move_pct: float) -> str:
    """Why this indicator fails to capture the finer level, most fundamental failure first.

    Absent, then unscoreable, then negative (a vote that ran backwards — magnitude
    cannot rescue it), then degenerate (one side dead), then simply short of the
    bar. ``row is None`` is a finer level that never scored the indicator at all.
    """
    if row is None:
        return (
            f"not scored at this level: no capture row for this indicator at "
            f"min_move_pct={min_move_pct}, so it cannot capture here"
        )
    if row.separation is None:
        return f"unscoreable at this level: {row.reason or 'no valid z reached both window sides'}"
    if row.separation <= 0.0:
        return (
            f"negative separation ({row.separation:+.4f}): the z votes rich at the bottoms, and "
            "abs() is never applied to this metric, so magnitude cannot rescue a backwards vote"
        )
    if row.degenerate:
        return (
            f"degenerate: separation {row.separation:+.4f} rests on a dead side (one window "
            f"mean inside +/-{DEGENERATE_MEAN_ABS}), so the pass is one-sided"
        )
    return f"below the capture bar: separation {row.separation:+.4f} < {capture_bar}"


def _qualifying(
    ordered: Sequence[SensitivityLevelRow], *, capture_bar: float
) -> tuple[SensitivityLevelRow, ...]:
    """Levels whose capture count loses nothing against every coarser level.

    Walked coarsest-first, which is what makes "less sensitive" mean "already
    visited": the running best is the max capture count strictly coarser than the
    level under test, and the coarsest level has none, so it always qualifies.

    The running max is over EVERY coarser level, not just the one before it. A
    ladder may dip and recover (counts [4, 1, 3]), and a recovered level must not
    be admitted by beating only the rung it recovered from — it still has to hold
    the best count any coarser level reached.
    """
    qualifying: list[SensitivityLevelRow] = []
    best_coarser = -1
    for level in ordered:
        if level.capture_count_at(capture_bar) >= best_coarser:
            qualifying.append(level)
        best_coarser = max(best_coarser, level.capture_count_at(capture_bar))
    return tuple(qualifying)


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
    verdict, every capture count, the qualifying set, the chosen level and every
    drop reason is evaluated AT that bar, and the returned choice records the bar
    it was actually made at. ``CAPTURE_BAR`` (0.5) remains the frozen default; a
    bar supplied here overrides it rather than merely annotating a 0.5 decision.

    Pure: no I/O, no series, no asset. The caller supplies the numbers it scored.
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

    qualifying = _qualifying(ordered, capture_bar=capture_bar)
    if not qualifying:  # unreachable: the coarsest level always qualifies
        raise ValueError(
            "no level qualifies: the coarsest level has no coarser level to lose against, so "
            "an empty qualifying set means the ladder is malformed"
        )
    # Among qualifiers: the largest capture count wins, and the coarser level
    # whenever the counts tie — the pair sorts capture count first, magnitude
    # second. Both counts are read at ``capture_bar``, so a caller-supplied bar
    # decides the choice rather than only annotating it.
    chosen = max(
        qualifying,
        key=lambda level: (level.capture_count_at(capture_bar), level.min_move_pct),
    )
    chosen_names = set(chosen.capturing_at(capture_bar))

    finer_rows = tuple(level for level in ordered if level.min_move_pct < chosen.min_move_pct)
    qualifying_pcts = {level.min_move_pct for level in qualifying}
    dropped_by_level: list[FinerLevelDrops] = []
    for level in finer_rows:
        finer_names = set(level.capturing_at(capture_bar))
        by_name = {row.name: row for row in level.indicators}
        drops = tuple(
            IndicatorDrop(
                name=name,
                separation_at_chosen_level=next(
                    row.separation for row in chosen.indicators if row.name == name
                ),
                separation_at_finer_level=(
                    None if by_name.get(name) is None else by_name[name].separation
                ),
                reason=_drop_reason(by_name.get(name), capture_bar, level.min_move_pct),
            )
            for name in sorted(chosen_names - finer_names)
        )
        dropped_by_level.append(
            FinerLevelDrops(
                min_move_pct=level.min_move_pct,
                n_turns=level.n_turns,
                capture_count=level.capture_count_at(capture_bar),
                qualifies=level.min_move_pct in qualifying_pcts,
                dropped=drops,
            )
        )

    return SensitivityChoice(
        capture_bar=capture_bar,
        chosen_min_move_pct=chosen.min_move_pct,
        chosen_n_turns=chosen.n_turns,
        capture_count=chosen.capture_count_at(capture_bar),
        capturing_indicators=chosen.capturing_at(capture_bar),
        non_capturing_indicators=tuple(
            row.name for row in chosen.indicators if not row.captures_at(capture_bar)
        ),
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
    "IndicatorCaptureRow",
    "IndicatorDrop",
    "SensitivityChoice",
    "SensitivityLevelRow",
    "captures_level",
    "row_is_degenerate",
    "select_sensitivity_level",
]
