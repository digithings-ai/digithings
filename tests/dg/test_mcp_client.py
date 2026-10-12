"""Operator remote MCP proxy (#3736)."""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from digigraph.models import WorkflowRequest
from digigraph.orchestration.mcp_client import (
    call_prefixed_tool,
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
    assert is_allowed_mcp_url("http://127.1/") is False
    assert is_allowed_mcp_url("http://127.0.1/") is False
    assert is_allowed_mcp_url("http://0x7f.0x0.0x0.0x1/") is False
    assert is_allowed_mcp_url("http://localtest.me/") is False
    assert is_allowed_mcp_url("http://foo.lvh.me/mcp") is False
    assert is_allowed_mcp_url("http://100.100.100.200/") is False


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
    assert prefixed_tool_name("datatap", "list_pipelines") == "datatap_list_pipelines"
    assert split_prefixed_tool_name("datatap_list_pipelines") == ("datatap", "list_pipelines")
    assert split_prefixed_tool_name("digisearch") is None


@pytest.mark.unit
def test_expand_mcp_disabled_tokens() -> None:
    extra = ["datatap_a", "datatap_b", "other_x"]
    assert expand_mcp_disabled_tokens(["datatap", "rm -rf"], extra) == frozenset(
        {"datatap_a", "datatap_b"}
    )
    assert expand_mcp_disabled_tokens(["other"], extra) == frozenset({"other_x"})


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
    raw = '[{"id":"linear","url":"https://mcp.linear.app/mcp","auth":"oauth","token":"tok"}]'
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
def test_parse_mcp_servers_json_keeps_valid_auth_header() -> None:
    raw = (
        '[{"id":"datatap","url":"https://mcp.datatap.example/mcp",'
        '"token":"tok","authHeader":"X-API-Key"}]'
    )
    assert parse_mcp_servers_json(raw) == [
        {
            "id": "datatap",
            "url": "https://mcp.datatap.example/mcp",
            "token": "tok",
            "authHeader": "X-API-Key",
        }
    ]


@pytest.mark.unit
def test_parse_mcp_servers_json_drops_malformed_auth_header() -> None:
    raw = (
        '[{"id":"datatap","url":"https://mcp.datatap.example/mcp",'
        '"token":"tok","authHeader":"bad header!"}]'
    )
    parsed = parse_mcp_servers_json(raw)
    assert parsed == [{"id": "datatap", "url": "https://mcp.datatap.example/mcp", "token": "tok"}]
    assert "authHeader" not in parsed[0]


@pytest.mark.unit
def test_mcp_http_headers_uses_custom_auth_header_when_present() -> None:
    from digigraph.orchestration.mcp_client import mcp_http_headers

    default = {"id": "s", "url": "https://mcp.example/mcp", "token": "tok"}
    assert mcp_http_headers(default) == {"Authorization": "Bearer tok"}

    custom = {
        "id": "datatap",
        "url": "https://mcp.datatap.example/mcp",
        "token": "tenant-static-key",
        "authHeader": "X-API-Key",
    }
    assert mcp_http_headers(custom) == {"X-API-Key": "tenant-static-key"}

    no_token = {"id": "s", "url": "https://mcp.example/mcp", "authHeader": "X-API-Key"}
    assert mcp_http_headers(no_token) is None

    malformed_header = {
        "id": "s",
        "url": "https://mcp.example/mcp",
        "token": "tok",
        "authHeader": "bad header!",
    }
    assert mcp_http_headers(malformed_header) == {"Authorization": "Bearer tok"}


@pytest.mark.unit
def test_mcp_cache_key_changes_with_auth_header() -> None:
    from digigraph.orchestration.mcp_client import mcp_list_cache_key

    bearer = {"id": "s", "url": "https://mcp.example/mcp", "token": "tok"}
    custom = {
        "id": "s",
        "url": "https://mcp.example/mcp",
        "token": "tok",
        "authHeader": "X-API-Key",
    }
    assert mcp_list_cache_key(bearer) != mcp_list_cache_key(custom)


@pytest.mark.unit
def test_call_prefixed_tool_passes_server_with_token() -> None:
    from digigraph.orchestration.mcp_client import call_prefixed_tool

    servers = [{"id": "s", "url": "https://mcp.example/mcp", "token": "secret"}]
    with patch(
        "digigraph.orchestration.mcp_client._call_tool_blocking",
        return_value={"ok": True},
    ) as call:
        call_prefixed_tool("s_echo", {"q": "hi"}, servers)
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
def test_http_mcp_servers_keep_auth_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_MCP_SERVERS", raising=False)
    from digigraph.http_api.context import _with_digi_request_context

    req = WorkflowRequest(prompt="hi")
    request = SimpleNamespace(
        state=SimpleNamespace(digi_bearer=None, digi_auth=None),
        headers={
            "X-Digi-Mcp-Servers": (
                '[{"id":"datatap","url":"https://mcp.datatap.example/mcp",'
                '"token":"tenant-static-key","authHeader":"X-API-Key"}]'
            ),
        },
    )
    copied = _with_digi_request_context(request, req)
    assert copied.mcp_servers is not None
    assert copied.mcp_servers[0].token == "tenant-static-key"
    assert copied.mcp_servers[0].auth_header == "X-API-Key"


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
                "name": "datatap_echo",
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
        allowed_tool_names=frozenset({"datatap_echo"}),
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
    assert "datatap_echo" in names
    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={},
        extra_mcp_servers=[{"id": "datatap", "url": "https://mcp.example/mcp"}],
        allowed_tool_names=frozenset({"datatap_echo"}),
    )
    with patch(
        "digigraph.orchestration.mcp_client.call_prefixed_tool",
        return_value={"ok": True, "text": "pong"},
    ) as call:
        out = execute("datatap_echo", {"q": "hi"}, ctx)
    call.assert_called_once_with(
        "datatap_echo",
        {"q": "hi"},
        [{"id": "datatap", "url": "https://mcp.example/mcp"}],
    )
    assert out == {"ok": True, "text": "pong"}


