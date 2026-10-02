"""Generic two-horizon (medium / long) DCA period optimizer (#4804, Plan 20).

The owner's premise: if the buy and sell *periods* are well identified, returns
and risk-adjusted returns improve. This module makes that testable without
touching the SDCA engine: it discovers candidate period windows **from the price
series itself**, scores each candidate with the ``perfect_strategy`` oracle
under a frozen objective, and combines a medium and a long set.

**Frozen objective** (owner-ruled 2026-10-02, Plan 20 header): maximize oracle
risk-adjusted quality — primary Sharpe, tie-break Calmar, then CAGR — subject to
a time-in-market floor of 70% of days. ``EXPOSURE_FLOOR_PCT`` and the ranking in
``rank_period_scores`` are module constants, not parameters of the search.

**The honesty frame.** Every score here is an *in-sample ceiling* on the same
history the windows were derived from: it measures period quality, never
achievable performance. ``split_sample_check`` (fit on the first half, score on
the unseen second half) is the only out-of-sample-ish read and reports both
sides. Real DCA still drips, never buys all-in at one close.

**Derivation, never invention.** ``cycle_windows.py`` forbids the optimizer
inventing peak/trough dates, and this module obeys that literally: candidate
windows come from *pivots the price series produced itself*.

    A bar is a **peak** when its close attains the maximum of its ±c-day
    confirmation neighbourhood, at least one bar in that neighbourhood is
    strictly below it, and it is the **first** bar of that neighbourhood to
    attain that maximum; **trough** symmetrically. The confirmation width ``c`` is
    ``max(2, min(half_widths) // 3)`` — a turn must dominate a third of the
    shortest window the horizon can express, so a pivot is never noise finer
    than the horizon's own resolution. Both neighbours must exist, so the first
    and last bars are never pivots.

    **A flat plateau yields exactly one pin** (Ruling 2). The corner is the
    information, so the pin is the *first* bar that attains the top (the bottom,
    for a trough) and the plateau's later bars are never counted again. Without
    that rule every bar of a flat top was its own pivot, so a single real corner
    on a two-bar plateau could satisfy ``MIN_PEAKS = 2`` by itself — and real
    closes do go flat, so a series carrying plateaus was inflating its pivot
    count rather than reporting structure. Two consequences, both intended: a
    wholly flat series
    attains neither a strict maximum nor a strict minimum, so it yields no pivot
    at all; and two turns closer together than ``c`` bars cannot both be pinned
    (the first one owns its neighbourhood), so detected pins are more than ``c``
    bars apart. Discovery is deterministic.

Every detected pivot is then emitted as a ``CycleWindow`` at **each** candidate
half-width, so one detected corner yields one candidate per width and the
optimizer searches widths rather than re-deriving structure per width.

**Ruling 1 — both edges, truncation recorded, degenerate labelled.** The oracle
*holds* on neutral dates, so a window converted to dates without an exit edge is
silently held to end-of-history; every candidate then saturates exposure (~100%)
and the 70% floor stops discriminating. Therefore:

- Every window emits **both** edge dates. A window's ``enter`` is its first
  in-calendar bar — a BUY date for a trough, a SELL date for a peak. Its ``exit``
  is the ``enter`` of the next window of the *opposite* kind: a trough's exit is
  the SELL that closes the accumulation, a peak's exit is the BUY that re-enters.
  Both edges of every window therefore land on an explicit action date.
- A trough window with no later peak **would hold past the final bar**: its exit is
  truncated at the last bar and the truncation is **recorded** in
  ``PeriodEdges.truncated_windows`` (never silently held).
- A zero-stdev path reports ``sharpe == 0.0`` and ties the all-cash flat
  comparator. ``rank_period_scores`` states the tie rule explicitly: a
  zero-stdev candidate is labelled ``degenerate``, ranks **below** any
  positive-Sharpe candidate and **above** any negative-Sharpe one, and is never
  eligible. (Under ``risk_metrics``' conventions a zero-stdev path is monotone,
  so its Calmar is 0.0 too and the ordering is the same one a plain Sharpe sort
  gives — the rule is spelled out so the degenerate state can never be read as a
  real result, and the gate that bites is ``eligible is False``.)

**Combination precedence.** ``combine_periods`` emits, in this order, long peaks,
medium peaks, long troughs, medium troughs. ``SdcaCycleWindows.kind_on`` returns
the first match, so **long sells override medium buys** on a shared date —
flat is the conservative read of an ambiguous pin, matching the oracle's own
"sell beats buy" rule.

Generic core: no ``nautilus_trader`` import (SDCA core rule), no asset
knowledge, no engine call. Polars/Python over plain sequences.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Collection, Sequence
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from digiquant.strategies.sdca.cycle_windows import CycleKind, CycleWindow, SdcaCycleWindows
from digiquant.strategies.sdca.perfect_strategy import (
    PerfectStrategyMetrics,
    perfect_strategy_metrics,
)

# Frozen by the owner (Plan 20, 2026-10-02): the objective is reported and
# filtered against this time-in-market floor, never tuned.
EXPOSURE_FLOOR_PCT = 70.0

# Oracle capital. Every metric here is a ratio or a ×100 percent, so the scale
# is irrelevant to the ranking; it is named so callers can read the module
# without hunting for a magic number.
DEFAULT_INITIAL_CASH = 1000.0

# Frozen candidate grids (Plan 20 header): medium is swing-scale (15-60d), long
# is cycle-scale (60-180d); both require at least 2 peaks and 2 troughs.
MEDIUM_HALF_WIDTHS = (15, 20, 30, 45, 60)
LONG_HALF_WIDTHS = (60, 90, 120, 150, 180)

# Frozen hit-test thresholds (Plan 21): what a window must have caught inside its own
# bars to be worth trading. They are constants, not parameters of the call — a window
# may not pick its own bar, so these are the only values either regime may use.
LONG_MIN_MOVE_PCT = 15.0
MEDIUM_MIN_MOVE_PCT = 10.0
MIN_PEAKS = 2
MIN_TROUGHS = 2


class PeriodHorizon(BaseModel):
    """One horizon's frozen search space: candidate widths plus window minima."""

    model_config = ConfigDict(frozen=True, strict=True)

    name: str = Field(..., min_length=1, description="Horizon label ('medium', 'long', …)")
    half_widths: tuple[int, ...] = Field(
        ...,
        min_length=1,
        description=(
            "Candidate half-widths in calendar days, ascending and unique; every detected "
            "pivot is emitted once per width"
        ),
    )
    min_peaks: int = Field(
        default=MIN_PEAKS,
        ge=1,
        description="Minimum peak windows a candidate must carry to be scored at all",
    )
    min_troughs: int = Field(
        default=MIN_TROUGHS,
        ge=1,
        description="Minimum trough windows a candidate must carry to be scored at all",
    )

    @model_validator(mode="after")
    def _ordered_widths(self) -> PeriodHorizon:
        if any(width < 1 for width in self.half_widths):
            raise ValueError(f"half_widths must all be >= 1, got {self.half_widths}")
        if tuple(sorted(set(self.half_widths))) != self.half_widths:
            raise ValueError(f"half_widths must be ascending and unique, got {self.half_widths}")
        return self

    @classmethod
    def medium(cls) -> PeriodHorizon:
        """Frozen swing-scale grid: 15-60d half-widths, minima 2 peaks / 2 troughs."""
        return cls(
            name="medium",
            half_widths=MEDIUM_HALF_WIDTHS,
            min_peaks=MIN_PEAKS,
            min_troughs=MIN_TROUGHS,
        )

    @classmethod
    def long(cls) -> PeriodHorizon:
        """Frozen cycle-scale grid: 60-180d half-widths, minima 2 peaks / 2 troughs."""
        return cls(
            name="long",
            half_widths=LONG_HALF_WIDTHS,
            min_peaks=MIN_PEAKS,
            min_troughs=MIN_TROUGHS,
        )


class PeriodCandidate(BaseModel):
    """One candidate period set: every derived pivot window at a single half-width."""

    model_config = ConfigDict(frozen=True, strict=True)

    horizon: str = Field(..., min_length=1, description="Name of the horizon this set came from")
    half_width_days: int = Field(..., ge=1, description="Half-width of every window in this set")
    peaks: tuple[CycleWindow, ...] = Field(
        ..., description="Peak (sell-zone) windows, chronological"
    )
    troughs: tuple[CycleWindow, ...] = Field(
        ..., description="Trough (buy-zone) windows, chronological"
    )

    @property
    def windows(self) -> tuple[CycleWindow, ...]:
        """Every window in the set, chronological — what ``score_periods`` consumes."""
        return tuple(sorted((*self.peaks, *self.troughs), key=_window_order))

    @property
    def n_peaks(self) -> int:
        return len(self.peaks)

    @property
    def n_troughs(self) -> int:
        return len(self.troughs)


class PeriodEdge(BaseModel):
    """One window's two edge dates, per Ruling 1 — both are action dates."""

    model_config = ConfigDict(frozen=True, strict=True)

    window: str = Field(..., min_length=1, description="Name of the window these edges belong to")
    enter: date = Field(..., description="First in-calendar bar of the window: buys or sells")
    exit: date = Field(
        ..., description="Edge that closes the position; the last bar when truncated"
    )
    truncated: bool = Field(
        ...,
        description=(
            "True when no opposite-kind successor window exists, so the exit would fall past "
            "the final bar and was cut at the last bar (recorded, never silently held)"
        ),
    )


