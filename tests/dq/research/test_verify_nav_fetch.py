"""Unit tests for ``verify_nav_replay._fetch_table`` stable pagination (#3803).

``_fetch_table`` must page over a deterministic ``(date, ticker)`` order with
a last-seen-key cursor (never an offset), so a concurrent book upsert between
pages can neither shift rows out of the series nor duplicate them into the
weight schedule that ``--write`` persists as truth. A truncated or unstable
page must raise — never return a partial series.

``build_request`` must also repair vendor OHLC envelope drift — a float ULP or
a few cents — by widening ``high``/``low`` around ``open``/``close`` before the
strict replay contract validates each bar (#3995).

The script is loaded via importlib like the other script-level tests
(``digiquant/scripts`` are not installed packages).
"""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.dq.research.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "scripts"
    / "research"
    / "verify_nav_replay.py"
)


def _load_verify_module():
    spec = importlib.util.spec_from_file_location("verify_nav_replay_fetch", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_verify_module()

_POSITIONS = "date,ticker,weight_pct"


def _positions(rows: list[tuple[str, str, float]]) -> list[dict[str, Any]]:
    return [{"date": d, "ticker": t, "weight_pct": w} for d, t, w in rows]


class TestDeterministicOrder:
    def test_multi_page_fetch_returns_sorted_keys_without_loss_or_dup(self) -> None:
        """Same-date tickers arrive in a stable order across page boundaries."""
        house = "house-id"
        canned = _positions(
            [
                ("2026-09-02", "SPY", 60.0),
                ("2026-09-01", "TLT", 40.0),
                ("2026-09-01", "SPY", 60.0),
                ("2026-09-03", "SPY", 55.0),
                ("2026-09-02", "TLT", 40.0),
                ("2026-09-01", "CASH", 0.0),
            ]
        )
        sb = FakeSupabaseClient(
            canned_reads={"positions": [{**r, "workspace_id": house} for r in canned]}
        )
        rows = _mod._fetch_table(sb, "positions", house, _POSITIONS, page_size=2)
        keys = [(r["date"], r["ticker"]) for r in rows]
        assert keys == sorted(keys)
        assert len(keys) == len(set(keys)) == 6

    def test_nav_history_without_ticker_orders_by_date(self) -> None:
        house = "house-id"
        sb = FakeSupabaseClient(
            canned_reads={
                "nav_history": [
                    {"date": "2026-09-03", "nav": 99.5, "workspace_id": house},
                    {"date": "2026-09-01", "nav": 100.0, "workspace_id": house},
                    {"date": "2026-09-02", "nav": 99.8, "workspace_id": house},
                ]
            }
        )
        rows = _mod._fetch_table(sb, "nav_history", house, "date,nav", page_size=2)
        assert [r["date"] for r in rows] == ["2026-09-01", "2026-09-02", "2026-09-03"]

    def test_house_pin_excludes_overlay_rows(self) -> None:
        """Workspace scoping per HOUSE_BOOK_SCOPE: omitted id means house only."""
        from digiquant.dashboard.tenancy import house_workspace_id

        house = str(house_workspace_id())
        sb = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    {
                        "date": "2026-09-01",
                        "ticker": "SPY",
                        "weight_pct": 60.0,
                        "workspace_id": house,
                    },
                    {
                        "date": "2026-09-01",
                        "ticker": "SPY",
                        "weight_pct": 10.0,
                        "workspace_id": "00000000-0000-4000-8000-000000000001",
                    },
                ]
            }
        )
        rows = _mod._fetch_table(sb, "positions", house, _POSITIONS, page_size=10)
        assert [(r["date"], r["ticker"], r["weight_pct"]) for r in rows] == [
            ("2026-09-01", "SPY", 60.0)
        ]


