"""Generic paired peak/trough turn detector for any time series (#4804, Plan 22).

The owner's ruling (2026-10-03, Plan 22): the granularity a period set needs must
come from an **algorithm over the price series**, not from hand-entered pins.
This module is that algorithm, and nothing else — no asset names, no calendar,
no engine call, no ``nautilus_trader`` import (SDCA core rule), no pandas.

**It reads like ``cycle_windows.py`` and is interchangeable with it.** The
documented pin factories (``SdcaCycleWindows.gold_v1()`` and friends) hand-enter
peaks and troughs; the owner's approved set A is six such pins. This detector
produces the *same type* from a price series, so a scoring target chosen by hand
and one chosen by algorithm can be swapped without touching the consumer:
``turns_to_cycle_windows`` returns an ``SdcaCycleWindows``. Windows remain what
the ``cycle_windows`` docstring says they are — a **scoring target** for
indicator weights, not an execution period — and this module adds no exposure
floor of any kind.

**Two filters, and one of them is the knob.** ``min_move_pct`` (magnitude) and
``min_separation_days`` (time) are the only rules that can remove a turn.
``min_move_pct`` is the sensitivity crank: lower it and smaller swings survive
as their own turns, so the turn count rises. ``tests/dq/strategies/sdca/
test_turn_detect.py`` pins that at three levels, because an inverted or
saturated knob is the failure mode that matters.

**The algorithm, in four steps.**

1. **Candidates — a symmetric confirmation rule.** A bar is a **peak** when its
   close attains the maximum of its ±``confirmation_bars`` neighbourhood, at
   least one bar in that neighbourhood is strictly below it, and it is the
   *first* bar of that neighbourhood to attain the maximum; **trough**
   symmetrically. Both neighbours must exist, so the first and last bars are
   never candidates. This is ``period_optimize``'s derivation rule, repeated
   here rather than imported: that module's width is a function of a horizon
   (``confirmation_days``), which this detector does not have, and it must not
   inherit a half-width chosen by a window grid. Requiring the *first*
   attainment is what keeps a flat plateau to a single candidate — a later bar of
   the plateau attains the same extreme, and an earlier bar of its own
   neighbourhood equals it, which rejects it. A wholly flat or monotone series
   therefore produces **no** candidate at all, which raises rather than quietly
   returning nothing.

2. **Zigzag collapse — one kept turn, one live direction, one provisional
   pivot.** Walking the candidates in order, the walk holds the last *kept*
   turn, the *direction* of the leg it is currently seeking (an up leg ends at a
   peak, a down leg at a trough), and the *pivot* — the most extreme corner of
   the leg in progress. A pivot is **provisional**: it is only a turn once a
   reversal confirms it.

   - A corner of the live leg's **own** kind continues that leg, so the more
     extreme of it and the pivot stands — the higher peak, or the lower trough —
     and the other is recorded as ``superseded_by_stronger_turn``. On equal
     prices the **earlier** candidate stands, so the choice never depends on
     which one the loop reached first.
   - A corner of the **opposite** kind is a **reversal**, and it is resolved in
     this order:
     1. *Did the leg from the last kept turn to the pivot clear both filters?*
        (move ≥ ``min_move_pct`` **and** separation ≥ ``min_separation_days``.)
        If yes, the pivot is confirmed as a turn, it becomes the last kept turn,
        the direction flips, and the reversal corner becomes the new pivot.
     2. If no, the pivot is **not** a turn and is recorded against the filter
        that refused it (``leg_below_magnitude``, or ``leg_below_separation`` when
        the move was big enough but arrived too soon). Magnitude is reported
        first: a leg too small to be a move at all is the more fundamental
        failure, and its short separation is a consequence of it.
     3. Then the reversal corner competes with the last kept turn **of its own
        kind** — the same zig-zag rule as a continuing leg. A reversal that is
        more extreme than the turn it would displace replaces it (and the
        displaced turn is recorded); one that is shallower is recorded against
        the turn that stood, so nothing is ever discarded silently.

   Ordering matters: step 1 is settled **before** step 3, because a reversal that
   fell beyond the last kept turn invalidates that turn as a leg origin — the
   sequence ``trough 100 → peak 200 → trough 90`` is three turns, and settling
   step 3 first would discard the 100 trough that a 100% up-leg legitimately
   confirmed.

3. **The seed, and the trailing leg.** The **first** candidate is the seed turn:
   it has no preceding leg to qualify, so it stands until a more extreme
   same-kind corner displaces it (step 2.3 is the only rule that can). The
   **last** candidate's leg is never settled by a reversal, because there is
   none, so it is evaluated once against both filters exactly like every other
   leg: it either stands as a turn or is recorded as filtered out. Nothing is
   held open on trust.

4. **Pairing, enforced structurally.** Turns come out strictly alternating
   peak/trough, and a trailing turn with **no opposite partner** is dropped and
   recorded as ``dangling_no_partner``. ``TurnSet`` re-checks the invariant in a
   validator: an odd number of turns is legitimate — odd alternation still gives
   every peak an adjacent trough, which is why the owner's approved set A starts
   and ends on a trough — but a one-turn set is malformed, two same-kind turns in
   a row are malformed, and out-of-order or repeated pins are malformed. This is
   owner ruling 2, not a style preference: a malformed set would make the scoring
   target ambiguous.

**Two properties worth stating because they are what make the walk safe.**

- *A same-kind replacement can never break a filter.* A higher peak (or lower
  trough) is further from the same preceding turn in the same direction, so
  replacing a kept turn only enlarges that leg, and the replacement is always
  later in time so its separation only grows. That is why step 2.3 needs no
  re-check.
- *Every candidate is accounted for exactly once.* Each candidate either stands
  in ``turns`` or is written down in ``dropped`` with its reason — never both,
  never neither. ``len(turns) + len(dropped)`` therefore equals the number of
  candidates, which is what lets a shorter turn set be explained from the output
  alone.

**Nothing is invented.** ``prominence`` is derived, not asserted: a turn's is the
move to its adjacent turn(s) of opposite kind, in percent, and an interior turn
reports the **weaker** of its two legs — so prominence is never below
``min_move_pct``, which is why it is a consistency read and not a ranking
statistic.

**Degenerate input raises.** Mismatched lengths, fewer than two bars, fewer than
``2 * confirmation_bars + 1`` bars, non-ascending or repeated dates, a
non-finite or non-positive price, or no candidate turn at all each raise
``ValueError`` — never an ``IndexError``, and never a bare ``assert`` that
vanishes under ``python -O``. A series whose turns are *all* filtered out is not
degenerate: it returns an empty ``TurnSet`` with every candidate recorded.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from digiquant.strategies.sdca.cycle_windows import CycleKind, CycleWindow, SdcaCycleWindows

# Turns speak the vocabulary the pin factories already use: one enum, not two.
# Re-exported under the detector's own name so a reader of this module is not left
# wondering whether ``TurnKind`` is a different type.
TurnKind = CycleKind

# Half-width of the ±confirmation neighbourhood a candidate must dominate, in bars.
# Small on purpose: this is a *local extremum* test, not a cycle test, and the
# magnitude filter is what decides cycle scale.
DEFAULT_CONFIRMATION_BARS = 5

# Half-width the coverage statistic is measured at when a caller does not ask for
# another: the same ±45 days the pin factories use, so an algorithmic set and a
# hand-entered one are comparable on coverage without a second knob.
DEFAULT_WINDOW_HALF_WIDTH_DAYS = 45

# Frozen defaults for the two filters (owner ruling 3): 15% is the coarse default
# and 45 days is the swing-scale minimum separation between two kept turns.
DEFAULT_MIN_MOVE_PCT = 15.0
DEFAULT_MIN_SEPARATION_DAYS = 45

_UP = 1
_DOWN = -1


class DropReason(StrEnum):
    """Why a candidate turn did not survive into the paired set.

    Values are recorded data — they are serialized into ``dropped`` and read back
    by later analysis — so they are stable lowercase strings, never enum reprs.
    """

    SUPERSEDED_BY_STRONGER_TURN = "superseded_by_stronger_turn"
    LEG_BELOW_MAGNITUDE = "leg_below_magnitude"
    LEG_BELOW_SEPARATION = "leg_below_separation"
    DANGLING_NO_PARTNER = "dangling_no_partner"


class TurnDetectionConfig(BaseModel):
    """The detector's knobs. Frozen: a run's settings are part of its provenance.

    The two filters below are the only rules that can remove a turn; the
    confirmation width only decides what counts as a candidate at all, and the
    window half-width changes nothing but the reported coverage.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    min_move_pct: float = Field(
        default=DEFAULT_MIN_MOVE_PCT,
        ge=0.0,
        description=(
            "Magnitude filter: the smaller a kept turn's move to its adjacent turn of opposite "
            "kind may be, as a percent. This is the sensitivity crank — lower it and smaller "
            "swings survive as their own turns, so the turn count rises"
        ),
    )
    min_separation_days: int = Field(
        default=DEFAULT_MIN_SEPARATION_DAYS,
        ge=1,
        description=(
            "Time filter: the fewest calendar days two kept turns may be apart. 1 admits "
            "consecutive-day turns; the default refuses a swing that resolves inside a quarter"
        ),
    )
    confirmation_bars: int = Field(
        default=DEFAULT_CONFIRMATION_BARS,
        ge=1,
        description=(
            "Half-width, in bars, of the ±neighbourhood a candidate must dominate to be a local "
            "extremum. Larger values ignore shorter swings before either filter sees them"
        ),
    )
    window_half_width_days: int = Field(
        default=DEFAULT_WINDOW_HALF_WIDTH_DAYS,
        ge=0,
        description=(
            "Half-width, in days, of the coverage windows the window_day_share statistic is "
            "measured at. Not a detection filter — it changes only the reported coverage"
        ),
    )