class PeriodEdges(BaseModel):
    """The explicit date sets the oracle is driven with — no reliance on holds."""

    model_config = ConfigDict(frozen=True, strict=True)

    buy_dates: tuple[date, ...] = Field(..., description="Ascending all-in buy dates")
    sell_dates: tuple[date, ...] = Field(..., description="Ascending all-out sell dates")
    enter_edge: tuple[PeriodEdge, ...] = Field(
        ..., description="Both edge dates per window, ordered as the scored windows"
    )
    truncated_windows: tuple[str, ...] = Field(
        ..., description="Names of the windows whose exit was truncated at the final bar"
    )


class PeriodScore(BaseModel):
    """One candidate's oracle score under the frozen objective and floor."""

    model_config = ConfigDict(frozen=True, strict=True)

    half_width_days: int | None = Field(
        default=None,
        ge=1,
        description="Candidate half-width when the set came from discovery, else None",
    )
    windows: tuple[CycleWindow, ...] = Field(
        ..., description="The exact window set that was scored"
    )
    edges: PeriodEdges = Field(
        ..., description="Explicit buy/sell dates derived from those windows"
    )
    metrics: PerfectStrategyMetrics = Field(..., description="Oracle metrics + exposure_pct")
    meets_exposure_floor: bool = Field(
        ..., description="Whether exposure_pct reached EXPOSURE_FLOOR_PCT (70.0)"
    )
    degenerate: bool = Field(
        ...,
        description="Zero-return-stdev path (sharpe == 0.0): no period-quality information",
    )
    eligible: bool = Field(
        ...,
        description="Cleared the exposure floor and is not degenerate — may be selected as best",
    )
    rejection: str | None = Field(..., description="Why the candidate is ineligible, else None")

    # Flattened read-only views of ``metrics`` / ``metrics.metrics`` so a
    # candidate table reads as ``score.sharpe`` rather than ``score.metrics.metrics.sharpe``.
    @property
    def sharpe(self) -> float:
        return self.metrics.metrics.sharpe

    @property
    def calmar(self) -> float:
        return self.metrics.metrics.calmar

    @property
    def sortino(self) -> float:
        return self.metrics.metrics.sortino

    @property
    def cagr_pct(self) -> float:
        return self.metrics.metrics.cagr_pct

    @property
    def total_return_pct(self) -> float:
        return self.metrics.metrics.total_return_pct

    @property
    def max_drawdown_pct(self) -> float:
        return self.metrics.metrics.max_drawdown_pct

    @property
    def exposure_pct(self) -> float:
        return self.metrics.exposure_pct


class PeriodOptimizationResult(BaseModel):
    """A horizon's full candidate table plus the frozen-objective winner."""

    model_config = ConfigDict(frozen=True, strict=True)

    horizon: PeriodHorizon = Field(..., description="The horizon that was searched")
    peak_pins: tuple[date, ...] = Field(..., description="Detected peak pivot dates, ascending")
    trough_pins: tuple[date, ...] = Field(..., description="Detected trough pivot dates, ascending")
    scores: tuple[PeriodScore, ...] = Field(
        ..., description="Every scored candidate, best-first under rank_period_scores"
    )
    best: PeriodScore | None = Field(
        ...,
        description="Best eligible candidate, or None when every candidate was rejected",
    )


class SplitSampleResult(BaseModel):
    """Fit on the first half, score on the unseen second half — both sides reported."""

    model_config = ConfigDict(frozen=True, strict=True)

    horizon: PeriodHorizon = Field(..., description="The horizon that was fitted")
    split: float = Field(..., description="Fraction of the calendar used for the fit")
    fit_days: int = Field(..., ge=2, description="Days in the fit half")
    score_days: int = Field(..., ge=2, description="Days in the unseen half")
    fit_best: PeriodScore | None = Field(
        ..., description="In-sample winner on the fit half (a ceiling on the fit history)"
    )
    out_of_sample: PeriodScore | None = Field(
        ...,
        description="The fit's window set scored on the unseen half, or None if there was no fit",
    )
    out_of_sample_eligible: bool = Field(
        ..., description="Whether the out-of-sample score cleared the same floor"
    )


def _window_order(window: CycleWindow) -> tuple[date, date, str]:
    return (window.start, window.end, str(window.kind))