class TestConcurrentUpsertStability:
    def test_boundary_date_insert_between_pages_is_captured_once(self) -> None:
        """A row upserted onto the cursor date mid-pagination is still read."""
        house = "house-id"
        base = _positions(
            [
                ("2026-09-01", "AAA", 50.0),
                ("2026-09-01", "BBB", 50.0),
                ("2026-09-02", "AAA", 60.0),
                ("2026-09-02", "BBB", 40.0),
            ]
        )
        sb = FakeSupabaseClient(
            canned_reads={"positions": [{**r, "workspace_id": house} for r in base]}
        )
        state = {"calls": 0}
        orig_table = sb.table

        def table(name: str):
            query = orig_table(name)
            orig_execute = query.execute

            def execute():
                state["calls"] += 1
                resp = orig_execute()
                if state["calls"] == 1:
                    # Concurrent book upsert lands on the cursor date (2026-09-01)
                    # after the first page is read — the offset scheme would
                    # shift every later page; the cursor scheme re-anchors
                    # (the fake copies rows per query like a live DB read, so
                    # the row must land before the second page is issued).
                    sb.canned_reads["positions"].append(
                        {
                            "date": "2026-09-01",
                            "ticker": "CCC",
                            "weight_pct": 10.0,
                            "workspace_id": house,
                        }
                    )
                return resp

            query.execute = execute
            return query

        sb.table = table  # type: ignore[method-assign]
        rows = _mod._fetch_table(sb, "positions", house, _POSITIONS, page_size=2)
        keys = [(r["date"], r["ticker"]) for r in rows]
        assert sorted(keys) == [
            ("2026-09-01", "AAA"),
            ("2026-09-01", "BBB"),
            ("2026-09-01", "CCC"),
            ("2026-09-02", "AAA"),
            ("2026-09-02", "BBB"),
        ]


class TestMaxRowsCap:
    """Regression (#3948): a capped PostgREST response must never be a silent truncation.

    ``verify_nav_replay._fetch_table`` used to widen each request by the
    already-seen boundary count (``limit(page_size + boundary_seen)``). With the
    production cap (``max_rows=1000``, ``page_size=1000``) the server clamps the
    response, ``len(page) < page_size + boundary_seen`` becomes true, and the
    loop breaks *before* the stall guard — silently dropping rows that
    ``--write`` then persists as NAV truth.
    """

    def _capped_client(self, rows: list[dict[str, Any]], *, cap: int):
        """Fake that mirrors PostgREST ``max_rows``: never returns more than ``cap``."""

        class _Capped(FakeSupabaseClient):
            def table(self, name: str):  # type: ignore[no-untyped-def]
                query = super().table(name)
                if name != "positions":
                    return query
                inner = query.execute

                def execute():  # type: ignore[no-untyped-def]
                    resp = inner()
                    resp.data = list(resp.data or [])[:cap]
                    return resp

                query.execute = execute  # type: ignore[method-assign]
                return query

        return _Capped(canned_reads={"positions": rows})

    def test_over_cap_dataset_is_never_silently_truncated(self) -> None:
        """3000 rows > max_rows=1000 with page_size=1000 must return all 3000."""
        from datetime import date, timedelta

        house = "house-id"
        # One ticker per distinct date, so every page after the first re-anchors
        # on a date that already emitted a row (``boundary_seen == 1``) — the
        # exact shape that tripped the old ``limit(page_size + boundary_seen)``
        # overflow and returned 1999/3000 rows without error.
        start = date(2026, 1, 1)
        canned = _positions(
            [((start + timedelta(days=i)).isoformat(), "SPY", 100.0) for i in range(3000)]
        )
        sb = self._capped_client(
            [{**r, "workspace_id": house} for r in canned],
            cap=1000,
        )
        rows = _mod._fetch_table(sb, "positions", house, _POSITIONS, page_size=1000)
        assert len(rows) == 3000, f"expected all 3000 rows, got {len(rows)} (silent truncation)"
        assert len({(r["date"], r["ticker"]) for r in rows}) == 3000

    def test_page_size_above_the_cap_fails_loudly(self) -> None:
        """A page request larger than ``max_rows`` must raise, not be clamped silently."""
        house = "house-id"
        sb = self._capped_client(
            [{**_positions([("2026-09-01", "SPY", 100.0)])[0], "workspace_id": house}],
            cap=1000,
        )
        with pytest.raises(RuntimeError, match="max_rows"):
            _mod._fetch_table(
                sb,
                "positions",
                house,
                _POSITIONS,
                page_size=1500,
                max_rows=1000,
            )


