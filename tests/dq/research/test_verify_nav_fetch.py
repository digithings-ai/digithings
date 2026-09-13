"""Unit tests for ``verify_nav_replay._fetch_table`` stable pagination (#3803).

``_fetch_table`` must page over a deterministic ``(date, ticker)`` order with
a last-seen-key cursor (never an offset), so a concurrent book upsert between
pages can neither shift rows out of the series nor duplicate them into the
weight schedule that ``--write`` persists as truth. A truncated or unstable
page must raise — never return a partial series.

The script is loaded via importlib like the other script-level tests
(``digiquant/scripts`` are not installed packages).
"""

from __future__ import annotations

import importlib.util
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


class TestOrNullWorkspaceKeyset:
    def test_house_and_null_workspace_rows_page_across_the_keyset(self) -> None:
        """The combined workspace-or-null + keyset ``or`` must not drop either branch.

        ``price_history`` is fetched with ``or_null_workspace=True`` (omitted
        workspace_id = house). The seek has to be ANDed inside *both* workspace
        branches, so this pins that house and NULL rows page together.
        """
        house = "house-id"
        rows = [
            {"date": "2026-09-01", "ticker": "SPY", "close": 1.0, "workspace_id": house},
            {"date": "2026-09-01", "ticker": "TLT", "close": 2.0, "workspace_id": None},
            {"date": "2026-09-02", "ticker": "SPY", "close": 3.0, "workspace_id": house},
            {"date": "2026-09-02", "ticker": "TLT", "close": 4.0, "workspace_id": None},
            {"date": "2026-09-03", "ticker": "SPY", "close": 5.0, "workspace_id": house},
        ]
        sb = FakeSupabaseClient(canned_reads={"price_history": rows})
        out = _mod._fetch_table(
            sb,
            "price_history",
            house,
            "date,ticker,close",
            or_null_workspace=True,
            page_size=2,
        )
        assert [(r["date"], r["ticker"]) for r in out] == [
            ("2026-09-01", "SPY"),
            ("2026-09-01", "TLT"),
            ("2026-09-02", "SPY"),
            ("2026-09-02", "TLT"),
            ("2026-09-03", "SPY"),
        ]


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
