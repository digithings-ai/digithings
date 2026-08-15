"""Unit tests for digisearch orchestrator tool schemas and digigraph HTTP search helpers."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterator
from unittest.mock import MagicMock, patch

import httpx
import pytest
from digigraph.tools.digisearch import digisearch, digisearch_fetch_all
from digisearch.orchestrator_tools import build_fetch_all_tool, build_search_tool


@pytest.fixture(autouse=True)
def _reset_legacy_digisearch_breaker() -> Iterator[None]:
    """Module-level CircuitBreaker singleton — reset so order can't leak OPEN state.

    Use importlib: ``digigraph.tools.__init__`` re-exports the ``digisearch``
    function, which shadows the submodule on attribute access.
    """
    ds = importlib.import_module("digigraph.tools.digisearch")

    def _reset() -> None:
        ds._cb._state = ds._cb._CLOSED
        ds._cb._failures = 0
        ds._cb._opened_at = None

    _reset()
    yield
    _reset()


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
    mock_response.json.return_value = {
        "results": [],
        "total": 0,
        "query": "q",
        "index_name": "default",
    }
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
        mock_digisearch.return_value = {
            "results": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
            "total": 10,
        }
        out = digisearch_fetch_all("q", index_name="idx", page_size=3, max_results=5)
        assert out is not None
        assert len(out["results"]) == 5
        assert out["total"] == 5


def _failing_sync_client() -> Callable[..., httpx.Client]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    def fake_sync_client(**kwargs: object) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    return fake_sync_client


def _client_error_sync_client(status: int = 422) -> Callable[..., httpx.Client]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "bad query"})

    def fake_sync_client(**kwargs: object) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    return fake_sync_client


@pytest.mark.unit
def test_legacy_digisearch_circuit_opens_after_five_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transport failures must open the legacy digisearch breaker (research path)."""
    ds = importlib.import_module("digigraph.tools.digisearch")

    monkeypatch.setenv("DIGISEARCH_URL", "http://example.test:8002")
    with patch.object(ds, "sync_client", _failing_sync_client()):
        # Force a fresh client so our patched sync_client is used.
        ds._sync_client = None
        for _ in range(5):
            assert digisearch("q") is None

    assert ds._cb.state == "OPEN"
    with patch.object(
        ds,
        "_get_sync_client",
        side_effect=AssertionError("must not call client when circuit is open"),
    ):
        assert digisearch("q") is None


@pytest.mark.unit
def test_legacy_digisearch_http_errors_never_open_the_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4xx/5xx from a live digisearch must not trip the process-wide breaker —
    mirrors hub Finding 2; research still calls this legacy helper."""
    ds = importlib.import_module("digigraph.tools.digisearch")

    monkeypatch.setenv("DIGISEARCH_URL", "http://example.test:8002")
    with patch.object(ds, "sync_client", _client_error_sync_client(422)):
        ds._sync_client = None
        for _ in range(10):
            assert digisearch("q") is None

    assert ds._cb.state == "CLOSED"

    with patch.object(ds, "sync_client", _client_error_sync_client(422)):
        ds._sync_client = None
        assert digisearch("q") is None
    assert ds._cb.state == "CLOSED"
