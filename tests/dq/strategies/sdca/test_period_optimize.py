"""Tests for the two-horizon period optimizer (#4804, Plan 20).

The pins that matter here, in order of importance:

- **Recovery.** A synthetic zigzag has exactly one right answer and the
  optimizer must find it. ``_up_heavy()`` is 12 cycles of 110 rising bars then
  30 falling bars (plus a tail), so the tightest candidate half-width buys
  closest to each pivot low and sells closest to each pivot high, while every
  wider candidate enters earlier (higher, inside the falling leg) and exits
  earlier (lower, short of the top). Sharpe therefore falls monotonically with
  the half-width and the optimum is derivable by hand: 15d, the tightest grid
  member.
- **Derivation, never invention** (``cycle_windows.py:3-6``). Candidate windows
  come from the price series' own corners; ``confirmation_days`` pins the
  detector's rule, and a flat series has no corners, so it yields no candidates
  at all.
- **Ruling 2 (unique pivots).** A flat plateau yields exactly **one** pin — the
  first bar that attains the top (the bottom, for a trough). Without that rule
  every bar of a flat top was its own pivot, so one real corner on a two-bar
  plateau could satisfy the frozen ``min_peaks = 2`` minimum by itself, and real
  closes do go flat. Pinned on a rise→flat→fall fixture (one peak pin) and its
  inverse (one trough pin), plus plateau-length invariance: the pin neither moves
  nor multiplies.
- **Ruling 1.** Every window emits *both* edge dates into the buy/sell sets — a
  window converted to dates without an exit is held to end-of-history, after
  which every candidate saturates exposure (~100%) and the frozen 70% floor
  stops discriminating. A trailing long window is truncated at the final bar and
  that truncation is *recorded*. A zero-stdev path reports ``sharpe == 0.0``, is
  labelled ``degenerate``, and is never eligible.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from digiquant.strategies.sdca.cycle_windows import CycleKind, CycleWindow, SdcaCycleWindows
from digiquant.strategies.sdca.period_optimize import (
    EXPOSURE_FLOOR_PCT,
    LONG_HALF_WIDTHS,
    LONG_MIN_MOVE_PCT,
    MIN_PEAKS,
    MIN_TROUGHS,
    CoverageSegment,
    HitTest,
    LongTermSelection,
    OverlayGrade,
    OverlayStep,
    PeriodCandidate,
    PeriodHorizon,
    PeriodOptimizationResult,
    PeriodScore,
    SplitSampleResult,
    combine_periods,
    confirmation_days,
    detect_pivots,
    discover_candidate_periods,
    grade_medium_overlay,
    optimize_periods,
    rank_period_scores,
    score_periods,
    select_long_term_periods,
    split_sample_check,
    window_is_hit,
)

pytestmark = pytest.mark.unit

_START = date(2020, 1, 1)
_LOW = 100.0
_HIGH = 200.0


def _calendar(n: int) -> list[date]:
    return [_START + timedelta(days=i) for i in range(n)]


def _leg(start_price: float, end_price: float, bars: int) -> list[float]:
    """``bars`` closes on a straight line, endpoints inclusive.

    The last close is *forced* onto ``end_price``: a straight-line ramp lands a
    few ULPs short of its endpoint, so the corner's bar index would then depend on
    floating-point rounding — and these fixtures assert corner *indexes*
    (``test_detected_pins_are_exactly_the_zigzag_corners``). Forcing the endpoint
    keeps the arithmetic and the fixture's structure in agreement.
    """
    step = (end_price - start_price) / (bars - 1)
    prices = [start_price + step * i for i in range(bars)]
    prices[-1] = end_price
    return prices


def _zigzag(
    up_days: int,
    down_days: int,
    cycles: int,
    *,
    tail_up: int = 0,
) -> tuple[list[date], list[float]]:
    """``cycles`` sawtooth legs: ``up_days`` rising bars then ``down_days`` falling.

    Prices are exact straight ramps, so the corners are the only strict local
    extrema and the pivot detector has nothing else to find. Each falling leg
    contributes its *interior* points only — both of its endpoints are corners and
    are emitted exactly once — so every corner is a single bar at ``_LOW`` or
    ``_HIGH``. Two bars at the same corner price would be a plateau, and a plateau
    pins at its *first* bar (Ruling 2), which would move the corner by a bar.
    ``tail_up`` appends a final rising leg whose top is never reached, which
    leaves a *trailing trough* whose exit edge would fall past the final bar — the
    Ruling 1 truncation case. A cycle is ``up_days + down_days - 2`` bars.
    """
    prices: list[float] = []
    for _ in range(cycles):
        prices.extend(_leg(_LOW, _HIGH, up_days))
        prices.extend(_leg(_HIGH, _LOW, down_days)[1:-1])
    if tail_up:
        prices.extend(_leg(_LOW, _HIGH, tail_up + 1)[1:])
    return _calendar(len(prices)), prices


def _up_heavy() -> tuple[list[date], list[float]]:
    """The recovery series: 110 of every 139 days rise (73.9% time in market)."""
    return _zigzag(110, 30, 12, tail_up=30)


def _down_heavy() -> tuple[list[date], list[float]]:
    """Same shape with the legs inverted: only ~22% of the calendar rises."""
    return _zigzag(30, 110, 12, tail_up=110)


# ---------------------------------------------------------------- horizons


def test_horizons_match_the_frozen_plan_header_grids() -> None:
    """Plan 20 header: medium 15-60d, long 60-180d, minima >= 2 peaks / 2 troughs."""
    medium, long = PeriodHorizon.medium(), PeriodHorizon.long()
    assert medium.name == "medium"
    assert min(medium.half_widths) == 15
    assert max(medium.half_widths) == 60
    assert (medium.min_peaks, medium.min_troughs) == (2, 2)
    assert long.name == "long"
    assert min(long.half_widths) == 60
    assert max(long.half_widths) == 180
    assert (long.min_peaks, long.min_troughs) == (2, 2)
    for horizon in (medium, long):
        assert horizon.half_widths == tuple(sorted(set(horizon.half_widths)))
        assert all(width >= 1 for width in horizon.half_widths)


def test_horizon_is_frozen_and_rejects_an_empty_or_nonsense_grid() -> None:
    horizon = PeriodHorizon.medium()
    with pytest.raises(Exception, match="frozen|immutable"):
        horizon.name = "other"  # type: ignore[misc]
    with pytest.raises(ValueError, match="half_widths"):
        PeriodHorizon(name="bad", half_widths=())
    with pytest.raises(ValueError, match="half_widths"):
        PeriodHorizon(name="bad", half_widths=(0, 15))
    with pytest.raises(ValueError, match="half_widths"):
        PeriodHorizon(name="bad", half_widths=(20, 15))
    with pytest.raises(ValueError, match="min_peaks"):
        PeriodHorizon(name="bad", half_widths=(15,), min_peaks=0)


def test_confirmation_width_is_derived_from_the_tightest_candidate_window() -> None:
    """A turn must dominate a third of the shortest window the horizon can express."""
    assert confirmation_days(PeriodHorizon.medium()) == 5
    assert confirmation_days(PeriodHorizon.long()) == 20
    assert confirmation_days(PeriodHorizon(name="tiny", half_widths=(1,))) == 2


# ------------------------------------------------------- discovery (derived)


def test_discovery_derives_windows_from_the_price_series_corners() -> None:
    dates, prices = _up_heavy()
    horizon = PeriodHorizon.medium()
    confirm = confirmation_days(horizon)
    candidates = discover_candidate_periods(dates, prices, horizon)
    assert candidates
    for candidate in candidates:
        assert isinstance(candidate, PeriodCandidate)
        assert candidate.horizon == horizon.name
        for kind, windows in (
            (CycleKind.PEAK, candidate.peaks),
            (CycleKind.TROUGH, candidate.troughs),
        ):
            for window in windows:
                # The pin is the middle of the emitted window …
                pin = window.start + timedelta(days=candidate.half_width_days)
                assert window.end == pin + timedelta(days=candidate.half_width_days)
                assert window.kind == kind
                # … and that pin is a strict extreme of the confirmation
                # neighbourhood on the price series itself.
                index = (pin - _START).days
                assert 0 <= index - confirm and index + confirm < len(prices)
                neighbourhood = prices[index - confirm : index + confirm + 1]
                if kind == CycleKind.PEAK:
                    assert prices[index] == max(neighbourhood)
                    assert any(p < prices[index] for p in neighbourhood)
                else:
                    assert prices[index] == min(neighbourhood)
                    assert any(p > prices[index] for p in neighbourhood)


def test_discovery_windows_are_chronological_and_one_candidate_per_width() -> None:
    dates, prices = _up_heavy()
    horizon = PeriodHorizon.medium()
    candidates = discover_candidate_periods(dates, prices, horizon)
    assert [c.half_width_days for c in candidates] == list(horizon.half_widths)
    for candidate in candidates:
        assert candidate.windows == tuple(
            sorted(candidate.windows, key=lambda w: (w.start, w.end, str(w.kind)))
        )
        assert candidate.n_peaks == len(candidate.peaks)
        assert candidate.n_troughs == len(candidate.troughs)


def test_detect_pivots_reads_the_series_and_matches_the_reported_pins() -> None:
    dates, prices = _up_heavy()
    horizon = PeriodHorizon.medium()
    assert detect_pivots(dates, prices, horizon) == (
        optimize_periods(dates, prices, horizon).peak_pins,
        optimize_periods(dates, prices, horizon).trough_pins,
    )


def test_detected_pins_are_exactly_the_zigzag_corners() -> None:
    """One pivot per corner — the detector reads the series, it does not invent one."""
    dates, prices = _up_heavy()
    result = optimize_periods(dates, prices, PeriodHorizon.medium())
    up, down, cycles = 110, 30, 12
    period = up + down - 2
    # Bar 0 is a corner but has no left neighbour, so it is never a pivot; the
    # last corner is the tail's first bar (it dips below the last falling-leg
    # interior point), which is what leaves the trailing trough unclosed.
    assert result.peak_pins == tuple(dates[up - 1 + period * c] for c in range(cycles))
    assert result.trough_pins == tuple(dates[period * c] for c in range(1, cycles + 1))


def test_every_candidate_window_count_clears_the_horizon_minima() -> None:
    dates, prices = _up_heavy()
    for candidate in discover_candidate_periods(dates, prices, PeriodHorizon.medium()):
        assert candidate.n_peaks >= 2
        assert candidate.n_troughs >= 2


def test_a_flat_series_has_no_corners_and_yields_no_candidates() -> None:
    """The optimizer must never invent dates out of a signal-free series."""
    dates = _calendar(200)
    prices = [_LOW] * 200
    assert discover_candidate_periods(dates, prices, PeriodHorizon.medium()) == ()
    with pytest.raises(ValueError, match="no candidate periods"):
        optimize_periods(dates, prices, PeriodHorizon.medium())


def test_candidates_below_the_horizon_minima_are_dropped() -> None:
    # Three cycles yield 3 peaks and 2 troughs, so a 4-peak minimum drops all.
    dates, prices = _zigzag(110, 30, 3, tail_up=30)
    loose = PeriodHorizon(name="loose", half_widths=(15,), min_peaks=2, min_troughs=2)
    strict = PeriodHorizon(name="strict", half_widths=(15,), min_peaks=4, min_troughs=2)
    assert discover_candidate_periods(dates, prices, loose)
    assert discover_candidate_periods(dates, prices, strict) == ()


def test_discovery_rejects_a_calendar_too_short_to_confirm_a_turn() -> None:
    dates, prices = _calendar(4), [_LOW, _HIGH, _LOW, _HIGH]
    with pytest.raises(ValueError, match="at least"):
        discover_candidate_periods(dates, prices, PeriodHorizon.medium())
    with pytest.raises(ValueError, match="at least"):
        optimize_periods(dates, prices, PeriodHorizon.medium())


def test_discovery_rejects_misaligned_inputs() -> None:
    dates, prices = _up_heavy()
    with pytest.raises(ValueError, match="same length"):
        discover_candidate_periods(dates[:10], prices, PeriodHorizon.medium())


# ---------------------------------------------- Ruling 2: unique pivots


def _top_with_flat_bars(flat_bars: int) -> tuple[list[date], list[float]]:
    """Rise → ``flat_bars`` equal closes at the top → fall.

    ``flat_bars=0`` is the single-bar corner every other fixture has; anything
    above it makes the top a *plateau* — one price level attained by several
    consecutive bars, which is what a real flat top looks like. The corner sits at
    bar 10 either way (the last rising bar is the first bar at ``_HIGH``).
    """
    prices = [*_leg(_LOW, _HIGH, 11), *[_HIGH] * flat_bars, *_leg(_HIGH, _LOW, 11)[1:]]
    return _calendar(len(prices)), prices


def _bottom_with_flat_bars(flat_bars: int) -> tuple[list[date], list[float]]:
    """The inverse of ``_top_with_flat_bars``: fall → flat bottom → rise."""
    prices = [*_leg(_HIGH, _LOW, 11), *[_LOW] * flat_bars, *_leg(_LOW, _HIGH, 11)[1:]]
    return _calendar(len(prices)), prices


def test_a_flat_top_pins_once_at_the_first_attaining_bar() -> None:
    """Ruling 2: a plateau is one pin, at the first bar that attains the top."""
    dates, prices = _top_with_flat_bars(5)
    confirm = confirmation_days(PeriodHorizon.medium())
    top = 10
    plateau = prices[top : top + confirm + 1]
    assert len(plateau) == confirm + 1 and set(plateau) == {_HIGH}, "fixture needs a real plateau"
    peaks, troughs = detect_pivots(dates, prices, PeriodHorizon.medium())
    assert peaks == (dates[top],), f"expected one peak pin, got {peaks}"
    assert troughs == ()
    # The ruling's motivation: one real corner must not be able to satisfy the
    # frozen two-peak minimum on its own, by counting each plateau bar as a pin.
    assert len(peaks) == 1 < MIN_PEAKS


def test_a_flat_bottom_pins_once_at_the_first_attaining_bar() -> None:
    """Symmetric: a flat bottom is one trough pin, and invents no peak."""
    dates, prices = _bottom_with_flat_bars(5)
    confirm = confirmation_days(PeriodHorizon.medium())
    bottom = 10
    plateau = prices[bottom : bottom + confirm + 1]
    assert len(plateau) == confirm + 1 and set(plateau) == {_LOW}, "fixture needs a real plateau"
    peaks, troughs = detect_pivots(dates, prices, PeriodHorizon.medium())
    assert troughs == (dates[bottom],), f"expected one trough pin, got {troughs}"
    assert len(troughs) == 1 < MIN_TROUGHS
    assert peaks == ()


@pytest.mark.parametrize("flat_bars", [0, 1, 2, 5, 9])
def test_the_plateau_length_neither_moves_nor_multiplies_the_pin(flat_bars: int) -> None:
    """One pin either way, on the same bar — the plateau is not the pivot's location."""
    dates, prices = _top_with_flat_bars(flat_bars)
    peaks, _ = detect_pivots(dates, prices, PeriodHorizon.medium())
    assert peaks == (dates[10],), f"flat_bars={flat_bars} gave {peaks}"