class TestUnscopedTablePaging:
    def test_price_history_pages_without_any_workspace_predicate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``price_history`` is market/reference data — it has no ``workspace_id``.

        Filtering it by ``workspace_id`` raises PostgREST 42703 in prod and kills
        the research-metrics refresh before the derived surfaces update (#3990),
        so the fetch must page on the keyset alone.
        """
        queries: list[Any] = []
        original_table = FakeSupabaseClient.table

        def spy_table(client: Any, name: str) -> Any:
            query = original_table(client, name)
            queries.append(query)
            return query

        monkeypatch.setattr(FakeSupabaseClient, "table", spy_table)
        rows = [
            {"date": "2026-09-01", "ticker": "SPY", "close": 1.0},
            {"date": "2026-09-01", "ticker": "TLT", "close": 2.0},
            {"date": "2026-09-02", "ticker": "SPY", "close": 3.0},
            {"date": "2026-09-02", "ticker": "TLT", "close": 4.0},
            {"date": "2026-09-03", "ticker": "SPY", "close": 5.0},
        ]
        sb = FakeSupabaseClient(canned_reads={"price_history": rows})
        out = _mod._fetch_table(
            sb,
            "price_history",
            "house-id",
            "date,ticker,close",
            workspace_scoped=False,
            page_size=2,
        )
        assert [(r["date"], r["ticker"]) for r in out] == [
            ("2026-09-01", "SPY"),
            ("2026-09-01", "TLT"),
            ("2026-09-02", "SPY"),
            ("2026-09-02", "TLT"),
            ("2026-09-03", "SPY"),
        ]
        assert queries, "expected the fetch to issue at least one query"
        for query in queries:
            assert not query._or_raw or "workspace_id" not in query._or_raw
            assert all(col != "workspace_id" for _op, col, _val in query._filters)

    def test_scoped_tables_still_pin_the_house_workspace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """House-scoped tables keep the ``workspace_id`` pin."""
        queries: list[Any] = []
        original_table = FakeSupabaseClient.table

        def spy_table(client: Any, name: str) -> Any:
            query = original_table(client, name)
            queries.append(query)
            return query

        monkeypatch.setattr(FakeSupabaseClient, "table", spy_table)
        rows = [
            {"date": "2026-09-01", "ticker": "AAA", "weight_pct": 20.0, "workspace_id": "house-id"},
            {"date": "2026-09-02", "ticker": "AAA", "weight_pct": 25.0, "workspace_id": "house-id"},
        ]
        sb = FakeSupabaseClient(canned_reads={"positions": rows})
        out = _mod._fetch_table(sb, "positions", "house-id", "date,ticker,weight_pct", page_size=2)
        assert [(r["date"], r["ticker"]) for r in out] == [
            ("2026-09-01", "AAA"),
            ("2026-09-02", "AAA"),
        ]
        assert any(("eq", "workspace_id", "house-id") in query._filters for query in queries)


class TestMissingTicker:
    def test_missing_ticker_raises_instead_of_false_duplicate(self) -> None:
        """A null ticker must not collapse to ``""`` and masquerade as a valid key.

        Two null-ticker rows on one date would previously key as ``("date", "")``
        twice and trip the duplicate-key guard — flagging a *pagination* failure
        for what is really corrupt input. Fail loudly on the missing key instead.
        """
        house = "house-id"
        rows = [
            {"date": "2026-09-01", "ticker": None, "weight_pct": 50.0, "workspace_id": house},
        ]
        sb = FakeSupabaseClient(canned_reads={"positions": rows})
        with pytest.raises(RuntimeError, match="ticker"):
            _mod._fetch_table(sb, "positions", house, _POSITIONS, page_size=10)


class TestFailClosed:
    def test_out_of_order_page_raises(self) -> None:
        """A server that ignores the secondary order must not yield a series."""

        class _UnsortedClient:
            def table(self, _name: str) -> "_UnsortedClient":
                return self

            def select(self, _cols: str) -> "_UnsortedClient":
                return self

            def order(self, _col: str, desc: bool = False) -> "_UnsortedClient":
                return self

            def eq(self, _col: str, _val: Any) -> "_UnsortedClient":
                return self

            def gte(self, _col: str, _val: Any) -> "_UnsortedClient":
                return self

            def limit(self, _n: int) -> "_UnsortedClient":
                return self

            def execute(self):
                return type(
                    "Resp",
                    (),
                    {
                        "data": [
                            {"date": "2026-09-01", "ticker": "ZZZ"},
                            {"date": "2026-09-01", "ticker": "AAA"},
                        ]
                    },
                )()

        with pytest.raises(RuntimeError, match="out of .*order"):
            _mod._fetch_table(_UnsortedClient(), "positions", "house-id", _POSITIONS, page_size=10)

    def test_duplicate_keys_within_page_raise(self) -> None:
        class _DupClient:
            def table(self, _name: str) -> "_DupClient":
                return self

            def select(self, _cols: str) -> "_DupClient":
                return self

            def order(self, _col: str, desc: bool = False) -> "_DupClient":
                return self

            def eq(self, _col: str, _val: Any) -> "_DupClient":
                return self

            def gte(self, _col: str, _val: Any) -> "_DupClient":
                return self

            def limit(self, _n: int) -> "_DupClient":
                return self

            def execute(self):
                return type(
                    "Resp",
                    (),
                    {
                        "data": [
                            {"date": "2026-09-01", "ticker": "AAA"},
                            {"date": "2026-09-01", "ticker": "AAA"},
                        ]
                    },
                )()

        with pytest.raises(RuntimeError, match="duplicate"):
            _mod._fetch_table(_DupClient(), "positions", "house-id", _POSITIONS, page_size=10)


class TestBarBoundsRepair:
    """Vendor OHLC rows can drift by a float ULP or a few cents (#3995).

    ``build_request`` must widen ``high``/``low`` to encompass ``open`` and
    ``close`` before the strict replay contract validates the bar. ``close``
    is the input the engine actually trades on and must never be rewritten.
    """

    def _bars(self, price_row: dict[str, Any]):
        positions = [{"date": "2026-09-01", "ticker": "AAA", "weight_pct": 100.0}]
        nav = [{"date": "2026-09-01", "nav": 100.0}]
        request, _closes, _recorded = _mod.build_request([price_row], positions, nav)
        (series,) = request.series
        return series.bars

    def test_ulp_boundary_close_is_repaired_without_moving_close(self) -> None:
        """SPY 1993-02-12: stored close sat ~4e-15 below the stored low."""
        row = {
            "date": "2026-09-01",
            "ticker": "AAA",
            "open": 24.691216563042346,
            "high": 24.691216563042346,
            "low": 24.536466598510746,
            "close": 24.536466598510742,
            "volume": 42500,
        }
        (bar,) = self._bars(row)
        assert float(bar.close) == 24.536466598510742
        assert bar.low == Decimal("24.536466598510742")
        assert bar.high == Decimal("24.691216563042346")

    def test_open_above_high_is_repaired(self) -> None:
        """DHR 2026-09-09: the vendor open exceeded its own high by a cent."""
        row = {
            "date": "2026-09-01",
            "ticker": "AAA",
            "open": 206.0,
            "high": 205.99,
            "low": 201.95,
            "close": 204.85,
            "volume": 1000,
        }
        (bar,) = self._bars(row)
        assert float(bar.high) == 206.0
        assert float(bar.close) == 204.85
        assert bar.low <= bar.open <= bar.high

    def test_sane_bar_passes_through_unchanged(self) -> None:
        row = {
            "date": "2026-09-01",
            "ticker": "AAA",
            "open": 100.0,
            "high": 110.0,
            "low": 95.0,
            "close": 105.0,
            "volume": 1000,
        }
        (bar,) = self._bars(row)
        assert (
            float(bar.open),
            float(bar.high),
            float(bar.low),
            float(bar.close),
        ) == (100.0, 110.0, 95.0, 105.0)

    def test_warn_is_one_aggregate_line_for_all_repairs(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Several repaired bars still emit a single aggregate WARN (#3995)."""
        rows = [
            {
                "date": "2026-09-01",
                "ticker": "AAA",
                "open": 24.691216563042346,
                "high": 24.691216563042346,
                "low": 24.536466598510746,
                "close": 24.536466598510742,
                "volume": 42500,
            },
            {
                "date": "2026-09-01",
                "ticker": "BBB",
                "open": 206.0,
                "high": 205.99,
                "low": 201.95,
                "close": 204.85,
                "volume": 1000,
            },
        ]
        positions = [
            {"date": "2026-09-01", "ticker": "AAA", "weight_pct": 50.0},
            {"date": "2026-09-01", "ticker": "BBB", "weight_pct": 50.0},
        ]
        nav = [{"date": "2026-09-01", "nav": 100.0}]
        _mod.build_request(rows, positions, nav)
        out = capsys.readouterr().out
        assert out.count("widened OHLC bounds") == 1
        assert "widened OHLC bounds on 2 bar(s)" in out


class TestScheduleAlignedSeries:
    """The replay contract needs one shared bar grid across instruments (#4002).

    Price history is per-ticker: tickers start on different dates, unrelated
    tickers sit in the table, and weekend/holiday books have no bars at all.
    The request must restrict the series to the schedule tickers, use the book
    dates as the grid, and forward-fill a hole flat at the last close so a
    weekend book still executes on the last mark.
    """

    @staticmethod
    def _price(date_: str, ticker: str, close: float, open_: float | None = None) -> dict:
        open_value = close if open_ is None else open_
        return {
            "date": date_,
            "ticker": ticker,
            "open": open_value,
            "high": max(open_value, close),
            "low": min(open_value, close),
            "close": close,
            "volume": 1000,
        }

    def test_unrelated_tickers_are_excluded_from_the_series(self) -> None:
        rows = [
            self._price("2026-09-01", "AAA", 100.0),
            self._price("2026-09-01", "BBB", 50.0),
            self._price("2026-09-01", "ZZZ", 10.0),
        ]
        positions = [
            {"date": "2026-09-01", "ticker": "AAA", "weight_pct": 60.0},
            {"date": "2026-09-01", "ticker": "BBB", "weight_pct": 40.0},
        ]
        nav = [{"date": "2026-09-01", "nav": 100.0}]
        request, _closes, _recorded = _mod.build_request(rows, positions, nav)
        assert [s.ticker for s in request.series] == ["AAA", "BBB"]

    def test_weekend_book_date_forward_fills_flat_bars(self) -> None:
        rows = [
            self._price("2026-09-04", "AAA", 100.0),
            self._price("2026-09-08", "AAA", 110.0),
            self._price("2026-09-04", "BBB", 50.0),
            self._price("2026-09-08", "BBB", 55.0),
        ]
        positions = [
            {"date": "2026-09-04", "ticker": "AAA", "weight_pct": 60.0},
            {"date": "2026-09-04", "ticker": "BBB", "weight_pct": 40.0},
            {"date": "2026-09-05", "ticker": "AAA", "weight_pct": 61.0},
            {"date": "2026-09-05", "ticker": "BBB", "weight_pct": 39.0},
            {"date": "2026-09-08", "ticker": "AAA", "weight_pct": 60.0},
            {"date": "2026-09-08", "ticker": "BBB", "weight_pct": 40.0},
        ]
        nav = [
            {"date": "2026-09-04", "nav": 100.0},
            {"date": "2026-09-05", "nav": 100.0},
            {"date": "2026-09-08", "nav": 103.0},
        ]
        request, _closes, _recorded = _mod.build_request(rows, positions, nav)
        aaa = next(s for s in request.series if s.ticker == "AAA")
        bbb = next(s for s in request.series if s.ticker == "BBB")
        assert len(aaa.bars) == len(bbb.bars) == 3
        assert [str(b.ts.date()) for b in aaa.bars] == ["2026-09-04", "2026-09-05", "2026-09-08"]
        flat = aaa.bars[1]
        assert flat.close == aaa.bars[0].close
        assert flat.open == flat.high == flat.low == flat.close
        assert flat.volume == 0
        assert bbb.bars[1].close == bbb.bars[0].close

    def test_ticker_hole_on_a_book_date_forward_fills_last_close(self) -> None:
        rows = [
            self._price("2026-09-04", "AAA", 100.0),
            self._price("2026-09-08", "AAA", 110.0),
            self._price("2026-09-04", "BBB", 50.0),
            self._price("2026-09-05", "BBB", 51.0),
            self._price("2026-09-08", "BBB", 55.0),
        ]
        positions = [
            {"date": "2026-09-04", "ticker": "AAA", "weight_pct": 60.0},
            {"date": "2026-09-04", "ticker": "BBB", "weight_pct": 40.0},
            {"date": "2026-09-05", "ticker": "AAA", "weight_pct": 60.0},
            {"date": "2026-09-05", "ticker": "BBB", "weight_pct": 40.0},
            {"date": "2026-09-08", "ticker": "AAA", "weight_pct": 60.0},
            {"date": "2026-09-08", "ticker": "BBB", "weight_pct": 40.0},
        ]
        nav = [
            {"date": "2026-09-04", "nav": 100.0},
            {"date": "2026-09-05", "nav": 100.0},
            {"date": "2026-09-08", "nav": 103.0},
        ]
        request, _closes, _recorded = _mod.build_request(rows, positions, nav)
        aaa = next(s for s in request.series if s.ticker == "AAA")
        bbb = next(s for s in request.series if s.ticker == "BBB")
        assert aaa.bars[1].close == aaa.bars[0].close
        assert aaa.bars[1].volume == 0
        assert bbb.bars[1].close == Decimal("51.0")

    def test_ticker_without_a_bar_at_or_before_the_first_book_date_fails(self) -> None:
        rows = [
            self._price("2026-09-04", "AAA", 100.0),
            self._price("2026-09-05", "BBB", 50.0),
        ]
        positions = [
            {"date": "2026-09-04", "ticker": "AAA", "weight_pct": 60.0},
            {"date": "2026-09-04", "ticker": "BBB", "weight_pct": 40.0},
        ]
        nav = [{"date": "2026-09-04", "nav": 100.0}]
        with pytest.raises(ValueError, match="BBB"):
            _mod.build_request(rows, positions, nav)

    def test_first_book_date_fills_from_a_bar_before_the_grid(self) -> None:
        rows = [
            self._price("2026-09-04", "AAA", 100.0),
            self._price("2026-09-08", "AAA", 110.0),
        ]
        positions = [
            {"date": "2026-09-05", "ticker": "AAA", "weight_pct": 100.0},
            {"date": "2026-09-08", "ticker": "AAA", "weight_pct": 100.0},
        ]
        nav = [
            {"date": "2026-09-05", "nav": 100.0},
            {"date": "2026-09-08", "nav": 110.0},
        ]
        request, _closes, _recorded = _mod.build_request(rows, positions, nav)
        aaa = next(s for s in request.series if s.ticker == "AAA")
        assert [str(b.ts.date()) for b in aaa.bars] == ["2026-09-05", "2026-09-08"]
        seeded = aaa.bars[0]
        assert seeded.close == Decimal("100.0")
        assert seeded.open == seeded.high == seeded.low == seeded.close
        assert seeded.volume == 0

    def test_fetch_table_scopes_tickers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[Any] = []
        original_table = FakeSupabaseClient.table

        def spy_table(client: FakeSupabaseClient, name: str) -> Any:
            query = original_table(client, name)
            seen.append(query)
            return query

        monkeypatch.setattr(FakeSupabaseClient, "table", spy_table)
        rows = [
            self._price("2026-08-29", "AAA", 90.0),
            self._price("2026-09-01", "AAA", 100.0),
            self._price("2026-09-01", "BBB", 50.0),
            self._price("2026-09-01", "ZZZ", 10.0),
        ]
        sb = FakeSupabaseClient(canned_reads={"price_history": rows})
        out = _mod._fetch_table(
            sb,
            "price_history",
            "house-id",
            "date,ticker,open,high,low,close,volume",
            workspace_scoped=False,
            tickers=["AAA", "BBB"],
        )
        assert [(str(r["date"]), r["ticker"]) for r in out] == [
            ("2026-08-29", "AAA"),
            ("2026-09-01", "AAA"),
            ("2026-09-01", "BBB"),
        ]
        for query in seen:
            assert ("in_", "ticker", ["AAA", "BBB"]) in query._filters
            assert all(col != "workspace_id" for _op, col, _val in query._filters)


class TestFillDriftReserve:
    """Fully-invested books must keep a reserve for integer-lot / split-fill drift (#4005)."""

    @staticmethod
    def _price(date_: str, ticker: str, close: float) -> dict:
        return {
            "date": date_,
            "ticker": ticker,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1000,
        }

    def test_fully_invested_book_keeps_a_fill_drift_reserve(self) -> None:
        rows = [self._price("2026-09-01", "AAA", 100.0), self._price("2026-09-01", "BBB", 50.0)]
        positions = [
            {"date": "2026-09-01", "ticker": "AAA", "weight_pct": 60.0},
            {"date": "2026-09-01", "ticker": "BBB", "weight_pct": 40.0},
        ]
        nav = [{"date": "2026-09-01", "nav": 100.0}]
        request, _closes, _recorded = _mod.build_request(rows, positions, nav)
        total = sum(t.weight for entry in request.weight_schedule for t in entry.weights)
        assert total == Decimal("0.9975")

    def test_book_with_idle_cash_is_not_scaled(self) -> None:
        rows = [self._price("2026-09-01", "AAA", 100.0), self._price("2026-09-01", "BBB", 50.0)]
        positions = [
            {"date": "2026-09-01", "ticker": "AAA", "weight_pct": 60.0},
            {"date": "2026-09-01", "ticker": "BBB", "weight_pct": 30.0},
        ]
        nav = [{"date": "2026-09-01", "nav": 100.0}]
        request, _closes, _recorded = _mod.build_request(rows, positions, nav)
        total = sum(t.weight for entry in request.weight_schedule for t in entry.weights)
        assert total == Decimal("0.9")

    def test_rows_from_inception_drops_pre_cutover_books(self) -> None:
        rows = [
            {"date": "2026-06-23", "ticker": "OLD"},
            {"date": "2026-07-17", "ticker": "NEW"},
            {"date": "2026-09-01", "ticker": "NEW"},
        ]
        kept = _mod._rows_from_inception(rows, "2026-07-17")
        assert [r["date"] for r in kept] == ["2026-07-17", "2026-09-01"]