class Turn(BaseModel):
    """One detected turn: a corner of the zigzag that survived both filters."""

    model_config = ConfigDict(frozen=True, strict=True)

    kind: CycleKind = Field(..., description="Peak (sell side) or trough (buy side), as detected")
    pin: date = Field(..., description="Calendar date of the bar at the turn")
    price: float = Field(
        ..., gt=0.0, description="Close at the pin bar, in the input series' own price units"
    )
    prominence: float = Field(
        ...,
        ge=0.0,
        description=(
            "The weaker of the moves to this turn's adjacent turn(s) of opposite kind, as a "
            "percent. An interior turn has two legs and reports the smaller; a first or last "
            "turn has one. Never below min_move_pct, so it reads as a consistency check rather "
            "than a ranking statistic"
        ),
    )
    index: int = Field(..., ge=0, description="0-based index of the pin bar in the input series")


class DroppedTurn(BaseModel):
    """A candidate that did not survive, and the reason it did not.

    ``survivor_pin`` is the pin that stood in its place: the more extreme corner
    of a collapsed pair, the last kept turn a refused leg pointed back to, or the
    last kept turn a shallower reversal failed to displace. It is ``None`` only
    for ``dangling_no_partner``, where nothing replaced the turn.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    kind: CycleKind = Field(..., description="Kind the candidate had when it was refused")
    pin: date = Field(..., description="Calendar date of the candidate's bar")
    price: float = Field(..., gt=0.0, description="Close at the candidate's bar")
    index: int = Field(..., ge=0, description="0-based index of the candidate's bar")
    reason: DropReason = Field(..., description="Why the candidate did not survive")
    survivor_pin: date | None = Field(
        ..., description="Pin of the turn that stood instead, or None when nothing replaced it"
    )


class TurnSet(BaseModel):
    """Paired turns plus the receipt for every candidate that did not survive.

    ``turns`` is strictly alternating and every peak has an adjacent trough (owner
    ruling 2). ``dropped`` explains the rest, so a set can be audited without
    re-running the detector.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    turns: tuple[Turn, ...] = Field(
        ..., description="Kept turns in chronological order, strictly alternating peak/trough"
    )
    dropped: tuple[DroppedTurn, ...] = Field(
        ..., description="Every refused candidate, chronological, with its reason"
    )
    min_move_pct: float = Field(..., ge=0.0, description="Magnitude filter that produced this set")
    min_separation_days: int = Field(..., ge=1, description="Time filter that produced this set")
    confirmation_bars: int = Field(
        ..., ge=1, description="Confirmation half-width, in bars, that produced this set"
    )
    bars: int = Field(..., ge=1, description="Length of the input price series")
    days_in_span: int = Field(
        ..., ge=1, description="Inclusive calendar days from the first input date to the last"
    )
    window_half_width_days: int = Field(
        ..., ge=0, description="Half-width the coverage statistic below was measured at"
    )
    window_day_share: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Share of the input calendar's days that fall inside at least one ±"
            "window_half_width_days window around a kept pin, windows clipped to the calendar"
        ),
    )

    @model_validator(mode="after")
    def _paired(self) -> TurnSet:
        """Owner ruling 2 as a validator: strictly alternating, and never a lone turn."""
        indexes = [turn.index for turn in self.turns]
        if indexes != sorted(indexes) or len(set(indexes)) != len(indexes):
            raise ValueError(f"turn indexes must be strictly ascending, got {indexes}")
        kinds = [turn.kind for turn in self.turns]
        if len(kinds) == 1:
            raise ValueError(
                "a single turn cannot pair: every peak needs an adjacent trough, so one turn "
                "is malformed and must be dropped with a dangling_no_partner reason"
            )
        for earlier, later in zip(kinds, kinds[1:], strict=False):
            if earlier is later:
                raise ValueError(
                    f"turn kinds must strictly alternate peak/trough, got {earlier} twice in a row"
                )
        return self

    @property
    def n_peaks(self) -> int:
        """Peaks in the kept set — the sell side of the pairing."""
        return sum(1 for turn in self.turns if turn.kind is CycleKind.PEAK)

    @property
    def n_troughs(self) -> int:
        """Troughs in the kept set — the buy side of the pairing."""
        return sum(1 for turn in self.turns if turn.kind is CycleKind.TROUGH)


