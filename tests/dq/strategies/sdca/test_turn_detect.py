"""Tests for the generic paired turn detector (#4804, Plan 22, Engine 1).

Pins that matter here, in order of importance:

- **Recovery** (a). A synthetic zigzag has exactly one right answer, so the
  detector must return those corners — same indices, same dates, same prices —
  and drop nothing.
- **The sensitivity crank** (b). The owner's central claim about
  ``min_move_pct`` is that a lower threshold yields more turns. Three levels
  (15 / 10 / 5%) are pinned with exact counts, so a detector that quietly
  inverts, saturates or ignores the knob goes red.
- **The two filters** (c). Magnitude and time are enforced independently: a
  -20% move 5 days after the previous turn fails the *time* filter, a -8% move
  60 days later fails the *magnitude* filter, and each displaced turn is
  recorded in ``dropped`` with its own reason.
- **The pairing invariant** (d). Owner ruling 2: strictly alternating
  peak/trough pairs, every peak adjacent to a trough, a dangling trailing turn
  dropped and recorded. The ``TurnSet`` validator enforces it structurally, so
  a hand-built malformed set is refused rather than merely discouraged.
- **Determinism** (e), **degenerate input** (f: a clean ``ValueError``, never
  an ``IndexError`` or a disabled assertion), and **window conversion** (g).

Every number below is derived from the documented conventions in
``sdca/turn_detect.py`` — no value was copied from a previous run.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from digiquant.strategies.sdca.cycle_windows import CycleKind, SdcaCycleWindows
from digiquant.strategies.sdca.turn_detect import (
    DropReason,
    Turn,
    TurnDetectionConfig,
    TurnSet,
    detect_turns,
    turns_to_cycle_windows,
)

pytestmark = pytest.mark.unit

_START = date(2020, 1, 1)
_CONFIG = TurnDetectionConfig()


def _dates(n: int) -> list[date]:
    """``n`` consecutive calendar days from a fixed origin — no calendar, no asset."""
    return [_START + timedelta(days=i) for i in range(n)]


def _to(prices: list[float], target: float, bars: int) -> None:
    """Extend ``prices`` by a linear ``bars``-bar ramp landing exactly on ``target``."""
    start = prices[-1]
    step = (target - start) / bars
    for i in range(1, bars + 1):
        prices.append(start + step * i)


def _zigzag(start: float, legs: list[tuple[int, float]]) -> tuple[list[date], list[float]]:
    """Absolute-step series: ``legs`` are ``(bars, price_step)`` pairs."""
    prices = [start]
    for bars, step in legs:
        _to(prices, prices[-1] + step * bars, bars)
    return _dates(len(prices)), prices


def _percent_legs(
    start: float, moves: list[float], bars: int = 60
) -> tuple[list[date], list[float]]:
    """Series whose legs are exact percentage moves of the previous corner's price."""
    prices = [start]
    for move in moves:
        _to(prices, prices[-1] * (1.0 + move), bars)
    return _dates(len(prices)), prices


# (a) Six legs, five interior corners: 400 -> 160 -> 460 -> 190 -> 490 -> 220 -> 340.
# Corner bar indexes are the leg boundaries; every leg clears 15% by a wide margin
# and spans 60 calendar days, so neither filter can touch this fixture.
_A_LEGS = [(60, -4.0), (60, 5.0), (60, -4.5), (60, 5.0), (60, -4.5), (40, 3.0)]
_A_INDEXES = (60, 120, 180, 240, 300)
_A_PRICES = (160.0, 460.0, 190.0, 490.0, 220.0)
_A_KINDS = (CycleKind.TROUGH, CycleKind.PEAK, CycleKind.TROUGH, CycleKind.PEAK, CycleKind.TROUGH)

# (d) The mirror image: the same zigzag cut one leg short, so its last corner is a
# peak and the kept set has an even count. 400 -> 160 -> 460 -> 190 -> 490.
_D_LEGS = [(60, -4.0), (60, 5.0), (60, -4.5), (60, 5.0), (40, -3.0)]