# ------------------------------------------------------- Ruling 1: the edges


def test_every_window_emits_both_edge_dates_into_the_buy_and_sell_sets() -> None:
    dates, prices = _up_heavy()
    score = optimize_periods(dates, prices, PeriodHorizon.medium()).best
    assert score is not None
    edges = score.edges
    buy, sell = set(edges.buy_dates), set(edges.sell_dates)
    assert buy and sell
    assert len(edges.enter_edge) == len(score.windows)
    trough_edges, peak_edges = [], []
    for window, edge in zip(score.windows, edges.enter_edge, strict=True):
        assert edge.window == window.name
        assert edge.enter in dates and edge.exit in dates
        (trough_edges if window.kind == CycleKind.TROUGH else peak_edges).append(edge)
        # Nothing is closed or opened by the oracle's neutral-date hold.
        assert edge.enter in buy | sell
        assert edge.exit in buy | sell
        assert edge.enter < edge.exit
    # A trough buys on its enter and is closed by a SELL on its exit; a peak
    # sells on its enter and is re-entered by a BUY on its exit.
    assert buy == {edge.enter for edge in trough_edges}
    assert {edge.enter for edge in peak_edges} <= sell
    assert {edge.exit for edge in trough_edges} <= sell
    assert {edge.exit for edge in peak_edges} <= buy


def test_a_trailing_long_window_is_truncated_at_the_final_bar_and_recorded() -> None:
    dates, prices = _up_heavy()
    score = optimize_periods(dates, prices, PeriodHorizon.medium()).best
    assert score is not None
    last_bar = dates[-1]
    edges = score.edges
    assert edges.truncated_windows, "the tail trough must record its truncation"
    assert last_bar in set(edges.sell_dates)
    for edge in edges.enter_edge:
        if edge.truncated:
            assert edge.exit == last_bar
            assert edge.window in edges.truncated_windows
        else:
            assert edge.exit != last_bar


def test_a_trough_window_closed_by_the_next_peak_is_not_truncated() -> None:
    """The exit edge is the next peak window's enter, so the hold is closed."""
    dates, prices = _up_heavy()
    score = optimize_periods(dates, prices, PeriodHorizon.medium()).best
    assert score is not None
    peak_enters = {
        edge.enter
        for window, edge in zip(score.windows, score.edges.enter_edge, strict=True)
        if window.kind == CycleKind.PEAK
    }
    closed = [
        edge
        for window, edge in zip(score.windows, score.edges.enter_edge, strict=True)
        if window.kind == CycleKind.TROUGH and not edge.truncated
    ]
    assert closed
    for edge in closed:
        assert edge.exit in peak_enters
        assert edge.exit > edge.enter


def test_a_peak_window_without_a_reentry_is_not_a_truncation() -> None:
    """A flat book holds nothing open, so a missing re-entry is not a truncation."""
    dates = _calendar(3)
    peak = CycleWindow(name="only_sell", kind=CycleKind.PEAK, start=dates[0], end=dates[0])
    score = score_periods(dates, [_LOW, _HIGH, _LOW], [peak])
    assert score.edges.enter_edge[0].truncated is False
    assert score.edges.enter_edge[0].exit == dates[-1]
    assert score.edges.truncated_windows == ()
    assert score.edges.sell_dates == (dates[0],)


# ------------------------------------------------- Ruling 1: the degenerate tie


def test_a_zero_stdev_path_is_degenerate_and_never_eligible() -> None:
    """A flat price series gives a constant equity path: Sharpe exactly 0.0."""
    dates = _calendar(30)
    prices = [_LOW] * 30
    window = CycleWindow(name="hold", kind=CycleKind.TROUGH, start=dates[0], end=dates[0])
    score = score_periods(dates, prices, [window], half_width_days=15)
    assert score.sharpe == 0.0
    assert score.degenerate is True
    assert score.eligible is False
    assert score.rejection is not None and "degenerate" in score.rejection
    # The degeneracy rule, not the exposure floor, is what excludes it.
    relaxed = score_periods(dates, prices, [window], exposure_floor_pct=0.0)
    assert relaxed.meets_exposure_floor is True
    assert relaxed.degenerate is True
    assert relaxed.eligible is False


def test_a_zero_stdev_candidate_ranks_below_any_positive_sharpe_candidate() -> None:
    dates, prices = _up_heavy()
    candidates = discover_candidate_periods(dates, prices, PeriodHorizon.medium())
    by_width = {c.half_width_days: c for c in candidates}
    positive = score_periods(dates, prices, by_width[15].windows, half_width_days=15)
    negative = score_periods(dates, prices, by_width[60].windows, half_width_days=60)
    assert positive.degenerate is False and positive.sharpe > 0.0
    assert negative.degenerate is False and negative.sharpe < 0.0

    flat_dates = _calendar(30)
    degenerate = score_periods(
        flat_dates,
        [_LOW] * 30,
        [CycleWindow(name="hold", kind=CycleKind.TROUGH, start=flat_dates[0], end=flat_dates[0])],
        half_width_days=15,
    )
    ranked = rank_period_scores([degenerate, negative, positive])
    assert [s.sharpe for s in ranked] == [
        positive.sharpe,
        degenerate.sharpe,
        negative.sharpe,
    ]
    assert ranked[0] is positive
    assert ranked[1] is degenerate


def test_rank_period_scores_is_a_stable_total_order() -> None:
    dates, prices = _up_heavy()
    candidates = discover_candidate_periods(dates, prices, PeriodHorizon.medium())
    scores = [
        score_periods(dates, prices, c.windows, half_width_days=c.half_width_days)
        for c in candidates[:2]
    ]
    assert scores[0].sharpe != scores[1].sharpe
    first = rank_period_scores(scores)
    assert rank_period_scores(list(reversed(scores))) == first


# ---------------------------------------------------------------- scoring


def test_score_periods_is_frozen_typed_and_described() -> None:
    dates, prices = _up_heavy()
    score = score_periods(
        dates,
        prices,
        discover_candidate_periods(dates, prices, PeriodHorizon.medium())[0].windows,
        half_width_days=15,
    )
    assert isinstance(score, PeriodScore)
    assert 0.0 <= score.exposure_pct <= 100.0
    assert score.half_width_days == 15
    with pytest.raises(Exception, match="frozen|immutable"):
        score.degenerate = False  # type: ignore[misc]
    for name, field in PeriodScore.model_fields.items():
        assert field.description, f"{name} has no description"


def test_score_periods_rejects_bad_input() -> None:
    dates, prices = _up_heavy()
    windows = discover_candidate_periods(dates, prices, PeriodHorizon.medium())[0].windows
    with pytest.raises(ValueError, match="at least one window"):
        score_periods(dates, prices, [])
    with pytest.raises(ValueError, match="same length"):
        score_periods(dates[:10], prices, windows)
    with pytest.raises(ValueError, match="exposure_floor_pct"):
        score_periods(dates, prices, windows, exposure_floor_pct=101.0)
    with pytest.raises(ValueError, match="initial_cash"):
        score_periods(dates, prices, windows, initial_cash=0.0)


