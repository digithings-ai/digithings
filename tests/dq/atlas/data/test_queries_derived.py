"""Tests for the Pillar 1D data readers + the agent tool dispatcher.

These readers (raw prices, breadth, relative-strength, VIX term structure) are the
backends the research agents and PM call via DATA_TOOLS to ground claims in real
numbers — no pre-injected blobs.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from digiquant.olympus.atlas.data.queries import (
    get_market_breadth,
    get_price_history,
    get_sector_relative_strength,
    get_vix_term_structure,
)
from digiquant.olympus.atlas.data.tools import DATA_TOOLS, build_data_tool_dispatcher


class _FakeTable:
    def __init__(self, rows: list[dict]):
        self._rows = list(rows)
        self._eq: dict = {}
        self._in: dict = {}
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

    def gte(self, *a, **k):  # date filters are no-ops in the fake
        return self

    def lte(self, *a, **k):
        return self

    def order(self, *a, **k):
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
        ]
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
    def test_get_price_history(self) -> None:
        client = _FakeClient(
            {
                "price_history": [
                    {"date": "2026-06-15", "ticker": "SPY", "close": 110.0, "volume": 5},
                    {"date": "2026-06-12", "ticker": "SPY", "close": 100.0, "volume": 4},
                ]
            }
        )
        out = get_price_history(client=client, ticker="SPY", lookback=5)
        assert out["ticker"] == "SPY"
        assert out["latest"]["close"] == 110.0
        assert len(out["window"]) == 2

    def test_get_market_breadth(self) -> None:
        client = _FakeClient({"price_technicals": _breadth_rows()})
        out = get_market_breadth(client=client, run_date=date(2026, 6, 15))
        assert out["universe_size"] == 4
        assert out["pct_above_50dma"] == 75.0

    def test_get_market_breadth_empty(self) -> None:
        assert get_market_breadth(client=_FakeClient({}), run_date=date(2026, 6, 15)) == {}

    def test_get_sector_relative_strength(self) -> None:
        client = _FakeClient({"price_history": _rs_rows()})
        out = get_sector_relative_strength(
            client=client, run_date=date(2026, 6, 15), etfs=["XLK"], benchmark="SPY"
        )
        assert out["XLK"]["rs_21d"] is None or "rs_21d" in out["XLK"]  # default windows present
        # With the default (21,63,126) windows and only 4 rows, returns are None but
        # the ticker is still represented.
        assert "XLK" in out

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
class TestToolDispatcher:
    def test_new_tools_registered(self) -> None:
        names = {t["function"]["name"] for t in DATA_TOOLS}
        assert {
            "get_price_history",
            "get_market_breadth",
            "get_sector_relative_strength",
            "get_vix_term_structure",
        } <= names

    def test_dispatch_breadth_returns_json(self) -> None:
        client = _FakeClient({"price_technicals": _breadth_rows()})
        execute = build_data_tool_dispatcher(client)
        result = json.loads(execute("get_market_breadth", {}))
        assert result["universe_size"] == 4

    def test_dispatch_price_history(self) -> None:
        client = _FakeClient(
            {"price_history": [{"date": "2026-06-15", "ticker": "QQQ", "close": 1.0, "volume": 1}]}
        )
        execute = build_data_tool_dispatcher(client)
        result = json.loads(execute("get_price_history", {"ticker": "QQQ"}))
        assert result["ticker"] == "QQQ"

    def test_dispatch_unknown_tool(self) -> None:
        execute = build_data_tool_dispatcher(_FakeClient({}))
        assert "unknown tool" in execute("nope", {})