@pytest.mark.unit
def test_parse_mcp_servers_json_preserves_setup() -> None:
    servers = parse_mcp_servers_json(
        '[{"id": "digisearch", "url": "http://digisearch-mcp:8765/mcp",'
        ' "setup": {"index_name": "occ_help"}}]'
    )
    assert servers[0]["setup"] == '{"index_name": "occ_help"}'


@pytest.mark.unit
def test_call_prefixed_tool_injects_setup() -> None:
    servers = [
        {
            "id": "digisearch",
            "url": "http://digisearch-mcp:8765/mcp",
            "setup": '{"index_name": "occ_help"}',
        }
    ]
    with patch(
        "digigraph.orchestration.mcp_client._call_tool_blocking",
        return_value={"ok": True},
    ) as call:
        out = call_prefixed_tool(
            "digisearch_semantic",
            {"index_name": "wrong", "text": "q"},
            servers,
        )
    call.assert_called_once_with(
        servers[0],
        "semantic",
        {"index_name": "occ_help", "text": "q"},
    )
    assert out == {"ok": True}


@pytest.mark.unit
def test_call_prefixed_tool_setup_path_prefix_wins_over_model_arg() -> None:
    """Operator setup.path_prefix must override a model-supplied value (#4223 review)."""
    servers = [
        {
            "id": "digivault",
            "url": "http://digivault-mcp:8769/mcp",
            "setup": '{"path_prefix": "clients/acme"}',
        }
    ]
    with patch(
        "digigraph.orchestration.mcp_client._call_tool_blocking",
        return_value={"ok": True},
    ) as call:
        call_prefixed_tool(
            "digivault_search_tag",
            {"tag": "guide", "path_prefix": "clients/other"},
            servers,
        )
    call.assert_called_once_with(
        servers[0],
        "search_tag",
        {"tag": "guide", "path_prefix": "clients/acme"},
    )