@pytest.fixture(scope="module")
def zigzag() -> tuple[list[date], list[float]]:
    return _zigzag(400.0, _A_LEGS)


def test_recovers_every_corner_of_a_clean_zigzag(zigzag: tuple[list[date], list[float]]) -> None:
    """(a) Five corners in, five paired turns out — exact dates, prices and kinds."""
    dates, prices = zigzag
    result = detect_turns(dates, prices, _CONFIG)

    assert tuple(turn.index for turn in result.turns) == _A_INDEXES
    assert tuple(turn.kind for turn in result.turns) == _A_KINDS
    assert tuple(turn.pin for turn in result.turns) == tuple(dates[i] for i in _A_INDEXES)
    assert tuple(turn.price for turn in result.turns) == _A_PRICES
    assert result.dropped == ()
    assert (result.n_peaks, result.n_troughs) == (2, 3)


def test_prominence_is_the_weaker_adjacent_leg(zigzag: tuple[list[date], list[float]]) -> None:
    """A turn's prominence is the smaller of its adjacent legs, in percent.

    Legs: 160->460 = +187.5%, 460->190 = -58.695652%, 190->490 = +157.894737%,
    490->220 = -55.102041%. The first and last turn have one leg each; the three
    interior turns report the weaker of their two, so prominence is never below
    ``min_move_pct``.
    """
    result = detect_turns(*zigzag, _CONFIG)

    assert [round(turn.prominence, 6) for turn in result.turns] == [
        187.5,
        58.695652,
        58.695652,
        55.102041,
        55.102041,
    ]
    assert all(turn.prominence >= _CONFIG.min_move_pct for turn in result.turns)


# (b) Nested wiggles on a 100 start: +45%, -13%, +20%, -30%, +50%, -11%, +25%,
# -7%, +30%, -40%, +10%. Three dips (13%, 11%, 7%) each sit inside the band a
# coarser threshold refuses and a finer one admits, and each is followed by a leg
# that qualifies at every level, so every dip the crank admits becomes an extra
# pair rather than collapsing back into its neighbour.
_B_MOVES = [0.45, -0.13, 0.20, -0.30, 0.50, -0.11, 0.25, -0.07, 0.30, -0.40, 0.10]
_B_COUNTS = {15.0: 4, 10.0: 8, 5.0: 10}
_B_CORNERS = 10  # 11 legs, so 10 interior corners — every move reverses direction


@pytest.fixture(scope="module")
def wiggly() -> tuple[list[date], list[float]]:
    return _percent_legs(100.0, _B_MOVES)


@pytest.mark.parametrize("min_move_pct", [15.0, 10.0, 5.0])
def test_sensitivity_crank_counts_are_pinned(
    wiggly: tuple[list[date], list[float]],
    min_move_pct: float,
) -> None:
    """(b) Exact turn count per threshold level — the knob is pinned, not eyeballed."""
    result = detect_turns(wiggly[0], wiggly[1], TurnDetectionConfig(min_move_pct=min_move_pct))

    assert len(result.turns) == _B_COUNTS[min_move_pct]
    assert result.min_move_pct == min_move_pct


def test_lowering_min_move_pct_strictly_increases_turns(
    wiggly: tuple[list[date], list[float]],
) -> None:
    """(b) The owner's central claim: 15 -> 10 -> 5 must yield more turns, not fewer.

    Strictly increasing, not merely non-decreasing: a saturated knob (all levels
    collapsing to the same count) is as wrong as an inverted one.
    """
    counts = [
        len(detect_turns(wiggly[0], wiggly[1], TurnDetectionConfig(min_move_pct=pct)).turns)
        for pct in (15.0, 10.0, 5.0)
    ]

    assert counts == [4, 8, 10]
    assert counts[0] < counts[1] < counts[2]