def confirmation_days(horizon: PeriodHorizon) -> int:
    """Pivot confirmation half-width in bars: ``max(2, min(half_widths) // 3)``.

    A turn must dominate every bar within a third of the shortest window the
    horizon can express, so no pivot is noise finer than the horizon's own
    resolution. Derived, never a hand-tuned constant.
    """
    return max(2, min(horizon.half_widths) // 3)


def _pivot_indexes(prices: Sequence[float], confirm: int) -> tuple[list[int], list[int]]:
    """Peak / trough pivot indexes from the price series alone.

    A peak is the **first** bar of its ±``confirm`` neighbourhood to attain that
    neighbourhood's maximum, and at least one bar in it must be strictly lower; a
    trough is the symmetric rule (first to attain the minimum, at least one bar
    strictly higher). Both neighbours must exist, so the first and last bars are
    never pivots.

    Requiring the *first* attainment is what keeps a flat plateau to a single
    pin: every later bar of the plateau attains the same extreme, so an earlier
    bar of its own neighbourhood is equal to it, which rejects it.
    """
    n = len(prices)
    peaks: list[int] = []
    troughs: list[int] = []
    for index in range(confirm, n - confirm):
        window = prices[index - confirm : index + confirm + 1]
        here = prices[index]
        # ``window.index(here) == confirm`` reads "no earlier bar of this
        # neighbourhood attains the same value" — the first-attaining rule.
        if here == max(window) and any(p < here for p in window) and window.index(here) == confirm:
            peaks.append(index)
        elif (
            here == min(window) and any(p > here for p in window) and window.index(here) == confirm
        ):
            troughs.append(index)
    return peaks, troughs


def _check_calendar(dates: Sequence[date], prices: Sequence[float], confirm: int) -> None:
    if len(dates) != len(prices):
        raise ValueError("period_optimize requires dates and prices of the same length")
    if len(dates) < 2 * confirm + 1:
        raise ValueError(
            "period_optimize requires at least "
            f"{2 * confirm + 1} days to confirm a pivot, got {len(dates)}"
        )


def detect_pivots(
    dates: Sequence[date],
    prices: Sequence[float],
    horizon: PeriodHorizon,
) -> tuple[tuple[date, ...], tuple[date, ...]]:
    """Read the pivot pins straight off the price series: ``(peak_pins, trough_pins)``.

    This is the derivation rule of ``cycle_windows.py`` made callable — see the
    module docstring for why the confirmation width is derived rather than
    hand-picked, and why a flat plateau yields exactly one pin (Ruling 2). Exposed
    separately so the pins can be read without the per-width window sets (the
    optimizer reports them as ``PeriodOptimizationResult.peak_pins`` /
    ``trough_pins``).
    """
    confirm = confirmation_days(horizon)
    _check_calendar(dates, prices, confirm)
    peaks, troughs = _pivot_indexes([float(p) for p in prices], confirm)
    return tuple(dates[i] for i in peaks), tuple(dates[i] for i in troughs)


def discover_candidate_periods(
    dates: Sequence[date],
    prices: Sequence[float],
    horizon: PeriodHorizon,
) -> tuple[PeriodCandidate, ...]:
    """Derive candidate period sets from the price series, one per half-width.

    Every detected pivot is emitted as a ``CycleWindow`` at each candidate
    half-width (see ``detect_pivots`` for the rule), so one corner yields one
    candidate per width and the optimizer searches widths rather than
    re-deriving structure per width. Returns the candidates in ascending
    half-width order; a width whose pivot count falls below ``horizon.min_peaks``
    / ``min_troughs`` is dropped rather than scored, and an empty tuple means the
    series carries no usable structure — the caller must never substitute
    hand-entered dates for it.
    """
    peak_pins, trough_pins = detect_pivots(dates, prices, horizon)

    candidates: list[PeriodCandidate] = []
    for width in horizon.half_widths:
        offset = timedelta(days=width)
        peak_windows = tuple(
            CycleWindow(
                name=f"{horizon.name}_peak_{day:%Y%m%d}_pm{width}",
                kind=CycleKind.PEAK,
                start=day - offset,
                end=day + offset,
            )
            for day in peak_pins
        )
        trough_windows = tuple(
            CycleWindow(
                name=f"{horizon.name}_trough_{day:%Y%m%d}_pm{width}",
                kind=CycleKind.TROUGH,
                start=day - offset,
                end=day + offset,
            )
            for day in trough_pins
        )
        if len(peak_windows) < horizon.min_peaks or len(trough_windows) < horizon.min_troughs:
            continue
        candidates.append(
            PeriodCandidate(
                horizon=horizon.name,
                half_width_days=width,
                peaks=peak_windows,
                troughs=trough_windows,
            )
        )
    return tuple(candidates)


def _derive_edges(
    dates: Sequence[date],
    windows: Sequence[CycleWindow],
) -> PeriodEdges:
    """Convert closed windows into explicit ``[enter, exit]`` date pairs (Ruling 1).

    **The rule.** Each window's ``enter`` is its first in-calendar bar: a BUY date
    for a trough (buy zone), a SELL date for a peak (sell zone). Its ``exit`` is
    the ``enter`` of the next window of the *opposite* kind — the first one that
    lands strictly after this window's own ``enter``, so an overlapping window
    cannot close a position that had not opened yet. A trough's ``exit`` is
    therefore a SELL (the top that closes the accumulation) and a peak's ``exit``
    is a BUY (the re-entry).

    Both edges of every window therefore land on an explicit action date, so
    nothing is ever closed or opened by the oracle's neutral-date hold. Only the
    edge dates are emitted: a trough window's *interior* bars are not buy dates,
    because the oracle is all-in and a same-day sell would otherwise veto them
    wherever a peak window overlaps.

    A trough with no later peak ``enter`` **would hold past the final bar**, so its
    exit is cut at the last bar and the window is **recorded** in
    ``truncated_windows`` — never silently held. A peak whose re-entry never
    arrives inside the sample is not a truncation: a flat book holds nothing open.

    A window lying wholly outside the price calendar is a no-op pin, matching the
    oracle's documented out-of-calendar behaviour — not an edge and not a
    truncation.
    """
    ordered = tuple(sorted(windows, key=_window_order))
    # dates is ascending, so each window covers a contiguous [lo, hi) index span.
    spans = [
        (window, bisect_left(dates, window.start), bisect_right(dates, window.end))
        for window in ordered
    ]
    enters = [(window, lo) for window, lo, hi in spans if hi > lo]
    peak_enters = sorted(
        (lo, window.name) for window, lo in enters if window.kind == CycleKind.PEAK
    )
    trough_enters = sorted(
        (lo, window.name) for window, lo in enters if window.kind == CycleKind.TROUGH
    )

    def next_edge(own: int, pool: Sequence[tuple[int, str]]) -> int | None:
        """First ``enter`` index in ``pool`` strictly after ``own``."""
        return next((index for index, _name in pool if index > own), None)

    edges: list[PeriodEdge] = []
    buy_dates: list[int] = []
    sell_dates: list[int] = []
    truncated: list[str] = []
    for window, lo in enters:
        if window.kind == CycleKind.TROUGH:
            exit_index = next_edge(lo, peak_enters)
            if exit_index is None:
                edges.append(
                    PeriodEdge(
                        window=window.name,
                        enter=dates[lo],
                        exit=dates[-1],
                        truncated=True,
                    )
                )
                truncated.append(window.name)
                buy_dates.append(lo)
                sell_dates.append(len(dates) - 1)
            else:
                edges.append(
                    PeriodEdge(
                        window=window.name, enter=dates[lo], exit=dates[exit_index], truncated=False
                    )
                )
                buy_dates.append(lo)
                sell_dates.append(exit_index)
            continue
        re_entry = next_edge(lo, trough_enters)
        edges.append(
            PeriodEdge(
                window=window.name,
                enter=dates[lo],
                exit=dates[len(dates) - 1 if re_entry is None else re_entry],
                truncated=False,
            )
        )
        sell_dates.append(lo)

    return PeriodEdges(
        buy_dates=tuple(dates[i] for i in sorted(set(buy_dates))),
        sell_dates=tuple(dates[i] for i in sorted(set(sell_dates))),
        enter_edge=tuple(edges),
        truncated_windows=tuple(truncated),
    )


def score_periods(
    dates: Sequence[date],
    prices: Sequence[float],
    windows: Collection[CycleWindow],
    *,
    exposure_floor_pct: float = EXPOSURE_FLOOR_PCT,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    half_width_days: int | None = None,
) -> PeriodScore:
    """Score one period set with the oracle under the frozen objective and floor.

    ``windows`` are closed calendar windows; they are converted to explicit
    ``[enter, exit]`` date pairs first (Ruling 1), so nothing depends on the
    oracle holding through the end of history. Raises ``ValueError`` for an empty
    window set, misaligned inputs, a non-positive exposure floor or negative cash.
    """
    window_list = tuple(windows)
    if not window_list:
        raise ValueError("score_periods requires at least one window")
    if not 0.0 <= exposure_floor_pct <= 100.0:
        raise ValueError(f"exposure_floor_pct must be within [0, 100], got {exposure_floor_pct}")
    if len(dates) != len(prices):
        raise ValueError("score_periods requires dates and prices of the same length")
    if len(dates) < 2:
        raise ValueError("score_periods requires at least two days")
    if initial_cash <= 0.0:
        raise ValueError(f"score_periods requires positive initial_cash, got {initial_cash}")

    edges = _derive_edges(dates, window_list)
    metrics = perfect_strategy_metrics(
        dates, prices, edges.buy_dates, edges.sell_dates, initial_cash
    )
    degenerate = metrics.metrics.sharpe == 0.0
    meets_floor = metrics.exposure_pct >= exposure_floor_pct
    if degenerate:
        rejection: str | None = (
            "degenerate: zero return stdev (sharpe == 0.0) ties the all-cash flat comparator"
        )
    elif not meets_floor:
        rejection = (
            f"exposure {metrics.exposure_pct:.2f}% below the frozen "
            f"{exposure_floor_pct:.1f}% time-in-market floor"
        )
    else:
        rejection = None
    return PeriodScore(
        half_width_days=half_width_days,
        windows=tuple(sorted(window_list, key=_window_order)),
        edges=edges,
        metrics=metrics,
        meets_exposure_floor=meets_floor,
        degenerate=degenerate,
        eligible=meets_floor and not degenerate,
        rejection=rejection,
    )


def _rank_key(score: PeriodScore) -> tuple[int, float, float, float]:
    """Frozen objective: Sharpe primary, Calmar tie-break, CAGR tertiary.

    The leading band states Ruling 1's tie rule outright: a zero-stdev
    (degenerate) candidate can never be *silently equal* to a positive-Sharpe one
    — it sits below every positive-Sharpe candidate and above every negative one.
    """
    band = 1 if score.sharpe > 0.0 else 0
    return (band, score.sharpe, score.calmar, score.cagr_pct)


def rank_period_scores(scores: Collection[PeriodScore]) -> tuple[PeriodScore, ...]:
    """Order candidates best-first under the frozen objective (stable)."""
    return tuple(sorted(scores, key=_rank_key, reverse=True))


def optimize_periods(
    dates: Sequence[date],
    prices: Sequence[float],
    horizon: PeriodHorizon,
    *,
    exposure_floor_pct: float = EXPOSURE_FLOOR_PCT,
    initial_cash: float = DEFAULT_INITIAL_CASH,
) -> PeriodOptimizationResult:
    """Derive, score and rank every candidate period set for one horizon.

    Reports the full candidate table (including rejected candidates with their
    reason) so a run with no eligible candidate is visible rather than silent.
    ``best`` is the top *eligible* candidate, or ``None`` when every candidate
    was rejected. Raises ``ValueError`` when the series carries no usable pivot
    structure — periods are never hand-entered to fill the gap.
    """
    candidates = discover_candidate_periods(dates, prices, horizon)
    if not candidates:
        raise ValueError(
            f"no candidate periods discovered for horizon {horizon.name!r}: the price series "
            f"has no pivot structure at confirmation width {confirmation_days(horizon)}d"
        )
    scored = [
        score_periods(
            dates,
            prices,
            candidate.windows,
            exposure_floor_pct=exposure_floor_pct,
            initial_cash=initial_cash,
            half_width_days=candidate.half_width_days,
        )
        for candidate in candidates
    ]
    ranked = rank_period_scores(scored)
    best = next((score for score in ranked if score.eligible), None)
    peak_pins, trough_pins = detect_pivots(dates, prices, horizon)
    return PeriodOptimizationResult(
        horizon=horizon,
        peak_pins=peak_pins,
        trough_pins=trough_pins,
        scores=ranked,
        best=best,
    )


def combine_periods(
    medium: Sequence[CycleWindow] | SdcaCycleWindows,
    long: Sequence[CycleWindow] | SdcaCycleWindows,
) -> SdcaCycleWindows:
    """Merge a medium and a long window set; **long sells override medium buys**.

    The emitted order is long peaks, medium peaks, long troughs, medium troughs.
    ``SdcaCycleWindows.kind_on`` returns the first match, so a date covered by a
    long peak resolves to ``PEAK`` even when a medium trough also covers it —
    flat is the conservative read of an ambiguous pin, matching the oracle's own
    "sell beats buy" rule. Neither input is mutated, and no window is renamed or
    dropped.
    """
    medium_windows = medium.windows if isinstance(medium, SdcaCycleWindows) else tuple(medium)
    long_windows = long.windows if isinstance(long, SdcaCycleWindows) else tuple(long)
    ordered = (
        *(w for w in long_windows if w.kind == CycleKind.PEAK),
        *(w for w in medium_windows if w.kind == CycleKind.PEAK),
        *(w for w in long_windows if w.kind == CycleKind.TROUGH),
        *(w for w in medium_windows if w.kind == CycleKind.TROUGH),
    )
    if not ordered:
        raise ValueError("combine_periods requires at least one window across both horizons")
    return SdcaCycleWindows(windows=ordered)


def split_sample_check(
    dates: Sequence[date],
    prices: Sequence[float],
    horizon: PeriodHorizon,
    *,
    split: float = 0.5,
    exposure_floor_pct: float = EXPOSURE_FLOOR_PCT,
    initial_cash: float = DEFAULT_INITIAL_CASH,
) -> SplitSampleResult:
    """Fit periods on the first ``split`` of the calendar, score on the unseen rest.

    The fit half reproduces the in-sample ceiling; the out-of-sample score applies
    the *fitted window dates* to the unseen half (windows that fall before the
    split simply do not act there — the oracle ignores out-of-calendar pins). Both
    sides are always reported: an out-of-sample failure is the result, not an
    error to hide.
    """
    if not 0.0 < split < 1.0:
        raise ValueError(f"split must be strictly within (0, 1), got {split}")
    confirm = confirmation_days(horizon)
    _check_calendar(dates, prices, confirm)
    split_at = int(len(dates) * split)
    if split_at < 2 * confirm + 1 or len(dates) - split_at < 2:
        raise ValueError(
            "split_sample_check requires each half to hold at least "
            f"{2 * confirm + 1} days and 2 scoring days, got {split_at} / {len(dates) - split_at}"
        )

    fit = optimize_periods(
        dates[:split_at],
        prices[:split_at],
        horizon,
        exposure_floor_pct=exposure_floor_pct,
        initial_cash=initial_cash,
    )
    if fit.best is None:
        return SplitSampleResult(
            horizon=horizon,
            split=split,
            fit_days=split_at,
            score_days=len(dates) - split_at,
            fit_best=None,
            out_of_sample=None,
            out_of_sample_eligible=False,
        )
    out_of_sample = score_periods(
        dates[split_at:],
        prices[split_at:],
        fit.best.windows,
        exposure_floor_pct=exposure_floor_pct,
        initial_cash=initial_cash,
        half_width_days=fit.best.half_width_days,
    )
    return SplitSampleResult(
        horizon=horizon,
        split=split,
        fit_days=split_at,
        score_days=len(dates) - split_at,
        fit_best=fit.best,
        out_of_sample=out_of_sample,
        out_of_sample_eligible=out_of_sample.eligible,
    )


# ======================= Plan 21: long-first period model (additive) =========
#
# The period model is rebuilt **long-first**: a *small* secular window set is the
# primary regime and medium windows are layered on gradually afterwards. Two
# additive functions land here. The Plan-20 machinery above is untouched — the
# every-swing-pivot discovery it contains is the record of the earlier attempt,
# and pivot DENSITY is exactly what kept exposure pinned (~55%) regardless of
# window width.


class HitTest(BaseModel):
    """Did this window actually catch a move, and how big was the best one?

    A window that covered nothing but decoration is decoration, so the verdict
    carries the **observed** largest move rather than only a boolean: an
    abandoned window can then be read — ``max_move_pct`` says what the window
    actually contained, and ``min_move_pct`` says what it would have needed.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    window: str = Field(..., min_length=1, description="Name of the window that was tested")
    kind: CycleKind = Field(
        ...,
        description=(
            "Window kind: a peak is a sell zone, a trough a buy zone, so the same "
            "threshold is read against the regime the window was drawn for"
        ),
    )
    bars: int = Field(
        ...,
        ge=0,
        description=(
            "In-calendar bars the window actually covers; a window hanging off the "
            "calendar has 0 and cannot be hit"
        ),
    )
    min_move_pct: float = Field(
        ...,
        ge=0.0,
        description=(
            "The threshold applied, passed by the caller (frozen: 15.0 long, 10.0 "
            "medium) — never defaulted here, so no call can silently pick its own bar"
        ),
    )
    max_move_pct: float = Field(
        ...,
        ge=0.0,
        description=(
            "Largest peak-to-trough move inside the window as a percent, in whichever "
            "direction it ran; 0.0 when the window has fewer than two in-calendar bars"
        ),
    )
    direction: Literal["up", "down", "flat"] = Field(
        ...,
        description=(
            "Which way the observed move ran: 'up', 'down', or 'flat' when the window "
            "contains no move at all"
        ),
    )
    hit: bool = Field(
        ...,
        description="True when max_move_pct >= min_move_pct, i.e. the window caught something",
    )


class DroppedWindow(BaseModel):
    """A prominence-ranked long pin the hit test refused, and what it held.

    A pin whose own window caught less than the frozen long bar is not worth
    trading, so it is skipped before it consumes any day budget — which is what
    lets the next pin that did catch something take its place. The record keeps
    the prominence it was ranked by *and* the move it actually contained, so an
    abandoned window is readable rather than merely absent: a reader can see the
    ranking that wanted it and the bar it missed.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    pin: date = Field(..., description="Date of the detected pivot the window was centred on")
    kind: CycleKind = Field(..., description="Peak (sell zone) or trough (buy zone), as detected")
    prominence_pct: float = Field(
        ...,
        ge=0.0,
        description="Prominence the pin was ranked by, as a percent, before the day budget",
    )
    observed_move_pct: float = Field(
        ...,
        ge=0.0,
        description=(
            "Largest peak-to-trough move the pin's own window actually contained, as a "
            "percent — what it had to beat `required_move_pct` and did not"
        ),
    )
    required_move_pct: float = Field(
        ...,
        ge=0.0,
        description=(
            "The frozen bar the window was held to (LONG_MIN_MOVE_PCT, 15.0), carried so "
            "the record is self-describing"
        ),
    )
    bars: int = Field(
        ...,
        ge=0,
        description="In-calendar bars the window covered; a window hanging off the calendar has 0",
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Why the pin was dropped, quoting the move it contained and the bar it needed",
    )


class CoverageSegment(BaseModel):
    """One calendar segment between consecutive selected trough windows.

    Actions are emitted at window ENTERS, so calendar holding no selected trough
    window is flat by construction. This is the measurement of that: the two
    bounding trough pins, the stretch of calendar between the two trough
    *windows* that neither of them covers, and what (if anything) was done about
    it. A stretch shorter than one window width cannot have held a whole
    window-shaped opportunity, so it is reported as covered.

    The repair Ruling 2 asks for is attempted and its verdict carried here —
    including the verdict that refuses it, because "the day cap is what blocks
    coverage" is the finding, and a segment that could not be repaired must say
    so rather than vanish.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    start: date = Field(..., description="The earlier selected trough pin bounding this segment")
    end: date = Field(..., description="The later selected trough pin bounding this segment")
    gap_start: date = Field(
        ...,
        description="First calendar day no selected trough window covers, inside the segment",
    )
    gap_end: date = Field(
        ...,
        description="Last calendar day no selected trough window covers, inside the segment",
    )
    gap_days: int = Field(
        ...,
        ge=0,
        description="Length of that uncovered stretch in calendar days — the flat run it implies",
    )
    covered: bool = Field(
        ...,
        description=(
            "True when the stretch is shorter than one trough window (2 * half_width + 1 days), "
            "so no whole window-shaped opportunity went by unselected"
        ),
    )
    repaired: bool = Field(
        ...,
        description="True when a selected peak was swapped out for a hit trough in this segment",
    )
    swapped_out_peak: date | None = Field(
        ...,
        description="Pin of the selected peak given up for a trough, if a repair was applied",
    )
    swapped_in_trough: date | None = Field(
        ...,
        description="Pin of the hit trough brought into this segment, if a repair was applied",
    )
    reason: str | None = Field(
        ...,
        description=(
            "Why the segment is not covered (no hit trough available, or the per-kind day cap "
            "refused to fund one, or no selected peak to give up); None when it is covered"
        ),
    )


class LongTermSelection(BaseModel):
    """The selected secular window set, or the stated reason there isn't one.

    Both ``peak_days_pct`` and ``trough_days_pct`` are reported so the cap that
    shaped the set can be checked on the record rather than inferred from the
    window count. ``selected is False`` with empty window lists is the *only*
    failure shape: the minima are never relaxed to manufacture a set.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    half_width_days: int = Field(
        ...,
        ge=1,
        description=(
            "Half-width every emitted window uses — the caller's `half_width_days`, "
            "defaulting to the tightest frozen long grid member. Carried so a run "
            "describes its own windows, on the refusal shape as much as the kept one"
        ),
    )
    calendar_days: int = Field(
        ..., ge=2, description="Bars in the price calendar the day shares are measured against"
    )
    max_peak_days_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description=(
            "Cap on how much of the calendar each kind's windows may cover; it is "
            "named for peaks because peak windows are the flat time that bounds "
            "exposure, and it is applied to troughs as well so both kinds stay small"
        ),
    )
    peak_days: int = Field(
        ...,
        ge=0,
        description=(
            "Calendar days the selected peak windows cover in total (overlap charged "
            "once); 0.0 when nothing was selected"
        ),
    )
    peak_days_pct: float = Field(
        ...,
        ge=0.0,
        description="peak_days as a percent of calendar_days — the cap, measured",
    )
    trough_days: int = Field(
        ...,
        ge=0,
        description="Calendar days the selected trough windows cover in total (overlap charged once)",
    )
    trough_days_pct: float = Field(
        ...,
        ge=0.0,
        description="trough_days as a percent of calendar_days — the cap, measured",
    )
    peak_pins: tuple[date, ...] = Field(
        ...,
        description="Every detected long-horizon peak pivot, ascending, before the cap truncated it",
    )
    trough_pins: tuple[date, ...] = Field(
        ...,
        description="Every detected long-horizon trough pivot, ascending, before the cap truncated it",
    )
    peak_prominence_pct: tuple[float, ...] = Field(
        ...,
        description="Prominence of each selected peak, index-aligned with `peaks`",
    )
    trough_prominence_pct: tuple[float, ...] = Field(
        ...,
        description="Prominence of each selected trough, index-aligned with `troughs`",
    )
    dropped_windows: tuple[DroppedWindow, ...] = Field(
        ...,
        description=(
            "Prominence-ranked long pins the frozen hit test refused, chronological. They were "
            "skipped BEFORE the day budget, so their budget went to a pin that was hit"
        ),
    )
    peak_hit_tests: tuple[HitTest, ...] = Field(
        ...,
        description=(
            "Hit verdict for each selected peak window, index-aligned with `peaks` — a kept "
            "window's observed move is on the record, not just its presence"
        ),
    )
    trough_hit_tests: tuple[HitTest, ...] = Field(
        ...,
        description="Hit verdict for each selected trough window, index-aligned with `troughs`",
    )
    coverage_segments: tuple[CoverageSegment, ...] = Field(
        ...,
        description=(
            "Every calendar segment between consecutive selected trough windows, in order, with "
            "its uncovered gap and — where a repair was refused — what blocked it"
        ),
    )
    peaks: tuple[CycleWindow, ...] = Field(
        ..., description="Selected peak (sell-zone) windows, chronological"
    )
    troughs: tuple[CycleWindow, ...] = Field(
        ..., description="Selected trough (buy-zone) windows, chronological"
    )
    selected: bool = Field(
        ...,
        description=(
            "True when min_peaks / min_troughs were met after truncation; False means "
            "no window set exists for this series"
        ),
    )
    reason: str | None = Field(
        ...,
        description="Why no window set was derived (with the counts that failed), else None",
    )

    @property
    def windows(self) -> tuple[CycleWindow, ...]:
        """Every selected window, chronological — what ``score_periods`` consumes."""
        return tuple(sorted((*self.peaks, *self.troughs), key=_window_order))

    @property
    def n_peaks(self) -> int:
        return len(self.peaks)

    @property
    def n_troughs(self) -> int:
        return len(self.troughs)

    @property
    def uncovered_segments(self) -> tuple[CoverageSegment, ...]:
        """Segments with no selected trough window in them, in order."""
        return tuple(segment for segment in self.coverage_segments if not segment.covered)

    @property
    def coverage_complete(self) -> bool:
        """Did every segment between selected trough windows hold a selected trough?

        True for the refusal shape and for a set with fewer than two troughs: there
        is nothing between them to be uncovered.
        """
        return not self.uncovered_segments


