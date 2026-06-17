"""Tests for pairwise_return_correlations (pure function) and get_return_correlations reader.

Covers:
  - perfectly-correlated pair → ρ ≈ 1.0
  - anti-correlated pair → ρ ≈ -1.0
  - insufficient overlap → pair omitted
  - look-ahead guard: a decision dated D sees no close > D
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any  # noqa  # scored-lint: heterogeneous FakeSupabase fixture dicts

import polars as pl
import pytest

from digiquant.data.prices.correlation import pairwise_return_correlations
from digiquant.olympus.atlas.data.queries import get_return_correlations

pytestmark = pytest.mark.unit


# ── helpers ──────────────────────────────────────────────────────────────────


def _close_rows(series: dict[str, list[float]], start: date) -> list[dict]:
    """Build long close-price rows for {ticker: [close, ...]}, consecutive trading days."""
    rows = []
    for ticker, closes in series.items():
        for i, c in enumerate(closes):
            rows.append(
                {"ticker": ticker, "date": (start + timedelta(days=i)).isoformat(), "close": c}
            )
    return rows


def _corr_map(frame: pl.DataFrame) -> dict[tuple[str, str], float]:
    """Convert the output frame to a {(a,b): corr} dict for easy assertion."""
    return {(r["a"], r["b"]): r["corr"] for r in frame.to_dicts()}


# ── FakeSupabaseClient (mirrors the atlas/test_supabase_io version, minimal) ─


@dataclass
class _FakeResponse:
    data: list[dict[str, Any]]


@dataclass
class _FakeQuery:
    table_name: str
    canned: list[dict[str, Any]] = field(default_factory=list)
    _filters: list[tuple[str, str, Any]] = field(default_factory=list)
    _order: tuple[str, bool] | None = None
    _limit: int | None = None

    def select(self, _cols: str) -> "_FakeQuery":
        return self

    def lte(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("lte", col, val))
        return self

    def gte(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("gte", col, val))
        return self

    def in_(self, col: str, vals: list[Any]) -> "_FakeQuery":
        self._filters.append(("in_", col, list(vals)))
        return self

    def order(self, col: str, desc: bool = False) -> "_FakeQuery":
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> "_FakeQuery":
        self._limit = n
        return self

    def execute(self) -> _FakeResponse:
        rows = list(self.canned)
        for op, col, val in self._filters:
            if op == "lte":
                rows = [r for r in rows if str(r.get(col, "")) <= str(val)]
            elif op == "gte":
                rows = [r for r in rows if str(r.get(col, "")) >= str(val)]
            elif op == "in_":
                rows = [r for r in rows if r.get(col) in val]
        if self._order is not None:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(data=rows)


@dataclass
class FakeSupabaseClient:
    canned_reads: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(table_name=name, canned=list(self.canned_reads.get(name, [])))


# ── pairwise_return_correlations — pure function ───────────────────────────────


class TestPairwiseReturnCorrelations:
    """Pure-function contract tests — no I/O, no Supabase fake needed."""

    def test_perfectly_correlated_pair_approx_one(self) -> None:
        # A and B move identically → Pearson r = 1.0.
        start = date(2026, 1, 2)
        closes = {
            "A": [100.0 + i for i in range(40)],
            "B": [200.0 + i * 2 for i in range(40)],  # same direction, different scale
        }
        frame = pairwise_return_correlations(pl.DataFrame(_close_rows(closes, start)))
        m = _corr_map(frame)
        assert ("A", "B") in m
        assert m[("A", "B")] == pytest.approx(1.0, abs=1e-6)

    def test_anti_correlated_pair_approx_minus_one(self) -> None:
        # Alternating pattern: A zig-zags up (+1, +1, +1, ...) while B zig-zags down
        # (-1, -1, -1, ...) with the same absolute return → Pearson r = -1.0.
        start = date(2026, 1, 2)
        # A alternates between two levels → constant return.
        # B is the mirror: same magnitude, opposite sign.
        a_closes = [100.0 if i % 2 == 0 else 101.0 for i in range(40)]
        b_closes = [100.0 if i % 2 == 0 else 99.0 for i in range(40)]
        closes = {"A": a_closes, "B": b_closes}
        frame = pairwise_return_correlations(pl.DataFrame(_close_rows(closes, start)))
        m = _corr_map(frame)
        assert ("A", "B") in m
        assert m[("A", "B")] == pytest.approx(-1.0, abs=1e-6)

    def test_insufficient_overlap_pair_omitted(self) -> None:
        # Only 5 common dates with returns — below the default min_overlap=30.
        start = date(2026, 1, 2)
        closes = {
            "A": [100.0 + i for i in range(10)],
            "B": [50.0 + i for i in range(10)],
        }
        frame = pairwise_return_correlations(
            pl.DataFrame(_close_rows(closes, start)), min_overlap=30
        )
        # Pair should be absent because only 9 return periods exist (10 closes → 9 returns).
        assert frame.is_empty()

    def test_sufficient_overlap_pair_present(self) -> None:
        # Exactly min_overlap=5 overlapping returns (6 closes → 5 returns) → pair included.
        start = date(2026, 1, 2)
        closes = {
            "A": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "B": [200.0, 201.0, 202.0, 203.0, 204.0, 205.0],
        }
        frame = pairwise_return_correlations(
            pl.DataFrame(_close_rows(closes, start)), min_overlap=5
        )
        assert not frame.is_empty()
        assert ("A", "B") in _corr_map(frame)

    def test_single_ticker_returns_empty(self) -> None:
        start = date(2026, 1, 2)
        closes = {"A": [100.0 + i for i in range(40)]}
        frame = pairwise_return_correlations(pl.DataFrame(_close_rows(closes, start)))
        assert frame.is_empty()

    def test_empty_frame_returns_empty(self) -> None:
        frame = pairwise_return_correlations(pl.DataFrame())
        assert frame.is_empty()

    def test_output_schema(self) -> None:
        # Output always has exactly columns a, b, corr with correct dtype.
        start = date(2026, 1, 2)
        closes = {
            "A": [100.0 + i for i in range(40)],
            "B": [200.0 + i for i in range(40)],
        }
        frame = pairwise_return_correlations(pl.DataFrame(_close_rows(closes, start)))
        assert set(frame.columns) == {"a", "b", "corr"}
        assert frame.schema["a"] == pl.Utf8
        assert frame.schema["b"] == pl.Utf8
        assert frame.schema["corr"] == pl.Float64

    def test_each_pair_appears_once(self) -> None:
        # Three tickers → 3 unordered pairs; verify no duplicate (a,b)/(b,a) rows.
        start = date(2026, 1, 2)
        closes = {
            "A": [100.0 + i for i in range(40)],
            "B": [200.0 + i for i in range(40)],
            "C": [300.0 + i for i in range(40)],
        }
        frame = pairwise_return_correlations(pl.DataFrame(_close_rows(closes, start)))
        pairs = [(r["a"], r["b"]) for r in frame.to_dicts()]
        assert len(pairs) == len(set(pairs))  # no duplicates
        assert len(pairs) == 3  # C(3,2) = 3


# ── get_return_correlations — look-ahead guard + fail-soft ───────────────────


class TestGetReturnCorrelations:
    """Reader tests — use FakeSupabaseClient; verify look-ahead guard and fail-soft."""

    _RUN_DATE = date(2026, 3, 15)

    def _price_rows(self, n: int = 40) -> list[dict]:
        """Generate n close rows for two tickers ending at _RUN_DATE.

        Anchored to _RUN_DATE so rows fall inside the default 63-day lookback window.
        """
        rows = []
        for i in range(n):
            d = (self._RUN_DATE - timedelta(days=n - 1 - i)).isoformat()
            rows.append({"date": d, "ticker": "A", "close": 100.0 + i})
            rows.append({"date": d, "ticker": "B", "close": 200.0 + i})
        return rows

    def test_returns_correlation_frame(self) -> None:
        client = FakeSupabaseClient(canned_reads={"price_history": self._price_rows()})
        frame = get_return_correlations(
            client=client,
            tickers=["A", "B"],
            run_date=self._RUN_DATE,
        )
        assert frame is not None
        assert not frame.is_empty()
        m = _corr_map(frame)
        assert ("A", "B") in m
        # Consecutive-integer closes produce very-high but not exact-1.0 correlation
        # (returns shrink as price rises), so 1e-3 absolute tolerance is appropriate.
        assert m[("A", "B")] == pytest.approx(1.0, abs=1e-3)

    def test_look_ahead_guard_excludes_future_closes(self) -> None:
        # We have 40 on-time rows (ending at _RUN_DATE) plus 2 future-dated rows.
        # The future rows have a huge jump for A and a crash for B, which would produce
        # extreme outlier returns and push ρ strongly negative if included.
        # The .lte(run_date) guard must exclude them so the result stays strongly positive.
        future_date = (self._RUN_DATE + timedelta(days=5)).isoformat()
        rows = self._price_rows(40)
        # Future rows: extreme outliers that would crush the positive correlation.
        rows.append({"date": future_date, "ticker": "A", "close": 99999.0})
        rows.append({"date": future_date, "ticker": "B", "close": 0.01})
        client = FakeSupabaseClient(canned_reads={"price_history": rows})
        frame = get_return_correlations(
            client=client,
            tickers=["A", "B"],
            run_date=self._RUN_DATE,
            lookback_days=63,
        )
        # The FakeQuery's lte filter strips future rows; result must still be strongly +.
        assert frame is not None
        m = _corr_map(frame)
        assert ("A", "B") in m
        assert m[("A", "B")] > 0.5  # strongly positive, not distorted by future data

    def test_fewer_than_two_tickers_returns_none(self) -> None:
        # The fast-path guard: a single-ticker portfolio has no pairs to compute.
        client = FakeSupabaseClient(canned_reads={"price_history": self._price_rows()})
        result = get_return_correlations(client=client, tickers=["A"], run_date=self._RUN_DATE)
        assert result is None

    def test_empty_price_history_returns_none(self) -> None:
        client = FakeSupabaseClient(canned_reads={"price_history": []})
        result = get_return_correlations(client=client, tickers=["A", "B"], run_date=self._RUN_DATE)
        assert result is None

    def test_db_error_returns_none(self) -> None:
        # The reader must not propagate exceptions — it returns None on failure.
        class _BrokenClient:
            def table(self, _name: str):
                raise RuntimeError("db down")

        result = get_return_correlations(
            client=_BrokenClient(), tickers=["A", "B"], run_date=self._RUN_DATE
        )
        assert result is None