def test_every_knob_setting_still_pairs(wiggly: tuple[list[date], list[float]]) -> None:
    """More turns must not buy an unpaired set — the invariant rides along with (b)."""
    for pct in (15.0, 10.0, 5.0):
        result = detect_turns(wiggly[0], wiggly[1], TurnDetectionConfig(min_move_pct=pct))
        kinds = [turn.kind for turn in result.turns]
        assert len(kinds) >= 2
        assert all(a is not b for a, b in zip(kinds, kinds[1:], strict=False))
        # Every turn is accounted for: kept or written down.
        assert len(result.turns) + len(result.dropped) >= _B_CORNERS


# (c1) 300 -> 120 -> 480 -> 384 -> 769 -> 409, with corners at bar indexes
# 60 / 120 / 125 / 180 / 240. The dip is -20%, which clears the magnitude filter,
# but it lands 5 calendar days after the peak it should have confirmed — so the
# *time* filter is the one that fires.
_C1_LEGS = [(60, -3.0), (60, 6.0), (5, -19.2), (55, 7.0), (60, -6.0), (40, 4.0)]
_C1_DIP_INDEX = 125


def test_separation_filter_drops_a_five_day_dip() -> None:
    """(c) A big move that arrives too soon is still dropped, and recorded as such."""
    dates, prices = _zigzag(300.0, _C1_LEGS)
    result = detect_turns(dates, prices, _CONFIG)

    dip = next(record for record in result.dropped if record.index == _C1_DIP_INDEX)
    assert dip.kind is CycleKind.TROUGH
    assert dip.reason is DropReason.LEG_BELOW_SEPARATION
    # The refused leg pointed back at the 480 peak, which stood at that moment.
    assert dip.survivor_pin == dates[120]
    assert dip.pin not in {turn.pin for turn in result.turns}
    # That peak then yielded to the higher one, so both ends are on the record.
    superseded = [r for r in result.dropped if r.reason is DropReason.SUPERSEDED_BY_STRONGER_TURN]
    assert tuple(record.pin for record in superseded) == (dates[120],)
    assert superseded[0].survivor_pin == dates[180]
    assert tuple(turn.index for turn in result.turns) == (60, 180, 240)


def test_relaxing_separation_readmits_the_five_day_dip() -> None:
    """The time filter is a knob too: 3 days admits the dip the 45-day rule refused."""
    dates, prices = _zigzag(300.0, _C1_LEGS)

    strict = detect_turns(dates, prices, TurnDetectionConfig(min_separation_days=45))
    loose = detect_turns(dates, prices, TurnDetectionConfig(min_separation_days=3))

    assert len(loose.turns) == len(strict.turns) + 2
    assert dates[_C1_DIP_INDEX] in {turn.pin for turn in loose.turns}


# (c2) 300 -> 120 -> 480 -> 441.6 -> 921.6 -> 621.6. The dip spans 60 days (time
# filter clears) but only -8%, so the magnitude filter is the one that fires.
_C2_LEGS = [(60, -3.0), (60, 6.0), (60, -0.64), (60, 8.0), (60, -5.0), (40, 4.0)]
_C2_DIP_INDEX = 180


def test_magnitude_filter_drops_a_shallow_dip() -> None:
    """(c) A long-but-small move is dropped, and recorded with the magnitude reason."""
    dates, prices = _zigzag(300.0, _C2_LEGS)
    result = detect_turns(dates, prices, _CONFIG)

    dip = next(record for record in result.dropped if record.index == _C2_DIP_INDEX)
    assert dip.reason is DropReason.LEG_BELOW_MAGNITUDE
    assert dip.survivor_pin == dates[120]
    assert dip.pin not in {turn.pin for turn in result.turns}
    superseded = [r for r in result.dropped if r.reason is DropReason.SUPERSEDED_BY_STRONGER_TURN]
    assert tuple(record.pin for record in superseded) == (dates[120],)
    assert tuple(turn.index for turn in result.turns) == (60, 240, 300)


def test_every_candidate_is_kept_or_recorded_for_each_filter_fixture() -> None:
    """(c) Both refusal fixtures account for all five corners, once each."""
    for legs, corners in ((_C1_LEGS, 5), (_C2_LEGS, 5)):
        dates, prices = _zigzag(300.0, legs)
        result = detect_turns(dates, prices, _CONFIG)
        assert len(result.turns) + len(result.dropped) == corners