def test_a_down_heavy_series_fails_the_frozen_exposure_floor() -> None:
    """Only ~22% of the calendar rises: every candidate is under the 70% floor."""
    dates, prices = _down_heavy()
    result = optimize_periods(dates, prices, PeriodHorizon.medium())
    assert result.scores
    assert all(not s.meets_exposure_floor for s in result.scores)
    assert all(s.exposure_pct < EXPOSURE_FLOOR_PCT for s in result.scores)
    assert all(s.eligible is False for s in result.scores)
    assert all(s.rejection is not None and "exposure" in s.rejection for s in result.scores)
    assert result.best is None


def test_the_up_heavy_series_clears_the_frozen_exposure_floor() -> None:
    dates, prices = _up_heavy()
    result = optimize_periods(dates, prices, PeriodHorizon.medium())
    assert result.best is not None
    assert result.best.meets_exposure_floor is True
    assert result.best.exposure_pct >= EXPOSURE_FLOOR_PCT
    assert result.best.rejection is None


# ----------------------------------------------------------------- recovery


def test_recovers_the_known_optimal_half_width_on_a_synthetic_zigzag() -> None:
    """THE key pin: the zigzag's tightest window is its right answer."""
    result = optimize_periods(*_up_heavy(), PeriodHorizon.medium())
    assert isinstance(result, PeriodOptimizationResult)
    assert result.best is not None
    assert result.best.half_width_days == 15
    assert result.best.sharpe > 0.0


def test_sharpe_falls_monotonically_as_the_window_widens() -> None:
    """Why 15d: wider buys higher (mid-fall) and sells lower (short of the top)."""
    dates, prices = _up_heavy()
    result = optimize_periods(dates, prices, PeriodHorizon.medium())
    by_width = {s.half_width_days: s for s in result.scores}
    sharpes = [by_width[w].sharpe for w in PeriodHorizon.medium().half_widths]
    assert sharpes == sorted(sharpes, reverse=True)
    assert sharpes[0] > sharpes[-1]


def test_the_result_reports_every_candidate_and_the_detected_pins() -> None:
    dates, prices = _up_heavy()
    horizon = PeriodHorizon.medium()
    result = optimize_periods(dates, prices, horizon)
    assert result.horizon == horizon
    assert sorted(s.half_width_days for s in result.scores) == list(horizon.half_widths)
    assert result.best is result.scores[0]
    assert len(result.peak_pins) >= 2
    assert len(result.trough_pins) >= 2
    assert result.peak_pins == tuple(sorted(result.peak_pins))
    assert result.trough_pins == tuple(sorted(result.trough_pins))
    for name, field in PeriodOptimizationResult.model_fields.items():
        assert field.description, f"{name} has no description"


# ------------------------------------------------------------------ combine


def _w(name: str, kind: CycleKind, day: date, half: int) -> CycleWindow:
    return CycleWindow(
        name=name, kind=kind, start=day - timedelta(days=half), end=day + timedelta(days=half)
    )


def test_long_sells_override_medium_buys_on_an_overlapping_date() -> None:
    shared = date(2024, 6, 1)
    combined = combine_periods(
        [_w("m_buy", CycleKind.TROUGH, shared, 10)],
        [_w("l_sell", CycleKind.PEAK, shared, 5)],
    )
    assert isinstance(combined, SdcaCycleWindows)
    assert combined.kind_on(shared) == CycleKind.PEAK
    assert combined.windows[0].name == "l_sell"


def test_combine_keeps_every_window_in_a_deterministic_precedence_order() -> None:
    day = date(2024, 6, 1)
    later = day + timedelta(days=90)
    combined = combine_periods(
        [_w("m_sell", CycleKind.PEAK, day, 3), _w("m_buy", CycleKind.TROUGH, later, 3)],
        [_w("l_sell", CycleKind.PEAK, day, 2), _w("l_buy", CycleKind.TROUGH, later, 2)],
    )
    assert [w.name for w in combined.windows] == ["l_sell", "m_sell", "l_buy", "m_buy"]
    assert len(combined.peaks()) == 2
    assert len(combined.troughs()) == 2


def test_combine_accepts_window_sequences_and_a_bare_sdcacyclewindows() -> None:
    day = date(2024, 6, 1)
    long = SdcaCycleWindows(windows=(_w("l_buy", CycleKind.TROUGH, day, 2),))
    assert combine_periods((), long).windows == long.windows
    assert combine_periods(long, ()).windows == long.windows


def test_combine_refuses_two_empty_horizons() -> None:
    with pytest.raises(ValueError, match="at least one window"):
        combine_periods((), ())


# ------------------------------------------------------------ split sample


def _regime_shift(bad_tail_up: int) -> tuple[list[date], list[float]]:
    """12 strong cycles (110 up / 30 down), then 12 cycles with the legs swapped."""
    good = _zigzag(110, 30, 12)[1]
    bad = _zigzag(30, 110, 12, tail_up=bad_tail_up)[1]
    prices = good + bad
    return _calendar(len(prices)), prices


def test_split_sample_reports_both_sides_when_the_regime_shift_blinds_it() -> None:
    """Honest read: periods fitted on the strong regime never fire on the weak one."""
    dates, prices = _regime_shift(bad_tail_up=0)
    result = split_sample_check(dates, prices, PeriodHorizon.medium())
    assert isinstance(result, SplitSampleResult)
    assert result.horizon == PeriodHorizon.medium()
    assert result.split == 0.5
    assert result.fit_days + result.score_days == len(dates)
    assert result.fit_best is not None
    assert result.fit_best.half_width_days == 15
    assert result.fit_best.sharpe > 0.0
    assert result.out_of_sample is not None
    assert result.out_of_sample.half_width_days == result.fit_best.half_width_days
    assert result.out_of_sample.exposure_pct == 0.0
    assert result.out_of_sample_eligible is False
    assert result.out_of_sample.sharpe < result.fit_best.sharpe


def test_split_sample_reports_a_transferable_but_weaker_out_of_sample_read() -> None:
    """The fitted windows still fire, but capture far less than they did in-sample."""
    dates, prices = _regime_shift(bad_tail_up=30)
    result = split_sample_check(dates, prices, PeriodHorizon.medium())
    assert result.fit_best is not None
    assert result.out_of_sample is not None
    assert result.out_of_sample.exposure_pct > 50.0
    assert result.out_of_sample_eligible is True
    assert result.out_of_sample.sharpe < result.fit_best.sharpe


def test_split_sample_scores_the_fitted_window_set_on_the_unseen_half() -> None:
    dates, prices = _regime_shift(bad_tail_up=0)
    result = split_sample_check(dates, prices, PeriodHorizon.medium())
    assert result.fit_best is not None
    assert result.out_of_sample is not None
    # The OOS side is driven only by dates inside the unseen calendar.
    acted = set(result.out_of_sample.edges.buy_dates) | set(result.out_of_sample.edges.sell_dates)
    assert acted <= set(dates[result.fit_days :])


def test_split_sample_validates_its_inputs() -> None:
    dates, prices = _up_heavy()
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="split"):
            split_sample_check(dates, prices, PeriodHorizon.medium(), split=bad)
    with pytest.raises(ValueError, match="at least"):
        split_sample_check(dates[:5], prices[:5], PeriodHorizon.medium())
    with pytest.raises(ValueError, match="at least"):
        split_sample_check(dates[:20], prices[:20], PeriodHorizon.medium())


# ============================================== Plan 21 Task 1: long-first
#
# The period model is rebuilt long-first: a SMALL secular window set is the
# primary regime, and medium windows are only later layered on (Task 2). Two
# functions land here, both additive:
#
# - ``window_is_hit`` — did a window actually *catch* a move? A window that
#   covered nothing but decoration is abandoned, and the verdict quotes the
#   observed move so the abandonment can be read rather than trusted.
# - ``select_long_term_periods`` — prominence-ranked cycle pivots, truncated so
#   peak windows stay within a share of the calendar. Peak windows are the flat
#   time that bounds exposure, so that cap is what makes the exposure floor
#   reachable instead of pinned by pivot density.
#
# The pins below assert the CONSTRAINTS, not merely that a value came back: the
# day cap must hold on the returned set, the cap must be the reason the set is
# small, and a minimum that cannot be met must produce a reason, never a
# silently relaxed threshold.


def _closes(values: list[float]) -> tuple[list[date], list[float]]:
    """A price calendar carrying exactly the given closes."""
    return _calendar(len(values)), [float(v) for v in values]


def _whole_calendar_window(dates: list[date], kind: CycleKind = CycleKind.PEAK) -> CycleWindow:
    return CycleWindow(name="w", kind=kind, start=dates[0], end=dates[-1])


# ------------------------------------------------------------- the hit test


def test_a_window_holding_a_twenty_percent_drop_is_hit_at_the_fifteen_percent_threshold() -> None:
    """A real 20% fall clears the frozen 15.0% long-horizon move threshold."""
    dates, prices = _closes([200.0, 200.0, 160.0, 160.0])
    verdict = window_is_hit(dates, prices, _whole_calendar_window(dates), min_move_pct=15.0)
    assert isinstance(verdict, HitTest)
    assert verdict.hit is True
    assert verdict.max_move_pct == pytest.approx(20.0)
    assert verdict.direction == "down"
    assert verdict.min_move_pct == 15.0


def test_a_window_holding_only_a_three_percent_move_is_not_hit() -> None:
    """The same threshold rejects drift: decoration is not a caught move."""
    dates, prices = _closes([100.0, 100.0, 103.0, 103.0])
    window = _whole_calendar_window(dates)
    verdict = window_is_hit(dates, prices, window, min_move_pct=15.0)
    assert verdict.hit is False
    assert verdict.max_move_pct == pytest.approx(3.0)
    assert verdict.direction == "up"
    # The verdict carries the regime it was drawn for, so a sell zone and a buy
    # zone are never mistaken for one another downstream.
    assert verdict.kind == CycleKind.PEAK
    trough = CycleWindow(name="w", kind=CycleKind.TROUGH, start=dates[0], end=dates[-1])
    assert window_is_hit(dates, prices, trough, min_move_pct=15.0).kind == CycleKind.TROUGH


def test_the_threshold_is_inclusive_in_both_move_directions() -> None:
    """Both directions count, and exactly-at-threshold is a hit.

    The boundary is pinned against the *observed* move rather than a rounded
    literal, so the ``>=`` comparison is exercised without a float-literal
    accident deciding the outcome.
    """
    up_dates, up = _closes([100.0, 100.0, 120.0, 120.0])
    rise = window_is_hit(up_dates, up, _whole_calendar_window(up_dates), min_move_pct=15.0)
    assert rise.hit is True and rise.direction == "up"

    dn_dates, dn = _closes([120.0, 120.0, 96.0, 96.0])
    fall = window_is_hit(dn_dates, dn, _whole_calendar_window(dn_dates), min_move_pct=15.0)
    assert fall.hit is True and fall.direction == "down"
    assert fall.max_move_pct == pytest.approx(20.0)

    for observed in (rise.max_move_pct, fall.max_move_pct):
        dates, prices = _closes([100.0, 100.0, 100.0 + observed])
        window = _whole_calendar_window(dates)
        at = window_is_hit(dates, prices, window, min_move_pct=observed)
        assert at.hit is True, f"a move of exactly {observed}% must be a hit"
        above = window_is_hit(dates, prices, window, min_move_pct=observed + 1e-9)
        assert above.hit is False, "a threshold above the observed move must not be a hit"