@dataclass(frozen=True, slots=True)
class _Candidate:
    """One candidate corner, before filtering. Not part of the public surface."""

    index: int
    pin: date
    kind: CycleKind
    price: float


def _validate_series(
    dates: Sequence[date], prices: Sequence[float], config: TurnDetectionConfig
) -> None:
    """Refuse degenerate input before any indexing happens, with the reason named."""
    if len(dates) != len(prices):
        raise ValueError(
            "detect_turns requires dates and prices of the same length, "
            f"got {len(dates)} dates and {len(prices)} prices"
        )
    if len(dates) < 2:
        raise ValueError(f"detect_turns requires at least 2 bars, got {len(dates)}")
    needed = 2 * config.confirmation_bars + 1
    if len(dates) < needed:
        raise ValueError(
            f"detect_turns requires at least {needed} bars to confirm a turn with "
            f"confirmation_bars={config.confirmation_bars}, got {len(dates)}"
        )
    for earlier, later in zip(dates, dates[1:], strict=False):
        if earlier >= later:
            raise ValueError(
                f"detect_turns requires strictly ascending dates, got {earlier} then {later}"
            )
    for index, price in enumerate(prices):
        value = float(price)
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(
                "detect_turns requires a finite, positive price at every bar (a move is a "
                f"percentage of the earlier price), got {price} at index {index}"
            )


