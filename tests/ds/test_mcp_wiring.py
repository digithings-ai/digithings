"""digisearch MCP wiring: CLI builds a real client; run_mcp fails loud without one.

Sub-track A (A1): invoking the CLI ``mcp`` entrypoint without a configured
backend must exit non-zero (``RuntimeError`` from the shared backend gate),
never serve stub results. The CLI must wire a real client via
``create_mcp_with_indexes`` before ``run_mcp``, and honor ``DIGISEARCH_MCP_PORT``
unless ``--port`` is passed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp")

from digisearch.cli import app
from typer.testing import CliRunner

from digisearch import mcp_server

_RUNNER = CliRunner()

_BACKEND_ENV = (
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_SEARCH_API_KEY",
    "CHROMA_PATH",
    "CHROMA_HOST",
    "DIGISEARCH_ALLOW_STUB",
)


@pytest.fixture
def _no_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip non-Cloudflare backend env (Cloudflare creds are cleared by conftest)."""
    for name in _BACKEND_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.unit
def test_run_mcp_fails_loud_without_backend(
    _no_backend: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(self: object, **kwargs: object) -> None:
        raise AssertionError("mcp.run must not be reached without a backend")

    monkeypatch.setattr(type(mcp_server.mcp), "run", _boom)
    with pytest.raises(RuntimeError, match="real backend"):
        mcp_server.run_mcp(port=8765)


@pytest.mark.unit
def test_run_mcp_serves_with_stub_flag(_no_backend: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    calls: dict = {}
    monkeypatch.setattr(type(mcp_server.mcp), "run", lambda self, **kw: calls.update(kw))
    mcp_server.run_mcp(port=8765)
    assert calls == {"transport": "streamable-http"}


@pytest.mark.unit
def test_cli_mcp_wires_client_and_fails_loud_without_backend(
    _no_backend: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    wired: dict = {}
    calls: dict = {}

    def _wire(client: object) -> object:
        wired["client"] = client
        return mcp_server.mcp

    monkeypatch.setattr(mcp_server, "create_mcp_with_indexes", _wire)
    monkeypatch.setattr(type(mcp_server.mcp), "run", lambda self, **kw: calls.update(kw))
    result = _RUNNER.invoke(app, ["mcp", "--port", "8765"])
    assert result.exit_code != 0
    assert "client" in wired
    assert calls == {}


@pytest.mark.unit
def test_cli_mcp_honors_port_env(monkeypatch: pytest.MonkeyPatch) -> None:
    wired: dict = {}
    seen: dict = {}
    monkeypatch.setattr(mcp_server, "create_mcp_with_indexes", lambda c: wired.setdefault("c", c))
    monkeypatch.setattr(mcp_server, "run_mcp", lambda **kw: seen.update(kw))
    monkeypatch.setenv("DIGISEARCH_MCP_PORT", "8771")
    result = _RUNNER.invoke(app, ["mcp"])
    assert result.exit_code == 0
    assert seen.get("port") == 8771
    assert "c" in wired


@pytest.mark.unit
def test_cli_mcp_flag_wins_over_port_env(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}
    monkeypatch.setattr(mcp_server, "create_mcp_with_indexes", lambda c: mcp_server.mcp)
    monkeypatch.setattr(mcp_server, "run_mcp", lambda **kw: seen.update(kw))
    monkeypatch.setenv("DIGISEARCH_MCP_PORT", "8771")
    result = _RUNNER.invoke(app, ["mcp", "--port", "8799"])
    assert result.exit_code == 0
    assert seen.get("port") == 8799
