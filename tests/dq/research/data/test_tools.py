from __future__ import annotations

import json
from datetime import date

import pytest
from digiquant.research.data.tools import DATA_TOOLS, build_data_tool_dispatcher

from tests.dq.research.data.test_queries import _FakeClient

# Registers Task 1's `r2_market` builder fixture for this module; pytest requires
# plugin modules to be named here rather than imported (an imported fixture would
# collide with the fixture-name parameters below under ruff F811).
pytest_plugins = ["tests.fixtures.r2_market"]


@pytest.mark.unit
def test_tool_definitions_shape():
    names = {t["function"]["name"] for t in DATA_TOOLS}
    # get_price_history stays retired, and the generic raw-table reader
    # query_data was folded into the dashboard research tool (#4436), but
    # get_price_technicals remains on the in-process surface after #3780 moved
    # market history off the generic reader: the skills must call a tool the
    # dispatcher actually handles, not the MCP-only `digiquant_`-prefixed name.
    assert names == {
        "get_price_technicals",
        "get_macro_series",
        "get_market_breadth",
        "get_sector_relative_strength",
        "get_vix_term_structure",
        "get_etf_flows_proxy",
        "get_fed_rate_probabilities",
    }
    for t in DATA_TOOLS:
        assert t["type"] == "function"
        assert "parameters" in t["function"]


@pytest.mark.unit
def test_dispatcher_routes_and_returns_json_string():
    client = _FakeClient(
        {
            "macro_series_observations": [
                {"series_id": "DFF", "obs_date": "2026-06-07", "value": 4.5}
            ],
        }
    )
    dispatch = build_data_tool_dispatcher(client)
    mc = json.loads(dispatch("get_macro_series", {"series_ids": ["DFF"], "lookback": 3}))
    assert mc["DFF"]["latest"]["value"] == 4.5
    err = dispatch("nonexistent_tool", {})
    assert "unknown tool" in err.lower()


@pytest.mark.unit
def test_dispatcher_routes_get_price_technicals(r2_market):
    """The in-process price-technicals tool is dispatched, not rejected (#3972).

    The research/portfolio skills execute against DATA_TOOLS, so pointing them
    at the MCP-only `digiquant_get_price_technicals` produced
    ``Error: unknown tool``. This pins the unprefixed in-process name. The rows
    come from the sealed R2 generation (#4053) — no Supabase market body.
    """
    r2_market(
        {
            "SPY": [
                {
                    "date": "2026-06-05",
                    "open": 99.0,
                    "high": 101.0,
                    "low": 98.0,
                    "close": 100.0,
                    "volume": 1000,
                },
                {
                    "date": "2026-06-08",
                    "open": 100.0,
                    "high": 102.0,
                    "low": 99.0,
                    "close": 101.0,
                    "volume": 1100,
                },
            ]
        },
        as_of="2026-06-08",
    )
    # run_date == the seal keeps the R2 read sealed (an as_of past the seal would
    # trigger the live overlap fetch).
    dispatch = build_data_tool_dispatcher(_FakeClient({}), run_date=date(2026, 6, 8))
    out = json.loads(dispatch("get_price_technicals", {"ticker": "SPY", "lookback": 2}))
    assert out["ticker"] == "SPY"
    assert [row["date"] for row in out["window"]] == ["2026-06-08", "2026-06-05"]
    assert len(out["window"]) == 2


@pytest.mark.unit
def test_dispatcher_get_price_technicals_missing_ticker_is_actionable_error():
    """Missing ticker returns an Error string, not a KeyError/unknown-tool (#814)."""
    dispatch = build_data_tool_dispatcher(_FakeClient({}))
    err = dispatch("get_price_technicals", {})
    assert "Error" in err
    assert "ticker" in err.lower()


@pytest.mark.unit
def test_query_data_is_retired():
    """#4436: the generic raw-table reader folded into the research tool.

    ``query_data`` must no longer be advertised or dispatched on the research
    data surface — the dashboard ``query_research`` tool owns filtered reads.
    """
    names = {t["function"]["name"] for t in DATA_TOOLS}
    assert "query_data" not in names
    dispatch = build_data_tool_dispatcher(_FakeClient({}))
    err = dispatch("query_data", {"table": "theses"})
    assert "unknown tool" in err.lower()


@pytest.mark.unit
def test_dispatcher_macro_series_anchored_to_run_date():
    """The dispatcher threads its run_date as as_of (look-ahead-safe backfills)."""
    client = _FakeClient(
        {
            "macro_series_observations": [
                {"series_id": "DFF", "obs_date": "2026-06-01", "value": 4.4},
                {"series_id": "DFF", "obs_date": "2026-06-10", "value": 4.5},
            ],
        }
    )
    dispatch = build_data_tool_dispatcher(client, run_date=date(2026, 6, 5))
    mc = json.loads(dispatch("get_macro_series", {"series_ids": ["DFF"], "lookback": 5}))
    assert mc["DFF"]["latest"]["obs_date"] == "2026-06-01"
    assert len(mc["DFF"]["window"]) == 1


@pytest.mark.unit
def test_data_tools_have_no_raw_table_reader():
    """No data tool advertises a raw table/columns surface (#4436).

    The retired ``query_data`` was the only raw reader; every surviving data
    tool is a typed reader (macro/technicals/breadth/…). Guards against the
    generic reader creeping back onto the in-process surface.
    """
    for tool in DATA_TOOLS:
        params = tool["function"]["parameters"].get("properties", {})
        assert "table" not in params, tool["function"]["name"]
        assert "columns" not in params, tool["function"]["name"]