def _candidates(
    dates: Sequence[date], prices: Sequence[float], confirm: int
) -> tuple[_Candidate, ...]:
    """Local extrema of the series, by the symmetric ±``confirm`` rule (step 1).

    A peak is the *first* bar of its neighbourhood to attain that neighbourhood's
    maximum, with at least one bar in it strictly lower; a trough is the symmetric
    rule. Both neighbours must exist, so the first and last bars are never
    candidates, and the first-attainment rule keeps a flat plateau to a single
    candidate.
    """
    values = [float(price) for price in prices]
    found: list[_Candidate] = []
    for index in range(confirm, len(values) - confirm):
        window = values[index - confirm : index + confirm + 1]
        here = values[index]
        # ``window.index(here) == confirm`` reads "no earlier bar of this neighbourhood attains
        # the same value" — the first-attainment rule that keeps a plateau to one corner.
        if here == max(window) and any(p < here for p in window) and window.index(here) == confirm:
            found.append(_Candidate(index, dates[index], CycleKind.PEAK, here))
        elif (
            here == min(window) and any(p > here for p in window) and window.index(here) == confirm
        ):
            found.append(_Candidate(index, dates[index], CycleKind.TROUGH, here))
    return tuple(found)


def _move_pct(earlier: _Candidate, later: _Candidate) -> float:
    """Absolute move between two turns, as a percent of the earlier turn's price."""
    return abs(later.price - earlier.price) / earlier.price * 100.0


def _separation_days(earlier: _Candidate, later: _Candidate) -> int:
    """Calendar days from one turn to another; turns are index-ordered, so this is >= 0."""
    return (later.pin - earlier.pin).days


def _stronger(kept: _Candidate, challenger: _Candidate) -> tuple[_Candidate, _Candidate]:
    """The stronger of two same-kind candidates as ``(winner, loser)``.

    The higher peak, or the lower trough. Equal prices keep the **earlier**
    candidate, so the outcome never depends on which one the walk reached first.
    """
    if kept.kind is not challenger.kind:
        raise ValueError(
            f"cannot rank a {kept.kind} candidate against a {challenger.kind} one: only same-kind "
            "turns compete for the same place in the zigzag"
        )
    if kept.kind is CycleKind.PEAK:
        return (kept, challenger) if kept.price >= challenger.price else (challenger, kept)
    return (kept, challenger) if kept.price <= challenger.price else (challenger, kept)


