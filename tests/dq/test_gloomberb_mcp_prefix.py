"""Public Gloomberb MCP names. digifetch names are a call-time redirect (DIG-3313)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("mcp.server.fastmcp")

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb.agent_tools import (  # noqa: E402
    build_digifetch_tool_dispatcher,
)
from digiquant.mcp_server import create_mcp_server  # noqa: E402
from digiquant.tool_names import GLOOMBERB_PLATFORM_NOTE  # noqa: E402
from digiquant.tool_refusals import is_refused  # noqa: E402


def _names(scope: str = "full") -> set[str]:
    server = create_mcp_server(scope=scope)
    return {tool.name for tool in server._tool_manager.list_tools()}


def test_quote_is_advertised_under_the_gloomberb_prefix() -> None:
    names = _names()
    assert "gloomberb_quote" in names
    assert "gloomberb_quotes_batch" in names
    assert "gloomberb_price_history" in names
    assert "gloomberb_quote" in _names("read")
    assert not any(name.startswith("digifetch_") for name in names)
    assert not any(name.startswith("digifetch_") for name in _names("read"))


def test_gloomberb_quote_is_the_only_mcp_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, dict]] = []

    class _Client:
        def quote(self, payload):
            captured.append(("quote", dict(payload)))

            class _Env:
                def model_dump(self, **_kwargs):
                    return {"data": {"quote": {"symbol": "AAPL", "price": 1}}}

            return _Env()

    monkeypatch.setattr(
        "digiquant.mcp_server._build_gloomberb_client",
        lambda: _Client(),
    )
    monkeypatch.setattr(
        "digiquant.mcp_server._gloomberb_envelope_json",
        lambda envelope, **_kwargs: json.dumps({"data": {"quote": {"symbol": "AAPL"}}}),
    )
    server = create_mcp_server()
    assert server._tool_manager.get_tool("digifetch_quote") is None
    public = server._tool_manager.get_tool("gloomberb_quote").fn
    assert GLOOMBERB_PLATFORM_NOTE in (public.__doc__ or "")
    assert "digiquant" not in (public.__doc__ or "").lower()
    assert json.loads(public(symbol="AAPL"))["data"]["quote"]["symbol"] == "AAPL"
    assert captured == [("quote", {"symbol": "AAPL", "exchange": None})]


def test_dispatcher_accepts_the_public_name() -> None:
    class _Env:
        data = {"ok": True}

        def model_dump(self, **_kwargs: object) -> dict:
            return {"data": self.data}

    class _Client:
        def quote(self, _payload):
            return _Env()

    execute = build_digifetch_tool_dispatcher(_Client())
    result = execute("gloomberb_quote", {"symbol": "AAPL"})
    assert result["ok"] is True
    legacy = execute("digifetch_quote", {"symbol": "AAPL"})
    assert legacy["ok"] is True


def test_congress_alias_stays_refused() -> None:
    assert is_refused("gloomberb_congress_trades")
    assert is_refused("digifetch_congress_trades")
    assert "gloomberb_congress_trades" not in _names()
    assert "digifetch_congress_trades" not in _names()
