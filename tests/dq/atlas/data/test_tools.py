from __future__ import annotations

import json

import pytest

from digiquant.olympus.atlas.data.tools import DATA_TOOLS, build_data_tool_dispatcher
from tests.dq.atlas.data.test_queries import _FakeClient


@pytest.mark.unit
def test_tool_definitions_shape():
    names = {t["function"]["name"] for t in DATA_TOOLS}
    assert names == {
        "get_price_technicals",
        "get_macro_series",
        "get_price_history",
        "get_market_breadth",
        "get_sector_relative_strength",
        "get_vix_term_structure",
    }
    for t in DATA_TOOLS:
        assert t["type"] == "function"
        assert "parameters" in t["function"]


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
    pt = json.loads(dispatch("get_price_technicals", {"ticker": "SPY", "lookback": 5}))
    assert pt["latest"]["rsi_14"] == 55.0
    mc = json.loads(dispatch("get_macro_series", {"series_ids": ["DFF"], "lookback": 3}))
    assert mc["DFF"]["latest"]["value"] == 4.5
    err = dispatch("nonexistent_tool", {})
    assert "unknown tool" in err.lower()