def _window_span(dates: Sequence[date], window: CycleWindow) -> tuple[int, int]:
    """In-calendar ``[lo, hi)`` index span of one window; empty when ``hi <= lo``."""
    return bisect_left(dates, window.start), bisect_right(dates, window.end)


def _max_move_pct(closes: Sequence[float]) -> tuple[float, Literal["up", "down", "flat"]]:
    """Largest percent move between any two closes, and the direction it ran.

    Measured from the *earlier* close to the later one and returned unsigned, so a
    fall counts exactly as much as a rise of the same size and the verdict never
    depends on which end of the window the move started at. One pass: the largest
    rise available at each bar is measured from the lowest close before it, the
    largest fall from the highest.
    """
    if len(closes) < 2:
        return 0.0, "flat"
    best = 0.0
    direction: Literal["up", "down", "flat"] = "flat"
    low = high = closes[0]
    for close in closes[1:]:
        rise = 100.0 * (close - low) / low
        fall = 100.0 * (high - close) / high
        if rise > best:
            best, direction = rise, "up"
        if fall > best:
            best, direction = fall, "down"
        low = min(low, close)
        high = max(high, close)
    return best, direction


def window_is_hit(
    dates: Sequence[date],
    prices: Sequence[float],
    window: CycleWindow,
    *,
    min_move_pct: float,
) -> HitTest:
    """Did ``window`` contain a real move of at least ``min_move_pct``?

    A window is only worth trading if it *caught* something, so this asks the
    price series directly: restricted to the window's in-calendar bars, the
    largest peak-to-trough move in either direction, as a percent of the earlier
    close. ``max_move_pct`` carries that observation, which is what lets an
    abandoned window quote what it actually contained instead of merely failing.

    ``min_move_pct`` has no default on purpose — the thresholds are frozen
    (15.0 long, 10.0 medium) and belong to the caller's regime, so no call can
    quietly pick its own bar. The comparison is inclusive, so a move of exactly
    the threshold is a hit. A window overlapping fewer than two bars has no move
    to measure and can never be hit. Raises ``ValueError`` for misaligned inputs,
    a negative threshold, or a non-positive close (a percent move is undefined
    from zero).
    """
    if len(dates) != len(prices):
        raise ValueError("window_is_hit requires dates and prices of the same length")
    if min_move_pct < 0.0:
        raise ValueError(f"window_is_hit requires min_move_pct >= 0, got {min_move_pct}")

    lo, hi = _window_span(dates, window)
    closes = [float(prices[i]) for i in range(lo, hi)]
    if any(close <= 0.0 for close in closes):
        raise ValueError("window_is_hit requires positive closes to measure a move percent")

    max_move, direction = _max_move_pct(closes)
    return HitTest(
        window=window.name,
        kind=window.kind,
        bars=len(closes),
        min_move_pct=min_move_pct,
        max_move_pct=max_move,
        direction=direction,
        hit=max_move >= min_move_pct,
    )