def test_raising_min_move_pct_above_every_leg_yields_an_empty_set() -> None:
    """Filters stricter than the whole series return an empty set, recording the rest.

    Not a silent empty tuple: every candidate is either kept or written down in
    ``dropped``, and at 400% (above the 300% seed leg) nothing survives — not even
    the seed, which is left dangling.
    """
    dates, prices = _zigzag(400.0, _A_LEGS)
    result = detect_turns(dates, prices, TurnDetectionConfig(min_move_pct=400.0))

    assert result.turns == ()
    assert result.n_peaks == 0
    assert result.n_troughs == 0
    assert {record.reason for record in result.dropped} == {
        DropReason.LEG_BELOW_MAGNITUDE,
        DropReason.SUPERSEDED_BY_STRONGER_TURN,
        DropReason.DANGLING_NO_PARTNER,
    }
    assert len(result.dropped) == len(_A_INDEXES)  # every corner accounted for once
    assert result.window_day_share == 0.0


# (d) Structural pairing assertions.
def test_pairing_invariant_holds_across_fixtures(
    zigzag: tuple[list[date], list[float]],
    wiggly: tuple[list[date], list[float]],
) -> None:
    """(d) Strict alternation, first/last kinds, every peak adjacent to a trough."""
    # The last fixture ends on a peak, so its set has an even count; the others end
    # on a trough. Both shapes must satisfy the same rule.
    series = [zigzag, wiggly, _zigzag(300.0, _C1_LEGS), _zigzag(400.0, _D_LEGS)]
    seen_parities: set[int] = set()
    first_kinds: set[CycleKind] = set()
    last_kinds: set[CycleKind] = set()

    for dates, prices in series:
        turns = detect_turns(dates, prices, _CONFIG).turns
        kinds = [turn.kind for turn in turns]
        assert len(kinds) >= 2
        for earlier, later in zip(kinds, kinds[1:], strict=False):
            assert earlier is not later, "turn kinds must strictly alternate"
        for position, kind in enumerate(kinds):
            if kind is CycleKind.PEAK:
                neighbours = kinds[max(position - 1, 0) : position] + kinds[position + 1 :]
                assert any(other is CycleKind.TROUGH for other in neighbours)
        seen_parities.add(len(turns) % 2)
        first_kinds.add(kinds[0])
        last_kinds.add(kinds[-1])

    # Both shapes are exercised, so the invariant is not accidentally pinned to one parity.
    assert seen_parities == {0, 1}
    assert first_kinds == {CycleKind.TROUGH, CycleKind.PEAK}
    assert last_kinds == {CycleKind.TROUGH, CycleKind.PEAK}


def test_every_candidate_is_kept_or_recorded(
    zigzag: tuple[list[date], list[float]],
    wiggly: tuple[list[date], list[float]],
) -> None:
    """(d) The receipt is complete: no candidate vanishes without a reason.

    ``len(turns) + len(dropped)`` equals the number of local extrema in the series,
    which is what makes a shorter turn set explainable from the output alone.
    """
    for dates, prices, corners in (
        (zigzag[0], zigzag[1], len(_A_INDEXES)),
        (wiggly[0], wiggly[1], _B_CORNERS),
        (_zigzag(300.0, _C1_LEGS)[0], _zigzag(300.0, _C1_LEGS)[1], 5),
    ):
        for pct in (15.0, 10.0, 5.0):
            result = detect_turns(dates, prices, TurnDetectionConfig(min_move_pct=pct))
            assert len(result.turns) + len(result.dropped) == corners
            kept_indexes = [turn.index for turn in result.turns]
            assert not set(kept_indexes) & {record.index for record in result.dropped}
            assert kept_indexes == sorted(kept_indexes)


