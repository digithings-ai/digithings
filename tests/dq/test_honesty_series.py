"""Unit tests for the honest-rate normalizer (``digiquant.stats.series``).

The cases are the ones that silently change N — the denominator every honest
rate is built on (DIG-428, L1 of DIG-474). Stdlib only: no Nautilus, polars or
pandas.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from digiquant.stats import normalize_series  # noqa: E402


class _FakePandasShape:
    """Duck-typed pandas Series: values + index, no pandas module."""

    def __init__(self, values, index) -> None:
        self.values = values
        self.index = index


class _FakePolars:
    """Duck-typed polars Series: to_list() only."""

    def __init__(self, values) -> None:
        self._values = values

    def to_list(self):
        return list(self._values)


def _exploding():
    """Yields two good values, then raises — a mid-iteration failure."""
    yield 1.0
    yield 2.0
    raise RuntimeError("series blew up mid-read")


def test_none_returns_none() -> None:
    assert normalize_series(None) is None


def test_empty_iterable_returns_none() -> None:
    assert normalize_series([]) is None
    assert normalize_series(iter(())) is None


def test_all_null_returns_none() -> None:
    assert normalize_series([None, None, None]) is None
    assert normalize_series([float("nan"), float("nan")]) is None


def test_non_finite_values_are_dropped_and_inf_never_escapes() -> None:
    result = normalize_series([1.0, float("nan"), 2.0, float("inf"), 3.0, float("-inf")])

    assert result is not None
    dates, values = result
    assert values == [1.0, 2.0, 3.0]
    assert all(math.isfinite(v) for v in values)
    assert len(dates) == len(values)


def test_pandas_shape_reads_values_index_and_truncates_dates() -> None:
    dates, values = normalize_series(
        _FakePandasShape([1.0, 2.0], ["2024-01-02T00:00:00", "2024-01-03T12:30:00"])
    )

    assert values == [1.0, 2.0]
    assert dates == ["2024-01-02", "2024-01-03"]
    assert all(len(d) == 10 for d in dates)


def test_polars_shape_uses_to_list_with_sequential_dates() -> None:
    dates, values = normalize_series(_FakePolars([0.5, float("nan"), 1.5]))

    assert values == [0.5, 1.5]
    assert dates == ["0", "2"]


def test_plain_list_uses_sequential_dates() -> None:
    assert normalize_series([1.0, 2.0, 3.0]) == (["0", "1", "2"], [1.0, 2.0, 3.0])


def test_generator_is_consumed_exactly_once() -> None:
    generator = (v for v in [1.0, 2.0])

    assert normalize_series(generator) == (["0", "1"], [1.0, 2.0])
    assert list(generator) == []


def test_failure_mid_iteration_returns_none_without_raising() -> None:
    assert normalize_series(_exploding()) is None


def test_non_numeric_strings_are_treated_as_null() -> None:
    assert normalize_series([1.0, "not-a-number", 2.0]) == (["0", "2"], [1.0, 2.0])


def test_no_pandas_or_polars_import_in_stats_package() -> None:
    """Real import statements only — prose mentioning pandas is allowed."""
    import digiquant.stats as stats_pkg

    banned = re.compile(r"^\s*(?:import|from)\s+(?:pandas|polars|pyarrow)\b", re.MULTILINE)
    offenders = [
        path
        for path in Path(stats_pkg.__file__).parent.glob("*.py")
        if banned.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


# --- Analyzer record shapes (DIG-937, corrective leaf for DIG-920) -------------
#
# ``nautilus_runner.py`` feeds ``analyzer.realized_pnls(USD)`` straight into this
# function, and the pyo3 analyzer changed what that returns between 1.228.0 and
# 1.230.0: ``dict {position_id: pnl}`` became ``list[(position_id, ts_event, pnl)]``.
# Neither is a series, so every row used to fail ``float()`` and the whole
# denominator came back ``None`` — an absent honest rate rather than a guarded one.
#
# These cases build a real ``PortfolioAnalyzer``. Constructing an analyzer is not
# running a backtest: no data, no bars, no strategy, no engine loop, so the
# SIGABRT-under-pytest hazard tracked as #42 does not apply.


def _pyo3():
    """The Rust/pyo3 analyzer namespace, or skip when nautilus is not installed.

    The type stubs ship incomplete — they do not declare ``realized_pnls`` or
    ``add_trade`` at all — so everything here binds off the real module.
    """
    return pytest.importorskip("nautilus_trader.core.nautilus_pyo3")


def _add_trade(analyzer, pyo3, usd, pid, pnl, ts=1_700_000_000_000_000_000):
    """``add_trade`` with the arity this build has: 2 args to 1.228, 3 from 1.230."""
    money = pyo3.Money(float(pnl), usd)
    try:
        analyzer.add_trade(pyo3.PositionId(pid), money)
    except TypeError:
        analyzer.add_trade(pyo3.PositionId(pid), int(ts), money)


def _analyzer_with_trades(trades):
    """A real analyzer holding ``trades`` — ``[(position_id, pnl), ...]``."""
    pyo3 = _pyo3()
    usd = pyo3.Currency.from_str("USD")
    analyzer = pyo3.PortfolioAnalyzer()
    for pid, pnl in trades:
        _add_trade(analyzer, pyo3, usd, pid, pnl)
    return analyzer, usd


#: The 1.230.0 record row. Not produced by the 1.228.0 build, so it is written
#: out literally: the shape is the contract, and the normalizer must honour it.
_ROWS_1230 = [
    ("P-1", 1_700_000_000_000_000_000, 10.0),
    ("P-2", 1_700_086_400_000_000_000, -4.0),
    ("P-3", 1_700_172_800_000_000_000, 0.0),
]


def test_case_1_engine_dict_shape_counts_every_row() -> None:
    """Required case 1: ``dict {pid: pnl}`` -> n = len(dict), k = count(pnl > 0)."""
    analyzer, usd = _analyzer_with_trades([("P-1", 10.0), ("P-2", -4.0), ("P-3", 0.0)])

    result = normalize_series(analyzer.realized_pnls(usd))

    assert result is not None, "the engine's own output must not normalize to None"
    dates, values = result
    assert len(values) == 3  # n == len(dict)
    assert sum(1 for v in values if v > 0) == 1  # k; the 0.0 close is a loss
    assert len(dates) == len(values)


def test_case_1_records_dict_does_not_fall_through_to_its_keys() -> None:
    """A dict has ``.values``; it must be read as a mapping, not listed into keys."""
    assert normalize_series({"P-1": 10.0, "P-2": -4.0}) is not None


def test_case_2_distinct_record_rows_all_count() -> None:
    """Required case 2: distinct ``(pid, ts)`` rows -> n = len(rows)."""
    result = normalize_series(_ROWS_1230)

    assert result is not None
    dates, values = result
    assert len(values) == 3
    assert sum(1 for v in values if v > 0) == 1
    assert len(set(dates)) == 3, "distinct ts_event means distinct dates"


def test_case_3_repeated_pair_counts_once_last_occurrence_wins() -> None:
    """Required case 3: a repeated ``(pid, ts)`` is one round trip, not two."""
    rows = [
        ("P-1", 1_700_000_000_000_000_000, 10.0),
        ("P-1", 1_700_000_000_000_000_000, 7.0),
        ("P-2", 1_700_086_400_000_000_000, 5.0),
    ]

    dates, values = normalize_series(rows)

    assert len(values) == 2, "the repeated (pid, ts) must be counted once"
    assert values == [7.0, 5.0], "the last occurrence is the engine's value"
    assert len(dates) == 2


def test_case_3_engine_repeated_position_id_is_one_row_too() -> None:
    """The same no-double-count property, measured on the installed build.

    Up to 1.228 the engine keys ``realized_pnls`` by position id, so it collapses
    the duplicate itself and the normalizer only has to not re-count it.
    """
    analyzer, usd = _analyzer_with_trades([("P-1", 10.0), ("P-1", -99.0), ("P-2", 5.0)])

    result = normalize_series(analyzer.realized_pnls(usd))

    assert result is not None
    assert len(result[1]) == 2


def test_case_4_recorded_trade_replaces_the_added_one_for_one_round_trip() -> None:
    """Required case 4: ``add_trade`` + ``record_trade`` on one ``(pid, ts)`` -> n = 1.

    The engine collapses this pair before the normalizer ever sees it, so this
    pins the *engine's* recorded-wins behaviour as the contract we mirror, and
    asserts we neither re-count the pair nor lose the recorded value. The
    ``record_trade`` entry point only exists from 1.230.0, hence the skip.
    """
    pyo3 = _pyo3()
    usd = pyo3.Currency.from_str("USD")
    analyzer = pyo3.PortfolioAnalyzer()
    if not hasattr(analyzer, "record_trade"):
        pytest.skip("record_trade is absent before nautilus_trader 1.230.0")
    ts = 1_700_000_000_000_000_000
    analyzer.add_trade(pyo3.PositionId("P-1"), ts, pyo3.Money(10.0, usd))
    analyzer.record_trade(pyo3.PositionId("P-1"), ts, pyo3.Money(4.0, usd))

    result = normalize_series(analyzer.realized_pnls(usd))

    assert result is not None
    assert len(result[1]) == 1, "one (pid, ts) is one round trip"
    assert result[1] == [4.0], "the recorded value is the one that survives"


def test_case_5_breakeven_is_a_loss_on_both_shapes() -> None:
    """Required case 5: only ``pnl > 0`` counts toward k (DIG-844 L2's ruling)."""
    assert sum(1 for v in normalize_series(_ROWS_1230)[1] if v > 0) == 1

    analyzer, usd = _analyzer_with_trades([("P-1", 0.0), ("P-2", 0.0)])
    _, values = normalize_series(analyzer.realized_pnls(usd))

    assert len(values) == 2
    assert sum(1 for v in values if v > 0) == 0


def test_case_6_none_and_empty_never_become_a_fabricated_zero() -> None:
    """Required case 6: a genuinely empty run is ``None`` — never 0, never num_trades."""
    assert normalize_series(None) is None
    assert normalize_series({}) is None
    assert normalize_series([]) is None

    analyzer, usd = _analyzer_with_trades([])

    assert analyzer.realized_pnls(usd) is None
    assert normalize_series(analyzer.realized_pnls(usd)) is None


def test_case_7_guarantees_survive_the_record_path() -> None:
    """Required case 7: non-finite dropped, iterable consumed once, no dataframe imports."""
    rows = [
        ("P-1", 1_700_000_000_000_000_000, 10.0),
        ("P-2", 1_700_086_400_000_000_000, float("nan")),
        ("P-3", 1_700_172_800_000_000_000, 3.0),
    ]
    dates, values = normalize_series(rows)

    assert values == [10.0, 3.0], "a non-finite record is dropped, and k cannot count it"
    assert len(dates) == len(values)

    generator = (row for row in _ROWS_1230)
    assert len(normalize_series(generator)[1]) == 3
    assert list(generator) == [], "the iterable is consumed exactly once"


def test_record_generator_is_rewound_not_double_consumed() -> None:
    """The shape probe must not eat the first record before the values are read."""
    generator = (row for row in _ROWS_1230)

    dates, values = normalize_series(generator)

    assert values == [10.0, -4.0, 0.0], "the first record must survive the shape probe"
    assert len(dates) == 3
    assert list(generator) == [], "the iterable is consumed exactly once"


def test_two_column_rows_fail_closed_rather_than_guessing_the_value_column() -> None:
    """A 2-element row is ambiguous, so it is refused rather than read as records.

    It could be ``(position_id, pnl)`` or ``(position_id, ts_event)``, and the
    second reading turns a timestamp into a 1.7e18 PnL that ``> 0`` counts as a
    win. Fabricating a number is the one outcome this module exists to prevent,
    so the answer is None. No build in reach emits a 2-column row.
    """
    assert normalize_series([("P-1", 10.0), ("P-2", -4.0)]) is None
    assert normalize_series([("P-1", 1_700_000_000_000_000_000)]) is None
    assert normalize_series([[0, 1.0], [1, 2.0]]) is None


def test_numeric_record_key_becomes_a_real_date_not_a_digit_prefix() -> None:
    """``ts_event`` is a nanosecond int; the date must be a date, not ``str(ns)[:10]``."""
    rows = [
        ("P-1", 1_700_000_000_000_000_000, 10.0),
        ("P-2", 1_700_086_400_000_000_000, -4.0),
    ]

    dates, _ = normalize_series(rows)

    assert dates == ["2023-11-14", "2023-11-15"]


def test_a_row_index_is_not_read_as_an_epoch_timestamp() -> None:
    """An ``int`` below the ns floor is an index, not a clock.

    ``(index, value)`` rows are a real thing to pass, and reading the index as
    epoch nanoseconds fabricates 1970-01-01 for every row — a wrong x-axis label
    where the honest answer is a position string. This is the case that would
    otherwise make the records path a new wrong-answer path. A 2-column
    ``(index, value)`` row is now refused outright, which satisfies the same
    intent by a stronger route: absent rather than wrong.
    """
    assert normalize_series([(0, 1.0), (1, 2.0)]) is None
    assert normalize_series([[1, 2], [3, 4], [5, 6]]) is None
    assert normalize_series([(0, 0, 1.0), (1, 1, 2.0)])[0] == ["0", "1"]
    assert normalize_series([("P-1", 1_700_000_000_000_000_000, 10.0)])[0] == ["2023-11-14"]


def test_unhashable_record_key_drops_only_its_own_row() -> None:
    """One row whose key cannot be a dict key must not take the whole series with it.

    The outer handler turns any escaping exception into None, so a single
    unhashable key used to discard every good row beside it — turning a guarded
    denominator into an absent one, the exact regression this leaf removes.
    """
    rows = [
        ("P-1", 1_700_000_000_000_000_000, 10.0),
        (["unhashable"], 1_700_000_008_640_000_000, -99.0),
        ("P-2", 1_700_000_017_280_000_000, 5.0),
    ]

    result = normalize_series(rows)

    assert result is not None, "one bad row must not empty the denominator"
    dates, values = result
    assert values == [10.0, 5.0], "only the unhashable row is dropped"
    assert len(dates) == 2


def test_a_row_of_another_width_is_dropped_rather_than_truncated() -> None:
    """A 4-column row must not silently yield its last element as a PnL."""
    # A 4-column row is dropped whole, never truncated to its last element
    assert normalize_series([("P-1", 1_700_000_000_000_000_000, 10.0, 1)]) is None
    assert (
        normalize_series([("P-1", 1_700_000_000_000_000_000, 10.0), ("P-2", 1, -4.0, 99.0)]) is None
    )
    # A batch with a non-row in it falls back to the plain series path, which drops
    # the element it cannot read rather than inventing a PnL for it.
    assert normalize_series([("P-1", 10.0), 5.0]) == (["1"], [5.0])


def test_day_boundaries_round_trip_at_the_nanosecond_edges() -> None:
    """Pins the ns->date boundary, which two comment threads got wrong by hand.

    Three stamps per day boundary, not one: the nanosecond *before* midnight is
    the case that matters, and it is the one a single exact-midnight fixture
    cannot see. ``/`` floats a stamp above 2^53 first, so that stamp rounds up to
    the next whole second and lands on the following day — wrong on 1826 of 1826
    boundaries, while every exact-midnight stamp was correct.

    The oracle is integer floor division, not the implementation's arithmetic:
    a stamp belongs to the second that contains it.
    """
    day_ns = 86_400_000_000_000
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    wrong = []
    for offset in range(1_826):  # every day boundary for five years
        midnight = (19_723 + offset) * day_ns
        for stamp in (midnight - 1, midnight, midnight + 1):
            truth = (epoch + timedelta(seconds=stamp // 1_000_000_000)).strftime("%Y-%m-%d")
            labelled = normalize_series([("P-1", stamp, 1.0)])[0][0]
            if labelled != truth:
                wrong.append((stamp, truth, labelled))
    assert wrong == [], f"{len(wrong)} of {1_826 * 3} stamps mislabelled, first {wrong[:3]}"


def test_returns_dict_is_no_longer_read_as_its_timestamps() -> None:
    """``analyzer.returns()`` is a ``{ts_ns: return}`` dict on 1.228.0.

    Listed into its keys it yields epoch nanoseconds, which are finite and
    positive — so every row counted as a win. The values are the returns.
    """
    pyo3 = _pyo3()
    usd = pyo3.Currency.from_str("USD")
    analyzer = pyo3.PortfolioAnalyzer()
    if not hasattr(analyzer, "add_position_return"):
        pytest.skip("add_position_return is absent in the installed nautilus_trader")
    analyzer.add_position_return(1_700_000_000_000_000_000, pyo3.Money(0.03, usd))
    analyzer.add_position_return(1_700_086_400_000_000_000, pyo3.Money(-0.01, usd))

    result = normalize_series(analyzer.returns())

    assert result is not None
    dates, values = result
    assert values == [0.03, -0.01], "the returns, not the nanosecond keys"
    assert dates == ["2023-11-14", "2023-11-15"]
