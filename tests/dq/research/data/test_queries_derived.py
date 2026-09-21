"""Tests for the Pillar 1D data readers + the agent tool dispatcher.

These readers (raw prices, breadth, relative-strength, VIX term structure) are the
backends the research agents and PM call via DATA_TOOLS to ground claims in real
numbers — no pre-injected blobs. The generic raw-table reader (``query_data``) was
retired in #4436 and folded into the dashboard ``query_research`` tool.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from digiquant.research.data.queries import (
    ALLOWED_READ_TABLES,
    HOUSE_BOOK_READ_TABLES,
    get_market_breadth,
    get_sector_relative_strength,
    get_vix_term_structure,
)
from digiquant.research.data.tools import DATA_TOOLS, build_data_tool_dispatcher

_ARCHITECTURE_MD = Path(__file__).resolve().parents[4] / "digiquant" / "ARCHITECTURE.md"


class _FakeTable:
    def __init__(self, rows: list[dict]):
        self._rows = list(rows)
        self._eq: dict = {}
        self._in: dict = {}
        self._gte: dict = {}
        self._lte: dict = {}
        self._n: int | None = None
        self._range: tuple[int, int] | None = None

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def in_(self, col, vals):
        self._in[col] = set(vals)
        return self

    def gte(self, col, val):
        self._gte[col] = val
        return self

    def lte(self, col, val):
        self._lte[col] = val
        return self

    def order(self, col=None, desc=False, **k):
        self._order = (col, desc) if col is not None else None
        return self

    def limit(self, n):
        self._n = n
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        rows = [
            r
            for r in self._rows
            if all(r.get(c) == v for c, v in self._eq.items())
            and all(r.get(c) in s for c, s in self._in.items())
            and all(str(r.get(c)) >= str(v) for c, v in self._gte.items())
            and all(str(r.get(c)) <= str(v) for c, v in self._lte.items())
        ]
        order = getattr(self, "_order", None)
        if order is not None:
            col, desc = order
            rows = sorted(rows, key=lambda r: str(r.get(col)), reverse=desc)
        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]
        elif self._n is not None:
            rows = rows[: self._n]
        return type("R", (), {"data": rows})


class _FakeClient:
    def __init__(self, tables: dict[str, list[dict]]):
        self._t = tables

    def table(self, name: str):
        return _FakeTable(self._t.get(name, []))


def _breadth_rows() -> list[dict]:
    return [
        {"ticker": t, "date": "2026-06-15", "pct_vs_sma50": v, "pct_vs_sma200": v}
        for t, v in (("A", 1.0), ("B", 1.0), ("C", 1.0), ("D", -1.0))
    ]


def _rs_rows() -> list[dict]:
    dates = ["2026-06-10", "2026-06-11", "2026-06-12", "2026-06-15"]
    series = {"SPY": [100, 100, 100, 110], "XLK": [100, 100, 100, 121]}
    return [
        {"date": d, "ticker": t, "close": float(c)}
        for t, closes in series.items()
        for d, c in zip(dates, closes)
    ]


@pytest.mark.unit
class TestReaders:
    def test_get_market_breadth(self) -> None:
        client = _FakeClient({"price_technicals": _breadth_rows()})
        out = get_market_breadth(client=client, run_date=date(2026, 6, 15))
        assert out["universe_size"] == 4
        assert out["pct_above_50dma"] == 75.0

    def test_get_market_breadth_empty(self) -> None:
        # Empty universe returns the stamped-empty shape (universe_size always present),
        # not a bare {} — consistent with compute_breadth + the breadth contract (#1011).
        assert get_market_breadth(client=_FakeClient({}), run_date=date(2026, 6, 15)) == {
            "as_of": "2026-06-15",
            "universe_size": 0,
        }

    def test_get_sector_relative_strength(self) -> None:
        client = _FakeClient({"price_history": _rs_rows()})
        out = get_sector_relative_strength(
            client=client, run_date=date(2026, 6, 15), etfs=["XLK"], benchmark="SPY"
        )
        # Default (21,63,126) windows; only 4 rows of history → the 21-day key exists
        # but its value is None (not enough history). The ticker is still represented.
        assert "XLK" in out
        assert "rs_21d" in out["XLK"]
        assert out["XLK"]["rs_21d"] is None

    def test_vix_backwardation(self) -> None:
        client = _FakeClient(
            {
                "macro_series_observations": [
                    {"series_id": "VIXCLS", "obs_date": "2026-06-15", "value": 30.0, "unit": "idx"},
                    {"series_id": "VXVCLS", "obs_date": "2026-06-15", "value": 25.0, "unit": "idx"},
                ]
            }
        )
        out = get_vix_term_structure(client=client, run_date=date(2026, 6, 15))
        assert out["state"] == "backwardation"
        assert out["ratio"] == 1.2

    def test_vix_respects_as_of_lookahead(self) -> None:
        # A future-dated obs must be excluded for an as-of read (look-ahead guard).
        client = _FakeClient(
            {
                "macro_series_observations": [
                    {"series_id": "VIXCLS", "obs_date": "2026-06-20", "value": 99.0, "unit": "idx"},
                    {"series_id": "VIXCLS", "obs_date": "2026-06-15", "value": 20.0, "unit": "idx"},
                    {"series_id": "VXVCLS", "obs_date": "2026-06-15", "value": 22.0, "unit": "idx"},
                ]
            }
        )
        out = get_vix_term_structure(client=client, run_date=date(2026, 6, 15))
        assert out["vix"] == 20.0  # not the future 99.0
        assert out["state"] == "contango"  # 20 < 22

    def test_vix_missing_series_returns_empty(self) -> None:
        client = _FakeClient(
            {
                "macro_series_observations": [
                    {"series_id": "VIXCLS", "obs_date": "2026-06-15", "value": 18.0, "unit": "idx"},
                ]
            }
        )
        assert get_vix_term_structure(client=client, run_date=date(2026, 6, 15)) == {}


@pytest.mark.unit
class TestQueryDataRetired:
    """#4436: the generic raw-table reader is gone.

    ``query_data`` (raw table/columns/filters) was folded into the dashboard
    ``query_research`` research tool, which owns filtered reads over the book,
    research documents, and portfolio tables. The generic reader, its raw-table
    MCP tool, and its relationship-syntax defence surface were all removed.
    """

    def test_query_data_is_not_importable(self) -> None:
        import digiquant.research.data.queries as q

        assert not hasattr(q, "query_data")

    def test_no_raw_table_reader_on_the_data_surface(self) -> None:
        # The dispatcher must not route a raw-table reader any more.
        execute = build_data_tool_dispatcher(_FakeClient({}))
        assert "unknown tool" in execute("query_data", {"table": "theses"})

    def test_whitelist_excludes_operator_tables(self) -> None:
        assert "decision_log" not in ALLOWED_READ_TABLES
        assert "atlas_run_diagnostics" not in ALLOWED_READ_TABLES
        assert {"positions", "theses", "trading_calendar"} <= ALLOWED_READ_TABLES

    def test_whitelist_excludes_r2_cutover_market_tables(self) -> None:
        # #3780 Task 7: market history is served from the R2 cache, never via
        # a generic reader — the MCP price/macro tools own those reads now.
        from digiquant.research.data.queries import MARKET_TABLES_REMOVED

        assert set(MARKET_TABLES_REMOVED) == {
            "price_history",
            "price_technicals",
            "macro_series_observations",
        }
        for table in MARKET_TABLES_REMOVED:
            assert table not in ALLOWED_READ_TABLES

    def test_group_a_tables_are_positions_nav_events_metrics(self) -> None:
        assert HOUSE_BOOK_READ_TABLES == frozenset(
            {"positions", "nav_history", "position_events", "portfolio_metrics"}
        )
        assert "theses" not in HOUSE_BOOK_READ_TABLES
        assert "price_history" not in HOUSE_BOOK_READ_TABLES

    def test_dead_market_column_allowlist_machinery_is_deleted(self) -> None:
        # #3780 removed price_history/price_technicals from ALLOWED_READ_TABLES,
        # so the #3771 per-table column allowlist could never run. The dead
        # machinery must be deleted, not kept as a half-built "defensive choke"
        # no test reaches (#3959).
        import digiquant.research.data.queries as q

        for name in (
            "PRICE_HISTORY_COLUMNS",
            "PRICE_TECHNICALS_COLUMNS",
            "_TABLE_COLUMN_ALLOWLISTS",
            "_OHLCV_COLUMNS",
            "_TECHNICAL_INDICATOR_COLUMNS",
            "_referenced_query_columns",
            "_column_allowlist_error",
            "_validate_table_columns",
        ):
            assert not hasattr(q, name), f"{name} is unreachable dead code; delete it (#3959)"

    def test_architecture_no_longer_claims_the_dead_choke_is_live(self) -> None:
        # ARCHITECTURE.md claimed the #3771 per-table column allowlists were
        # "retained in code as a defensive choke, and covered directly by unit
        # tests" — false on both counts after #3780. Pin the correction (#3959).
        text = _ARCHITECTURE_MD.read_text(encoding="utf-8")
        assert "defensive choke" not in text
        assert "covered directly by unit tests" not in text


@pytest.mark.unit
class TestToolDispatcher:
    def test_new_tools_registered(self) -> None:
        names = {t["function"]["name"] for t in DATA_TOOLS}
        assert {
            "get_price_technicals",
            "get_macro_series",
            "get_market_breadth",
            "get_sector_relative_strength",
            "get_vix_term_structure",
        } <= names
        # The generic raw-table reader folded into query_research (#4436).
        assert "query_data" not in names

    def test_dispatch_breadth_returns_json(self) -> None:
        # Pin run_date to the fixture's date so the breadth window includes the rows
        # regardless of today (previously defaulted to date.today() — a time-bomb that
        # broke once today drifted >7 days past the fixture, #1011).
        client = _FakeClient({"price_technicals": _breadth_rows()})
        execute = build_data_tool_dispatcher(client, run_date=date(2026, 6, 15))
        result = json.loads(execute("get_market_breadth", {}))
        assert result["universe_size"] == 4

    def test_dispatch_breadth_no_rows_returns_stamped_universe_size(self) -> None:
        # No price_technicals in window → stamped-empty shape (universe_size: 0),
        # never a bare {} that KeyErrors on universe_size downstream (#1011).
        client = _FakeClient({"price_technicals": []})
        execute = build_data_tool_dispatcher(client, run_date=date(2026, 6, 15))
        result = json.loads(execute("get_market_breadth", {}))
        assert result["universe_size"] == 0

    def test_dispatch_query_data_retired(self) -> None:
        # #4436: the raw-table reader is gone; the dispatcher reports it as unknown
        # rather than ever reaching Supabase for a raw `table` scan.
        client = _FakeClient({"price_history": [{"ticker": "QQQ"}]})
        execute = build_data_tool_dispatcher(client)
        for table in ("price_history", "price_technicals", "macro_series_observations"):
            result = execute("query_data", {"table": table, "eq": {"ticker": "QQQ"}})
            assert "unknown tool" in result.lower()

    def test_dispatch_unknown_tool(self) -> None:
        execute = build_data_tool_dispatcher(_FakeClient({}))
        assert "unknown tool" in execute("nope", {})
