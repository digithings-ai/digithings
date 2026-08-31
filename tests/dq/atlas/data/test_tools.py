from __future__ import annotations

import json
from unittest.mock import patch

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
        "get_fed_rate_probabilities",
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
def test_macro_obs_date_rewritten_from_date(monkeypatch):
    """Server-side rewrite: 'date' → 'obs_date' for macro_series_observations (#814).

    The LLM commonly sorts/filters by 'date' on this table (generic name) instead of
    'obs_date' (the real Postgres column). The dispatcher must silently correct it so
    the query returns data rather than a column-not-found error.
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
    # LLM sends 'order':'date' — should be silently rewritten to 'obs_date'.
    result = json.loads(
        dispatch(
            "query_data",
            {"table": "macro_series_observations", "eq": {"series_id": "DGS10"}, "order": "date"},
        )
    )
    assert len(result["rows"]) == 2


@pytest.mark.unit
def test_query_data_description_mentions_obs_date_not_date():
    """The tool description must advertise obs_date as the date column for macro_series_observations
    so the model learns the correct column name (#814)."""
    query_data_tool = next(t for t in DATA_TOOLS if t["function"]["name"] == "query_data")
    description = query_data_tool["function"]["description"]
    assert "obs_date" in description
    # The hint must be specific to macro_series_observations context.
    assert "macro_series_observations" in description


@pytest.mark.unit
def test_query_data_description_warns_no_close_in_price_technicals():
    """The tool description must warn that price_technicals has no 'close' column (#814)."""
    query_data_tool = next(t for t in DATA_TOOLS if t["function"]["name"] == "query_data")
    description = query_data_tool["function"]["description"]
    assert "price_history" in description
    assert "close" in description
    # Must guide the model to use price_history for OHLCV.
    assert "OHLCV" in description or "price_history" in description


class _FlakyTable:
    def __init__(self, rows: list[dict[str, object]], *, fails: int, err: Exception) -> None:
        self._rows = rows
        self._fails = fails
        self._err = err
        self.calls = 0
        self._f: dict[str, object] = {}

    def select(self, *a: object, **k: object) -> _FlakyTable:
        return self

    def eq(self, col: str, val: object) -> _FlakyTable:
        self._f[col] = val
        return self

    def in_(self, col: str, vals: object) -> _FlakyTable:
        self._f[col] = vals
        return self

    def order(self, *a: object, **k: object) -> _FlakyTable:
        return self

    def limit(self, n: int) -> _FlakyTable:
        return self

    def execute(self) -> object:
        self.calls += 1
        if self.calls <= self._fails:
            raise self._err
        return type("R", (), {"data": self._rows})


class _FlakyClient:
    def __init__(self, table: _FlakyTable) -> None:
        self._table = table

    def table(self, name: str) -> _FlakyTable:
        del name
        return self._table


@pytest.mark.unit
def test_dispatcher_retries_server_disconnect_then_succeeds() -> None:
    table = _FlakyTable(
        [{"series_id": "DFF", "obs_date": "2026-08-29", "value": 4.5}],
        fails=2,
        err=RuntimeError("Server disconnected without sending a response."),
    )
    dispatch = build_data_tool_dispatcher(_FlakyClient(table))
    with patch("digiquant.olympus.transient.time.sleep"):
        result = json.loads(dispatch("get_macro_series", {"series_ids": ["DFF"], "lookback": 3}))
    assert result["DFF"]["latest"]["value"] == 4.5
    assert table.calls == 3


@pytest.mark.unit
def test_dispatcher_returns_error_after_retries_exhausted() -> None:
    table = _FlakyTable(
        [],
        fails=5,
        err=RuntimeError("PGRST002: Could not query the database for the schema cache."),
    )
    dispatch = build_data_tool_dispatcher(_FlakyClient(table))
    with patch("digiquant.olympus.transient.time.sleep"):
        err = dispatch("get_macro_series", {"series_ids": ["DFF"]})
    assert err.startswith("Error:")
    assert "PGRST002" in err
    assert table.calls == 3