@pytest.mark.unit
def test_mcp_setup_survives_http_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Operator ``setup`` survives header → McpServerRef → state → tool call (#4246 review).

    The HTTP boundary rebuilt ``McpServerRef`` field-by-field and silently
    dropped ``setup``, so digivault's ``path_prefix`` (and digisearch's
    ``index_name``) never reached :func:`call_prefixed_tool` in production.
    """
    monkeypatch.delenv("DIGI_MCP_SERVERS", raising=False)
    from digigraph.http_api.context import _digi_fields_from_request, _with_digi_request_context

    request = SimpleNamespace(
        state=SimpleNamespace(digi_bearer=None, digi_auth=None),
        headers={
            "X-Digi-Mcp-Servers": (
                '[{"id":"digivault","url":"http://digivault-mcp:8769/mcp",'
                '"setup":{"path_prefix":"clients/acme"}}]'
            )
        },
    )
    refs = _digi_fields_from_request(request)["mcp_servers"]
    assert refs
    assert refs[0].setup == {"path_prefix": "clients/acme"}

    copied = _with_digi_request_context(request, WorkflowRequest(prompt="hi"))
    assert copied.mcp_servers is not None
    assert copied.mcp_servers[0].setup == {"path_prefix": "clients/acme"}

    # workflow.py projects refs with model_dump(exclude_none=True, by_alias=True)
    # into graph state; research.py hands that list to execute → call_prefixed_tool.
    state_servers = [r.model_dump(exclude_none=True, by_alias=True) for r in copied.mcp_servers]
    with patch(
        "digigraph.orchestration.mcp_client._call_tool_blocking",
        return_value={"ok": True},
    ) as call:
        call_prefixed_tool(
            "digivault_search_tag",
            {"tag": "guide", "path_prefix": "clients/other"},
            state_servers,
        )
    call.assert_called_once_with(
        state_servers[0],
        "search_tag",
        {"tag": "guide", "path_prefix": "clients/acme"},
    )


@pytest.mark.unit
def test_mcp_web_search_denied_without_opt_in() -> None:
    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={},
        extra_mcp_servers=[{"id": "digisearch", "url": "https://mcp.example/mcp"}],
        allowed_tool_names=frozenset({"digisearch_web_search"}),
    )
    out = execute("digisearch_web_search", {"query": "x"}, ctx)
    assert isinstance(out, dict)
    assert out.get("error") == "tool_not_allowed"
    assert out.get("tool") == "digisearch_web_search"


@pytest.mark.unit
def test_mcp_web_search_allowed_with_opt_in() -> None:
    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={"enable_web_search": True},
        extra_mcp_servers=[{"id": "digisearch", "url": "https://mcp.example/mcp"}],
        allowed_tool_names=frozenset({"digisearch_web_search"}),
    )
    with patch(
        "digigraph.orchestration.mcp_client.call_prefixed_tool",
        return_value={"ok": True},
    ) as call:
        out = execute("digisearch_web_search", {"query": "x"}, ctx)
    call.assert_called_once()
    assert out == {"ok": True}


# --- DIG-507: the remote MCP server must be asked for the name it advertised ---


def _capture_names(monkeypatch: pytest.MonkeyPatch, server: dict[str, str], names: list[str]) -> None:
    from digigraph.orchestration import mcp_client

    monkeypatch.setitem(mcp_client._raw_names_cache, mcp_client.mcp_list_cache_key(server), names)


def _forget_names(monkeypatch: pytest.MonkeyPatch, server: dict[str, str]) -> None:
    from digigraph.orchestration import mcp_client

    key = mcp_client.mcp_list_cache_key(server)
    monkeypatch.delitem(mcp_client._raw_names_cache, key, raising=False)


@pytest.mark.unit
def test_list_tools_async_captures_the_advertised_tool_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The capture is the mechanism; pin it at the only place names still exist."""
    from digigraph.orchestration import mcp_client

    class _Tool:
        def __init__(self, name: str) -> None:
            self.name = name
            self.description = None
            self.inputSchema = {"type": "object", "properties": {}}

    class _Listing:
        tools = [_Tool("atlassian.executeWrite"), _Tool("plain"), _Tool("atlassian.executeWrite")]

    class _Session:
        async def __aenter__(self) -> "_Session":
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def initialize(self) -> None:
            return None

        async def list_tools(self) -> _Listing:
            return _Listing()

    @contextlib.asynccontextmanager
    async def _wire(url: str, **kwargs: object):
        yield (object(), object(), object())

    monkeypatch.setattr("mcp.client.streamable_http.streamablehttp_client", _wire)
    monkeypatch.setattr("mcp.ClientSession", lambda read, write: _Session())

    server = {"id": "atlassian", "url": "https://mcp.example/mcp"}
    _forget_names(monkeypatch, server)

    offered = asyncio.run(mcp_client._list_tools_async(server))

    # The model is still offered the sanitised names -- unchanged by DIG-507.
    assert [t["function"]["name"] for t in offered] == [
        "atlassian_atlassian_executeWrite",
        "atlassian_plain",
        "atlassian_atlassian_executeWrite",
    ]
    # Captured advertised names, de-duplicated and order-preserved.
    assert mcp_client.raw_tool_names_for_server(server) == ["atlassian.executeWrite", "plain"]