def test_trailing_dangling_turn_is_dropped_and_recorded() -> None:
    """(d) A lone trough with no opposite partner cannot stand: drop it, say why.

    300 -> 120 -> 300 is a single V, so exactly one corner is a candidate and it
    never acquires a partner.
    """
    dates, prices = _zigzag(300.0, [(60, -3.0), (60, 3.0)])
    result = detect_turns(dates, prices, _CONFIG)

    assert result.turns == ()
    assert len(result.dropped) == 1
    assert result.dropped[0].reason is DropReason.DANGLING_NO_PARTNER
    assert result.dropped[0].pin == dates[60]
    assert result.dropped[0].survivor_pin is None


def _with_turns(result: TurnSet, turns: tuple[Turn, ...]) -> TurnSet:
    """Re-validate a real ``TurnSet`` with a hand-built ``turns`` tuple.

    The validator is the point of these tests, so the model is *constructed*
    (not ``model_copy``-ed, which skips validation) — with the provenance fields
    carried over so only ``turns`` differs.
    """
    return TurnSet(**{**result.model_dump(), "turns": turns})


def test_turnset_refuses_a_lone_turn(zigzag: tuple[list[date], list[float]]) -> None:
    """The pairing rule is structural: a hand-built one-turn set is refused."""
    result = detect_turns(*zigzag, _CONFIG)

    with pytest.raises(ValueError, match="pair"):
        _with_turns(result, result.turns[:1])


def test_turnset_refuses_two_peaks_in_a_row(zigzag: tuple[list[date], list[float]]) -> None:
    """Two peaks in a row is malformed (owner ruling 2), not merely unusual."""
    result = detect_turns(*zigzag, _CONFIG)
    trough, peak, later_trough = result.turns[:3]

    with pytest.raises(ValueError, match="alternate"):
        _with_turns(
            result, (trough, peak, later_trough.model_copy(update={"kind": CycleKind.PEAK}))
        )


def test_turnset_refuses_out_of_order_turns(zigzag: tuple[list[date], list[float]]) -> None:
    """Chronology is the detector's own invariant, not a caller repair."""
    result = detect_turns(*zigzag, _CONFIG)
    first, second = result.turns[:2]

    with pytest.raises(ValueError, match="ascending"):
        _with_turns(result, (second, first))


# (e)
def test_detection_is_deterministic(wiggly: tuple[list[date], list[float]]) -> None:
    """(e) Same input, byte-identical output — no dict ordering, no clock, no RNG."""
    dates, prices = wiggly
    runs = [detect_turns(dates, prices, TurnDetectionConfig(min_move_pct=10.0)) for _ in range(3)]

    assert runs[0] == runs[1] == runs[2]
    assert runs[0].model_dump_json() == runs[1].model_dump_json() == runs[2].model_dump_json()


def test_input_sequences_are_not_mutated(wiggly: tuple[list[date], list[float]]) -> None:
    """The caller's lists survive the walk, and equivalent tuples behave identically."""
    dates, prices = wiggly
    before = (list(dates), list(prices))
    from_lists = detect_turns(dates, prices, _CONFIG)
    from_tuples = detect_turns(tuple(dates), tuple(prices), _CONFIG)

    assert (dates, prices) == before
    assert from_lists == from_tuples


# (f)
def test_flat_series_raises_value_error() -> None:
    """A series with no corner has no cycle structure to report — say so cleanly."""
    dates, prices = _dates(200), [100.0] * 200

    with pytest.raises(ValueError, match="candidate turn"):
        detect_turns(dates, prices, _CONFIG)


def test_monotone_series_raises_value_error() -> None:
    """A strictly rising series is degenerate for this detector, and is not silent."""
    dates = _dates(200)
    prices = [100.0 + i for i in range(200)]

    with pytest.raises(ValueError, match="candidate turn"):
        detect_turns(dates, prices, _CONFIG)


@pytest.mark.parametrize("bars", [0, 1])
def test_short_series_raises_value_error(bars: int) -> None:
    """Fewer than two bars is refused before any indexing happens."""
    with pytest.raises(ValueError):
        detect_turns(_dates(bars), [100.0 + i for i in range(bars)], _CONFIG)


