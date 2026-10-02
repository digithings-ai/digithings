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
    PeriodCandidate,
    PeriodHorizon,
    PeriodOptimizationResult,
    PeriodScore,
    SplitSampleResult,
    combine_periods,
    confirmation_days,
    detect_pivots,
    discover_candidate_periods,
    optimize_periods,
    rank_period_scores,
    score_periods,
    split_sample_check,
)

pytestmark = pytest.mark.unit

_START = date(2020, 1, 1)
_LOW = 100.0
_HIGH = 200.0


def _calendar(n: int) -> list[date]:
    return [_START + timedelta(days=i) for i in range(n)]


def _leg(start_price: float, end_price: float, bars: int) -> list[float]:
    """``bars`` closes on a straight line, endpoints inclusive.

    The last close is *forced* onto ``end_price``: a straight-line ramp otherwise
    lands a few ULPs short of it, which would turn the corner into two pivots (a
    near-equal minimum one bar earlier) and the pivot detector — correctly — would
    read both. Exact corners keep the fixture's structure unambiguous.
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
    ``_HIGH``. Two bars at the same corner price would be a plateau, and a
    plateau carries no pivot. ``tail_up`` appends a final rising leg whose top is
    never reached, which leaves a *trailing trough* whose exit edge would fall
    past the final bar — the Ruling 1 truncation case. A cycle is
    ``up_days + down_days - 2`` bars.
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