@pytest.mark.unit
def test_registry_execute_calls_the_advertised_mcp_tool_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance 1: end to end through registry.execute(), a dotted name survives."""
    server = {"id": "atlassian", "url": "https://mcp.example/mcp"}
    _capture_names(
        monkeypatch,
        server,
        [
            "atlassian.discover",
            "atlassian.executeRead",
            "atlassian.executeWrite",
            "atlassian.executeDestructive",
        ],
    )
    offered = prefixed_tool_name("atlassian", "atlassian.executeWrite")
    assert offered == "atlassian_atlassian_executeWrite"

    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={},
        extra_mcp_servers=[server],
        allowed_tool_names=frozenset({offered}),
    )
    with patch(
        "digigraph.orchestration.mcp_client._call_tool_blocking",
        return_value={"ok": True},
    ) as call:
        out = execute(offered, {"text": "hi"}, ctx)

    assert out == {"ok": True}
    call.assert_called_once_with(server, "atlassian.executeWrite", {"text": "hi"})


@pytest.mark.unit
def test_registry_execute_calls_a_long_advertised_tool_name_in_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance 2: a name past the 64-safe-char cap is called correctly, not truncated."""
    raw = "a" * 64 + ".tail"
    server = {"id": "longtools", "url": "https://mcp.example/mcp"}
    _capture_names(monkeypatch, server, [raw])
    offered = prefixed_tool_name("longtools", raw)
    assert offered == "longtools_" + "a" * 64

    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={},
        extra_mcp_servers=[server],
        allowed_tool_names=frozenset({offered}),
    )
    with patch(
        "digigraph.orchestration.mcp_client._call_tool_blocking",
        return_value={"ok": True},
    ) as call:
        out = execute(offered, {"text": "hi"}, ctx)

    assert out == {"ok": True}
    call.assert_called_once_with(server, raw, {"text": "hi"})


@pytest.mark.unit
def test_call_prefixed_tool_refuses_a_name_the_server_never_advertised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = {"id": "atlassian", "url": "https://mcp.example/mcp"}
    _capture_names(monkeypatch, server, ["atlassian.executeRead"])
    with patch("digigraph.orchestration.mcp_client._call_tool_blocking") as call:
        out = call_prefixed_tool("atlassian_invented", {}, [server])
    call.assert_not_called()
    assert out["error"] == "mcp_tool_name_unresolved"
    assert out["tool"] == "atlassian_invented"
    assert out["server"] == "atlassian"


@pytest.mark.unit
def test_call_prefixed_tool_refuses_when_two_advertised_names_collapse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both truncate to the same offered name; guessing either calls the wrong tool."""
    first, second = "b" * 64 + "X", "b" * 64 + "Y"
    server = {"id": "collapser", "url": "https://mcp.example/mcp"}
    _capture_names(monkeypatch, server, [first, second])
    offered = prefixed_tool_name("collapser", first)
    assert prefixed_tool_name("collapser", second) == offered
    with patch("digigraph.orchestration.mcp_client._call_tool_blocking") as call:
        out = call_prefixed_tool(offered, {}, [server])
    call.assert_not_called()
    assert out["error"] == "mcp_tool_name_unresolved"


@pytest.mark.unit
def test_call_prefixed_tool_falls_back_to_the_offered_name_without_a_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No list_tools snapshot means the offered name is the best name there is."""
    server = {"id": "nocapture", "url": "https://mcp.example/mcp"}
    _forget_names(monkeypatch, server)
    with patch(
        "digigraph.orchestration.mcp_client._call_tool_blocking",
        return_value={"ok": True},
    ) as call:
        out = call_prefixed_tool("nocapture_echo", {"q": "hi"}, [server])
    assert out == {"ok": True}
    call.assert_called_once_with(server, "echo", {"q": "hi"})
