"""Unit tests for the honest-rate normalizer (``digiquant.stats.series``).

The cases are the ones that silently change N — the denominator every honest
rate is built on (DIG-428, L1 of DIG-474). Stdlib only: no Nautilus, polars or
pandas.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from fractions import Fraction
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


def _add_trade_at(analyzer, position_id, money, ts) -> bool:
    """``add_trade`` stamped with an explicit ``ts_event``. False if this build refuses one.

    Probed by *calling*, never by reading the signature: a signature test has to
    match a parameter name, so a build that still emitted rows but renamed
    ``ts_event`` would skip on exactly the builds that prove rows exist.

    ``TypeError`` alone is not proof of arity either — pyo3 raises it for
    argument *type conversion* too — so the 2-arg form this build does accept is
    the only thing that can tell the two apart. If that is refused too the error
    is something else and propagates, rather than being swallowed into a skip.

    The trade lands either way: a build that refuses the timestamp still gets the
    trade, with the 2-arg form, so the caller sees the engine's own behaviour for
    it rather than a hole in the data.
    """
    try:
        analyzer.add_trade(position_id, ts, money)
    except TypeError:
        analyzer.add_trade(position_id, money)
        return False
    return True


def _add_trade(analyzer, pyo3, usd, pid, pnl, ts=1_700_000_000_000_000_000):
    """``add_trade`` with the arity this build has: 2 args to 1.228, 3 from 1.230."""
    _add_trade_at(analyzer, pyo3.PositionId(pid), pyo3.Money(float(pnl), usd), int(ts))


def _analyzer_with_trades(trades):
    """A real analyzer holding ``trades`` — ``[(position_id, pnl), ...]``."""
    pyo3 = _pyo3()
    usd = pyo3.Currency.from_str("USD")
    analyzer = pyo3.PortfolioAnalyzer()
    for pid, pnl in trades:
        _add_trade(analyzer, pyo3, usd, pid, pnl)
    return analyzer, usd


#: Nanosecond stamps one day apart. Read off ``datetime`` rather than by hand:
#: two comment threads in this leaf mis-derived a day boundary in their heads and
#: published it as a defect before any code was run. ``test_the_stamps_are_the
#: _days_the_comments_named`` is the oracle.
_TS_1 = 1_700_000_000_000_000_000
_TS_2 = 1_700_086_400_000_000_000
_TS_3 = 1_700_172_800_000_000_000

#: The 1.230.0 record row. Not produced by the 1.228.0 build, so it is written
#: out literally: the shape is the contract, and the normalizer must honour it.
_ROWS_1230 = [
    ("P-1", _TS_1, 10.0),
    ("P-2", _TS_2, -4.0),
    ("P-3", _TS_3, 0.0),
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


def test_the_engine_really_emits_three_column_rows_with_a_real_timestamp() -> None:
    """The premise of this leaf, pinned against the engine that provides it.

    Every other case here proves the normalizer *handles* ``(pid, ts_event, pnl)``.
    This one proves the engine *produces* it, so a future nautilus that changes
    the row width — or stops producing rows at all — is caught here rather than
    silently losing the whole denominator in ``nautilus_runner.py``.

    Measured on 1.230.0, the build that returns rows: a ``list`` of ``(str, int,
    float)`` triples whose second column is the ``ts_event`` the trade was
    stamped with.

    The skip keys on the build's **capability** to emit a record row, not on the
    shape that came back. Keying on the observed shape would be the trap: a
    nautilus that reverted 1.230.0 to ``{pid: pnl}`` would then skip on the one
    build whose whole job is to prove rows exist. The capability probe is
    :func:`_add_trade_at`, shared with the two scale-out cases below.
    """
    pyo3 = _pyo3()
    usd = pyo3.Currency.from_str("USD")
    analyzer = pyo3.PortfolioAnalyzer()
    ts = _TS_1
    # Built outside the probe: only ``add_trade`` is under test, so a
    # TypeError from constructing these must fail loudly rather than skip.
    position_id = pyo3.PositionId("P-1")
    money = pyo3.Money(10.0, usd)
    if not _add_trade_at(analyzer, position_id, money, ts):
        pytest.skip("add_trade rejects a ts_event, so this build cannot emit record rows")

    raw = analyzer.realized_pnls(usd)

    assert isinstance(raw, list) and len(raw) == 1, f"expected one row, got {raw!r}"
    row = raw[0]
    assert isinstance(row, tuple) and len(row) == 3, f"expected (pid, ts, pnl), got {row!r}"
    key, ts_event, pnl = row
    assert key == "P-1", "the position id is the key"
    assert ts_event == ts, "the timestamp is the ts_event the trade was stamped with"
    # isinstance, not just ==: `10 == 10.0`, so equality alone would let an
    # int through and leave the docstring's `float` unbacked.
    assert isinstance(pnl, float), f"the realized pnl is a float, got {type(pnl).__name__}"
    assert pnl == 10.0, "the value is the realized pnl, not the timestamp"

    # ...and the normalizer reads that timestamp as the date rather than the row index.
    dates, values = normalize_series(raw)
    assert dates == ["2023-11-14"], "the ts_event column, not the row index"
    assert values == [10.0]


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


def test_the_stamps_are_the_days_the_comments_named() -> None:
    """The oracle for :data:`_TS_1`/:data:`_TS_2`/:data:`_TS_3`.

    Every label in this module is derived from these three stamps, so an off-by-a-
    day constant would silently move every assertion below with it — a set of
    tests that agree with each other and with nothing. Computed here from the
    epoch, one stamp at a time.

    Only the *differences* are whole days: ``_TS_1`` is 22:13:20Z, so it is not a
    midnight. Written as a per-stamp "is on a day boundary" check this test failed
    on its first run, which is why it is a difference.
    """
    day_ns = 86_400_000_000_000
    for stamp, day in ((_TS_1, "2023-11-14"), (_TS_2, "2023-11-15"), (_TS_3, "2023-11-16")):
        moment = datetime.fromtimestamp(stamp // 1_000_000_000, tz=timezone.utc)
        assert moment.strftime("%Y-%m-%d") == day, f"{stamp} is not {day}"
    assert _TS_2 - _TS_1 == day_ns, "the fixtures really are one day apart"
    assert _TS_3 - _TS_2 == day_ns


def test_case_8_a_repeated_pair_is_one_record_not_a_sum() -> None:
    """Board ruling (a), step 1: repeated records go before the parts are summed.

    Two ``add_trade`` calls for one ``(position_id, ts_event)`` leave that
    position worth **one** record's value. Summing first would report 17.0 — a
    close event counted twice, and a denominator that grows with the engine's own
    duplication instead of with the trading.
    """
    rows = [("P-1", _TS_1, 10.0), ("P-1", _TS_1, 7.0), ("P-2", _TS_2, 5.0)]

    dates, values = normalize_series(rows)

    assert len(values) == 2, "the repeated pair is one record, and P-2 is a second"
    assert values == [7.0, 5.0], "the later record wins; it is not the sum of both"
    assert 17.0 not in values, "the duplicated close event must not be added twice"


def test_case_8_engine_two_adds_on_one_pair_stay_one_row() -> None:
    """The same property on the installed engine, where the pair is built, not spelled out.

    Up to 1.228 ``realized_pnls`` is keyed by position id and the engine collapses
    the pair itself, last write winning; from 1.230.0 the pair reaches us and
    :func:`normalize_series` has to collapse it. Either way one position, one row.
    """
    analyzer, usd = _analyzer_with_trades([("P-1", 10.0), ("P-1", 7.0), ("P-2", 5.0)])

    result = normalize_series(analyzer.realized_pnls(usd))

    assert result is not None
    assert result[1] == [7.0, 5.0], "one row per position, the later record's value"


def test_case_9_two_parts_of_one_position_sum_into_a_single_row() -> None:
    """Board ruling (a), step 2: two legs of one position are one row.

    A scale-out closes one position in two parts. Counting the parts would report
    ``n=2`` here and ``n=1`` on the 1.228 dict that cannot express them, so the
    same strategy would carry a different honest rate depending on the installed
    engine. This is the case the ruling was made for: it returns ``[10.0, -5.0]``
    today and would have returned three rows.
    """
    rows = [("P-1", _TS_1, 6.0), ("P-1", _TS_2, 4.0), ("P-2", _TS_3, -5.0)]

    dates, values = normalize_series(rows)

    assert len(values) == 2, "one row per closed position, not per close event"
    assert values == [10.0, -5.0], "P-1's two legs are summed into its single row"
    assert sum(1 for v in values if v > 0) == 1, "k counts positions whose total is positive"


def test_case_9_engine_scale_out_is_one_position_not_two_legs() -> None:
    """The same scale-out, built on the engine that can express it.

    Only a build whose ``add_trade`` carries a ``ts_event`` can hold two legs of
    one position, so this skips on 1.228 — where the equivalent is measured by
    :func:`test_the_denominator_is_the_closed_position_count_on_both_engine_shapes`.
    """
    pyo3 = _pyo3()
    usd = pyo3.Currency.from_str("USD")
    analyzer = pyo3.PortfolioAnalyzer()
    money_1, money_2 = pyo3.Money(6.0, usd), pyo3.Money(4.0, usd)
    if not _add_trade_at(analyzer, pyo3.PositionId("P-1"), money_1, _TS_1):
        pytest.skip("add_trade rejects a ts_event, so this build cannot carry two legs")
    analyzer.add_trade(pyo3.PositionId("P-1"), _TS_2, money_2)
    analyzer.add_trade(pyo3.PositionId("P-2"), _TS_3, pyo3.Money(-5.0, usd))

    result = normalize_series(analyzer.realized_pnls(usd))

    assert result is not None
    dates, values = result
    assert len(values) == 2, "the scale-out is one position, not two legs"
    assert values == [10.0, -5.0]
    assert dates == ["2023-11-15", "2023-11-16"], "labelled with each position's last close"


def test_the_repeated_pair_is_collapsed_before_the_parts_are_summed() -> None:
    """Both steps at once, which is where their order shows.

    ``(P-1, ts1)`` arrives twice and ``(P-1, ts2)`` once. Collapsing first leaves
    99.0 + 4.0 = 103.0. Summing first leaves 6.0 + 99.0 + 4.0 = 109.0 — the same
    close event counted twice, in a value nobody can audit.

    Measured, by mutating the source and running the committed tests against the
    copy: against a true sum-before-dedupe (step 2 fed the raw records instead of
    the collapsed ones), the case above **fails** — its P-1 comes out 17.0 rather
    than 7.0 — while the two-legs case above still passes, because it has no
    repeated pair to double-count. So this case is not redundant with either of
    them: it is the only one that pins *which* record survives into the sum, the
    survivor rather than the record that step 1 discarded.
    """
    rows = [
        ("P-1", _TS_1, 6.0),
        ("P-1", _TS_1, 99.0),
        ("P-1", _TS_2, 4.0),
    ]

    _, values = normalize_series(rows)

    assert values == [103.0], "the surviving 99.0 is what gets summed, not the 6.0"


def test_a_position_whose_parts_cancel_below_zero_is_a_loss() -> None:
    """Summing is what decides the sign, so a winner's legs can make it a loss.

    10.0 and -12.0 are two winning-ish parts of one position whose total is -2.0.
    Counting the parts would report a win and add a fake one to ``k``, so the
    honest rate would be flattered by the very duplication the ruling removes.
    """
    rows = [("P-1", _TS_1, 10.0), ("P-1", _TS_2, -12.0), ("P-2", _TS_3, 1.0)]

    _, values = normalize_series(rows)

    assert values == [-2.0, 1.0]
    assert sum(1 for v in values if v > 0) == 1, "a net loss is not a win, however its legs fell"


def test_a_position_with_one_unreadable_part_is_dropped_whole() -> None:
    """No partial sums. One unreadable part makes the position's total unknowable.

    Keeping P-1's readable 10.0 and dropping only its NaN part would report a
    fabricated total — the one outcome this module exists to prevent, and a new
    one the summing introduces. The position goes instead; a row we can state is
    worth more than a row we cannot.
    """
    rows = [
        ("P-1", _TS_1, 10.0),
        ("P-1", _TS_2, float("nan")),
        ("P-2", _TS_3, 3.0),
    ]

    result = normalize_series(rows)

    assert result is not None, "P-2 survives on its own"
    assert result[1] == [3.0], "P-1 is dropped whole, not summed from its readable part"


def test_a_total_that_overflows_drops_the_position_rather_than_reporting_infinity() -> None:
    """Two finite parts can sum to ``inf``; ``inf`` is not a realized PnL."""
    rows = [("P-1", _TS_1, 1e308), ("P-1", _TS_2, 1e308), ("P-2", _TS_3, 3.0)]

    result = normalize_series(rows)

    assert result is not None, "P-2 survives on its own"
    assert result[1] == [3.0]
    assert all(math.isfinite(v) for v in result[1]), "no infinity reaches the caller"


def test_a_summed_position_is_labelled_with_its_last_close_event() -> None:
    """A position's realized PnL is complete when its final leg closes.

    Taking the first part's stamp instead would date the round trip to when it
    began being unwound, which is the open, not the close. The dict shape has one
    part per position, so this changes nothing there.
    """
    rows = [("P-1", _TS_1, 6.0), ("P-1", _TS_2, 4.0), ("P-2", _TS_3, 1.0)]

    dates, values = normalize_series(rows)

    assert values == [10.0, 1.0]
    assert dates == ["2023-11-15", "2023-11-16"]


def test_the_denominator_is_the_closed_position_count_on_both_engine_shapes() -> None:
    """The invariant the ruling buys: ``n`` is the same whatever build produced the rows.

    One logical activity — P-1 scaled out into two closes, P-2 closed once — in
    both shapes an installed engine emits. ``n`` must be 2 either way. Under the
    ``(pid, ts_event)`` key this leaf started with, the rows reported 3 and the
    dict 2, so the same strategy carried a different honest rate, and a different
    Wilson interval, depending on the installed engine.

    The *values* are not the same and cannot be: up to 1.228 the engine keys
    ``realized_pnls`` by position id, so it has already collapsed P-1's two legs
    to one entry before this code sees them, and that entry is whatever the engine
    last computed. n is what this module promises to mean the same everywhere, and
    it is the number the honest rate is divided by.
    """
    from_dict = normalize_series({"P-1": 10.0, "P-2": -5.0})
    from_rows = normalize_series(
        [("P-1", _TS_1, 6.0), ("P-1", _TS_2, 4.0), ("P-2", _TS_3, -5.0)],
    )

    assert from_dict is not None
    assert from_rows is not None
    n_dict, n_rows = len(from_dict[1]), len(from_rows[1])
    assert n_dict == n_rows == 2, f"n is build-dependent: {n_dict} on the dict, {n_rows} on rows"
    assert from_dict[1][0] == from_rows[1][0] == 10.0, "P-1 is worth its legs on both shapes"
    assert sum(1 for v in from_dict[1] if v > 0) == 1
    assert sum(1 for v in from_rows[1] if v > 0) == 1, "same k, same rate, same interval"


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


# ---------------------------------------------------------------------------
# Carried forward from PR #5126 (DIG-843) at 2d89cddba.
#
# DIG-937's branch is a *parallel copy* of DIG-843's, not a stack on top of it:
# neither 2d89cddba nor the earlier 3f9a6a9ac is an ancestor of it, so
# `git merge-tree --write-tree HEAD 2d89cddba` reports add/add conflicts on this
# file and on `stats/series.py`. Whichever side the merge resolves to, the other
# side's behaviour disappears silently. These four cases are the two Important
# review findings #5126 was fixed for. They are carried here, on the same branch,
# so that the merge has one place where both halves are true and the resolution
# cannot quietly drop either.
# ---------------------------------------------------------------------------


def test_unrepresentable_number_drops_one_row_not_the_whole_series() -> None:
    """A row too large for a float is as null as NaN — it must not blank the series.

    An object-dtype ``.values`` (pandas) or an arbitrary Python scalar can hold an
    ``int`` no bigger than ``float`` can represent. ``float()`` raises
    ``OverflowError`` for those, which is not a ``ValueError``, so it used to
    escape the per-row guard and null the entire series instead of dropping the
    one bad row. That silently changes N from 2 to 0 — refused, not wrong, but it
    loses rate that the NaN case already keeps.
    """
    result = normalize_series([0.01, 10**400, -0.02])

    assert result is not None
    dates, values = result
    assert values == [0.01, -0.02]
    assert dates == ["0", "2"]


def test_unrepresentable_rational_drops_one_row() -> None:
    """A ``Fraction`` is a real number this guard cannot cast; drop its row only."""
    assert normalize_series([1.0, Fraction(10**500, 1)]) == (["0"], [1.0])


def test_series_of_only_unrepresentable_numbers_is_none() -> None:
    """Every row nulled is the same refusal as an all-NaN series."""
    assert normalize_series([10**400]) is None


def test_bools_are_kept_as_one_and_zero_in_every_container() -> None:
    """The chart path keeps bools, so the rate path must keep them too.

    ``charts/common.py::_extract_frame`` delegates to this function (DIG-848), so
    a boolean row has to survive here for both paths to see the same N. When the
    chart path still had its own polars cast with ``strict=False``, ``Boolean``
    became 1.0/0.0 there while this function dropped the row, and the two
    disagreed about N -- the one thing this module exists to prevent. Decided by
    value, so a ``numpy.bool_`` from ``list(arr)`` and a plain ``bool`` from
    ``.to_list()`` behave identically.
    """
    expected = (["0", "1", "2"], [1.0, 0.0, 1.0])

    assert normalize_series([True, False, True]) == expected
    assert normalize_series(_FakePolars([True, False, True])) == expected
    assert normalize_series(_FakePandasShape([True, False, True], [0, 1, 2])) == expected