def _prominence_pct(
    prices: Sequence[float],
    index: int,
    bound: int,
    *,
    peak: bool,
) -> float:
    """Percent move from one pivot's own close to the extreme that follows it.

    Bounded by the **next opposite-kind pin** (or the final bar when there is
    none), because the leg to the next corner is what gives the corner its
    significance: a pivot whose follow-through never arrives has nothing to
    catch. A corner therefore ranks above a shallow one from the same history
    rather than being kept for being first or for merely existing.
    """
    here = float(prices[index])
    later = [float(price) for price in prices[index : bound + 1]]
    if not later:
        return 0.0
    if peak:
        return max(0.0, 100.0 * (here - min(later)) / here)
    return max(0.0, 100.0 * (max(later) - here) / here)


class OverlayStep(BaseModel):
    """One rung of the graded medium overlay: what was added, and what came of it.

    Every rung reports **both** outcomes — kept or abandoned — and an abandoned rung
    keeps its measured metrics too, so "the ladder stopped here" is a readable claim
    rather than an absence. The exception is a rung abandoned by the **hit test**,
    which is decided *before* any oracle call: its metric fields are ``None`` because
    nothing was measured, and never zero, which would read as a measurement of 0.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    index: int = Field(..., ge=1, description="1-based rung number in the ladder")
    half_width_days: int = Field(
        ..., ge=1, description="Candidate half-width of the windows this rung added"
    )
    added: tuple[CycleWindow, ...] = Field(
        ...,
        description=(
            "Medium windows this rung actually added to the book, chronological. Empty "
            "when the candidate's windows were all already present, so the rung could "
            "not change anything"
        ),
    )
    kept_windows: tuple[CycleWindow, ...] = Field(
        ...,
        description=(
            "Every window in play at this rung — the long set plus every earlier kept "
            "addition plus this rung's own — which is the exact set that was scored"
        ),
    )
    hit: tuple[HitTest, ...] = Field(
        ...,
        description="One hit verdict per added window, measured before any scoring call",
    )
    sharpe: float | None = Field(..., description="Oracle Sharpe of kept_windows; None if ungraded")
    calmar: float | None = Field(..., description="Oracle Calmar of kept_windows; None if ungraded")
    cagr_pct: float | None = Field(
        ..., description="Oracle CAGR % of kept_windows; None if ungraded"
    )
    exposure_pct: float | None = Field(
        ...,
        description=(
            "Time in market % of kept_windows against the frozen exposure floor; "
            "None if the rung was abandoned before scoring"
        ),
    )
    max_drawdown_pct: float | None = Field(
        ..., description="Oracle max drawdown % of kept_windows; None if ungraded"
    )
    degenerate: bool | None = Field(
        ...,
        description=(
            "Zero-return-stdev path (sharpe == 0.0): no period-quality information. "
            "None if the rung was abandoned before scoring"
        ),
    )
    kept: bool = Field(
        ...,
        description=(
            "True when the rung was added to the book — hit, strictly improving, and "
            "at or above the exposure floor"
        ),
    )
    reason: str | None = Field(
        ...,
        description="Why the rung was abandoned ('unhit', 'sharpe', 'exposure' …), else None",
    )


class OverlayGrade(BaseModel):
    """The graded long-first period model: the long regime, plus the medium ladder.

    ``base_windows`` is the long set as given — this function never re-selects it and
    never rewrites it, so a caller keeps one place that decides the regime. ``steps``
    is the full ladder (kept and abandoned alike, in the order they were tried), while
    ``ladder`` is only the rungs that were kept, so "what ended up in the book" and
    "everything that was tried" are both readable without walking the list.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    exposure_floor_pct: float = Field(
        ..., description="Frozen time-in-market floor applied at every rung, never relaxed"
    )
    min_move_pct: float = Field(
        ..., description="Frozen move threshold each added window had to catch to be graded"
    )
    base_windows: tuple[CycleWindow, ...] = Field(
        ..., min_length=1, description="The long (secular) window set the overlay builds on"
    )
    baseline: PeriodScore = Field(
        ...,
        description="The long set scored alone — rung zero, before anything was added",
    )
    steps: tuple[OverlayStep, ...] = Field(
        ..., description="Every rung that was tried, in ladder order"
    )
    ladder: tuple[OverlayStep, ...] = Field(
        ..., description="Only the rungs that were kept, in the order they were kept"
    )
    kept_windows: tuple[CycleWindow, ...] = Field(
        ...,
        description=(
            "The final window set — the long set plus every kept addition, chronological. "
            "Equal to base_windows when no rung was kept"
        ),
    )
    stop_reason: str | None = Field(
        ...,
        description=(
            "Why the ladder stopped — the abandoning rung's reason. None when every rung "
            "was kept, or when there was nothing to grade"
        ),
    )


