"""The two gold cycle-window pin sets: the approved Set A and the algorithmic set (#4804, Plan 22).

The shipped ``SdcaCycleWindows.gold_v1()`` had **seven** pins, four of them peaks and
three troughs — peak…peak — which breaks owner ruling 2: a cycle set is a chain of
*paired* turns (buy, sell, buy, sell…), never two buys in a row with no sell between
them. It also carried a **fabricated** pin (``2026-09-29``, the real run high is
``2026-01-29``) and four misdated pins, and its docstring quoted spot/ETF prices mixed
together. Those tests are the regression net for exactly that incident, so they assert
the pins as **literals** (date *and* close) as well as against the price file, which is
the only place an off-by-one day or an invented pin can die.

Two sets ship, and they are comparable rather than competing:

- ``gold_v1()`` — **Set A**, six close-based pins the owner approved by hand.
- ``gold_v2()`` — the **algorithmic** set: 20 turns from
  ``turn_detect.detect_turns`` at ``min_move_pct=15.0`` / ``min_separation_days=45``,
  the granularity ``sensitivity_consolidate.select_sensitivity_level`` chose by the
  depth-weighted, fitted-direction rule (capture depth 15.7457 vs 10.6792 / 7.1547).

Set A is pinned as a **subset** of ``gold_v2()``: the approved pins all appear in the
algorithmic set with the same kind, so the two answer the same question at two
granularities instead of competing for the name.

Every pin here was verified against ``digiquant/data/price-history/GLD-USD.csv`` —
column ``close`` (columns[1] is ``open``, a trap that already caused one wrong-date
incident). The CSV-backed tests skip when the cache is absent; the literal pins do not,
so the regression net never silently disappears.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

import pytest
from digiquant.strategies.sdca.cycle_windows import (
    CycleKind,
    CycleWindow,
    SdcaCycleWindows,
    validate_paired_turns,
)

pytestmark = pytest.mark.unit

DATA_DIR = Path(__file__).resolve().parents[4] / "digiquant" / "data" / "price-history"
GLD_CSV = DATA_DIR / "GLD-USD.csv"

# Confirmation half-width ``turn_detect`` uses for a candidate. A pin must be the
# first bar of its +/-5-bar neighbourhood to attain that neighbourhood's extreme.
CONFIRMATION_BARS = 5

# Set A as approved: (name, kind, pin, close). Six pins, peak first, strictly alternating.
SET_A: tuple[tuple[str, CycleKind, date, float], ...] = (
    ("2011_peak", CycleKind.PEAK, date(2011, 8, 22), 184.59),
    ("2015_trough", CycleKind.TROUGH, date(2015, 12, 17), 100.50),
    ("2020_peak", CycleKind.PEAK, date(2020, 8, 6), 193.89),
    ("2022_trough", CycleKind.TROUGH, date(2022, 9, 26), 151.23),
    ("2026_peak", CycleKind.PEAK, date(2026, 1, 29), 495.90),
    ("2026_trough", CycleKind.TROUGH, date(2026, 7, 16), 364.96),
)

# The algorithmic set as landed: 20 turns from ``detect_turns`` at min_move_pct=15.0,
# min_separation_days=45, confirmation_bars=5, on GLD closes. (name, kind, pin, close).
# Names are year+kind; a second turn in the same year of the same kind takes an ordinal
# suffix so a name still identifies one pin (``2013_trough`` vs ``2013_trough_2``).
GOLD_V2: tuple[tuple[str, CycleKind, date, float], ...] = (
    ("2006_peak", CycleKind.PEAK, date(2006, 5, 12), 71.12),
    ("2006_trough", CycleKind.TROUGH, date(2006, 10, 4), 56.37),
    ("2008_peak", CycleKind.PEAK, date(2008, 3, 17), 99.17),
    ("2008_trough", CycleKind.TROUGH, date(2008, 11, 12), 70.00),
    ("2011_peak", CycleKind.PEAK, date(2011, 8, 22), 184.59),
    ("2011_trough", CycleKind.TROUGH, date(2011, 12, 29), 150.34),
    ("2012_peak", CycleKind.PEAK, date(2012, 10, 4), 173.61),
    ("2013_trough", CycleKind.TROUGH, date(2013, 6, 27), 115.94),
    ("2013_peak", CycleKind.PEAK, date(2013, 8, 27), 136.75),
    ("2013_trough_2", CycleKind.TROUGH, date(2013, 12, 19), 114.82),
    ("2014_peak", CycleKind.PEAK, date(2014, 3, 14), 133.10),
    ("2015_trough", CycleKind.TROUGH, date(2015, 12, 17), 100.50),
    ("2016_peak", CycleKind.PEAK, date(2016, 7, 8), 130.52),
    ("2016_trough", CycleKind.TROUGH, date(2016, 12, 15), 107.34),
    ("2020_peak", CycleKind.PEAK, date(2020, 8, 6), 193.89),
    ("2021_trough", CycleKind.TROUGH, date(2021, 3, 8), 157.49),
    ("2022_peak", CycleKind.PEAK, date(2022, 3, 8), 191.51),
    ("2022_trough", CycleKind.TROUGH, date(2022, 9, 26), 151.23),
    ("2026_peak", CycleKind.PEAK, date(2026, 1, 29), 495.90),
    ("2026_trough", CycleKind.TROUGH, date(2026, 7, 16), 364.96),
)

# Price tolerance. The CSV carries float32 prices (``184.58999633789062``), so the
# literals are compared as "the same price", not as equal digits.
CLOSE_TOL = 0.005

needs_gld_csv = pytest.mark.skipif(
    not GLD_CSV.exists(), reason="digiquant/data/price-history/GLD-USD.csv not in this environment"
)


def _gld_closes() -> dict[date, float]:
    """``{date: close}`` for the GLD cache. Column ``close``, never ``open`` (columns[1])."""
    closes: dict[date, float] = {}
    with GLD_CSV.open() as handle:
        for row in csv.DictReader(handle):
            closes[date.fromisoformat(row["timestamp"][:10])] = float(row["close"])
    return closes


def _chronological(windows: Sequence[CycleWindow]) -> list[CycleWindow]:
    """Windows in time order, which is the order the pairing invariant is judged in."""
    return sorted(windows, key=lambda window: (window.start, window.end))


def _pins(windows: Sequence[CycleWindow]) -> list[tuple[CycleKind, date]]:
    """``(kind, pin)`` per window, the pin being the window's midpoint."""
    return [(w.kind, w.start + (w.end - w.start) // 2) for w in _chronological(windows)]


def _assert_strictly_alternating(windows: Sequence[CycleWindow]) -> list[CycleKind]:
    """Alternation, and every peak paired with an adjacent trough (owner ruling 2)."""
    kinds = [w.kind for w in _chronological(windows)]
    assert kinds, "a pin set must not be empty"
    for earlier, later in zip(kinds, kinds[1:], strict=False):
        assert earlier is not later, (
            f"pin kinds must strictly alternate, got {earlier.value} then {later.value}"
        )
    for position, kind in enumerate(kinds):
        if kind is CycleKind.PEAK:
            neighbours = kinds[max(position - 1, 0) : position] + kinds[position + 1 :]
            assert any(other is CycleKind.TROUGH for other in neighbours), (
                "every peak needs an adjacent trough: a set of peaks alone defines no buy side"
            )
    return kinds


class TestGoldV1ApprovedSet:
    """(a) Set A is exactly the six approved pins, in order, alternating from a peak."""

    def test_exactly_the_six_approved_pins_in_order(self) -> None:
        windows = SdcaCycleWindows.gold_v1()
        assert [w.name for w in windows.windows] == [name for name, *_ in SET_A]
        assert [(w.kind, w.start + (w.end - w.start) // 2) for w in windows.windows] == [
            (kind, pin) for _, kind, pin, _ in SET_A
        ]

    def test_kinds_start_at_a_peak_and_strictly_alternate(self) -> None:
        kinds = _assert_strictly_alternating(SdcaCycleWindows.gold_v1().windows)
        assert kinds[0] is CycleKind.PEAK
        assert kinds == [CycleKind.PEAK, CycleKind.TROUGH] * 3
        assert len(SdcaCycleWindows.gold_v1().peaks()) == 3
        assert len(SdcaCycleWindows.gold_v1().troughs()) == 3

    def test_the_fabricated_2026_09_29_pin_is_gone(self) -> None:
        """The shipped set's last pin was invented; 2026-01-29 is the real run high."""
        pins = {pin for _, pin in _pins(SdcaCycleWindows.gold_v1().windows)}
        assert date(2026, 9, 29) not in pins
        assert date(2026, 1, 29) in pins

    def test_the_four_misdated_pins_are_corrected(self) -> None:
        """Off-by-one dates shipped before: 2011-09-06, 2020-08-07, 2022-10-21, and a
        fabricated 2026-09-29 in place of the 2026-01-29 high."""
        pins = {pin for _, pin in _pins(SdcaCycleWindows.gold_v1().windows)}
        for wrong in (date(2011, 9, 6), date(2020, 8, 7), date(2022, 10, 21)):
            assert wrong not in pins, f"{wrong} was a misdated pin, not a close-based extreme"
        assert date(2008, 3, 17) not in pins, "Set A starts at the 2011 secular top"


class TestPairingInvariant:
    """(c) The invariant is structural: legal shapes pass, malformed ones are refused."""

    @pytest.mark.parametrize("factory", ["gold_v1", "gold_v2"])
    def test_both_shipped_sets_satisfy_the_invariant(self, factory: str) -> None:
        windows = getattr(SdcaCycleWindows, factory)().windows
        _assert_strictly_alternating(windows)
        validate_paired_turns(windows)

    @pytest.mark.parametrize(
        ("kinds", "why"),
        [
            ([CycleKind.PEAK] * 4, "the shipped defect: peak...peak with no sell between"),
            ([CycleKind.TROUGH] * 3, "two buys in a row"),
            ([CycleKind.PEAK, CycleKind.PEAK], "a peak with no trough beside it"),
            ([CycleKind.TROUGH, CycleKind.TROUGH], "a trough with no peak beside it"),
        ],
    )
    def test_two_same_kind_neighbours_are_refused(self, kinds: list[CycleKind], why: str) -> None:
        windows = [
            CycleWindow(
                name=f"w{i}",
                kind=kind,
                start=date(2010, 1, 1) + timedelta(days=400 * i),
                end=date(2010, 1, 1) + timedelta(days=400 * i + 89),
            )
            for i, kind in enumerate(kinds)
        ]
        with pytest.raises(ValueError, match="alternate"):
            validate_paired_turns(windows)
        assert why  # the fixture is named for the shape it encodes

    def test_a_lone_turn_is_refused(self) -> None:
        """One pin has no partner at all: it defines neither a buy nor a sell period."""
        with pytest.raises(ValueError, match="pair"):
            validate_paired_turns(
                [
                    CycleWindow(
                        name="only",
                        kind=CycleKind.PEAK,
                        start=date(2015, 1, 1),
                        end=date(2015, 2, 1),
                    )
                ]
            )

    @pytest.mark.parametrize(
        "kinds",
        [
            [CycleKind.PEAK, CycleKind.TROUGH],
            [CycleKind.TROUGH, CycleKind.PEAK],
            [CycleKind.PEAK, CycleKind.TROUGH, CycleKind.PEAK],  # odd length
            [CycleKind.TROUGH, CycleKind.PEAK, CycleKind.TROUGH, CycleKind.PEAK],
            [CycleKind.PEAK, CycleKind.TROUGH, CycleKind.PEAK, CycleKind.TROUGH, CycleKind.PEAK],
        ],
    )
    def test_legal_shapes_are_accepted(self, kinds: list[CycleKind]) -> None:
        """Parity is NOT the rule. An odd count still pairs every peak inside it, and
        Set A's six pins (peak...trough) must not be rejected for being a closed pair."""
        windows = [
            CycleWindow(
                name=f"w{i}",
                kind=kind,
                start=date(2010, 1, 1) + timedelta(days=400 * i),
                end=date(2010, 1, 1) + timedelta(days=400 * i + 89),
            )
            for i, kind in enumerate(kinds)
        ]
        validate_paired_turns(windows)

    def test_the_shipped_documented_sets_all_validate(self) -> None:
        """btc_v1()'s five pins are peak...peak — legal by the odd-length reading."""
        for factory in ("btc_v1", "eth_research_v1", "gold_v1", "gold_v2"):
            windows = getattr(SdcaCycleWindows, factory)().windows
            validate_paired_turns(windows)
            _assert_strictly_alternating(windows)


class TestGoldV2AlgorithmicSet:
    """(e) The algorithmic set is the 20 turns the rule selected, and nothing else."""

    def test_twenty_pins_ten_peaks_and_ten_troughs(self) -> None:
        windows = SdcaCycleWindows.gold_v2()
        assert len(windows.windows) == 20
        assert len(windows.peaks()) == 10
        assert len(windows.troughs()) == 10

    def test_strictly_alternating_starting_at_a_peak(self) -> None:
        kinds = _assert_strictly_alternating(SdcaCycleWindows.gold_v2().windows)
        assert kinds[0] is CycleKind.PEAK
        assert kinds == [CycleKind.PEAK, CycleKind.TROUGH] * 10

    def test_exactly_the_twenty_algorithmic_pins_in_order(self) -> None:
        windows = SdcaCycleWindows.gold_v2()
        assert [w.name for w in windows.windows] == [name for name, *_ in GOLD_V2]
        assert [(w.kind, w.start + (w.end - w.start) // 2) for w in windows.windows] == [
            (kind, pin) for _, kind, pin, _ in GOLD_V2
        ]

    def test_turns_are_at_least_45_days_apart(self) -> None:
        """The detector's own time filter, re-derived from the landed dates. It is also
        what keeps every pin date out of an earlier window, so ``kind_on`` is unambiguous."""
        pins = [pin for _, pin in _pins(SdcaCycleWindows.gold_v2().windows)]
        separations = [(later - earlier).days for earlier, later in zip(pins, pins[1:])]
        assert min(separations) >= 45
        assert len(separations) == 19

    def test_each_name_identifies_exactly_one_pin(self) -> None:
        names = [w.name for w in SdcaCycleWindows.gold_v2().windows]
        assert len(names) == len(set(names)), "a name shared by two pins makes the set unauditable"


class TestApprovedSetIsASubset:
    """(d) Set A is a subset of the algorithmic set — the two are comparable, not competing."""

    def test_every_approved_pin_appears_in_the_algorithmic_set_with_the_same_kind(self) -> None:
        v2 = {(pin, kind) for kind, pin in _pins(SdcaCycleWindows.gold_v2().windows)}
        missing = [(pin, kind) for _, kind, pin, _ in SET_A if (pin, kind) not in v2]
        assert not missing, f"Set A pins absent from gold_v2(): {missing}"

    def test_a_name_shared_by_both_sets_is_the_same_turn(self) -> None:
        """A shared name means "the same turn in both sets", never two different pins. A
        collision between two DIFFERENT pins is the defect this rules out — which cannot
        be asserted as zero overlap, because six approved pins are in both sets by design."""
        v1_by_name = {w.name: w for w in SdcaCycleWindows.gold_v1().windows}
        v2_by_name = {w.name: w for w in SdcaCycleWindows.gold_v2().windows}
        shared = set(v1_by_name) & set(v2_by_name)
        assert shared == {name for name, *_ in SET_A}
        for name in shared:
            assert _pins([v1_by_name[name]]) == _pins([v2_by_name[name]])

    def test_the_algorithmic_set_is_strictly_coarser_and_wider(self) -> None:
        """Subset, not equal: the algorithm only ever ADDS turns here, and reaches back
        further. Neither direction is in question — this pins the relationship, not trivia."""
        v1_pins = {pin for _, pin in _pins(SdcaCycleWindows.gold_v1().windows)}
        v2_pins = {pin for _, pin in _pins(SdcaCycleWindows.gold_v2().windows)}
        assert v1_pins < v2_pins, "the algorithmic set must add turns, not drop approved ones"
        assert min(v2_pins) < min(v1_pins), "the algorithmic set reaches back before Set A starts"
        assert max(v1_pins) == max(v2_pins), "both sets end at the same last turn"


class TestWindowsAndKindOn:
    """(f) Both factories build +/-45d windows and ``kind_on`` resolves them consistently."""

    @pytest.mark.parametrize("factory", ["gold_v1", "gold_v2"])
    def test_every_window_is_exactly_45_days_either_side_of_its_pin(self, factory: str) -> None:
        windows = getattr(SdcaCycleWindows, factory)()
        offset = timedelta(days=45)
        for window in windows.windows:
            pin = window.start + (window.end - window.start) // 2
            assert (pin - window.start, window.end - pin) == (offset, offset)
            assert window.contains(pin)

    @pytest.mark.parametrize("factory", ["gold_v1", "gold_v2"])
    def test_kind_on_resolves_every_pin_to_its_own_kind(self, factory: str) -> None:
        windows = getattr(SdcaCycleWindows, factory)()
        for kind, pin in _pins(windows.windows):
            assert windows.kind_on(pin) is kind

    @pytest.mark.parametrize("factory", ["gold_v1", "gold_v2"])
    def test_kind_on_is_none_outside_every_window(self, factory: str) -> None:
        windows = getattr(SdcaCycleWindows, factory)()
        assert windows.kind_on(date(2004, 11, 18)) is None, "the series opens before the first pin"
        assert windows.kind_on(date(2049, 1, 1)) is None

    @pytest.mark.parametrize("factory", ["gold_v1", "gold_v2"])
    def test_kind_on_resolves_a_day_one_before_the_first_pin_to_none(self, factory: str) -> None:
        windows = getattr(SdcaCycleWindows, factory)()
        first = _chronological(windows.windows)[0]
        assert windows.kind_on(first.start - timedelta(days=1)) is None

    @pytest.mark.parametrize("factory", ["gold_v1", "gold_v2"])
    def test_the_first_window_edges_resolve_to_its_kind(self, factory: str) -> None:
        """At an edge the answer is the kind of the earliest window containing the day, so
        a window whose edges are inside no earlier window must answer with its own kind."""
        windows = getattr(SdcaCycleWindows, factory)()
        first = _chronological(windows.windows)[0]
        assert windows.kind_on(first.start) is first.kind
        assert windows.kind_on(first.end) is first.kind

    def test_overlapping_windows_resolve_to_the_earlier_pin_and_that_is_pinned(self) -> None:
        """Two 61-day-apart 2013 turns give windows that overlap for a month. The
        resolution is first-match by design, and it is pinned rather than left to chance."""
        windows = SdcaCycleWindows.gold_v2()
        overlapping = [
            (a, b)
            for a, b in zip(windows.windows, windows.windows[1:], strict=False)
            if b.start <= a.end
        ]
        assert overlapping, "the 2013 turns overlap — without this the assertion below is vacuous"
        for earlier, later in overlapping:
            assert windows.kind_on(later.start) is earlier.kind
            assert windows.kind_on(later.end) is later.kind

    def test_kind_on_prefers_the_first_matching_window_not_the_closest(self) -> None:
        windows = SdcaCycleWindows.gold_v2()
        names = [w.name for w in windows.windows]
        trough, peak = next(
            (a, b)
            for a, b in zip(windows.windows, windows.windows[1:], strict=False)
            if a.name == "2013_trough" and b.name == "2013_peak"
        )
        mid = trough.start + (trough.end - trough.start) // 2
        assert windows.kind_on(mid) is CycleKind.TROUGH
        assert names.index("2013_trough") < names.index("2013_peak")


class TestPinsAreRealCloseBasedExtremes:
    """(b) + (g) Every pin is a real close-based extreme of the GLD cache."""

    @needs_gld_csv
    @pytest.mark.parametrize("factory", ["gold_v1", "gold_v2"])
    def test_every_pin_date_carries_the_pinned_close(self, factory: str) -> None:
        """Off by one day and this dies: the pin must be a real bar carrying that close.

        Asserted against the pins the FACTORY returns, not against this module's own
        literals — otherwise the file would only be checking itself.
        """
        closes = _gld_closes()
        expected = {pin: want for _, _, pin, want in (SET_A if factory == "gold_v1" else GOLD_V2)}
        for _, pin in _pins(getattr(SdcaCycleWindows, factory)().windows):
            assert pin in closes, f"{pin} is not a bar in the GLD cache (off by one day?)"
            assert pin in expected, f"{pin} is a pin the factory added but the audit never verified"
            assert abs(closes[pin] - expected[pin]) <= CLOSE_TOL, (
                f"{pin}: cache close {closes[pin]} != pinned close {expected[pin]}"
            )

    @needs_gld_csv
    @pytest.mark.parametrize("factory", ["gold_v1", "gold_v2"])
    def test_every_pin_is_a_close_extremum_of_its_own_neighbourhood(self, factory: str) -> None:
        """A pin is the FIRST bar of its +/-5-bar neighbourhood to attain that
        neighbourhood's extreme -- ``detect_turns``' candidate rule. This is what makes a
        pin a turning point rather than a date someone liked."""
        closes = _gld_closes()
        order = sorted(closes)
        position = {day: i for i, day in enumerate(order)}
        for kind, pin in _pins(getattr(SdcaCycleWindows, factory)().windows):
            i = position[pin]
            lo = i - CONFIRMATION_BARS
            neighbourhood = [closes[day] for day in order[lo : i + CONFIRMATION_BARS + 1]]
            here = closes[pin]
            if kind is CycleKind.PEAK:
                assert here == max(neighbourhood), (
                    f"{pin} close {here} is not its neighbourhood max"
                )
            else:
                assert here == min(neighbourhood), (
                    f"{pin} close {here} is not its neighbourhood min"
                )
            assert neighbourhood.index(here) == CONFIRMATION_BARS, (
                f"{pin} is not the first bar of its neighbourhood to attain the extreme"
            )

    @needs_gld_csv
    def test_no_gold_v1_pin_falls_after_the_last_close(self) -> None:
        """A pin beyond the data has no close to be an extreme of."""
        closes = _gld_closes()
        last = max(closes)
        for _, pin in _pins(SdcaCycleWindows.gold_v1().windows):
            assert pin <= last, f"{pin} is after the last close in the cache ({last})"

    @needs_gld_csv
    def test_no_gold_v1_pin_is_an_edge_bar_of_the_series(self) -> None:
        """The sharper guard for the 2026-09-29 incident: the fabricated pin was the FINAL
        bar, which has no +5 bars after it, so it could never have been a candidate."""
        closes = _gld_closes()
        order = sorted(closes)
        position = {day: i for i, day in enumerate(order)}
        last_candidate = len(order) - 1 - CONFIRMATION_BARS
        for _, pin in _pins(SdcaCycleWindows.gold_v1().windows):
            i = position[pin]
            assert CONFIRMATION_BARS <= i <= last_candidate, (
                f"{pin} sits within {CONFIRMATION_BARS} bars of a series edge, "
                "so it cannot be a confirmed turning point"
            )

    @needs_gld_csv
    def test_the_pins_are_close_column_values_and_not_open_column_values(self) -> None:
        """columns[1] is ``open`` -- the trap behind the original wrong-date read. Every
        approved pin's open differs from its close, so the column choice is load-bearing
        and this test can tell the two apart rather than passing either silently."""
        closes = _gld_closes()
        opens = {}
        with GLD_CSV.open() as handle:
            for row in csv.DictReader(handle):
                opens[date.fromisoformat(row["timestamp"][:10])] = float(row["open"])
        for _, pin in _pins(SdcaCycleWindows.gold_v1().windows):
            assert abs(opens[pin] - closes[pin]) > CLOSE_TOL, (
                f"{pin}: open and close are identical, so this test proves nothing for it"
            )
        for _, _, pin, want in SET_A:
            assert abs(opens[pin] - want) > CLOSE_TOL, f"{pin}: the pin matches open, not close"
            assert abs(closes[pin] - want) <= CLOSE_TOL
