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


@pytest.mark.unit
def test_mcp_module_avoids_pep563_annotations() -> None:
    """FastMCP 1.9.3 in the stack image crashes on PEP 563 string annotations.

    ``from __future__ import annotations`` turns every annotated ``@mcp.tool()``
    parameter into a string, and FastMCP 1.9.3 ``Tool.from_function`` calls
    ``issubclass()`` on the raw annotation — see Dockerfile.digithings-stack-cloudflare
    rebuild marker v8.
    """
    import re
    from pathlib import Path

    source = Path(mcp_server.__file__).read_text()
    assert not any(
        re.match(r"^from\s+__future__\s+import\s+annotations", line.strip())
        for line in source.splitlines()
    )
