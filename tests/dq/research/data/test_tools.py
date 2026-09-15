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
    # get_price_history stays retired (query_data never served OHLCV), but
    # get_price_technicals is back on the in-process surface after #3780 moved
    # market history out of query_data: the skills must call a tool the
    # dispatcher actually handles, not the MCP-only `digiquant_`-prefixed name.
    assert names == {
        "query_data",
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
def test_coerce_bool_handles_string_args():
    from digiquant.research.data.tools import _coerce_bool

    assert _coerce_bool(True) is True
    assert _coerce_bool(False) is False
    # Tool args sometimes arrive as strings — "false" must not become True.
    assert _coerce_bool("false") is False
    assert _coerce_bool("0") is False
    assert _coerce_bool("no") is False
    assert _coerce_bool("true") is True
    assert _coerce_bool(None, default=True) is True
    assert _coerce_bool(None, default=False) is False


@pytest.mark.unit
def test_dispatcher_routes_and_returns_json_string():
    client = _FakeClient(
        {
            "theses": [{"ticker": "SPY", "date": "2026-06-08", "thesis_id": "t1"}],
            "macro_series_observations": [
                {"series_id": "DFF", "obs_date": "2026-06-07", "value": 4.5}
            ],
        }
    )
    dispatch = build_data_tool_dispatcher(client)
    pt = json.loads(dispatch("query_data", {"table": "theses", "eq": {"ticker": "SPY"}}))
    assert pt["rows"][0]["thesis_id"] == "t1"
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
def test_query_data_missing_table_returns_actionable_error():
    """'table' missing from args must return a helpful error string, not KeyError (#814)."""
    client = _FakeClient({})
    dispatch = build_data_tool_dispatcher(client)
    # Simulate LLM calling query_data without the required 'table' key.
    err = dispatch("query_data", {})
    assert "table" in err.lower()
    assert "Error" in err
    # Must not raise — errors are returned to the model as a tool result.


@pytest.mark.unit
def test_query_data_table_none_returns_actionable_error():
    """table=None (e.g. model passes null) must also return an error, not crash (#814)."""
    client = _FakeClient({})
    dispatch = build_data_tool_dispatcher(client)
    err = dispatch("query_data", {"table": None})
    assert "table" in err.lower()
    assert "Error" in err


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
def test_macro_query_data_refused_post_cutover(monkeypatch):
    """query_data no longer serves macro_series_observations (#3780, Task 7).

    The per-series-latest read the old 'date'→'obs_date' rewrite supported now
    lives exclusively behind the get_macro_series tool (which takes series_ids
    directly and needs no column rewrite).
    """
    client = _FakeClient(
        {
            "macro_series_observations": [
                {"series_id": "DGS10", "obs_date": "2026-06-07", "value": 4.3},
                {"series_id": "DGS10", "obs_date": "2026-06-06", "value": 4.2},
            ],
        }
    )
    dispatch = build_data_tool_dispatcher(client)
    result = json.loads(
        dispatch(
            "query_data",
            {"table": "macro_series_observations", "eq": {"series_id": "DGS10"}, "order": "date"},
        )
    )
    assert "error" in result and "not readable" in result["error"]


@pytest.mark.unit
def test_query_data_description_refuses_market_history_and_steers_to_dedicated_tools():
    """#3951: the description must not advertise market tables query_data refuses.

    ``price_history`` / ``price_technicals`` / ``macro_series_observations`` left
    the generic reader for the R2 cache (#3780), so naming them as queryable —
    or showing `table:'…'` examples — sends the model into a refusal.
    """
    query_data_tool = next(t for t in DATA_TOOLS if t["function"]["name"] == "query_data")
    description = query_data_tool["function"]["description"]
    # Named, but only to say they are NOT readable here.
    assert "price_history" in description
    assert "macro_series_observations" in description
    assert "NOT readable" in description
    # Steers to the dedicated tools that own the reads. The price tool must be
    # the in-process `get_price_technicals` the dispatcher handles — not the
    # MCP-only `digiquant_get_price_technicals` the research graph can't call.
    assert "get_macro_series" in description
    assert "get_price_technicals" in description
    assert "digiquant_get_price_technicals" not in description
    # No stale examples that would make the model call the refused tables.
    assert "table:'price_technicals'" not in description
    assert "table:'price_history'" not in description
    assert "table:'macro_series_observations'" not in description


@pytest.mark.unit
def test_query_data_description_mentions_house_workspace_default():
    """Agents must learn Group A books default to house, not an unfiltered scan."""
    query_data_tool = next(t for t in DATA_TOOLS if t["function"]["name"] == "query_data")
    description = query_data_tool["function"]["description"]
    assert "house workspace_id" in description
    assert "eq.workspace_id" in description


@pytest.mark.unit
def test_price_technicals_close_rejected_before_supabase():
    """Requesting 'close' from price_technicals must fail fast with a redirect (#3771).

    Guard lives in ``query_data`` (shared with MCP), not only the dispatcher.
    """

    class _ExplodingClient:
        def table(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("must not reach Supabase")

    dispatch = build_data_tool_dispatcher(_ExplodingClient())  # type: ignore[arg-type]
    err = json.loads(
        dispatch(
            "query_data",
            {"table": "price_technicals", "columns": "date,close,rsi_14", "eq": {"ticker": "SPY"}},
        )
    )
    # Merged-tree behavior (#3780 cutover): generic query_data no longer
    # serves market tables at all (table-level refusal), so the #3771
    # column allowlist never sees this call. Dedicated price tools serve it.
    assert "error" in err
    assert "not readable" in err["error"]
    assert "price_technicals" in err["error"]


@pytest.mark.unit
def test_query_data_description_warns_no_technicals_on_price_history():
    """Retired-table drift guard: no sma_/price_technicals query hints survive (#3951)."""
    query_data_tool = next(t for t in DATA_TOOLS if t["function"]["name"] == "query_data")
    description = query_data_tool["function"]["description"]
    # price_technicals may only appear to say it is not readable here.
    assert "price_technicals" in description
    assert "NOT readable" in description
    assert "sma_" not in description
