"""Unit tests for DigiGraph DigiSearch tool (build_search_tool, index config in description)."""

from __future__ import annotations

import pytest

from digigraph.tools.digisearch import build_search_tool


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
