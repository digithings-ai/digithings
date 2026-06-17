"""Unit tests for digigraph.tools.data_query — column hints and guards (#814)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from digigraph.tools.data_query import (
    DATA_QUERY_TOOL,
    _TABLE_HINTS,
    _rewrite_col_alias,
    handle_query_data,
)


@pytest.mark.unit
class TestDataQueryToolSchema:
    """The tool schema must embed column hints so the LLM picks correct names."""

    def test_tool_has_name_query_data(self) -> None:
        assert DATA_QUERY_TOOL["function"]["name"] == "query_data"

    def test_description_mentions_obs_date_for_macro_series(self) -> None:
        desc = DATA_QUERY_TOOL["function"]["description"]
        assert "obs_date" in desc
        assert "macro_series_observations" in desc

    def test_description_warns_price_technicals_has_no_close(self) -> None:
        desc = DATA_QUERY_TOOL["function"]["description"]
        assert "price_technicals" in desc
        # Must mention that price_technicals lacks 'close'
        assert "close" in desc.lower()
        assert "price_history" in desc

    def test_table_parameter_is_required(self) -> None:
        required = DATA_QUERY_TOOL["function"]["parameters"].get("required", [])
        assert "table" in required

    def test_table_hints_cover_key_tables(self) -> None:
        for table in ("macro_series_observations", "price_history", "price_technicals"):
            assert table in _TABLE_HINTS, f"Missing hint for {table}"


@pytest.mark.unit
class TestHandleQueryDataMissingTable:
    """Missing or blank 'table' must return an actionable error, not raise KeyError."""

    def test_missing_table_returns_error(self) -> None:
        result = handle_query_data({})
        assert "error" in result
        assert "table" in result["error"].lower()

    def test_none_table_returns_error(self) -> None:
        result = handle_query_data({"table": None})
        assert "error" in result

    def test_whitespace_table_returns_error(self) -> None:
        result = handle_query_data({"table": "  "})
        assert "error" in result

    def test_error_lists_available_tables(self) -> None:
        result = handle_query_data({})
        assert "macro_series_observations" in result["error"]


@pytest.mark.unit
class TestRewriteColAlias:
    """_rewrite_col_alias rewrites standalone 'date' to 'obs_date' in SELECT lists."""

    def test_rewrites_bare_date(self) -> None:
        assert _rewrite_col_alias("date, value", "date", "obs_date", "t") == "obs_date, value"

    def test_does_not_rewrite_update_date(self) -> None:
        """'update_date' contains 'date' as a substring — must not be rewritten."""
        result = _rewrite_col_alias("update_date, value", "date", "obs_date", "t")
        assert result == "update_date, value"

    def test_rewrites_date_in_star_select(self) -> None:
        # '*' has no 'date' token — must pass through unchanged.
        assert _rewrite_col_alias("*", "date", "obs_date", "t") == "*"

    def test_rewrites_multiple_occurrences(self) -> None:
        result = _rewrite_col_alias("date, obs_date, date", "date", "obs_date", "t")
        # Both bare 'date' tokens are rewritten; 'obs_date' is not a bare 'date'.
        assert result.count("obs_date") >= 2


@pytest.mark.unit
class TestHandleQueryDataColumnRewrite:
    """Server-side alias rewrite for macro_series_observations (#814)."""

    def _make_mock_client(self, rows: list) -> MagicMock:
        result = MagicMock()
        result.data = rows
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.execute.return_value = result
        client = MagicMock()
        client.table.return_value = chain
        return client

    def test_date_column_rewritten_in_select_for_macro_series(self) -> None:
        """'date' in column list is silently rewritten to 'obs_date' (#814)."""
        mock_client = self._make_mock_client([{"obs_date": "2026-06-10", "value": 1.5}])
        with patch(
            "digigraph.tools.data_query._get_supabase_client",
            return_value=mock_client,
        ):
            result = handle_query_data(
                {"table": "macro_series_observations", "columns": "date, value"}
            )
        assert "error" not in result
        assert result["table"] == "macro_series_observations"
        # Verify the SELECT was called with obs_date, not date.
        chain = mock_client.table.return_value
        select_call_args = chain.select.call_args[0][0]
        assert "obs_date" in select_call_args
        assert select_call_args.count("obs_date") >= 1

    def test_filter_date_key_rewritten_to_obs_date(self) -> None:
        """Filter key 'date' is rewritten to 'obs_date' for macro_series_observations."""
        mock_client = self._make_mock_client([])
        with patch(
            "digigraph.tools.data_query._get_supabase_client",
            return_value=mock_client,
        ):
            handle_query_data(
                {
                    "table": "macro_series_observations",
                    "columns": "*",
                    "filters": {"date": "2026-06-10"},
                }
            )
        chain = mock_client.table.return_value
        # eq() must have been called with 'obs_date', not 'date'.
        eq_calls = [str(call) for call in chain.eq.call_args_list]
        assert any("obs_date" in c for c in eq_calls), f"eq calls: {eq_calls}"

    def test_supabase_not_available_returns_error(self) -> None:
        """Missing supabase package returns a clean error, not an ImportError traceback."""
        with patch(
            "digigraph.tools.data_query._get_supabase_client",
            side_effect=RuntimeError("supabase package not installed"),
        ):
            result = handle_query_data({"table": "positions"})
        assert "error" in result
        assert "supabase" in result["error"].lower()

    def test_returns_rows_and_count(self) -> None:
        rows = [{"ticker": "SPY", "as_of": "2026-06-10", "weight": 0.4}]
        mock_client = self._make_mock_client(rows)
        with patch(
            "digigraph.tools.data_query._get_supabase_client",
            return_value=mock_client,
        ):
            result = handle_query_data({"table": "positions"})
        assert result["count"] == 1
        assert result["rows"] == rows
        assert result["table"] == "positions"
