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

    A bar is a **peak** when its close is the maximum of its ±c-day
    confirmation neighbourhood and is strictly greater than at least one bar in
    that neighbourhood (a flat plateau carries no price information, so it is
    not a peak); **trough** symmetrically. The confirmation width ``c`` is
    ``max(2, min(half_widths) // 3)`` — a turn must dominate a third of the
    shortest window the horizon can express, so a pivot is never noise finer
    than the horizon's own resolution. Both neighbours must exist, so the first
    and last bars are never pivots. Because a pivot must be a *strict* extreme,
    every detected pivot is unique in its neighbourhood: discovery is
    deterministic and a flat plateau yields nothing at all.

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

    A peak is the first bar attaining the maximum of its ±``confirm`` window that
    is also strictly greater than at least one bar in it (a plateau therefore
    yields no pivot); a trough is symmetric. Both neighbours must exist.
    """
    n = len(prices)
    peaks: list[int] = []
    troughs: list[int] = []
    for index in range(confirm, n - confirm):
        window = prices[index - confirm : index + confirm + 1]
        here = prices[index]
        if here == max(window) and any(p < here for p in window):
            peaks.append(index)
        elif here == min(window) and any(p > here for p in window):
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
    hand-picked, and why a strict extreme is required. Exposed separately so the
    pins can be read without the per-width window sets (the optimizer reports
    them as ``PeriodOptimizationResult.peak_pins`` / ``trough_pins``).
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


__all__ = [
    "DEFAULT_INITIAL_CASH",
    "EXPOSURE_FLOOR_PCT",
    "LONG_HALF_WIDTHS",
    "MEDIUM_HALF_WIDTHS",
    "MIN_PEAKS",
    "MIN_TROUGHS",
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
    "optimize_periods",
    "rank_period_scores",
    "score_periods",
    "split_sample_check",
]