def _leg_failure(
    kept: _Candidate, pivot: _Candidate, config: TurnDetectionConfig
) -> DropReason | None:
    """``None`` when the leg clears both filters, else the reason it did not.

    Magnitude is reported first: a leg too small to be a move at all is the more
    fundamental failure, and its short separation is a consequence of it.
    """
    if _move_pct(kept, pivot) < config.min_move_pct:
        return DropReason.LEG_BELOW_MAGNITUDE
    if _separation_days(kept, pivot) < config.min_separation_days:
        return DropReason.LEG_BELOW_SEPARATION
    return None


def _drop(candidate: _Candidate, reason: DropReason, survivor: _Candidate | None) -> DroppedTurn:
    return DroppedTurn(
        kind=candidate.kind,
        pin=candidate.pin,
        price=candidate.price,
        index=candidate.index,
        reason=reason,
        survivor_pin=survivor.pin if survivor is not None else None,
    )


def _walk(
    candidates: Sequence[_Candidate], config: TurnDetectionConfig
) -> tuple[list[_Candidate], list[DroppedTurn]]:
    """Zigzag collapse (steps 2 and 3 of the module docstring).

    Holds at most one kept turn, one leg direction and one provisional pivot, so
    a same-kind replacement can never leave two same-kind turns adjacent: the
    alternation invariant is structural in the walk, not repaired afterwards.
    """
    turns: list[_Candidate] = []
    dropped: list[DroppedTurn] = []
    pivot: _Candidate | None = None
    direction = 0  # +1: an up leg is in progress (its corner is a peak)

    for candidate in candidates:
        if not turns:
            # The seed: no preceding leg to qualify, so it stands until displaced.
            turns.append(candidate)
            direction = _UP if candidate.kind is CycleKind.TROUGH else _DOWN
            continue
        leg_kind = CycleKind.PEAK if direction > 0 else CycleKind.TROUGH
        if candidate.kind is leg_kind:
            # The leg continues: the more extreme corner of it stands.
            if pivot is None:
                pivot = candidate
            else:
                winner, loser = _stronger(pivot, candidate)
                pivot = winner
                dropped.append(_drop(loser, DropReason.SUPERSEDED_BY_STRONGER_TURN, winner))
            continue
        # A reversal. Settle the leg first: a fall beyond the last kept turn
        # invalidates that turn as a leg origin, so the pivot is judged against
        # the turn as it stands now.
        if pivot is not None:
            failure = _leg_failure(turns[-1], pivot, config)
            if failure is None:
                turns.append(pivot)
                pivot = candidate
                direction = _DOWN if direction > 0 else _UP
                continue
            dropped.append(_drop(pivot, failure, turns[-1]))
            pivot = None
        winner, loser = _stronger(turns[-1], candidate)
        turns[-1] = winner
        dropped.append(_drop(loser, DropReason.SUPERSEDED_BY_STRONGER_TURN, winner))

    if pivot is not None:
        # Trailing leg: judged once against both filters, exactly like every other.
        failure = _leg_failure(turns[-1], pivot, config)
        if failure is None:
            turns.append(pivot)
        else:
            dropped.append(_drop(pivot, failure, turns[-1]))
    while len(turns) == 1:
        dropped.append(_drop(turns[-1], DropReason.DANGLING_NO_PARTNER, None))
        turns.pop()
    return turns, dropped


def _window_day_share(
    pins: Sequence[date], half_width_days: int, span_start: date, span_end: date
) -> float:
    """Share of the input calendar's days covered by ±``half_width_days`` pin windows.

    Intervals are merged before summing, so overlapping windows count their shared
    days once and the result cannot exceed 1.0. Windows are clipped to the input
    calendar: coverage beyond the series is not calendar the caller has.
    """
    span_days = (span_end - span_start).days + 1
    if not pins or span_days <= 0:
        return 0.0
    offset = timedelta(days=half_width_days)
    clipped = sorted((max(pin - offset, span_start), min(pin + offset, span_end)) for pin in pins)
    covered = 0
    current_start, current_end = clipped[0]
    for start, end in clipped[1:]:
        if start <= current_end + timedelta(days=1):
            current_end = max(current_end, end)
            continue
        covered += (current_end - current_start).days + 1
        current_start, current_end = start, end
    covered += (current_end - current_start).days + 1
    return min(covered / span_days, 1.0)


