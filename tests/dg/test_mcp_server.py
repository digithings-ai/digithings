"""Unit tests for DigiGraph MCP server bind defaults and lazy init."""

from __future__ import annotations

import os

import pytest


@pytest.mark.unit
def test_mcp_default_bind_is_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGIGRAPH_MCP_HOST", raising=False)
    from digigraph.mcp_server import run_mcp

    captured: dict[str, str] = {}

    def _fake_run(*_a: object, **kwargs: object) -> None:
        captured["host"] = str(kwargs.get("host", ""))

    monkeypatch.setattr("digigraph.mcp_server.get_mcp_server", lambda: type("M", (), {"run": _fake_run})())
    run_mcp(host=None)
    assert captured["host"] == "127.0.0.1"


@pytest.mark.unit
def test_mcp_respects_digigraph_mcp_host_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIGRAPH_MCP_HOST", "127.0.0.1")
    assert os.environ.get("DIGIGRAPH_MCP_HOST") == "127.0.0.1"


@pytest.mark.unit
def test_get_mcp_server_singleton() -> None:
    pytest.importorskip("mcp")
    from digigraph.mcp_server import get_mcp_server

    a = get_mcp_server()
    b = get_mcp_server()
    assert a is b