def test_an_abandoned_window_quotes_the_move_it_actually_contained() -> None:
    """The verdict carries the observed move, so an abandonment can be read."""
    dates, prices = _closes([100.0, 101.0, 102.0, 101.5, 100.5])
    verdict = window_is_hit(dates, prices, _whole_calendar_window(dates), min_move_pct=15.0)
    assert verdict.hit is False
    assert verdict.max_move_pct == pytest.approx(2.0)
    assert verdict.bars == len(dates)
    # Same window, looser threshold: the verdict flips on the recorded move only.
    assert window_is_hit(dates, prices, _whole_calendar_window(dates), min_move_pct=2.0).hit is True


def test_a_window_barely_touching_the_calendar_has_no_move_to_quote() -> None:
    dates, prices = _up_heavy()
    edge = CycleWindow(name="edge", kind=CycleKind.TROUGH, start=dates[0], end=dates[0])
    verdict = window_is_hit(dates, prices, edge, min_move_pct=15.0)
    assert verdict.bars == 1
    assert verdict.max_move_pct == 0.0
    assert verdict.hit is False
    assert verdict.direction == "flat"
    off = CycleWindow(name="off", kind=CycleKind.PEAK, start=dates[-1], end=dates[-1])
    assert window_is_hit(dates, prices, off, min_move_pct=15.0).bars == 1


def test_hit_test_validates_its_inputs() -> None:
    dates, prices = _closes([200.0, 160.0])
    window = _whole_calendar_window(dates)
    with pytest.raises(ValueError, match="min_move_pct"):
        window_is_hit(dates, prices, window, min_move_pct=-1.0)
    with pytest.raises(ValueError, match="same length"):
        window_is_hit(dates, prices[:-1], window, min_move_pct=15.0)
    with pytest.raises(ValueError, match="positive"):
        window_is_hit(dates, [200.0, 0.0], window, min_move_pct=15.0)


# -------------------------------------------------- the long-term selection


def _secular_three_cycles() -> tuple[list[date], list[float]]:
    """Three secular cycles wide enough that the day cap is what limits the set.

    1894 bars with pins 568 bars apart, so the three 121-day peak windows are
    disjoint and cost 363 days of a 473-day budget (25% of the calendar) — while
    a fourth would cost 484 and breach the cap outright. The set is small
    because the cap made it small, not because the series was thin.
    """
    return _zigzag(380, 190, 3, tail_up=190)


def test_three_secular_cycles_select_three_peaks_and_three_troughs_within_the_day_cap() -> None:
    """Pin: the constraint HOLDS on the returned set, not merely that it returned."""
    dates, prices = _secular_three_cycles()
    selection = select_long_term_periods(dates, prices)
    assert isinstance(selection, LongTermSelection)
    assert selection.selected is True
    assert selection.n_peaks == 3
    assert selection.n_troughs == 3
    assert selection.peak_pins == tuple(dates[pin] for pin in (379, 947, 1515))
    assert selection.trough_pins == tuple(dates[pin] for pin in (568, 1136, 1704))
    # The cap, asserted on the numbers the model reports and recomputed here.
    assert selection.peak_days_pct <= selection.max_peak_days_pct == 25.0
    assert selection.trough_days_pct <= selection.max_peak_days_pct
    budget = len(dates) * selection.max_peak_days_pct // 100
    assert selection.peak_days <= budget
    # And the cap is BINDING here: one more window would not have fit.
    window_days = (selection.peaks[0].end - selection.peaks[0].start).days + 1
    assert selection.peak_days + window_days > budget
    # Every window is centred on its own detected pin, at the derived half-width.
    assert [window.kind for window in selection.peaks] == [CycleKind.PEAK] * 3
    assert [window.kind for window in selection.troughs] == [CycleKind.TROUGH] * 3
    for window in selection.windows:
        centre = window.start + timedelta(days=selection.half_width_days)
        assert centre in selection.peak_pins or centre in selection.trough_pins


def test_the_day_cap_truncates_a_denser_series_to_a_small_set() -> None:
    """Six detected secular peaks, three kept: the cap is the mechanism."""
    dates, prices = _zigzag(200, 100, 6, tail_up=100)
    selection = select_long_term_periods(dates, prices)
    assert selection.selected is True
    assert len(selection.peak_pins) == 6 > selection.n_peaks == 3
    assert len(selection.trough_pins) == 6 > selection.n_troughs == 3
    assert selection.peak_days_pct <= 25.0
    assert selection.trough_days_pct <= 25.0
    assert selection.n_peaks >= MIN_PEAKS and selection.n_troughs >= MIN_TROUGHS
    # Kept in prominence-then-date order, reported chronologically.
    kept = [window.start + timedelta(days=selection.half_width_days) for window in selection.peaks]
    assert kept == sorted(kept)
    assert set(kept) <= set(selection.peak_pins)


def _ramped_series(spec: list[tuple[float, float, int]]) -> tuple[list[date], list[float]]:
    """Concat straight ``(from, to, bars)`` ramps, each corner emitted once."""
    prices: list[float] = []
    for index, (start, end, bars) in enumerate(spec):
        ramp = _leg(start, end, bars)
        prices.extend(ramp if index == 0 else ramp[1:])
    return _calendar(len(prices)), prices


def test_prominence_ranks_the_selection_and_date_breaks_its_ties() -> None:
    """The weakest corner is the EARLIEST peak, so date order alone would fail.

    A 561-bar series whose budget admits exactly one window per kind: the first
    peak rises only 23.1% before its trough while the second rises 44.4%, so the
    prominent one survives and the earlier one is dropped. The two troughs are
    exactly tied, so the earlier date wins there — ranking and tie-break in one
    fixture.
    """
    dates, prices = _ramped_series(
        [
            (100.0, 130.0, 161),
            (130.0, 100.0, 81),
            (100.0, 180.0, 161),
            (180.0, 100.0, 81),
            (100.0, 180.0, 81),
        ]
    )
    selection = select_long_term_periods(dates, prices, min_peaks=1, min_troughs=1)
    assert selection.selected is True
    assert selection.peak_pins == (dates[160], dates[400])
    assert selection.n_peaks == 1
    assert selection.peaks[0].start + timedelta(days=selection.half_width_days) == dates[400]
    assert selection.peak_prominence_pct == pytest.approx((44.444444,))
    assert selection.trough_pins == (dates[240], dates[480])
    assert selection.n_troughs == 1
    assert selection.troughs[0].start + timedelta(days=selection.half_width_days) == dates[240]


def test_a_series_with_too_few_pivots_is_refused_with_a_reason_and_never_relaxed() -> None:
    """No structure is not a licence to lower the minimum (pin: never a relaxed minimum)."""
    dates = _calendar(200)
    flat = [_LOW] * 200
    selection = select_long_term_periods(dates, flat)
    assert selection.selected is False
    assert selection.n_peaks == 0 and selection.n_troughs == 0
    assert selection.windows == ()
    assert selection.reason is not None
    assert "min_peaks" in selection.reason and "min_troughs" in selection.reason


def test_truncation_that_breaks_a_minimum_refuses_rather_than_reporting_a_short_set() -> None:
    """The same refusal when the cap, not the series, is what broke the minimum."""
    dates, prices = _ramped_series(
        [
            (100.0, 130.0, 161),
            (130.0, 100.0, 81),
            (100.0, 180.0, 161),
            (180.0, 100.0, 81),
            (100.0, 180.0, 81),
        ]
    )
    relaxed = select_long_term_periods(dates, prices, min_peaks=1, min_troughs=1)
    assert relaxed.selected is True and relaxed.n_peaks == 1
    strict = select_long_term_periods(dates, prices)
    assert strict.selected is False
    assert strict.n_peaks < MIN_PEAKS
    assert strict.reason is not None and "min_peaks" in strict.reason
    assert strict.peak_pins == relaxed.peak_pins, "the same pivots were detected either way"


def test_selection_is_deterministic_across_repeated_calls() -> None:
    for series in (_secular_three_cycles(), _up_heavy(), _zigzag(200, 100, 6, tail_up=100)):
        first = select_long_term_periods(*series)
        second = select_long_term_periods(*series)
        assert first == second


def test_selection_is_deterministic_when_the_input_order_of_pivots_cannot_leak_in() -> None:
    """Detection is index-order, so a re-run of the same series is the same set."""
    dates, prices = _zigzag(200, 100, 6, tail_up=100)
    forward = select_long_term_periods(dates, prices)
    again = select_long_term_periods(dates, prices)
    assert forward.windows == again.windows
    assert forward.peak_prominence_pct == again.peak_prominence_pct


def test_the_selection_models_are_frozen_strict_and_described() -> None:
    dates, prices = _secular_three_cycles()
    selection = select_long_term_periods(dates, prices)
    assert selection.half_width_days == min(PeriodHorizon.long().half_widths)
    with pytest.raises(Exception, match="frozen|immutable"):
        selection.n_peaks = 9  # type: ignore[misc]
    with pytest.raises(Exception, match="frozen|immutable"):
        selection.peaks = ()  # type: ignore[misc]
    for model in (HitTest, LongTermSelection):
        for name, field in model.model_fields.items():
            assert field.description, f"{model.__name__}.{name} has no description"


def test_selection_validates_its_inputs() -> None:
    dates, prices = _secular_three_cycles()
    for bad in (-1.0, 101.0):
        with pytest.raises(ValueError, match="max_peak_days_pct"):
            select_long_term_periods(dates, prices, max_peak_days_pct=bad)
    with pytest.raises(ValueError, match="min_peaks"):
        select_long_term_periods(dates, prices, min_peaks=0)
    with pytest.raises(ValueError, match="min_troughs"):
        select_long_term_periods(dates, prices, min_troughs=0)
    with pytest.raises(ValueError, match="same length"):
        select_long_term_periods(dates[:10], prices)
    with pytest.raises(ValueError, match="at least"):
        select_long_term_periods(dates[:5], prices[:5])


def test_the_long_first_surface_is_exported() -> None:
    from digiquant.strategies.sdca import period_optimize

    for name in ("HitTest", "LongTermSelection", "window_is_hit", "select_long_term_periods"):
        assert name in period_optimize.__all__, f"{name} is missing from __all__"
        assert hasattr(period_optimize, name)


# ================================= Plan 21 Task 1b: the half-width parameter (Ruling 1)
#
# Task-1 review: the long half-width was pinned to ``min(LONG_HALF_WIDTHS)`` = 60d,
# so the ladder could not be re-run per width even though widening is qualitative —
# it can drop ``n_peaks`` below ``MIN_PEAKS`` and the set then refuses. The width is
# therefore settable up-front. Three things must hold:
#
# - **the default reproduces the pre-change selection exactly.** The literals below
#   ARE that pre-change output (captured before the keyword existed), so a refactor
#   that quietly moves the default fails here instead of being noticed by a rerun
#   nobody diffs;
# - **an explicit width is honoured** — wider windows, cap still enforced;
# - **the value travels in the model**, including on the refusal shape, so a run
#   describes its own windows rather than leaving the reader to re-derive them.
#
# Plus the calendar guard: a too-short series must raise a clean ``ValueError``,
# never an ``IndexError`` from indexing ``dates[0]`` / ``dates[-1]``.

