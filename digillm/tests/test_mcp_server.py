"""Unit tests for the digillm MCP server (generic completion tool)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

pytest.importorskip("mcp")

import digillm
from digillm.mcp_server import _coerce_messages
from digillm.mcp_server import mcp as digillm_mcp


def test_coerce_messages_rejects_bad_shapes() -> None:
    with pytest.raises(ValueError, match="non-empty list"):
        _coerce_messages([])
    with pytest.raises(ValueError, match="non-empty list"):
        _coerce_messages("nope")
    with pytest.raises(ValueError, match="valid role"):
        _coerce_messages([{"role": "villain", "content": "hi"}])
    with pytest.raises(ValueError, match="non-empty content"):
        _coerce_messages([{"role": "user", "content": "  "}])


def test_coerce_messages_accepts_valid_list() -> None:
    assert _coerce_messages([{"role": "user", "content": "hi"}]) == [
        {"role": "user", "content": "hi"}
    ]


def test_server_registers_single_complete_tool() -> None:
    async def _names() -> list[str]:
        return [t.name for t in await digillm_mcp.list_tools()]

    assert asyncio.run(_names()) == ["complete"]


def test_complete_tool_routes_through_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    """The MCP complete tool calls digillm.completion and returns text + served model."""
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="  ok  "))]
    resp.model = "served-model"
    made: dict[str, Any] = {}

    def fake_completion(model: str, messages: Any, **kwargs: Any) -> Any:
        made.update(model=model, messages=messages, kwargs=kwargs)
        return resp

    monkeypatch.setattr(digillm, "completion", fake_completion)

    async def _run() -> Any:
        return await digillm_mcp.call_tool(
            "complete",
            {
                "model": "deepseek/deepseek-v4-flash",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    out = asyncio.run(_run())
    assert made["model"] == "deepseek/deepseek-v4-flash"
    assert made["messages"] == [{"role": "user", "content": "hi"}]
    assert "ok" in str(out)
    assert "served-model" in str(out)


def test_complete_tool_rejects_empty_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(digillm, "completion", MagicMock())

    async def _run() -> Any:
        return await digillm_mcp.call_tool("complete", {"model": "m", "messages": []})

    # Validation errors surface (fail-fast) rather than reaching a provider.
    with pytest.raises(Exception, match="non-empty list"):
        asyncio.run(_run())


@pytest.mark.unit
def test_run_mcp_applies_bind_to_settings_not_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digillm import mcp_server

    calls: dict = {}
    monkeypatch.setattr(type(mcp_server.mcp), "run", lambda self, **kw: calls.update(kw))
    old_host, old_port = mcp_server.mcp.settings.host, mcp_server.mcp.settings.port
    try:
        mcp_server.run_mcp(host="0.0.0.0", port=8128)
        new_host, new_port = mcp_server.mcp.settings.host, mcp_server.mcp.settings.port
    finally:
        mcp_server.mcp.settings.host = old_host
        mcp_server.mcp.settings.port = old_port
    assert calls == {"transport": "streamable-http"}
    assert (new_host, new_port) == ("0.0.0.0", 8128)
