from __future__ import annotations

import json

import pytest

from digiquant.olympus.atlas.data.tools import DATA_TOOLS, build_data_tool_dispatcher
from tests.dq.atlas.data.test_queries import _FakeClient


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
    }
    for t in DATA_TOOLS:
        assert t["type"] == "function"
        assert "parameters" in t["function"]


@pytest.mark.unit
def test_coerce_bool_handles_string_args():
    from digiquant.olympus.atlas.data.tools import _coerce_bool

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
            "price_technicals": [{"ticker": "SPY", "date": "2026-06-08", "rsi_14": 55.0}],
            "macro_series_observations": [
                {"series_id": "DFF", "obs_date": "2026-06-07", "value": 4.5}
            ],
        }
    )
    dispatch = build_data_tool_dispatcher(client)
    pt = json.loads(dispatch("query_data", {"table": "price_technicals", "eq": {"ticker": "SPY"}}))
    assert pt["rows"][0]["rsi_14"] == 55.0
    mc = json.loads(dispatch("get_macro_series", {"series_ids": ["DFF"], "lookback": 3}))
    assert mc["DFF"]["latest"]["value"] == 4.5
    err = dispatch("nonexistent_tool", {})
    assert "unknown tool" in err.lower()