_PRE_CHANGE_HALF_WIDTH = min(LONG_HALF_WIDTHS)


def test_the_default_half_width_reproduces_the_pre_change_selection_exactly() -> None:
    """Ruling 1 is additive: the default call is what it was, field for field."""
    dates, prices = _secular_three_cycles()
    selection = select_long_term_periods(dates, prices)
    assert _PRE_CHANGE_HALF_WIDTH == 60
    assert selection.half_width_days == _PRE_CHANGE_HALF_WIDTH
    # Captured from the pre-change implementation on this exact fixture. The four
    # Ruling-2 fields are excluded and pinned separately by the Task-3b pins: this
    # fixture's selection is unchanged by them, but the coverage report on it is not
    # empty (its trough windows sit 447 days apart), so the fields cannot ride in a
    # literal that is about the windows themselves.
    assert selection.model_dump(
        exclude={
            "peak_days_pct",
            "trough_days_pct",
            "dropped_windows",
            "peak_hit_tests",
            "trough_hit_tests",
            "coverage_segments",
        }
    ) == {
        "half_width_days": 60,
        "calendar_days": 1894,
        "max_peak_days_pct": 25.0,
        "peak_days": 363,
        "trough_days": 363,
        "peak_pins": (date(2021, 1, 14), date(2022, 8, 5), date(2024, 2, 24)),
        "trough_pins": (date(2021, 7, 22), date(2023, 2, 10), date(2024, 8, 31)),
        "peak_prominence_pct": (50.0, 50.0, 49.73684210526316),
        "trough_prominence_pct": (100.0, 100.0, 98.95287958115183),
        "peaks": (
            {
                "name": "long_peak_20210114_pm60",
                "kind": CycleKind.PEAK,
                "start": date(2020, 11, 15),
                "end": date(2021, 3, 15),
            },
            {
                "name": "long_peak_20220805_pm60",
                "kind": CycleKind.PEAK,
                "start": date(2022, 6, 6),
                "end": date(2022, 10, 4),
            },
            {
                "name": "long_peak_20240224_pm60",
                "kind": CycleKind.PEAK,
                "start": date(2023, 12, 26),
                "end": date(2024, 4, 24),
            },
        ),
        "troughs": (
            {
                "name": "long_trough_20210722_pm60",
                "kind": CycleKind.TROUGH,
                "start": date(2021, 5, 23),
                "end": date(2021, 9, 20),
            },
            {
                "name": "long_trough_20230210_pm60",
                "kind": CycleKind.TROUGH,
                "start": date(2022, 12, 12),
                "end": date(2023, 4, 11),
            },
            {
                "name": "long_trough_20240831_pm60",
                "kind": CycleKind.TROUGH,
                "start": date(2024, 7, 2),
                "end": date(2024, 10, 30),
            },
        ),
        "selected": True,
        "reason": None,
    }
    assert selection.peak_days_pct == pytest.approx(19.165786694825766)
    assert selection.trough_days_pct == pytest.approx(19.165786694825766)
    # And the default is the frozen tightest long width, named explicitly — not a
    # bare literal that could drift away from the grid it claims to come from.
    assert selection.half_width_days == min(PeriodHorizon.long().half_widths)
    assert select_long_term_periods(dates, prices, half_width_days=_PRE_CHANGE_HALF_WIDTH) == (
        selection
    )


def test_the_default_call_is_unchanged_on_every_long_first_fixture() -> None:
    """The behaviour-preservation pin is a family, not one lucky fixture."""
    fixtures = (
        _secular_three_cycles(),
        _up_heavy(),
        _zigzag(200, 100, 6, tail_up=100),
    )
    for dates, prices in fixtures:
        default = select_long_term_periods(dates, prices)
        explicit = select_long_term_periods(dates, prices, half_width_days=60)
        assert default == explicit
        assert default.half_width_days == 60
    # The refusal shape is unchanged too (captured pre-change).
    dates, prices = _ramped_series(
        [
            (100.0, 130.0, 161),
            (130.0, 100.0, 81),
            (100.0, 180.0, 161),
            (180.0, 100.0, 81),
            (100.0, 180.0, 81),
        ]
    )
    refused = select_long_term_periods(dates, prices)
    assert refused == select_long_term_periods(dates, prices, half_width_days=60)
    assert refused.selected is False
    assert refused.half_width_days == 60
    assert refused.peak_pins == (dates[160], dates[400])
    assert refused.trough_pins == (dates[240], dates[480])
    assert refused.reason is not None
    assert "minimums are never relaxed" in refused.reason


def test_an_explicit_half_width_widens_the_windows_and_still_enforces_the_cap() -> None:
    """90d windows are 181 days wide (not 121), and the day cap still binds."""
    dates, prices = _secular_three_cycles()
    default = select_long_term_periods(dates, prices)
    wide = select_long_term_periods(dates, prices, half_width_days=90)
    assert wide.half_width_days == 90
    assert wide.selected is True
    default_span = (default.peaks[0].end - default.peaks[0].start).days + 1
    wide_span = (wide.peaks[0].end - wide.peaks[0].start).days + 1
    assert default_span == 121
    assert wide_span == 181 > default_span
    for window in wide.windows:
        assert (window.end - window.start).days + 1 == 181
        # The pin is still the window's centre — only the width moved.
        centre = window.start + timedelta(days=90)
        assert centre in wide.peak_pins or centre in wide.trough_pins
    # Width is what costs days, so a wider window buys fewer of them — and the
    # cap is still enforced, still binding, on the set it returned.
    budget = int(len(dates) * wide.max_peak_days_pct / 100.0)
    assert wide.peak_days <= budget
    assert wide.peak_days_pct <= wide.max_peak_days_pct == 25.0
    assert wide.trough_days_pct <= wide.max_peak_days_pct
    assert wide.n_peaks == 2 < default.n_peaks == 3
    assert wide.n_troughs == 2 < default.n_troughs == 3
    assert wide.peak_days + wide_span > budget, "the cap must be the reason it is small"
    # Same detected structure: the pins do not depend on the width.
    assert wide.peak_pins == default.peak_pins
    assert wide.trough_pins == default.trough_pins


def test_a_wide_half_width_can_refuse_by_dropping_below_the_frozen_minima() -> None:
    """Ruling 1's stated hazard: widening can break the minimum — never relaxed."""
    dates, prices = _secular_three_cycles()
    refused = select_long_term_periods(dates, prices, half_width_days=120)
    assert refused.selected is False
    assert refused.windows == ()
    assert refused.n_peaks == 0
    assert refused.n_troughs == 0
    assert refused.peak_days == 0 and refused.peak_days_pct == 0.0
    # The reason quotes what the cap *did* keep, so the width is legible as the cause.
    assert refused.reason is not None
    assert "kept 1 peak / 1 trough windows" in refused.reason
    assert f"min_peaks={MIN_PEAKS}" in refused.reason
    assert "minimums are never relaxed" in refused.reason
    # The refusal still describes the run that produced it.
    assert refused.half_width_days == 120
    assert refused.peak_pins == select_long_term_periods(dates, prices).peak_pins


def test_a_narrower_half_width_keeps_more_real_structure_under_the_same_cap() -> None:
    """Width is the lever the cap trades against; the cap itself never moves.

    Two regimes, because Ruling 2 made the hit test part of long selection. Where a
    narrow window still catches a move, it costs fewer days and so buys more of the
    detected structure under the same cap (``_up_heavy``: 3 windows at 60d, 6 at 30d).
    Where it does not — these secular legs rise 380 bars, so a +-30d window at the peak
    sees about 4% of move — every candidate misses the frozen 15.0% bar and the
    selection refuses rather than shipping decoration. Both are the same cap, doing the
    same job.
    """
    dates, prices = _up_heavy()
    default = select_long_term_periods(dates, prices)
    narrow = select_long_term_periods(dates, prices, half_width_days=30)
    assert narrow.half_width_days == 30
    assert narrow.selected is True, narrow.reason
    assert narrow.n_peaks == default.n_peaks + 3 == 6
    assert narrow.troughs and narrow.peak_days_pct <= narrow.max_peak_days_pct
    assert narrow.max_peak_days_pct == default.max_peak_days_pct == 25.0
    assert narrow.dropped_windows == ()

    secular_dates, secular_prices = _secular_three_cycles()
    refused = select_long_term_periods(secular_dates, secular_prices, half_width_days=30)
    assert refused.selected is False
    assert refused.windows == ()
    assert refused.dropped_windows, "the drops are what the refusal rests on"
    assert all(window.required_move_pct == LONG_MIN_MOVE_PCT for window in refused.dropped_windows)
    assert "hit test" in (refused.reason or "")


def test_selection_rejects_a_non_positive_half_width() -> None:
    dates, prices = _secular_three_cycles()
    for bad in (0, -1, -90):
        with pytest.raises(ValueError, match="half_width_days"):
            select_long_term_periods(dates, prices, half_width_days=bad)


def test_a_calendar_too_short_to_index_fails_cleanly_never_with_indexerror() -> None:
    """The guard: a clean ValueError, because ``dates[0]`` / ``dates[-1]`` are read."""
    for length in (0, 1):
        dates, prices = _calendar(length), [_LOW] * length
        with pytest.raises(ValueError, match="at least"):
            select_long_term_periods(dates, prices)
        with pytest.raises(ValueError) as excinfo:
            select_long_term_periods(dates, prices, half_width_days=30)
        assert not isinstance(excinfo.value, IndexError)
        assert "at least" in str(excinfo.value)
    # A misaligned pair is still caught by length, not by a stray index.
    with pytest.raises(ValueError, match="same length"):
        select_long_term_periods(_calendar(1), [])
    # Two bars are enough to pass this guard; the pivot confirmation requirement is
    # reported by the detector's own message.
    with pytest.raises(ValueError, match="at least"):
        select_long_term_periods(_calendar(2), [_LOW, _HIGH])


# ============ Plan 21 Task 3b: the long-side hit test + coverage constraint (Ruling 2)
#
# Task-3 review found the real mechanism and corrected the framing twice. The long
# set was wrong in two separate ways, and both are pinned here:
#
# - **The hit test only gated MEDIUM additions.** A long window that caught 9.25%
#   of move was kept, so the owner's "identify and abandon windows that do not get
#   hit" was never applied to the primary regime at all. Every prominence-ranked
#   long candidate is now hit-tested at the frozen ``LONG_MIN_MOVE_PCT`` BEFORE it
#   consumes its per-kind day budget: an unhit pin is skipped, its budget stays
#   available to the next pin that did catch a move, and the drop is recorded with
#   the move that pin's window actually contained.
# - **Coverage.** Actions are emitted at window ENTERS, so any stretch of calendar
#   holding no selected trough window is flat by construction — on GLD one such
#   stretch ran 3063 days. The selection now measures every calendar segment
#   between consecutive selected trough windows and records the ones that are
#   uncovered, with their dates and their gap length, rather than emitting a set
#   whose holes have to be discovered from a tearsheet.
#
# The repair Ruling 2 asks for — swap the lowest-prominence selected PEAK in the
# segment for the best hit trough available there — is attempted and its verdict
# recorded, and it is never admissible. The reason is structural, not a tuning
# accident: ``_truncate_to_day_cap`` walks the ranked candidates and keeps every
# window that fits, so the kept set is **addition-maximal**. A candidate it skipped
# had ``covered_then | days`` over budget, and the covered set only grows, so
# re-adding it breaches the very per-kind cap the walk enforced. Giving up a PEAK
# cannot help either, because the two kinds are capped independently. So a segment
# that HAS a hit trough available is recorded as blocked by the day cap — the
# constraint that actually binds — and never quietly left unreported.


