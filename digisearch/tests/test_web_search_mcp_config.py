"""Bad-env fail-closed test for the MCP web_search tool (offline, mocked).

The real `mcp` package is not installed in this env, so it is stubbed with a
no-op FastMCP whose `tool()` decorator returns the function unchanged.
"""

from __future__ import annotations

import sys
import types

import pytest


def _load_mcp_server(monkeypatch: pytest.MonkeyPatch):
    """Import digisearch.mcp_server without the real mcp package installed."""
    monkeypatch.delitem(sys.modules, "digisearch.mcp_server", raising=False)
    fastmcp_mod = types.ModuleType("mcp.server.fastmcp")

    class _FakeFastMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self):
            def _deco(fn):
                return fn

            return _deco

    fastmcp_mod.FastMCP = _FakeFastMCP
    server_mod = types.ModuleType("mcp.server")
    server_mod.fastmcp = fastmcp_mod
    pkg_mod = types.ModuleType("mcp")
    pkg_mod.server = server_mod
    monkeypatch.setitem(sys.modules, "mcp", pkg_mod)
    monkeypatch.setitem(sys.modules, "mcp.server", server_mod)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fastmcp_mod)
    import digisearch.mcp_server as mod

    return mod


def test_mcp_web_search_bad_backend_is_clean_message(monkeypatch: pytest.MonkeyPatch):
    """Bad DIGISEARCH_WEB_SEARCH_BACKEND → clean unavailable message, never raise."""
    mod = _load_mcp_server(monkeypatch)
    monkeypatch.setenv("DIGISEARCH_WEB_SEARCH_BACKEND", "bogus")
    out = mod.web_search(query="etf flows")
    assert out.startswith("[web_search unavailable:")
    assert "bogus" in out
    assert "Traceback" not in out


def test_mcp_web_search_good_env_passthrough(monkeypatch: pytest.MonkeyPatch):
    """Good env still returns the service JSON (happy path unchanged)."""
    import digisearch.web_search.service as svc
    from digisearch.web_search.models import WebSearchResponse

    mod = _load_mcp_server(monkeypatch)
    monkeypatch.delenv("DIGISEARCH_WEB_SEARCH_BACKEND", raising=False)
    monkeypatch.setattr(
        svc,
        "run_web_search",
        lambda req: WebSearchResponse(query=req.query, results=[], provider="searxng"),
    )
    out = mod.web_search(query="etf flows")
    assert not out.startswith("[web_search")
    assert "searxng" in out
