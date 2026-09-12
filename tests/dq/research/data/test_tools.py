from __future__ import annotations

import json

import pytest
from digiquant.research.data.tools import DATA_TOOLS, build_data_tool_dispatcher

from tests.dq.research.data.test_queries import _FakeClient


@pytest.mark.unit
def test_tool_definitions_shape():
    names = {t["function"]["name"] for t in DATA_TOOLS}
    # get_price_technicals/get_price_history retired from the tool surface in favor of
    # the generic query_data reader; get_macro_series kept (per-series-latest across
    # mixed cadences, which query_data can't do without starving slow series).
    assert names == {
        "query_data",
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
    from datetime import date

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
    # Steers to the dedicated tools that own the reads.
    assert "get_macro_series" in description
    assert "digiquant_get_price_technicals" in description
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