def _prominent_but_unhit() -> tuple[list[date], list[float]]:
    """A high-prominence peak pin whose own window caught only 11.11% of move.

    The first peak pin's prominence (40.0%, the fall to the next trough) is measured
    over a 301-bar leg, far longer than its own 121-day window, so the window sees
    only the last fifth of the rise into the pin and the first slice of the fall out
    of it: 11.11% in total, under the frozen 15.0% bar. It is the
    second-most-prominent pin on the series and it is not worth trading, so the hit
    test has to drop it and hand its budget to the next pin that did catch
    something. The legs behind it are 121 bars, so those windows do clear the bar.
    """
    return _ramped_series(
        [
            (100.0, 200.0, 301),
            (200.0, 120.0, 301),
            (120.0, 240.0, 121),
            (240.0, 100.0, 121),
            (100.0, 180.0, 121),
            (180.0, 130.0, 121),
            (130.0, 210.0, 121),
            (210.0, 160.0, 121),
        ]
    )


def _scattered_secular_set() -> tuple[list[date], list[float]]:
    """Ten secular cycles at VARYING amplitude, so the cap keeps a scattered subset.

    Every cycle is 181 bars up and 181 down with a different high/low pair, so
    prominence differs cycle to cycle and the day cap keeps the prominent pins
    rather than the early ones. The kept troughs therefore sit far apart while
    unselected HIT troughs exist between them — the synthetic twin of the GLD
    coverage hole, and the fixture the repair attempt is pinned on.
    """
    pairs = (
        (200.0, 120.0),
        (150.0, 105.0),
        (240.0, 130.0),
        (170.0, 110.0),
        (230.0, 125.0),
        (160.0, 115.0),
        (250.0, 135.0),
        (180.0, 108.0),
        (210.0, 122.0),
        (165.0, 112.0),
    )
    prices = [pairs[0][0]]
    for high, low in pairs:
        if prices[-1] != low:
            prices.extend(_leg(prices[-1], low, 181)[1:])
        prices.extend(_leg(low, high, 181)[1:])
    prices.extend(_leg(prices[-1], 140.0, 121)[1:])
    return _calendar(len(prices)), prices


def _centres(selection: LongTermSelection, windows: tuple[CycleWindow, ...]) -> tuple[date, ...]:
    """The pins a set of emitted windows is centred on, chronological."""
    offset = timedelta(days=selection.half_width_days)
    return tuple(window.start + offset for window in windows)


def _kept_verdict(name: str, kind: CycleKind, max_move_pct: float, direction: str) -> HitTest:
    """The verdict a kept window must carry: hit, at the frozen long bar."""
    return HitTest(
        window=name,
        kind=kind,
        bars=121,
        min_move_pct=LONG_MIN_MOVE_PCT,
        max_move_pct=max_move_pct,
        direction=direction,
        hit=True,
    )


def _kept_segment(start: date, end: date) -> CoverageSegment:
    """A covered segment between two selected trough windows, nothing to report."""
    gap_start, gap_end = start + timedelta(days=61), end - timedelta(days=61)
    return CoverageSegment(
        start=start,
        end=end,
        gap_start=gap_start,
        gap_end=gap_end,
        gap_days=(gap_end - gap_start).days + 1,
        covered=True,
        repaired=False,
        swapped_out_peak=None,
        swapped_in_trough=None,
        reason=None,
    )


def test_an_unhit_prominent_long_candidate_is_dropped_for_the_next_hit_pin() -> None:
    """The long side abandons what it did not catch, and the budget is not wasted."""
    dates, prices = _prominent_but_unhit()
    unhit_pin, promoted_pin = dates[300], dates[960]
    peak_pins, _trough_pins = detect_pivots(dates, prices, PeriodHorizon.long())
    assert unhit_pin in peak_pins and promoted_pin in peak_pins

    selection = select_long_term_periods(dates, prices)
    assert selection.selected is True, selection.reason
    kept_peaks = _centres(selection, selection.peaks)
    # Pre-change the cap's second slot went to the unhit pin; now it goes to the
    # next pin that cleared the frozen bar. Same count, a different window.
    assert kept_peaks == (dates[720], promoted_pin)
    assert kept_peaks != (unhit_pin, dates[720])
    assert set(kept_peaks) <= set(selection.peak_pins)

    dropped = {window.pin: window for window in selection.dropped_windows}
    assert unhit_pin in dropped, "the drop must be recorded, not silent"
    record = dropped[unhit_pin]
    assert record.kind == CycleKind.PEAK
    assert record.prominence_pct == pytest.approx(40.0)
    assert record.observed_move_pct == pytest.approx(100.0 * (200.0 - 180.0) / 180.0)
    assert record.required_move_pct == LONG_MIN_MOVE_PCT == 15.0
    assert record.observed_move_pct < record.required_move_pct
    assert record.bars > 0
    assert f"{LONG_MIN_MOVE_PCT:.1f}" in record.reason
    assert f"{record.observed_move_pct:.2f}" in record.reason


def test_the_hit_verdicts_for_the_kept_windows_travel_with_the_selection() -> None:
    """A kept window's verdict is re-readable, not merely implied by its presence."""
    dates, prices = _prominent_but_unhit()
    selection = select_long_term_periods(dates, prices)
    for windows, verdicts in (
        (selection.peaks, selection.peak_hit_tests),
        (selection.troughs, selection.trough_hit_tests),
    ):
        assert len(verdicts) == len(windows)
        assert verdicts == tuple(
            window_is_hit(dates, prices, window, min_move_pct=LONG_MIN_MOVE_PCT)
            for window in windows
        )
        for window, verdict in zip(windows, verdicts, strict=True):
            assert verdict.window == window.name
            assert verdict.kind == window.kind
            assert verdict.hit is True, "nothing unhit may survive into a kept window"
            assert verdict.min_move_pct == LONG_MIN_MOVE_PCT


def test_a_series_needing_neither_a_drop_nor_a_repair_is_field_for_field_unchanged() -> None:
    """Ruling 2 is additive: a set that needs neither is exactly what it was.

    ``_up_heavy`` is the fixture for it — no candidate misses the frozen bar, and its
    selected trough windows are 17 days apart (far inside one window width), so
    nothing is uncovered and no repair is attempted. The dict below was captured
    from the pre-change implementation on this exact fixture: it is that output, field
    for field, so a refactor that quietly moves the new rules onto a set that needed
    neither fails here instead of being noticed by a rerun nobody diffs.
    """
    dates, prices = _up_heavy()
    selection = select_long_term_periods(dates, prices)
    # The two new rules are inert on this fixture, so they are compared as models
    # (the four excluded fields below) while every pre-change field is compared
    # straight out of ``model_dump``.
    assert selection.model_dump(
        exclude={"dropped_windows", "peak_hit_tests", "trough_hit_tests", "coverage_segments"}
    ) == {
        "half_width_days": 60,
        "calendar_days": 1686,
        "max_peak_days_pct": 25.0,
        "peak_days": 363,
        "peak_days_pct": 21.530249110320284,
        "trough_days": 363,
        "trough_days_pct": 21.530249110320284,
        "peak_pins": (
            date(2020, 4, 19),
            date(2020, 9, 4),
            date(2021, 1, 20),
            date(2021, 6, 7),
            date(2021, 10, 23),
            date(2022, 3, 10),
            date(2022, 7, 26),
            date(2022, 12, 11),
            date(2023, 4, 28),
            date(2023, 9, 13),
            date(2024, 1, 29),
            date(2024, 6, 15),
        ),
        "trough_pins": (
            date(2020, 5, 18),
            date(2020, 10, 3),
            date(2021, 2, 18),
            date(2021, 7, 6),
            date(2021, 11, 21),
            date(2022, 4, 8),
            date(2022, 8, 24),
            date(2023, 1, 9),
            date(2023, 5, 27),
            date(2023, 10, 12),
            date(2024, 2, 27),
            date(2024, 7, 14),
        ),
        "peak_prominence_pct": (50.0, 50.0, 50.0),
        "trough_prominence_pct": (100.0, 100.0, 100.0),
        "peaks": (
            {
                "name": "long_peak_20200419_pm60",
                "kind": CycleKind.PEAK,
                "start": date(2020, 2, 19),
                "end": date(2020, 6, 18),
            },
            {
                "name": "long_peak_20200904_pm60",
                "kind": CycleKind.PEAK,
                "start": date(2020, 7, 6),
                "end": date(2020, 11, 3),
            },
            {
                "name": "long_peak_20210120_pm60",
                "kind": CycleKind.PEAK,
                "start": date(2020, 11, 21),
                "end": date(2021, 3, 21),
            },
        ),
        "troughs": (
            {
                "name": "long_trough_20200518_pm60",
                "kind": CycleKind.TROUGH,
                "start": date(2020, 3, 19),
                "end": date(2020, 7, 17),
            },
            {
                "name": "long_trough_20201003_pm60",
                "kind": CycleKind.TROUGH,
                "start": date(2020, 8, 4),
                "end": date(2020, 12, 2),
            },
            {
                "name": "long_trough_20210218_pm60",
                "kind": CycleKind.TROUGH,
                "start": date(2020, 12, 20),
                "end": date(2021, 4, 19),
            },
        ),
        "selected": True,
        "reason": None,
    }
    # The two new rules, both inert on this fixture: nothing dropped, both segments
    # covered, and every kept window's verdict read off its own bars.
    assert selection.dropped_windows == ()
    assert selection.peak_hit_tests == (
        _kept_verdict("long_peak_20200419_pm60", CycleKind.PEAK, 50.0, "down"),
        _kept_verdict("long_peak_20200904_pm60", CycleKind.PEAK, 50.0, "down"),
        _kept_verdict("long_peak_20210120_pm60", CycleKind.PEAK, 50.0, "down"),
    )
    assert selection.trough_hit_tests == (
        _kept_verdict("long_trough_20200518_pm60", CycleKind.TROUGH, 55.04587155963304, "up"),
        _kept_verdict("long_trough_20201003_pm60", CycleKind.TROUGH, 55.04587155963304, "up"),
        _kept_verdict("long_trough_20210218_pm60", CycleKind.TROUGH, 55.04587155963304, "up"),
    )
    assert selection.coverage_segments == (
        _kept_segment(date(2020, 5, 18), date(2020, 10, 3)),
        _kept_segment(date(2020, 10, 3), date(2021, 2, 18)),
    )
    assert selection.coverage_complete is True
    assert selection.uncovered_segments == ()


