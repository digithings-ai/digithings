"""Unit tests for generic (non-retrieval) tool-result trace clipping."""

import pytest

from digigraph.workflow import _clip_tool_result


@pytest.mark.unit
def test_clip_scalars() -> None:
    assert _clip_tool_result("hello") == "hello"
    assert _clip_tool_result(42) == 42
    assert _clip_tool_result(True) is True
    assert _clip_tool_result(None) is None
    assert _clip_tool_result("   ") is None


@pytest.mark.unit
def test_clip_dict_result() -> None:
    result = _clip_tool_result(
        {"connections": [{"name": "a", "id": "1"}, {"name": "b", "id": "2"}]}
    )
    assert result == {"connections": [{"name": "a", "id": "1"}, {"name": "b", "id": "2"}]}


@pytest.mark.unit
def test_clip_drops_rag_sources_and_deep_blobs() -> None:
    result = _clip_tool_result(
        {"rag_sources": [{"a": 1}], "deep": {"x": {"y": {"z": 1}}}, "ok": "yes"}
    )
    # rag_sources excluded (retrieval channel owns those); depth>1 dicts
    # collapse to nothing, leaving only the scalar survivor.
    assert result == {"ok": "yes"}


@pytest.mark.unit
def test_clip_caps_string_length() -> None:
    big = "x" * 5000
    assert _clip_tool_result(big) == "x" * 2000


@pytest.mark.unit
def test_clip_empty_dict_is_none() -> None:
    assert _clip_tool_result({}) is None
    assert _clip_tool_result([]) is None


@pytest.mark.unit
def test_mcp_server_ref_round_trips_auth_header_by_alias() -> None:
    """Pin the workflow.py by_alias=True contract: auth_header must dump as
    ``authHeader`` so mcp_http_headers picks the custom header downstream.
    A revert to snake_case would silently break X-API-Key auth with all
    existing tests still green (review finding on #3850)."""
    from digigraph.models import McpServerRef

    ref = McpServerRef(
        id="datatap",
        url="https://datatap-dev-mcp.azurewebsites.net/",
        token="tok",
        auth_header="X-API-Key",
    )
    assert ref.model_dump(exclude_none=True, by_alias=True) == {
        "id": "datatap",
        "url": "https://datatap-dev-mcp.azurewebsites.net/",
        "token": "tok",
        "authHeader": "X-API-Key",
    }
