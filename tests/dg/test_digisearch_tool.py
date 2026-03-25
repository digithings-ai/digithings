"""Unit tests for DigiSearch orchestrator tool schemas and DigiGraph HTTP search helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from digigraph.tools.digisearch import digisearch, digisearch_fetch_all
from digisearch.orchestrator_tools import build_fetch_all_tool, build_search_tool


@pytest.mark.unit
def test_build_search_tool_default_when_no_config() -> None:
    """With no config, tool has name and required query param."""
    tool = build_search_tool({})
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "digisearch"
    assert "query" in (tool["function"]["parameters"]["properties"])
    assert "query" in tool["function"]["parameters"]["required"]


@pytest.mark.unit
def test_build_search_tool_description_includes_index_and_filterable() -> None:
    """With index config, description includes index name and filterable fields."""
    index_config = {
        "index_name": "unified-content-index",
        "filterable_fields": ["sourceType", "itemType", "fromAddress"],
        "result_metadata_fields": ["subject", "fromAddress"],
    }
    tool = build_search_tool(index_config)
    desc = tool["function"]["description"]
    assert "unified-content-index" in desc
    assert "sourceType" in desc
    assert "filterable" in desc.lower() or "Filterable" in desc
    assert "filters" in tool["function"]["parameters"]["properties"]


@pytest.mark.unit
def test_build_search_tool_filters_param_describes_filterable_fields() -> None:
    """Structured filters param description mentions filterable fields when config provided."""
    index_config = {
        "filterable_fields": ["sourceType", "itemType"],
    }
    tool = build_search_tool(index_config)
    filters_desc = tool["function"]["parameters"]["properties"]["filters"]["description"]
    assert "sourceType" in filters_desc
    assert "itemType" in filters_desc
    assert "eq" in filters_desc or "op" in filters_desc


@pytest.mark.unit
def test_build_search_tool_has_facets_order_by_skip_params() -> None:
    """Tool parameters include facets, order_by, skip, include_total_count."""
    tool = build_search_tool({})
    props = tool["function"]["parameters"]["properties"]
    assert "facets" in props
    assert "order_by" in props
    assert "skip" in props
    assert "include_total_count" in props


@pytest.mark.unit
def test_build_fetch_all_tool_has_required_query() -> None:
    """digisearch_fetch_all tool has name and required query."""
    tool = build_fetch_all_tool({})
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "digisearch_fetch_all"
    assert tool["function"]["parameters"]["required"] == ["query"]
    assert "filter" in tool["function"]["parameters"]["properties"]
    assert "filters" in tool["function"]["parameters"]["properties"]


@pytest.mark.unit
def test_digisearch_post_sends_x_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://example.test:8002")
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": [], "total": 0, "query": "q", "index_name": "default"}
    mock_response.raise_for_status = MagicMock()
    inner = MagicMock()
    inner.post.return_value = mock_response
    inner.is_closed = False
    with patch("digigraph.tools.digisearch._get_sync_client", return_value=inner):
        digisearch("hello", request_id="rid-42")
    inner.post.assert_called_once()
    hdrs = inner.post.call_args[1]["headers"]
    assert hdrs.get("X-Request-ID") == "rid-42"


@pytest.mark.unit
def test_digisearch_fetch_all_pagination_mock() -> None:
    """fetch_all loops until no more results or total reached."""
    with patch("digigraph.tools.digisearch.digisearch") as mock_digisearch:
        mock_digisearch.side_effect = [
            {"results": [{"id": "1"}, {"id": "2"}], "total": 4},
            {"results": [{"id": "3"}, {"id": "4"}], "total": 4},
            {"results": [], "total": 4},
        ]
        out = digisearch_fetch_all("test", index_name="idx", page_size=2)
        assert out is not None
        assert len(out["results"]) == 4
        assert out["total"] == 4
        assert mock_digisearch.call_count == 2


@pytest.mark.unit
def test_digisearch_fetch_all_respects_max_results() -> None:
    """fetch_all caps at max_results when set."""
    with patch("digigraph.tools.digisearch.digisearch") as mock_digisearch:
        mock_digisearch.return_value = {"results": [{"id": "1"}, {"id": "2"}, {"id": "3"}], "total": 10}
        out = digisearch_fetch_all("q", index_name="idx", page_size=3, max_results=5)
        assert out is not None
        assert len(out["results"]) == 5
        assert out["total"] == 5