def test_an_uncovered_segment_is_recorded_with_its_dates_and_gap_length() -> None:
    """A calendar stretch holding no trough window is named, not left to be found."""
    dates, prices = _scattered_secular_set()
    selection = select_long_term_periods(dates, prices)
    assert selection.selected is True, selection.reason
    kept_troughs = _centres(selection, selection.troughs)
    segments = selection.coverage_segments
    # One segment per consecutive pair of selected trough windows, in order.
    assert [(segment.start, segment.end) for segment in segments] == list(
        zip(kept_troughs, kept_troughs[1:], strict=False)
    )
    assert segments, "the fixture keeps several troughs, so it has segments to report"
    uncovered = selection.uncovered_segments
    assert uncovered, "the scattered set leaves gaps a trough window could have filled"
    assert selection.coverage_complete is False
    for segment in uncovered:
        # The gap is the calendar between the two trough WINDOWS, quoted in days.
        assert segment.gap_start == segment.start + timedelta(days=61)
        assert segment.gap_end == segment.end - timedelta(days=61)
        assert segment.gap_days == (segment.gap_end - segment.gap_start).days + 1
        # Shorter than one window width, the stretch cannot have held a whole
        # window-shaped opportunity, so it is not a hole worth reporting.
        assert segment.gap_days >= 2 * selection.half_width_days + 1
        assert segment.covered is False
        assert segment.repaired is False
        assert segment.swapped_in_trough is None
        assert segment.reason


def test_a_segment_with_a_hit_trough_records_the_day_cap_that_blocks_the_repair() -> None:
    """The repair is attempted, and the verdict names the constraint that binds.

    Ruling 2's swap — the lowest-prominence selected peak out, the best hit trough
    available in that segment in — is refused here by the per-kind day cap, and the
    segment says so. It cannot be otherwise: ``_truncate_to_day_cap`` keeps every
    window that fits, so its kept set is addition-maximal and re-adding any skipped
    candidate breaches the cap it enforced, and the two kinds are capped
    independently, so giving up a peak frees no trough budget. The verdict is
    reported rather than swallowed, because "the day cap is what blocks coverage" is
    the finding.
    """
    dates, prices = _scattered_secular_set()
    selection = select_long_term_periods(dates, prices)
    blocked_by_cap = [
        segment for segment in selection.uncovered_segments if "day cap" in (segment.reason or "")
    ]
    starved = [
        segment
        for segment in selection.uncovered_segments
        if "no hit trough" in (segment.reason or "")
    ]
    assert blocked_by_cap, "at least one uncovered segment has a hit trough available to try"
    assert starved, "at least one uncovered segment has nothing to swap in"
    for segment in blocked_by_cap:
        # A selected peak was there to give up — the day cap is what stopped it.
        assert segment.swapped_out_peak is None
        assert f"{selection.max_peak_days_pct:.1f}%" in (segment.reason or "")
    # And the refusal held: nothing about the set broke on the way there.
    budget = len(dates) * selection.max_peak_days_pct // 100
    assert selection.peak_days <= budget
    assert selection.trough_days <= budget


def test_the_per_kind_day_cap_and_both_minima_hold_on_every_returned_set() -> None:
    """What a swap must never break, asserted on every fixture that returns a set.

    Ruling 2 requires the cap and both minima to still hold after a swap. No swap is
    admissible (see the cap pin above), so what is pinned here is the invariant
    itself: no returned set breaches the per-kind day cap and none is short of either
    minimum. A refusal stays a refusal — the minima are never relaxed to manufacture a
    set, and hit-testing candidates never becomes a licence to ship a short one.
    """
    fixtures = (
        _prominent_but_unhit(),
        _scattered_secular_set(),
        _secular_three_cycles(),
        _up_heavy(),
        _zigzag(200, 100, 6, tail_up=100),
    )
    for dates, prices in fixtures:
        selection = select_long_term_periods(dates, prices)
        assert selection.selected is True, selection.reason
        budget = len(dates) * selection.max_peak_days_pct // 100
        assert selection.peak_days <= budget
        assert selection.trough_days <= budget
        assert selection.peak_days_pct <= selection.max_peak_days_pct
        assert selection.trough_days_pct <= selection.max_peak_days_pct
        assert selection.n_peaks >= MIN_PEAKS
        assert selection.n_troughs >= MIN_TROUGHS
        assert len(selection.peak_hit_tests) == selection.n_peaks
        assert len(selection.trough_hit_tests) == selection.n_troughs
        assert len(selection.coverage_segments) == max(0, selection.n_troughs - 1)
    # A hit test that removes too many windows refuses rather than shipping a short set.
    refused = select_long_term_periods(*_secular_three_cycles(), max_peak_days_pct=5.0)
    assert refused.selected is False
    assert refused.windows == ()


def test_the_coverage_report_holds_no_segment_when_there_is_nothing_between_two_troughs() -> None:
    """One selected trough cannot straddle itself, so no segment is invented."""
    dates, prices = _prominent_but_unhit()
    selection = select_long_term_periods(dates, prices)
    assert selection.n_troughs == 2
    assert len(selection.coverage_segments) == selection.n_troughs - 1


# ==================================== Plan 21 Task 2: the graded medium overlay
#
# The long set is the primary regime; medium windows are layered on GRADUALLY, one
# rung at a time, and a rung is kept only if all three frozen conditions hold:
#
# - **(a) hit** — every offered window actually caught a move of at least
#   ``min_move_pct``, tested BEFORE scoring, so a decorative window costs nothing;
# - **(b) strict improvement** — oracle Sharpe must *strictly* beat the current set;
# - **(c) the exposure floor** — and the floor is never relaxed to let a rung through.
#
# The first rung that fails stops the ladder. Skipping ahead would grade a book that
# was never built, so "the next one looked good" is not a reason to continue.
#
# Fixtures are read off real oracle numbers, so each pin asserts the DECISION rather
# than a shape: the up-heavy series has a long set that is *worse than flat* on its
# own (Sharpe -0.037) and a 15d medium set that fixes it (2.085), while the 20d set
# then gives it back (0.654) — keep, abandon, stop, in two rungs.


def _candidate_at(candidates: tuple[PeriodCandidate, ...], half_width_days: int) -> PeriodCandidate:
    """The one candidate at a given half-width, asserted unique so a pin cannot drift."""
    matches = [c for c in candidates if c.half_width_days == half_width_days]
    assert len(matches) == 1, f"expected one candidate at {half_width_days}d, got {matches}"
    return matches[0]


def _medium_candidates(dates: list[date], prices: list[float]) -> tuple[PeriodCandidate, ...]:
    """Every medium candidate discovery offers, in the order the module grades them."""
    return discover_candidate_periods(dates, prices, PeriodHorizon.medium())


def _hand_candidate(name: str, half_width_days: int, centre: date) -> PeriodCandidate:
    """A candidate built by hand, for pinning behaviour discovery cannot produce.

    Ordering is a property of the *input*, so a fixture that only exists to test
    ordering is written directly rather than bent out of a price series. The pins
    always neutralize the metrics (an unreachable move threshold), so what is under
    test is which rung was offered first, never whether it was a good idea.
    """
    offset = timedelta(days=half_width_days)
    return PeriodCandidate(
        horizon="medium",
        half_width_days=half_width_days,
        peaks=(
            CycleWindow(
                name=f"{name}_peak", kind=CycleKind.PEAK, start=centre - offset, end=centre + offset
            ),
        ),
        troughs=(
            CycleWindow(
                name=f"{name}_trough",
                kind=CycleKind.TROUGH,
                start=centre - offset,
                end=centre + offset,
            ),
        ),
    )


def _long_base(dates: list[date], prices: list[float]) -> tuple[CycleWindow, ...]:
    selection = select_long_term_periods(dates, prices)
    assert selection.selected is True, selection.reason
    return selection.windows


def _unhit_never(*_: object) -> float:
    """A move threshold no window can clear, so a rung always stops at the hit test."""
    return 1.0e9


def test_an_improving_overlay_is_kept_and_the_ladder_shows_the_rung() -> None:
    dates, prices = _up_heavy()
    base = _long_base(dates, prices)
    candidates = _medium_candidates(dates, prices)
    grade = grade_medium_overlay(dates, prices, base, candidates)
    assert isinstance(grade, OverlayGrade)
    assert grade.exposure_floor_pct == EXPOSURE_FLOOR_PCT == 70.0
    assert grade.min_move_pct == 10.0
    assert grade.base_windows == base
    # Rung 0 is the long set ALONE, reported whatever it scores — the floor gates
    # what gets added onto it, never whether the base is even read.
    assert grade.baseline.sharpe == pytest.approx(-0.03680572090431364, rel=1e-9)
    assert grade.baseline.exposure_pct == pytest.approx(91.87425860023724, rel=1e-9)

    first = grade.steps[0]
    assert first.index == 1
    assert first.half_width_days == 15
    assert first.added == _candidate_at(candidates, 15).windows
    assert first.kept_windows == base + first.added
    assert first.kept is True
    assert first.reason is None
    assert first.degenerate is False
    assert first.sharpe == pytest.approx(2.084666040985284, rel=1e-9)
    assert first.sharpe > grade.baseline.sharpe
    assert first.exposure_pct == pytest.approx(71.23368920521945, rel=1e-9)
    assert first.exposure_pct >= EXPOSURE_FLOOR_PCT
    assert first.calmar == pytest.approx(1.1893985667672913, rel=1e-9)
    assert first.cagr_pct == pytest.approx(40.54767841252129, rel=1e-9)
    assert first.max_drawdown_pct == pytest.approx(34.09090909090909, rel=1e-9)
    # The rung is on the ladder, and it is on the book.
    assert grade.ladder == (first,)
    # The book is the base plus the rung, reported in one chronological order.
    assert set(grade.kept_windows) == set(base) | set(first.added)
    assert grade.kept_windows == tuple(
        sorted((*base, *first.added), key=lambda w: (w.start, w.end, str(w.kind)))
    )


def test_a_non_improving_addition_is_abandoned_and_the_ladder_stops_there() -> None:
    """No skipping ahead: the 30d / 45d / 60d sets are never even offered."""
    dates, prices = _up_heavy()
    base = _long_base(dates, prices)
    candidates = _medium_candidates(dates, prices)
    grade = grade_medium_overlay(dates, prices, base, candidates)
    assert [candidate.half_width_days for candidate in candidates] == [15, 20, 30, 45, 60]

    kept, stalled = grade.steps
    assert kept.kept is True
    assert stalled.index == 2
    assert stalled.half_width_days == 20
    assert stalled.kept is False
    assert stalled.reason is not None
    assert stalled.reason.startswith("sharpe:")
    # The reason quotes both sides, so "no improvement" is readable, not asserted.
    assert f"{stalled.sharpe:.4f}" in stalled.reason
    assert f"{grade.ladder[0].sharpe:.4f}" in stalled.reason
    assert stalled.sharpe < grade.ladder[0].sharpe
    # Stopped here: two rungs graded out of five offered, and no later rung appears.
    assert len(grade.steps) == 2
    assert grade.stop_reason == stalled.reason
    assert grade.ladder == (kept,)
    # Nothing from the abandoned rung or from the untried ones reached the book: the
    # 15d set is in it, and no other medium width is.
    assert set(stalled.added).isdisjoint(grade.kept_windows)
    medium_widths = {
        int(window.name.rsplit("_pm", 1)[1])
        for window in grade.kept_windows
        if window.name.startswith("medium_")
    }
    assert medium_widths == {15}


