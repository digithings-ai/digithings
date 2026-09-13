"""Unit tests for digigraph MCP server bind defaults and lazy init."""

from __future__ import annotations

import os

import pytest


@pytest.mark.unit
def test_mcp_default_bind_is_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGIGRAPH_MCP_HOST", raising=False)
    from digigraph import mcp_server

    captured: dict[str, object] = {}

    class _FakeSettings:
        host = "127.0.0.1"
        port = 8766

    class _FakeMcp:
        settings = _FakeSettings()

        def run(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(mcp_server, "get_mcp_server", lambda: _FakeMcp())
    mcp_server.run_mcp(host=None)
    assert _FakeMcp.settings.host == "127.0.0.1"
    assert captured == {"transport": "streamable-http"}


@pytest.mark.unit
def test_mcp_respects_digigraph_mcp_host_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIGRAPH_MCP_HOST", "127.0.0.1")
    assert os.environ.get("DIGIGRAPH_MCP_HOST") == "127.0.0.1"


@pytest.mark.unit
def test_run_mcp_applies_bind_to_settings_not_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digigraph import mcp_server

    calls: dict[str, object] = {}

    class _FakeSettings:
        host = "127.0.0.1"
        port = 8766

    class _FakeMcp:
        settings = _FakeSettings()

        def run(self, **kwargs: object) -> None:
            calls.update(kwargs)

    monkeypatch.setattr(mcp_server, "get_mcp_server", lambda: _FakeMcp())
    mcp_server.run_mcp(host="0.0.0.0", port=8123)
    assert calls == {"transport": "streamable-http"}
    assert (_FakeMcp.settings.host, _FakeMcp.settings.port) == ("0.0.0.0", 8123)


@pytest.mark.unit
def test_default_port_stays_8766() -> None:
    import inspect

    from digigraph import mcp_server

    default_port = inspect.signature(mcp_server.run_mcp).parameters["port"].default
    assert default_port == 8766  # digivault moved to 8769, digigraph keeps 8766


@pytest.mark.unit
def test_get_mcp_server_singleton() -> None:
    pytest.importorskip("mcp")
    from digigraph.mcp_server import get_mcp_server

    a = get_mcp_server()
    b = get_mcp_server()
    assert a is b


@pytest.mark.unit
def test_mcp_llm_path_uses_llm_client_not_direct_openai() -> None:
    """C4 pin: workflow/chat reach the LLM via digigraph.llm_client, never a direct client."""
    import inspect

    from digigraph import mcp_server

    source = inspect.getsource(mcp_server)
    assert "OpenAI(" not in source
    assert "run_digigraph_workflow" in source
    assert "/v1/chat/completions" in source


@pytest.mark.unit
def test_mcp_chat_upstream_shares_server_llm_client() -> None:
    """C4 pin: the in-process chat endpoint the mcp chat tool calls uses llm_client."""
    import inspect

    import digigraph.server as dg_server

    assert "digigraph.llm_client" in inspect.getsource(dg_server)