def _build_turns(turns: Sequence[_Candidate]) -> tuple[Turn, ...]:
    """Attach each turn's prominence — the weaker of its adjacent legs."""
    legs = [_move_pct(turns[position], turns[position + 1]) for position in range(len(turns) - 1)]
    built: list[Turn] = []
    for position, turn in enumerate(turns):
        adjacent = [legs[i] for i in (position - 1, position) if 0 <= i < len(legs)]
        built.append(
            Turn(
                kind=turn.kind,
                pin=turn.pin,
                price=turn.price,
                prominence=min(adjacent),
                index=turn.index,
            )
        )
    return tuple(built)


def detect_turns(
    dates: Sequence[date],
    prices: Sequence[float],
    config: TurnDetectionConfig | None = None,
) -> TurnSet:
    """Detect paired peak/trough turns in any price series.

    The algorithm is the module docstring; this is its callable form. It reads
    only ``dates`` and ``prices`` — no asset knowledge, no calendar convention, no
    engine call. Deterministic: the same inputs return an equal ``TurnSet`` every
    time, and the caller's sequences are never mutated.
    """
    settings = config or TurnDetectionConfig()
    _validate_series(dates, prices, settings)
    candidates = _candidates(dates, prices, settings.confirmation_bars)
    if not candidates:
        raise ValueError(
            "detect_turns found no candidate turn in this series: a flat or monotone series has "
            "no local extremum to pair, so there is no cycle structure to report"
        )
    kept, dropped = _walk(candidates, settings)
    built = _build_turns(kept)
    return TurnSet(
        turns=built,
        dropped=tuple(sorted(dropped, key=lambda record: record.index)),
        min_move_pct=settings.min_move_pct,
        min_separation_days=settings.min_separation_days,
        confirmation_bars=settings.confirmation_bars,
        bars=len(prices),
        days_in_span=(dates[-1] - dates[0]).days + 1,
        window_half_width_days=settings.window_half_width_days,
        window_day_share=_window_day_share(
            [turn.pin for turn in built], settings.window_half_width_days, dates[0], dates[-1]
        ),
    )


def turns_to_cycle_windows(
    turns: TurnSet | Sequence[Turn], half_width_days: int
) -> SdcaCycleWindows:
    """Convert detected turns into ±``half_width_days`` cycle windows.

    The result is an ``SdcaCycleWindows`` — the same type the documented pin
    factories return — so an algorithmic pin set and a hand-entered one are
    interchangeable wherever a scoring target is consumed. ``SdcaCycleWindows
    .kind_on`` returns the first matching window, so a date inside two overlapping
    windows resolves to the **earlier** pin; window names therefore carry the
    turn's position to make that order explicit rather than incidental.
    """
    if half_width_days < 1:
        raise ValueError(f"half_width_days must be at least 1, got {half_width_days}")
    pins: tuple[Turn, ...] = tuple(turns.turns) if isinstance(turns, TurnSet) else tuple(turns)
    if not pins:
        raise ValueError(
            "turns_to_cycle_windows requires at least one turn; an empty set is a report that "
            "this series yielded no paired structure, not a window set"
        )
    offset = timedelta(days=half_width_days)
    windows: list[CycleWindow] = []
    previous: Turn | None = None
    for position, turn in enumerate(pins):
        if previous is not None:
            if turn.kind is previous.kind:
                raise ValueError(
                    "turn kinds must strictly alternate peak/trough, got "
                    f"{turn.kind} twice in a row (pins {previous.pin} and {turn.pin})"
                )
            if turn.index <= previous.index:
                raise ValueError(
                    f"turn indexes must be strictly ascending, got {previous.index} then {turn.index}"
                )
        previous = turn
        windows.append(
            CycleWindow(
                name=f"turn_{position:03d}_{turn.kind}_{turn.pin:%Y%m%d}_pm{half_width_days}",
                kind=turn.kind,
                start=turn.pin - offset,
                end=turn.pin + offset,
            )
        )
    return SdcaCycleWindows(windows=tuple(windows))


__all__ = [
    "DEFAULT_CONFIRMATION_BARS",
    "DEFAULT_MIN_MOVE_PCT",
    "DEFAULT_MIN_SEPARATION_DAYS",
    "DEFAULT_WINDOW_HALF_WIDTH_DAYS",
    "DropReason",
    "DroppedTurn",
    "Turn",
    "TurnDetectionConfig",
    "TurnKind",
    "TurnSet",
    "detect_turns",
    "turns_to_cycle_windows",
]