def test_an_unhit_window_is_abandoned_before_scoring_with_the_move_it_contained() -> None:
    """Pin: reason ``unhit``, the observed move quoted, and nothing measured."""
    dates, prices = _secular_three_cycles()
    base = _long_base(dates, prices)
    candidates = _medium_candidates(dates, prices)
    grade = grade_medium_overlay(dates, prices, base, candidates)

    assert len(grade.steps) == 1, "the unhit rung stops the ladder before any scoring"
    step = grade.steps[0]
    assert step.half_width_days == 15
    assert step.kept is False
    assert step.reason is not None
    assert step.reason.startswith("unhit:")
    unhit = next(verdict for verdict in step.hit if not verdict.hit)
    assert unhit.window in step.reason
    assert f"{unhit.max_move_pct:.2f}" in step.reason
    assert f"{grade.min_move_pct:.1f}" in step.reason
    # Abandoned BEFORE scoring: no metric was measured, so none is invented.
    assert step.sharpe is None
    assert step.exposure_pct is None
    assert step.calmar is None
    assert step.cagr_pct is None
    assert step.max_drawdown_pct is None
    assert step.degenerate is None
    # But the hit verdicts are all there, one per offered window, so the
    # abandonment can be read rather than trusted.
    assert step.hit == tuple(
        window_is_hit(dates, prices, window, min_move_pct=10.0)
        for window in _candidate_at(candidates, 15).windows
    )
    assert all(not verdict.hit for verdict in step.hit)
    assert all(verdict.max_move_pct < 10.0 for verdict in step.hit)
    # And the long set is untouched: nothing was added, so nothing is claimed.
    assert grade.ladder == ()
    assert grade.kept_windows == base
    assert grade.stop_reason == step.reason
    # The 15d set really would have raised exposure if it had been graded — the
    # hit test, not a convenient floor, is what refused it.
    trial = score_periods(dates, prices, base + _candidate_at(candidates, 15).windows)
    assert trial.exposure_pct == pytest.approx(53.16789862724393, rel=1e-9)


def test_a_rung_that_breaches_the_exposure_floor_is_abandoned_naming_the_floor() -> None:
    """Pin: it improved (b) and still died on (c), with reason ``exposure``."""
    dates, prices = _zigzag(200, 100, 6, tail_up=100)
    base = _long_base(dates, prices)
    candidates = _medium_candidates(dates, prices)
    # A lower move threshold so the rung reaches scoring at all: what must bite here
    # is the floor, not the hit test.
    grade = grade_medium_overlay(dates, prices, base, candidates, min_move_pct=5.0)
    assert len(grade.steps) == 1
    step = grade.steps[0]
    assert step.kept is False
    assert step.reason is not None
    assert step.reason.startswith("exposure:")
    assert f"{step.exposure_pct:.2f}" in step.reason
    assert f"{EXPOSURE_FLOOR_PCT:.1f}" in step.reason
    # It DID improve — so the floor is what stopped it, not the improvement test.
    assert step.sharpe == pytest.approx(4.00516691370638, rel=1e-9)
    assert step.sharpe > grade.baseline.sharpe == pytest.approx(0.6225142675136313, rel=1e-9)
    assert step.exposure_pct == pytest.approx(61.1228813559322, rel=1e-9)
    assert step.exposure_pct < EXPOSURE_FLOOR_PCT
    # Unlike an unhit rung, an exposure rung IS measured — the numbers are there.
    assert step.calmar is not None and step.cagr_pct is not None
    assert step.max_drawdown_pct is not None and step.degenerate is False
    assert grade.ladder == ()
    assert grade.kept_windows == base
    assert grade.stop_reason == step.reason


def test_the_exposure_floor_is_never_relaxed_to_let_a_rung_through() -> None:
    """The same rung that clears 70% is abandoned at 80%, and the floor is reported."""
    dates, prices = _up_heavy()
    base = _long_base(dates, prices)
    candidates = _medium_candidates(dates, prices)
    allowed = grade_medium_overlay(dates, prices, base, candidates)
    assert allowed.steps[0].kept is True

    stricter = grade_medium_overlay(dates, prices, base, candidates, exposure_floor_pct=80.0)
    assert stricter.exposure_floor_pct == 80.0
    assert stricter.steps[0].kept is False
    assert stricter.steps[0].reason is not None
    assert stricter.steps[0].reason.startswith("exposure:")
    assert stricter.steps[0].sharpe == allowed.steps[0].sharpe, "the score did not move"
    assert stricter.ladder == ()
    assert stricter.kept_windows == base
    assert stricter.baseline.sharpe == allowed.baseline.sharpe


def test_rungs_are_graded_shortest_window_first_then_earlier_date() -> None:
    """The frozen tie-break, pinned where it is unambiguous: the first rung.

    ``min_move_pct`` no window can clear stops every ladder at rung one, so the
    first rung graded IS the ordering decision — no metric noise can hide it.
    """
    dates, prices = _up_heavy()
    base = _long_base(dates, prices)
    narrow_early = _hand_candidate("narrow_early", 15, date(2020, 3, 1))
    narrow_late = _hand_candidate("narrow_late", 15, date(2020, 9, 1))
    wide_early = _hand_candidate("wide_early", 45, date(2020, 2, 1))
    assert wide_early.windows[0].start < narrow_early.windows[0].start, "fixture: date order"

    grade = grade_medium_overlay(
        dates,
        prices,
        base,
        [wide_early, narrow_late, narrow_early],
        min_move_pct=_unhit_never(),
    )
    assert len(grade.steps) == 1
    assert grade.steps[0].half_width_days == 15
    assert grade.steps[0].added == narrow_early.windows
    # Width dominates date, and the input order is irrelevant.
    for order in ([narrow_late, wide_early, narrow_early], [narrow_early, narrow_late, wide_early]):
        assert (
            grade_medium_overlay(dates, prices, base, order, min_move_pct=_unhit_never()) == grade
        )


def test_the_real_ladder_climbs_widths_in_order_and_is_repeatable() -> None:
    dates, prices = _up_heavy()
    base = _long_base(dates, prices)
    candidates = _medium_candidates(dates, prices)
    first = grade_medium_overlay(dates, prices, base, candidates)
    second = grade_medium_overlay(dates, prices, base, tuple(reversed(candidates)))
    assert first == second
    widths = [step.half_width_days for step in first.steps]
    assert widths == sorted(widths)
    assert widths == [step.half_width_days for step in first.ladder] + [widths[-1]]
    assert [step.index for step in first.steps] == list(range(1, len(first.steps) + 1))


def test_a_candidate_the_book_already_carries_is_not_scored_twice() -> None:
    """Re-offering an identical set cannot improve anything, so it is abandoned."""
    dates, prices = _up_heavy()
    base = _long_base(dates, prices)
    candidates = _medium_candidates(dates, prices)
    duplicate = _candidate_at(candidates, 15)
    grade = grade_medium_overlay(dates, prices, base, [duplicate, duplicate])
    assert len(grade.steps) == 2
    kept, duplicate_rung = grade.steps
    assert kept.kept is True
    assert duplicate_rung.index == 2
    assert duplicate_rung.kept is False
    assert duplicate_rung.reason is not None
    assert duplicate_rung.reason.startswith("duplicate:")
    # Nothing was added, so nothing was hit-tested or scored: reporting a score for
    # the set that was already there would be a phantom rung.
    assert duplicate_rung.added == ()
    assert duplicate_rung.hit == ()
    assert duplicate_rung.sharpe is None
    assert duplicate_rung.exposure_pct is None
    assert duplicate_rung.kept_windows == kept.kept_windows  # the set itself is unchanged
    # The book is unchanged and un-duplicated.
    assert grade.kept_windows == tuple(
        sorted(kept.kept_windows, key=lambda w: (w.start, w.end, str(w.kind)))
    )
    assert len(grade.kept_windows) == len(base) + len(duplicate.windows)
    assert len(set(grade.kept_windows)) == len(grade.kept_windows)
    assert grade.stop_reason == duplicate_rung.reason


def test_the_overlay_models_are_frozen_strict_and_described() -> None:
    dates, prices = _up_heavy()
    grade = grade_medium_overlay(
        dates, prices, _long_base(dates, prices), _medium_candidates(dates, prices)
    )
    with pytest.raises(Exception, match="frozen|immutable"):
        grade.steps = ()  # type: ignore[misc]
    with pytest.raises(Exception, match="frozen|immutable"):
        grade.kept_windows = ()  # type: ignore[misc]
    with pytest.raises(Exception, match="frozen|immutable"):
        grade.steps[0].kept = False  # type: ignore[misc]
    for model in (OverlayGrade, OverlayStep):
        for name, field in model.model_fields.items():
            assert field.description, f"{model.__name__}.{name} has no description"


def test_the_overlay_validates_its_inputs() -> None:
    dates, prices = _up_heavy()
    base = _long_base(dates, prices)
    candidates = _medium_candidates(dates, prices)
    with pytest.raises(ValueError, match="at least one long-term window"):
        grade_medium_overlay(dates, prices, (), candidates)
    with pytest.raises(ValueError, match="same length"):
        grade_medium_overlay(dates[:10], prices, base, candidates)
    with pytest.raises(ValueError, match="at least"):
        grade_medium_overlay(_calendar(1), [_LOW], base, candidates)
    with pytest.raises(ValueError, match="exposure_floor_pct"):
        grade_medium_overlay(dates, prices, base, candidates, exposure_floor_pct=101.0)
    with pytest.raises(ValueError, match="min_move_pct"):
        grade_medium_overlay(dates, prices, base, candidates, min_move_pct=-1.0)
    with pytest.raises(ValueError, match="PeriodCandidate"):
        grade_medium_overlay(dates, prices, base, [candidates[0].windows[0]])
    with pytest.raises(ValueError, match="no windows"):
        grade_medium_overlay(
            dates,
            prices,
            base,
            [PeriodCandidate(horizon="medium", half_width_days=15, peaks=(), troughs=())],
        )


def test_an_empty_candidate_list_grades_nothing_and_leaves_the_long_set_alone() -> None:
    dates, prices = _up_heavy()
    base = _long_base(dates, prices)
    grade = grade_medium_overlay(dates, prices, base, ())
    assert grade.steps == ()
    assert grade.ladder == ()
    assert grade.kept_windows == base
    assert grade.stop_reason is None
    assert grade.baseline.sharpe == pytest.approx(-0.03680572090431364, rel=1e-9)


def test_the_overlay_surface_is_exported() -> None:
    from digiquant.strategies.sdca import period_optimize

    for name in ("OverlayGrade", "OverlayStep", "grade_medium_overlay"):
        assert name in period_optimize.__all__, f"{name} is missing from __all__"
        assert hasattr(period_optimize, name)