def test_series_shorter_than_the_confirmation_width_raises_value_error() -> None:
    """A window wider than the series cannot confirm anything; refuse, do not index."""
    dates, prices = _dates(6), [100.0, 90.0, 80.0, 120.0, 110.0, 100.0]

    with pytest.raises(ValueError, match="confirm"):
        detect_turns(dates, prices, _CONFIG)


def test_non_monotonic_dates_raise_value_error() -> None:
    """Out-of-order dates break the separation filter's arithmetic: refuse up front."""
    dates = _dates(200)
    dates[100], dates[101] = dates[101], dates[100]
    prices = [100.0 + (10.0 if i % 20 < 10 else -10.0) for i in range(200)]

    with pytest.raises(ValueError, match="ascending"):
        detect_turns(dates, prices, _CONFIG)


def test_repeated_dates_raise_value_error() -> None:
    """A duplicated day is not an ascending calendar either."""
    dates = _dates(200)
    dates[100] = dates[99]
    prices = [100.0 + (10.0 if i % 20 < 10 else -10.0) for i in range(200)]

    with pytest.raises(ValueError, match="ascending"):
        detect_turns(dates, prices, _CONFIG)


def test_mismatched_lengths_raise_value_error() -> None:
    """Dates and prices must describe the same bars."""
    with pytest.raises(ValueError, match="same length"):
        detect_turns(_dates(200), [100.0] * 199, _CONFIG)


@pytest.mark.parametrize("bad", [0.0, -5.0, float("nan"), float("inf")])
def test_unusable_prices_raise_value_error(bad: float) -> None:
    """Percentage moves divide by the earlier price, so it must be finite and positive."""
    prices = [100.0 + (10.0 if i % 20 < 10 else -10.0) for i in range(200)]
    prices[150] = bad

    with pytest.raises(ValueError, match="price"):
        detect_turns(_dates(200), prices, _CONFIG)


@pytest.mark.parametrize("field", ["min_move_pct", "min_separation_days", "confirmation_bars"])
def test_config_rejects_out_of_range_knobs(field: str) -> None:
    """Frozen strict models refuse a nonsensical knob instead of coercing it."""
    payload: dict[str, object] = {field: -1}

    with pytest.raises(ValueError):
        TurnDetectionConfig(**payload)  # type: ignore[arg-type]


def test_config_is_frozen() -> None:
    config = TurnDetectionConfig()
    with pytest.raises(ValueError):
        config.min_move_pct = 5.0  # type: ignore[misc]


# (g)
def test_turns_convert_to_half_width_cycle_windows(zigzag: tuple[list[date], list[float]]) -> None:
    """(g) Algorithmic turns and the documented pin factories produce the same type."""
    dates, prices = zigzag
    result = detect_turns(dates, prices, _CONFIG)

    windows = turns_to_cycle_windows(result.turns, 45)

    assert isinstance(windows, SdcaCycleWindows)
    assert len(windows.windows) == len(result.turns)
    assert len(windows.peaks()) == result.n_peaks
    assert len(windows.troughs()) == result.n_troughs
    for turn, window in zip(result.turns, windows.windows, strict=True):
        assert window.kind is turn.kind
        assert window.start == turn.pin - timedelta(days=45)
        assert window.end == turn.pin + timedelta(days=45)
        assert windows.kind_on(turn.pin) is turn.kind
    assert windows.windows[0].name.startswith("turn_000_")
    assert windows.kind_on(_START - timedelta(days=10)) is None


def test_window_conversion_accepts_a_whole_turnset(zigzag: tuple[list[date], list[float]]) -> None:
    """The converter takes the ``TurnSet`` itself as well as a bare turn sequence."""
    result = detect_turns(*zigzag, _CONFIG)

    assert turns_to_cycle_windows(result, 45) == turns_to_cycle_windows(result.turns, 45)


