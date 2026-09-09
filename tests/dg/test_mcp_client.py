"""Operator remote MCP proxy (#3736)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from digigraph.models import WorkflowRequest
from digigraph.orchestration.mcp_client import (
    expand_mcp_disabled_tokens,
    is_allowed_mcp_url,
    merge_mcp_servers,
    parse_mcp_servers_env,
    parse_mcp_servers_json,
    prefixed_tool_name,
    resolve_mcp_force_id,
    split_prefixed_tool_name,
)
from digigraph.orchestration.registry import ToolContext, execute


@pytest.mark.unit
def test_is_allowed_mcp_url() -> None:
    assert is_allowed_mcp_url("https://mcp.datatap.example/mcp") is True
    assert is_allowed_mcp_url("http://datatap-mcp:8080/mcp") is True
    assert is_allowed_mcp_url("https://user:pass@evil.test/mcp") is False
    assert is_allowed_mcp_url("https://169.254.169.254/latest") is False
    assert is_allowed_mcp_url("ftp://mcp.example/mcp") is False
    assert is_allowed_mcp_url("http://127.0.0.1:8005/") is False
    assert is_allowed_mcp_url("http://localhost:8080/mcp") is False
    assert is_allowed_mcp_url("http://[::1]/mcp") is False
    assert is_allowed_mcp_url("http://2130706433/") is False
    assert is_allowed_mcp_url("http://[::ffff:169.254.169.254]/latest/meta-data/") is False
    assert is_allowed_mcp_url("http://169.254.169.254.nip.io/") is False
    assert is_allowed_mcp_url("http://10.0.0.5:8080/mcp") is False
    assert is_allowed_mcp_url("http://[fd12:3456::1]/mcp") is False
    assert is_allowed_mcp_url("http://0x7f000001/") is False


@pytest.mark.unit
def test_parse_mcp_servers_json_drops_bad_entries() -> None:
    raw = (
        '[{"id":"datatap","url":"https://mcp.datatap.example/mcp"},'
        '{"id":"bad","url":"https://169.254.169.254/"},'
        '{"id":"DATATAP","url":"https://dup.example/mcp"}]'
    )
    assert parse_mcp_servers_json(raw) == [
        {"id": "datatap", "url": "https://mcp.datatap.example/mcp"},
    ]
    assert parse_mcp_servers_json("not-json") == []
    assert parse_mcp_servers_json("x" * 20000) == []


@pytest.mark.unit
def test_parse_mcp_servers_env_and_merge_header_wins() -> None:
    env = parse_mcp_servers_env(
        "envonly=https://env.example/mcp,datatap=https://env-dt.example/mcp"
    )
    header = [{"id": "datatap", "url": "https://header.example/mcp"}]
    merged = merge_mcp_servers(header, env)
    by_id = {s["id"]: s["url"] for s in merged}
    assert by_id["datatap"] == "https://header.example/mcp"
    assert by_id["envonly"] == "https://env.example/mcp"


@pytest.mark.unit
def test_prefixed_tool_names() -> None:
    assert prefixed_tool_name("datatap", "list_pipelines") == "datatap__list_pipelines"
    assert split_prefixed_tool_name("datatap__list_pipelines") == ("datatap", "list_pipelines")
    assert split_prefixed_tool_name("digisearch") is None


@pytest.mark.unit
def test_expand_mcp_disabled_tokens() -> None:
    extra = ["datatap__a", "datatap__b", "other__x"]
    assert expand_mcp_disabled_tokens(["datatap", "rm -rf"], extra) == frozenset(
        {"datatap__a", "datatap__b"}
    )
    assert expand_mcp_disabled_tokens(["other"], extra) == frozenset({"other__x"})


@pytest.mark.unit
def test_resolve_mcp_force_id() -> None:
    servers = [{"id": "datatap", "url": "https://mcp.example/mcp"}]
    assert resolve_mcp_force_id("datatap", servers) == "datatap"
    assert resolve_mcp_force_id("/datatap", servers) == "datatap"
    assert resolve_mcp_force_id("web_search", servers) is None


@pytest.mark.unit
def test_http_overwrites_body_mcp_servers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_MCP_SERVERS", raising=False)
    from digigraph.http_api.context import _with_digi_request_context

    req = WorkflowRequest(
        prompt="hi",
        mcp_servers=[{"id": "evil", "url": "https://evil.example/mcp"}],
    )
    request = SimpleNamespace(
        state=SimpleNamespace(digi_bearer=None, digi_auth=None),
        headers={
            "X-Digi-Mcp-Servers": '[{"id":"datatap","url":"https://mcp.datatap.example/mcp"}]',
        },
    )
    copied = _with_digi_request_context(request, req)
    assert copied.mcp_servers is not None
    assert [s.id for s in copied.mcp_servers] == ["datatap"]
    assert copied.mcp_servers[0].url == "https://mcp.datatap.example/mcp"


@pytest.mark.unit
def test_parse_mcp_servers_json_keeps_auth_token() -> None:
    raw = (
        '[{"id":"linear","url":"https://mcp.linear.app/mcp",'
        '"auth":"oauth","token":"tok"}]'
    )
    assert parse_mcp_servers_json(raw) == [
        {
            "id": "linear",
            "url": "https://mcp.linear.app/mcp",
            "auth": "oauth",
            "token": "tok",
        }
    ]


@pytest.mark.unit
def test_mcp_cache_key_changes_with_token_and_omits_raw_secret() -> None:
    from digigraph.orchestration.mcp_client import mcp_http_headers, mcp_list_cache_key

    a = {"id": "s", "url": "https://mcp.example/mcp", "token": "aaa"}
    b = {"id": "s", "url": "https://mcp.example/mcp", "token": "bbb"}
    c = {"id": "s", "url": "https://mcp.example/mcp"}
    assert mcp_http_headers(a) == {"Authorization": "Bearer aaa"}
    assert mcp_list_cache_key(a) != mcp_list_cache_key(b)
    assert mcp_list_cache_key(a) != mcp_list_cache_key(c)
    assert "aaa" not in mcp_list_cache_key(a)


@pytest.mark.unit
def test_call_prefixed_tool_passes_server_with_token() -> None:
    from digigraph.orchestration.mcp_client import call_prefixed_tool

    servers = [{"id": "s", "url": "https://mcp.example/mcp", "token": "secret"}]
    with patch(
        "digigraph.orchestration.mcp_client._call_tool_blocking",
        return_value={"ok": True},
    ) as call:
        call_prefixed_tool("s__echo", {"q": "hi"}, servers)
    call.assert_called_once_with(servers[0], "echo", {"q": "hi"})


@pytest.mark.unit
def test_http_mcp_servers_keep_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_MCP_SERVERS", raising=False)
    from digigraph.http_api.context import _with_digi_request_context

    req = WorkflowRequest(prompt="hi")
    request = SimpleNamespace(
        state=SimpleNamespace(digi_bearer=None, digi_auth=None),
        headers={
            "X-Digi-Mcp-Servers": (
                '[{"id":"datatap","url":"https://mcp.datatap.example/mcp",'
                '"auth":"oauth","token":"tok"}]'
            ),
        },
    )
    copied = _with_digi_request_context(request, req)
    assert copied.mcp_servers is not None
    assert copied.mcp_servers[0].token == "tok"
    assert copied.mcp_servers[0].auth == "oauth"


@pytest.mark.unit
def test_http_effort_header() -> None:
    from digigraph.http_api.context import _digi_fields_from_request

    request = SimpleNamespace(
        state=SimpleNamespace(digi_bearer=None, digi_auth=None),
        headers={"X-Digi-Effort": "high"},
    )
    updates = _digi_fields_from_request(request)
    assert updates["effort"] == "high"
    request2 = SimpleNamespace(state=SimpleNamespace(digi_bearer=None, digi_auth=None), headers={})
    updates2 = _digi_fields_from_request(request2)
    assert updates2["effort"] is None


@pytest.mark.unit
def test_http_clears_body_mcp_servers_when_header_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIGI_MCP_SERVERS", raising=False)
    from digigraph.http_api.context import _with_digi_request_context

    req = WorkflowRequest(
        prompt="hi",
        mcp_servers=[{"id": "evil", "url": "https://evil.example/mcp"}],
    )
    request = SimpleNamespace(
        state=SimpleNamespace(digi_bearer=None, digi_auth=None),
        headers={},
    )
    copied = _with_digi_request_context(request, req)
    assert list(copied.mcp_servers or []) == []


@pytest.mark.unit
def test_get_tools_merges_prefixed_mcp_tools() -> None:
    from digigraph.orchestration.registry import get_tools

    fake = [
        {
            "type": "function",
            "function": {
                "name": "datatap__echo",
                "description": "echo",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={},
        extra_mcp_servers=[{"id": "datatap", "url": "https://mcp.example/mcp"}],
        allowed_tool_names=frozenset({"datatap__echo"}),
    )
    with patch(
        "digigraph.orchestration.mcp_client.openai_tools_for_servers",
        return_value=fake,
    ):
        tools = get_tools(["search"], ctx)
    names = []
    for t in tools:
        fn = t.get("function") if isinstance(t, dict) else None
        if isinstance(fn, dict) and fn.get("name"):
            names.append(fn["name"])
    assert "datatap__echo" in names
    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={},
        extra_mcp_servers=[{"id": "datatap", "url": "https://mcp.example/mcp"}],
        allowed_tool_names=frozenset({"datatap__echo"}),
    )
    with patch(
        "digigraph.orchestration.mcp_client.call_prefixed_tool",
        return_value={"ok": True, "text": "pong"},
    ) as call:
        out = execute("datatap__echo", {"q": "hi"}, ctx)
    call.assert_called_once_with(
        "datatap__echo",
        {"q": "hi"},
        [{"id": "datatap", "url": "https://mcp.example/mcp"}],
    )
    assert out == {"ok": True, "text": "pong"}