def _medium_rung_order_key(candidate: PeriodCandidate) -> tuple[int, date, str]:
    """Frozen contribution order: shorter window first, then the earlier date.

    A wider window encloses more days, so it is the bigger intervention and is tried
    last; at equal width the earlier window goes first. The candidate's own horizon
    name is the final tie-break so the order is *total* — two candidates sharing a
    width and a date can never be graded in either order.
    """
    return (candidate.half_width_days, candidate.windows[0].start, candidate.horizon)


def _validate_overlay_inputs(
    dates: Sequence[date],
    prices: Sequence[float],
    long_windows: Collection[CycleWindow],
    medium_candidates: Collection[PeriodCandidate],
    *,
    exposure_floor_pct: float,
    min_move_pct: float,
) -> None:
    """Refuse nonsense before any oracle call, with a message naming the cause."""
    if len(dates) != len(prices):
        raise ValueError("grade_medium_overlay requires dates and prices of the same length")
    if len(dates) < 2:
        raise ValueError(f"grade_medium_overlay requires at least two days, got {len(dates)}")
    if not long_windows:
        raise ValueError("grade_medium_overlay requires at least one long-term window")
    if not 0.0 <= exposure_floor_pct <= 100.0:
        raise ValueError(f"exposure_floor_pct must be within [0, 100], got {exposure_floor_pct}")
    if min_move_pct < 0.0:
        raise ValueError(f"grade_medium_overlay requires min_move_pct >= 0, got {min_move_pct}")
    for candidate in medium_candidates:
        if not isinstance(candidate, PeriodCandidate):
            raise ValueError(
                "grade_medium_overlay requires PeriodCandidate entries, got "
                f"{type(candidate).__name__}"
            )
        if not candidate.windows:
            raise ValueError(
                "grade_medium_overlay received a PeriodCandidate with no windows "
                f"(half_width_days={candidate.half_width_days})"
            )


def grade_medium_overlay(
    dates: Sequence[date],
    prices: Sequence[float],
    long_windows: Collection[CycleWindow],
    medium_candidates: Collection[PeriodCandidate],
    *,
    exposure_floor_pct: float = EXPOSURE_FLOOR_PCT,
    min_move_pct: float = MEDIUM_MIN_MOVE_PCT,
) -> OverlayGrade:
    """Layer medium windows onto a long set ONE AT A TIME, keeping only what earns it.

    **The three frozen conditions.** A rung is kept only when all three hold:

    - **hit** — every window it adds actually caught a move of at least
      ``min_move_pct`` (``window_is_hit``). Tested **before** any scoring, so a
      decorative window costs nothing and the abandonment quotes the move it did
      contain rather than merely failing;
    - **strict improvement** — oracle Sharpe of the whole set must *strictly* beat
      the set before this rung (never merely tie);
    - **the floor** — exposure at or above ``exposure_floor_pct``, which is **never
      relaxed** to rescue a rung. A floor lowered after seeing the data is exactly the
      backward-fitting this model exists to avoid.

    **One at a time, and no skipping ahead.** Rungs are tried shortest-window-first,
    earlier date breaking ties, and the **first** rung that fails any condition stops
    the ladder. Continuing past a failure would grade a book that was never built, so
    "the next one might have been better" is not a reason to keep going — it is the
    reason the model reports ``stop_reason`` instead.

    **What it does not do.** It does not re-select the long set, relax a threshold, or
    hand-place a date: the base comes from ``select_long_term_periods`` and the
    candidates from ``discover_candidate_periods``, and both are taken as given. As
    with every function in this module the numbers are an **in-sample ceiling** on the
    same history the windows were derived from — a description of that history, never
    a forecast. Deterministic: same inputs, same ladder, every time.
    """
    _validate_overlay_inputs(
        dates,
        prices,
        long_windows,
        medium_candidates,
        exposure_floor_pct=exposure_floor_pct,
        min_move_pct=min_move_pct,
    )
    base = tuple(sorted(long_windows, key=_window_order))
    baseline = score_periods(dates, prices, base, exposure_floor_pct=exposure_floor_pct)

    current = base
    best_sharpe = baseline.sharpe
    steps: list[OverlayStep] = []
    ladder: list[OverlayStep] = []
    stop_reason: str | None = None

    ordered = sorted(medium_candidates, key=_medium_rung_order_key)
    for index, candidate in enumerate(ordered, start=1):
        # A window already in the book is not added twice: re-offering the same set
        # cannot improve anything, and scoring the same set as if it were new would
        # report a gain nobody could act on. Such a rung is recorded and abandoned,
        # so the ladder's history still says the candidate was seen and refused.
        in_book = {window.name for window in current}
        added = tuple(w for w in candidate.windows if w.name not in in_book)
        if not added:
            stop_reason = (
                f"duplicate: the {candidate.half_width_days}d medium windows are already in the "
                "book, so this rung could add nothing"
            )
            steps.append(
                OverlayStep(
                    index=index,
                    half_width_days=candidate.half_width_days,
                    added=(),
                    kept_windows=current,
                    hit=(),
                    sharpe=None,
                    calmar=None,
                    cagr_pct=None,
                    exposure_pct=None,
                    max_drawdown_pct=None,
                    degenerate=None,
                    kept=False,
                    reason=stop_reason,
                )
            )
            break

        hits = tuple(
            window_is_hit(dates, prices, window, min_move_pct=min_move_pct) for window in added
        )
        unhit = next((verdict for verdict in hits if not verdict.hit), None)
        if unhit is not None:
            # Decided before any oracle call, so this rung carries no metrics.
            stop_reason = (
                f"unhit: {unhit.window} caught a {unhit.max_move_pct:.2f}% move over "
                f"{unhit.bars} bars, below the {min_move_pct:.1f}% medium threshold; the "
                f"{candidate.half_width_days}d windows were abandoned before scoring"
            )
            steps.append(
                OverlayStep(
                    index=index,
                    half_width_days=candidate.half_width_days,
                    added=added,
                    kept_windows=current,
                    hit=hits,
                    sharpe=None,
                    calmar=None,
                    cagr_pct=None,
                    exposure_pct=None,
                    max_drawdown_pct=None,
                    degenerate=None,
                    kept=False,
                    reason=stop_reason,
                )
            )
            break

        trial = current + added
        score = score_periods(dates, prices, trial, exposure_floor_pct=exposure_floor_pct)
        improves = score.sharpe > best_sharpe
        meets_floor = score.exposure_pct >= exposure_floor_pct
        if not improves:
            reason: str | None = (
                f"sharpe: adding the {candidate.half_width_days}d windows moved oracle Sharpe "
                f"{score.sharpe:.4f} against {best_sharpe:.4f} — no strict improvement"
            )
        elif not meets_floor:
            reason = (
                f"exposure: {score.exposure_pct:.2f}% time in market is below the frozen "
                f"{exposure_floor_pct:.1f}% floor, which is never relaxed"
            )
        else:
            reason = None

        step = OverlayStep(
            index=index,
            half_width_days=candidate.half_width_days,
            added=added,
            kept_windows=trial,
            hit=hits,
            sharpe=score.sharpe,
            calmar=score.calmar,
            cagr_pct=score.cagr_pct,
            exposure_pct=score.exposure_pct,
            max_drawdown_pct=score.max_drawdown_pct,
            degenerate=score.degenerate,
            kept=reason is None,
            reason=reason,
        )
        steps.append(step)
        if reason is not None:
            stop_reason = reason
            break
        ladder.append(step)
        current = trial
        best_sharpe = score.sharpe

    return OverlayGrade(
        exposure_floor_pct=exposure_floor_pct,
        min_move_pct=min_move_pct,
        base_windows=base,
        baseline=baseline,
        steps=tuple(steps),
        ladder=tuple(ladder),
        kept_windows=tuple(sorted(current, key=_window_order)),
        stop_reason=stop_reason,
    )


def _ranked_pivots(
    dates: Sequence[date],
    prices: Sequence[float],
    pins: Sequence[date],
    *,
    peak: bool,
) -> tuple[tuple[date, float], ...]:
    """Every pin with its prominence, in rank order: prominence desc, then date asc.

    The date tie-break is what makes the ranking a *total* order — an equal-
    prominence pivot keeps the earlier one, so the same series can only ever
    select the same set.
    """
    index_of = {day: i for i, day in enumerate(dates)}
    opposite = [index_of[day] for day in pins]
    ranked: list[tuple[date, float]] = []
    for pin in pins:
        own = index_of[pin]
        later = [i for i in opposite if i > own]
        bound = min(later) if later else len(prices) - 1
        ranked.append((pin, _prominence_pct(prices, own, bound, peak=peak)))
    return tuple(sorted(ranked, key=lambda item: (-item[1], item[0])))


def _covered_days(windows: Sequence[CycleWindow], *, first_day: date, last_day: date) -> int:
    """Calendar days the windows cover in total, overlap charged once, in-calendar only."""
    covered: set[int] = set()
    for window in windows:
        covered.update(
            range(
                max(window.start, first_day).toordinal(),
                min(window.end, last_day).toordinal() + 1,
            )
        )
    return len(covered)


def _truncate_to_day_cap(
    ranked: Sequence[tuple[date, float]],
    *,
    half_width_days: int,
    budget_days: int,
    first_day: date,
    last_day: date,
) -> tuple[tuple[date, float], ...]:
    """Keep the most prominent pivots while their windows stay inside a day budget.

    Walked in rank order, so prominence decides and the date only breaks ties. A
    window is charged only for the calendar days it *adds*: overlapping windows
    share days, and exposure is paid once. Days falling outside the price
    calendar are charged to nobody — they are not bars, so they cannot be the
    flat time a peak window is capping.

    A pivot that does not fit is skipped rather than ending the walk, because
    stopping early would let window width stand in for prominence.
    """
    offset = timedelta(days=half_width_days)
    covered: set[int] = set()
    kept: list[tuple[date, float]] = []
    for pin, prominence in ranked:
        days = set(
            range(
                max(pin - offset, first_day).toordinal(),
                min(pin + offset, last_day).toordinal() + 1,
            )
        )
        if len(covered | days) > budget_days:
            continue
        covered |= days
        kept.append((pin, prominence))
    return tuple(sorted(kept))