def test_kind_on_resolves_overlaps_in_pin_order(zigzag: tuple[list[date], list[float]]) -> None:
    """Adjacent ±45d windows overlap by 30 days; the earlier pin wins, deterministically.

    ``SdcaCycleWindows.kind_on`` returns the first match, so pin order is the
    precedence rule — stated here rather than left to whichever window is
    constructed first.
    """
    dates, prices = zigzag
    result = detect_turns(dates, prices, _CONFIG)
    windows = turns_to_cycle_windows(result.turns, 45)

    earlier, later = result.turns[0], result.turns[1]
    overlap = earlier.pin + timedelta(days=20)  # inside both ±45d windows
    assert later.pin - timedelta(days=45) <= overlap <= earlier.pin + timedelta(days=45)
    assert windows.kind_on(overlap) is earlier.kind
    assert windows.kind_on(overlap) is earlier.kind


def test_window_conversion_refuses_an_empty_set(zigzag: tuple[list[date], list[float]]) -> None:
    """``SdcaCycleWindows`` requires at least one window; fail before constructing."""
    empty = detect_turns(*zigzag, TurnDetectionConfig(min_move_pct=400.0))

    with pytest.raises(ValueError, match="at least one turn"):
        turns_to_cycle_windows(empty, 45)


def test_window_conversion_refuses_a_zero_half_width(
    zigzag: tuple[list[date], list[float]],
) -> None:
    """A zero half-width is a point, not a window — refuse rather than clamp."""
    result = detect_turns(*zigzag, _CONFIG)

    with pytest.raises(ValueError, match="half_width_days"):
        turns_to_cycle_windows(result.turns, 0)


def test_coverage_stats_are_reported(zigzag: tuple[list[date], list[float]]) -> None:
    """Coverage is provenance: which knob, over how many bars, covering how much calendar."""
    dates, prices = zigzag
    result = detect_turns(
        dates, prices, TurnDetectionConfig(min_move_pct=15.0, window_half_width_days=45)
    )

    assert result.bars == len(prices)
    assert result.days_in_span == (dates[-1] - dates[0]).days + 1
    assert result.confirmation_bars == _CONFIG.confirmation_bars
    assert result.min_separation_days == _CONFIG.min_separation_days
    assert 0.0 < result.window_day_share < 1.0
    # Pins are 60 days apart at indexes 60..300 with ±45d windows, so the covered
    # calendar is day 15 through day 340 of a 341-day span.
    assert result.window_day_share == pytest.approx(326 / 341)


def test_coverage_share_shrinks_when_windows_shrink(zigzag: tuple[list[date], list[float]]) -> None:
    """The coverage stat is a measurement of the requested width, not a constant."""
    dates, prices = zigzag

    wide = detect_turns(dates, prices, TurnDetectionConfig(window_half_width_days=45))
    narrow = detect_turns(dates, prices, TurnDetectionConfig(window_half_width_days=5))

    assert wide.window_half_width_days == 45
    assert narrow.window_half_width_days == 5
    assert narrow.window_day_share < wide.window_day_share


def test_default_config_matches_the_documented_defaults() -> None:
    """The defaults are part of the contract, not whatever the signature happens to be."""
    config = TurnDetectionConfig()

    assert config.min_move_pct == 15.0
    assert config.min_separation_days == 45
    assert config.confirmation_bars == 5
    assert config.window_half_width_days == 45


def test_drop_reasons_are_stable_strings() -> None:
    """Reason values are recorded data: they must serialize, not leak enum reprs."""
    assert DropReason.DANGLING_NO_PARTNER.value == "dangling_no_partner"
    assert DropReason.LEG_BELOW_MAGNITUDE.value == "leg_below_magnitude"
    assert DropReason.LEG_BELOW_SEPARATION.value == "leg_below_separation"
    assert DropReason.SUPERSEDED_BY_STRONGER_TURN.value == "superseded_by_stronger_turn"


def test_kind_enum_is_the_shared_cycle_kind() -> None:
    """Turns speak the same vocabulary as the pin factories — one enum, not two."""
    from digiquant.strategies.sdca.turn_detect import TurnKind

    assert TurnKind is CycleKind
