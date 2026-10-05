"""Unit tests for the honest-rate normalizer (``digiquant.stats.series``).

The cases are the ones that silently change N — the denominator every honest
rate is built on (DIG-428, L1 of DIG-474). Stdlib only: no Nautilus, polars or
pandas.
"""

from __future__ import annotations

import math
import re
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