def select_long_term_periods(
    dates: Sequence[date],
    prices: Sequence[float],
    *,
    max_peak_days_pct: float = 25.0,
    min_peaks: int = MIN_PEAKS,
    min_troughs: int = MIN_TROUGHS,
    half_width_days: int | None = None,
) -> LongTermSelection:
    """Select a SMALL secular window set: prominence-ranked pivots under a day cap.

    **Why not every pivot.** The Plan-20 record is the argument: period sets built
    from every swing pivot pinned exposure near 55% no matter how wide the windows
    were, because *pivot density* — not window width — decided how much time was
    left flat. Ranking by prominence and then truncating on **covered days** attacks
    that directly. Peak windows are the flat time that bounds exposure, so capping
    them at ``max_peak_days_pct`` of the calendar is what makes the frozen 70%
    floor reachable rather than pinned. The same share is applied to the trough
    windows: keeping every trough would reintroduce exactly the density the cap
    exists to remove, so the parameter is named for peaks because peaks are what
    bounds exposure, not because the two kinds are exempt from the cap.

    **The order.** Pivots come from ``detect_pivots`` on the frozen long horizon —
    the derivation is this module's own, reused unmodified, never a hand-entered
    pin. Each is then ranked by prominence (the move to its next opposite-kind
    corner) with the earlier date breaking ties, and the walk takes them in that
    order until the day budget is spent.

    **The long side is hit-tested too (Ruling 2).** Every prominence-ranked
    candidate — peak and trough alike — is measured against the frozen
    ``LONG_MIN_MOVE_PCT`` BEFORE it is charged any day budget. The hit test
    belonged to the medium overlay alone, which meant a long window that caught
    9.25% of move was kept while the owner's "abandon windows that do not get
    hit" was never applied to the primary regime. Gating first means an unhit pin
    is skipped rather than spending budget, so the freed days admit the next
    prominence-ranked pin that *did* catch a move. Each skip is recorded in
    ``dropped_windows`` with the prominence that wanted it and the move its own
    window contained, and every kept window's verdict travels in
    ``peak_hit_tests`` / ``trough_hit_tests``.

    **Coverage is measured, and the repair is attempted.** Actions are emitted at
    window ENTERS, so calendar holding no selected trough window is flat by
    construction; on GLD one such stretch ran 3063 days. Every calendar segment
    between consecutive selected trough windows is therefore measured, and a
    stretch at least one trough window wide — long enough that a whole
    window-shaped opportunity went by unselected — is reported as uncovered in
    ``coverage_segments``. Ruling 2 asks for the worst offending segment to be
    repaired by swapping its lowest-prominence selected PEAK for the best HIT
    trough available there, and that repair is attempted with the per-kind day cap
    and both minima intact.

    **Why the repair is never admissible today.** It is not a tuning accident:
    ``_truncate_to_day_cap`` keeps every window that fits, so its kept set is
    addition-maximal. A candidate it skipped had ``covered_then | days`` over
    budget, and the covered set only grows, so putting that window back breaches
    the very cap the walk enforced; and the two kinds are capped independently,
    so giving up a peak frees no trough budget. The attempt is therefore made and
    its **verdict recorded** — ``day cap``, ``no hit trough``, or ``min_peaks`` —
    because "the frozen day cap is what blocks coverage" is the finding a reader
    needs, and a segment that could not be repaired must say so rather than
    disappear. Widening the trough share of the cap, or funding the repair from a
    dropped trough instead of a dropped peak, is an owner decision this function
    does not make for itself.

    **The width (Ruling 1).** ``half_width_days`` defaults to the tightest frozen
    long grid member, and the default is *behaviour-preserving*: it is the width
    this function always used. The parameter exists because widening is qualitative
    — a wider window costs more days under the same cap, so it can drop the set
    below ``min_peaks`` and the selection then refuses outright — which is only
    legible if the width can be set up front rather than discovered after a run.
    Detection is unaffected by the width: only the emitted windows' extent, and
    therefore how many of them the day budget admits, changes. The chosen width
    travels in ``LongTermSelection``, including on the refusal shape, so a saved
    run never leaves the reader to re-derive the windows it describes.

    **No relaxed minimum.** When the detected pivots — or what survives the cap —
    cannot meet ``min_peaks`` / ``min_troughs``, the result is ``selected is False``
    with empty window lists and a ``reason`` carrying the counts. The minima are
    never lowered to manufacture a set; a series with no secular structure yields no
    window set at all.

    Deterministic: same series in, same set out, every time. As with every function
    here, the pivots are read off the same history the windows are derived from, so
    the result is a description of that history, never a forecast.
    """
    if not 0.0 <= max_peak_days_pct <= 100.0:
        raise ValueError(f"max_peak_days_pct must be within [0, 100], got {max_peak_days_pct}")
    if min_peaks < 1:
        raise ValueError(f"select_long_term_periods requires min_peaks >= 1, got {min_peaks}")
    if min_troughs < 1:
        raise ValueError(f"select_long_term_periods requires min_troughs >= 1, got {min_troughs}")
    if half_width_days is not None and half_width_days < 1:
        raise ValueError(
            f"select_long_term_periods requires half_width_days >= 1, got {half_width_days}"
        )
    # ``dates[0]`` / ``dates[-1]`` are read below, and the day budget is measured
    # against the calendar, so a series that cannot be indexed is refused here —
    # with a message, rather than as an IndexError from inside the walk.
    if len(dates) != len(prices):
        raise ValueError("select_long_term_periods requires dates and prices of the same length")
    if len(dates) < 2:
        raise ValueError(
            f"select_long_term_periods requires at least two calendar days, got {len(dates)}"
        )

    horizon = PeriodHorizon.long()
    half_width = min(horizon.half_widths) if half_width_days is None else half_width_days
    peak_pins, trough_pins = detect_pivots(dates, prices, horizon)
    offset = timedelta(days=half_width)

    def window_for(pin: date, kind: CycleKind) -> CycleWindow:
        return CycleWindow(
            name=f"long_{kind}_{pin:%Y%m%d}_pm{half_width}",
            kind=kind,
            start=pin - offset,
            end=pin + offset,
        )

    def hit_gate(
        ranked: Sequence[tuple[date, float]], kind: CycleKind
    ) -> tuple[list[tuple[date, float, HitTest]], list[tuple[date, float, HitTest]]]:
        """Split ranked candidates into the ones that were hit and the ones that were not.

        The frozen bar, applied before any day budget is charged: that is what lets
        an unhit pin's share of the budget go to the next pin that did catch a move.
        """
        hit: list[tuple[date, float, HitTest]] = []
        missed: list[tuple[date, float, HitTest]] = []
        for pin, prominence in ranked:
            verdict = window_is_hit(
                dates, prices, window_for(pin, kind), min_move_pct=LONG_MIN_MOVE_PCT
            )
            (hit if verdict.hit else missed).append((pin, prominence, verdict))
        return hit, missed

    budget_days = int(len(dates) * max_peak_days_pct / 100.0)
    ranked_peaks = _ranked_pivots(dates, prices, peak_pins, peak=True)
    ranked_troughs = _ranked_pivots(dates, prices, trough_pins, peak=False)
    hit_peaks, missed_peaks = hit_gate(ranked_peaks, CycleKind.PEAK)
    hit_troughs, missed_troughs = hit_gate(ranked_troughs, CycleKind.TROUGH)
    verdict_of = {
        pin: verdict for group in (hit_peaks, hit_troughs) for pin, _prominence, verdict in group
    }
    dropped_windows = tuple(
        sorted(
            (
                DroppedWindow(
                    pin=pin,
                    kind=kind,
                    prominence_pct=prominence,
                    observed_move_pct=verdict.max_move_pct,
                    required_move_pct=LONG_MIN_MOVE_PCT,
                    bars=verdict.bars,
                    reason=(
                        f"unhit: its own window contained {verdict.max_move_pct:.2f}% of move, "
                        f"under the frozen {LONG_MIN_MOVE_PCT:.1f}% long bar, so it was skipped "
                        f"before it could spend any of the {max_peak_days_pct:.1f}% day budget"
                    ),
                )
                for kind, group in (
                    (CycleKind.PEAK, missed_peaks),
                    (CycleKind.TROUGH, missed_troughs),
                )
                for pin, prominence, verdict in group
            ),
            key=lambda window: window.pin,
        )
    )
    kept_peaks = _truncate_to_day_cap(
        [(pin, prominence) for pin, prominence, _verdict in hit_peaks],
        half_width_days=half_width,
        budget_days=budget_days,
        first_day=dates[0],
        last_day=dates[-1],
    )
    kept_troughs = _truncate_to_day_cap(
        [(pin, prominence) for pin, prominence, _verdict in hit_troughs],
        half_width_days=half_width,
        budget_days=budget_days,
        first_day=dates[0],
        last_day=dates[-1],
    )

    if len(kept_peaks) < min_peaks or len(kept_troughs) < min_troughs:
        return LongTermSelection(
            half_width_days=half_width,
            calendar_days=len(dates),
            max_peak_days_pct=max_peak_days_pct,
            peak_days=0,
            peak_days_pct=0.0,
            trough_days=0,
            trough_days_pct=0.0,
            peak_pins=peak_pins,
            trough_pins=trough_pins,
            peak_prominence_pct=(),
            trough_prominence_pct=(),
            dropped_windows=dropped_windows,
            peak_hit_tests=(),
            trough_hit_tests=(),
            coverage_segments=(),
            peaks=(),
            troughs=(),
            selected=False,
            reason=(
                f"no long-term window set: the {max_peak_days_pct:.1f}% peak-day cap kept "
                f"{len(kept_peaks)} peak / {len(kept_troughs)} trough windows from "
                f"{len(peak_pins)} / {len(trough_pins)} detected long-horizon pivots, "
                f"below min_peaks={min_peaks} / min_troughs={min_troughs} "
                f"(minimums are never relaxed)"
                + (
                    f"; the frozen hit test had already dropped {len(dropped_windows)} of those "
                    f"pins for containing less than {LONG_MIN_MOVE_PCT:.1f}% of move"
                    if dropped_windows
                    else ""
                )
            ),
        )

    def emit(
        kept: Sequence[tuple[date, float]], kind: CycleKind
    ) -> tuple[tuple[CycleWindow, ...], tuple[float, ...]]:
        windows = tuple(window_for(pin, kind) for pin, _prominence in kept)
        return windows, tuple(prominence for _pin, prominence in kept)

    # ---- coverage: every calendar segment between consecutive selected trough windows.
    window_days = 2 * half_width + 1

    def spans(trough_pins_kept: Sequence[date]) -> list[tuple[date, date, date, date, int]]:
        """``(earlier pin, later pin, gap start, gap end, gap days)`` per segment."""
        out: list[tuple[date, date, date, date, int]] = []
        for earlier, later in zip(trough_pins_kept, trough_pins_kept[1:], strict=False):
            gap_start = max(window_for(earlier, CycleKind.TROUGH).end, dates[0]) + timedelta(days=1)
            gap_end = min(window_for(later, CycleKind.TROUGH).start, dates[-1]) - timedelta(days=1)
            gap_days = 0 if gap_end < gap_start else (gap_end - gap_start).days + 1
            out.append((earlier, later, gap_start, gap_end, gap_days))
        return out

    kept_peak_pins = [pin for pin, _prominence in kept_peaks]
    kept_trough_pins = [pin for pin, _prominence in kept_troughs]
    verdicts: dict[tuple[date, date], CoverageSegment] = {}
    origins: dict[tuple[date, date], tuple[date, date]] = {}
    blocked: set[tuple[date, date]] = set()

    def record(
        span: tuple[date, date],
        gap_start: date,
        gap_end: date,
        gap_days: int,
        *,
        covered: bool,
        reason: str | None,
    ) -> None:
        origin = origins.get(span)
        verdicts[span] = CoverageSegment(
            start=span[0],
            end=span[1],
            gap_start=gap_start,
            gap_end=gap_end,
            gap_days=gap_days,
            covered=covered,
            repaired=origin is not None,
            swapped_out_peak=origin[1] if origin is not None else None,
            swapped_in_trough=origin[0] if origin is not None else None,
            reason=reason,
        )

    # Each pass either gives up a selected peak or records a segment as blocked, so
    # the loop runs out of both: no repair can repeat on a peak that is already gone,
    # and a blocked segment is never retried.
    while True:
        outstanding = [
            span
            for span in spans(kept_trough_pins)
            if span[4] >= window_days and (span[0], span[1]) not in blocked
        ]
        if not outstanding:
            break
        # Worst-offending segment first: the longest flat run, earliest on a tie.
        earlier, later, gap_start, gap_end, gap_days = max(
            outstanding, key=lambda span: (span[4], -span[0].toordinal())
        )
        span = (earlier, later)
        available = [
            (pin, prominence)
            for pin, prominence, _verdict in hit_troughs
            if earlier <= pin <= later and pin not in kept_trough_pins
        ]
        give_up = [(pin, prominence) for pin, prominence in kept_peaks if earlier <= pin <= later]
        if not available:
            record(
                span,
                gap_start,
                gap_end,
                gap_days,
                covered=False,
                reason=(
                    "uncovered: no hit trough candidate sits in this segment, so there is "
                    "nothing to swap a peak for and no window may be invented"
                ),
            )
            blocked.add(span)
            continue
        if not give_up:
            record(
                span,
                gap_start,
                gap_end,
                gap_days,
                covered=False,
                reason="uncovered: no selected peak sits in this segment to give up for a trough",
            )
            blocked.add(span)
            continue
        lowest_peak = min(give_up, key=lambda item: (item[1], item[0]))
        if len(kept_peak_pins) - 1 < min_peaks:
            record(
                span,
                gap_start,
                gap_end,
                gap_days,
                covered=False,
                reason=(
                    f"uncovered: giving up a peak here would leave {len(kept_peak_pins) - 1} "
                    f"peak windows, under min_peaks={min_peaks}, which is never relaxed"
                ),
            )
            blocked.add(span)
            continue
        fitted: tuple[date, float] | None = None
        would_need = 0
        for pin, prominence in available:  # prominence desc, so the best candidate first
            trough_days = _covered_days(
                [window_for(kept, CycleKind.TROUGH) for kept in (*kept_trough_pins, pin)],
                first_day=dates[0],
                last_day=dates[-1],
            )
            if trough_days <= budget_days:
                fitted = (pin, prominence)
                break
            would_need = max(would_need, trough_days)
        if fitted is None:
            record(
                span,
                gap_start,
                gap_end,
                gap_days,
                covered=False,
                reason=(
                    f"uncovered: the {max_peak_days_pct:.1f}% per-kind day cap cannot fund "
                    f"another trough window here (it would need {would_need} of the "
                    f"{budget_days} trough days the cap allows), and the two kinds are capped "
                    f"independently, so giving up a peak frees no trough budget"
                ),
            )
            blocked.add(span)
            continue
        kept_peaks = tuple(item for item in kept_peaks if item[0] != lowest_peak[0])
        kept_troughs = tuple(sorted((*kept_troughs, fitted)))
        kept_peak_pins = [pin for pin, _prominence in kept_peaks]
        kept_trough_pins = [pin for pin, _prominence in kept_troughs]
        # The span no longer exists once the trough is in; both spans it became carry
        # the swap that created them.
        origins[(earlier, fitted[0])] = (fitted[0], lowest_peak[0])
        origins[(fitted[0], later)] = (fitted[0], lowest_peak[0])

    # Report the FINAL trough set: a span a repair split is gone from the set, and both
    # spans it became carry the swap through ``origins``. Every uncovered span has a
    # recorded verdict already — the loop above blocks or repairs each one — so the
    # fallback only ever fills in the covered segments, and the uncovered branch in it
    # is a guard rather than an expectation.
    final_spans = spans(kept_trough_pins)
    for earlier, later, gap_start, gap_end, gap_days in final_spans:
        if (earlier, later) not in verdicts:
            covered = gap_days < window_days
            record(
                (earlier, later),
                gap_start,
                gap_end,
                gap_days,
                covered=covered,
                reason=None if covered else "uncovered: no repair was attempted",
            )
    coverage_segments = tuple(verdicts[(earlier, later)] for earlier, later, *_rest in final_spans)

    peaks, peak_prominence = emit(kept_peaks, CycleKind.PEAK)
    troughs, trough_prominence = emit(kept_troughs, CycleKind.TROUGH)
    peak_days = _covered_days(peaks, first_day=dates[0], last_day=dates[-1])
    trough_days = _covered_days(troughs, first_day=dates[0], last_day=dates[-1])
    return LongTermSelection(
        half_width_days=half_width,
        calendar_days=len(dates),
        max_peak_days_pct=max_peak_days_pct,
        peak_days=peak_days,
        peak_days_pct=100.0 * peak_days / len(dates),
        trough_days=trough_days,
        trough_days_pct=100.0 * trough_days / len(dates),
        peak_pins=peak_pins,
        trough_pins=trough_pins,
        peak_prominence_pct=peak_prominence,
        trough_prominence_pct=trough_prominence,
        dropped_windows=dropped_windows,
        peak_hit_tests=tuple(verdict_of[pin] for pin, _prominence in kept_peaks),
        trough_hit_tests=tuple(verdict_of[pin] for pin, _prominence in kept_troughs),
        coverage_segments=coverage_segments,
        peaks=peaks,
        troughs=troughs,
        selected=True,
        reason=None,
    )


__all__ = [
    "DEFAULT_INITIAL_CASH",
    "EXPOSURE_FLOOR_PCT",
    "LONG_HALF_WIDTHS",
    "LONG_MIN_MOVE_PCT",
    "MEDIUM_HALF_WIDTHS",
    "MEDIUM_MIN_MOVE_PCT",
    "MIN_PEAKS",
    "MIN_TROUGHS",
    "CoverageSegment",
    "DroppedWindow",
    "HitTest",
    "LongTermSelection",
    "OverlayGrade",
    "OverlayStep",
    "PeriodCandidate",
    "PeriodEdge",
    "PeriodEdges",
    "PeriodHorizon",
    "PeriodOptimizationResult",
    "PeriodScore",
    "SplitSampleResult",
    "combine_periods",
    "confirmation_days",
    "detect_pivots",
    "discover_candidate_periods",
    "grade_medium_overlay",
    "optimize_periods",
    "rank_period_scores",
    "score_periods",
    "select_long_term_periods",
    "split_sample_check",
    "window_is_hit",
]
