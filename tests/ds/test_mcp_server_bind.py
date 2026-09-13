"""MCP bind: host/port belong on the server, not run() (#3854 scope work).

Installed mcp's ``FastMCP.run()`` takes ``(transport, mount_path)`` only —
passing ``host=``/``port=`` raises TypeError, so every ``run_mcp`` entrypoint
would crash on boot. run_mcp must apply the bind to the server settings and
call ``run(transport=...)`` only.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp")

from digisearch import mcp_server


@pytest.mark.unit
def test_run_mcp_applies_bind_to_settings_not_run(monkeypatch):
    calls: dict = {}
    monkeypatch.setattr(type(mcp_server.mcp), "run", lambda self, **kw: calls.update(kw))
    old_host, old_port = mcp_server.mcp.settings.host, mcp_server.mcp.settings.port
    try:
        mcp_server.run_mcp(host="0.0.0.0", port=8125)
        new_host, new_port = mcp_server.mcp.settings.host, mcp_server.mcp.settings.port
    finally:
        mcp_server.mcp.settings.host = old_host
        mcp_server.mcp.settings.port = old_port
    assert calls == {"transport": "streamable-http"}
    assert (new_host, new_port) == ("0.0.0.0", 8125)
