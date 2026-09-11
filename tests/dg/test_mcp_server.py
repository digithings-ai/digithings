"""Unit tests for digigraph MCP server bind defaults and lazy init."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any

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


def _mint(
    *,
    scopes: list[str] | None = None,
    audience: str | None = None,
    ttl_sec: int | None = None,
) -> str:
    """Mint an RS256 JWT with the pytest keypair (conftest sets the public PEM)."""
    from digikey.crypto_keys import load_private_key_from_pem
    from digikey.jwt_issue import issue_access_token

    pem = os.environ["_PYTEST_DIGIKEY_PRIVATE_PEM"]
    token, _ = issue_access_token(
        load_private_key_from_pem(pem),
        kid="pytest-kid",
        sub="pytest-sub",
        tenant_slug="pytest-tenant",
        scopes=scopes if scopes is not None else ["*"],
        audience=audience,
        ttl_sec=ttl_sec,
    )
    return token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bearer_headers(scopes: list[str]) -> dict[str, str]:
    return _bearer(_mint(scopes=scopes))


class _FakeRequest:
    def __init__(self, headers: dict[str, str] | None) -> None:
        self.headers = headers or {}


class _FakeRequestContext:
    def __init__(self, headers: dict[str, str] | None) -> None:
        self.request = _FakeRequest(headers)


class _FakeContext:
    """Duck-typed stand-in for mcp.server.fastmcp.Context in unit tests."""

    def __init__(self, headers: dict[str, str] | None) -> None:
        self.request_context = _FakeRequestContext(headers)


def _mcp_tool(name: str) -> Any:
    from digigraph.mcp_server import create_mcp_server

    tool = create_mcp_server()._tool_manager.get_tool(name)
    assert tool is not None, f"MCP tool {name!r} not registered"
    return tool


def _call_tool(name: str, headers: dict[str, str] | None, **kwargs: Any) -> str:
    tool = _mcp_tool(name)
    if tool.context_kwarg is not None:
        kwargs[tool.context_kwarg] = _FakeContext(headers)
    return tool.fn(**kwargs)


def _dummy_server_app() -> Any:
    """Minimal ASGI app so a pre-fix chat tool cannot reach an LLM in unit tests."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI()

    @app.post("/v1/chat/completions")
    def _completions() -> JSONResponse:
        return JSONResponse(status_code=401, content={"error": "no"})

    return app


@pytest.mark.unit
class TestMcpAuthGate:
    def test_auth_not_required_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DIGI_MCP_REQUIRE_AUTH", raising=False)
        from digigraph import mcp_server

        assert mcp_server._mcp_auth_required() is False
        # No verifier and no token is fine when the gate is off.
        mcp_server._authorize_mcp_headers(None, "digigraph:workflow")

    def test_missing_or_malformed_token_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGI_MCP_REQUIRE_AUTH", "1")
        from digigraph import mcp_server

        for headers in (
            None,
            {},
            {"Authorization": "Bearer "},
            {"Authorization": "Token abc"},
        ):
            with pytest.raises(mcp_server.McpAuthDenied):
                mcp_server._authorize_mcp_headers(headers, "digigraph:workflow")

    def test_fails_closed_when_verifier_not_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGI_MCP_REQUIRE_AUTH", "1")
        monkeypatch.delenv("DIGIKEY_JWKS_URL", raising=False)
        monkeypatch.delenv("DIGIKEY_PUBLIC_KEY_PEM", raising=False)
        from digigraph import mcp_server

        with pytest.raises(mcp_server.McpAuthDenied):
            mcp_server._authorize_mcp_headers(
                _bearer_headers(["digigraph:workflow"]), "digigraph:workflow"
            )

    def test_valid_token_with_scope_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGI_MCP_REQUIRE_AUTH", "1")
        from digigraph import mcp_server

        mcp_server._authorize_mcp_headers(
            _bearer_headers(["digigraph:workflow"]), "digigraph:workflow"
        )

    def test_wildcard_scope_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGI_MCP_REQUIRE_AUTH", "1")
        from digigraph import mcp_server

        mcp_server._authorize_mcp_headers(_bearer_headers(["*"]), "digigraph:workflow")

    def test_tampered_signature_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGI_MCP_REQUIRE_AUTH", "1")
        from digigraph import mcp_server

        head, payload, sig = _mint(scopes=["digigraph:workflow"]).split(".")
        flip = "BB" if sig.endswith("AA") else "AA"
        tampered = f"{head}.{payload}.{sig[:-2]}{flip}"
        with pytest.raises(mcp_server.McpAuthDenied):
            mcp_server._authorize_mcp_headers(_bearer(tampered), "digigraph:workflow")

    def test_expired_token_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGI_MCP_REQUIRE_AUTH", "1")
        from digigraph import mcp_server

        token = _mint(scopes=["digigraph:workflow"], ttl_sec=-30)
        with pytest.raises(mcp_server.McpAuthDenied):
            mcp_server._authorize_mcp_headers(_bearer(token), "digigraph:workflow")

    def test_wrong_audience_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGI_MCP_REQUIRE_AUTH", "1")
        from digigraph import mcp_server

        token = _mint(scopes=["digigraph:workflow"], audience="some-other-service")
        with pytest.raises(mcp_server.McpAuthDenied):
            mcp_server._authorize_mcp_headers(_bearer(token), "digigraph:workflow")

    def test_wrong_scope_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGI_MCP_REQUIRE_AUTH", "1")
        from digigraph import mcp_server

        token = _mint(scopes=["digigraph:chat"])
        with pytest.raises(mcp_server.McpAuthDenied):
            mcp_server._authorize_mcp_headers(_bearer(token), "digigraph:workflow")


class _FakeWorkflowResult(SimpleNamespace):
    pass


def _fake_workflow_result() -> _FakeWorkflowResult:
    return _FakeWorkflowResult(
        success=True,
        message="ok",
        backtest_result=None,
        research_brief=None,
        rag_sources=None,
        profiling_questions=None,
    )


@pytest.mark.unit
class TestMcpToolEnforcement:
    def test_workflow_rejects_unauthenticated_without_running(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGI_MCP_REQUIRE_AUTH", "1")
        called: dict[str, bool] = {}

        def _fake_workflow(_req: object) -> _FakeWorkflowResult:
            called["ran"] = True
            return _fake_workflow_result()

        monkeypatch.setattr("digigraph.workflow.run_digigraph_workflow", _fake_workflow)
        out = json.loads(_call_tool("workflow", None, prompt="hi"))
        assert out["success"] is False
        assert called == {}

    def test_workflow_accepts_valid_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGI_MCP_REQUIRE_AUTH", "1")
        called: dict[str, bool] = {}

        def _fake_workflow(_req: object) -> _FakeWorkflowResult:
            called["ran"] = True
            return _fake_workflow_result()

        monkeypatch.setattr("digigraph.workflow.run_digigraph_workflow", _fake_workflow)
        out = json.loads(
            _call_tool("workflow", _bearer_headers(["digigraph:workflow"]), prompt="hi")
        )
        assert out["success"] is True
        assert called.get("ran") is True

    def test_workflow_rejects_wrong_scope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGI_MCP_REQUIRE_AUTH", "1")
        called: dict[str, bool] = {}

        def _fake_workflow(_req: object) -> _FakeWorkflowResult:
            called["ran"] = True
            return _fake_workflow_result()

        monkeypatch.setattr("digigraph.workflow.run_digigraph_workflow", _fake_workflow)
        out = json.loads(
            _call_tool("workflow", _bearer_headers(["digigraph:chat"]), prompt="hi")
        )
        assert out["success"] is False
        assert called == {}

    @pytest.mark.parametrize(
        ("tool_name", "kwargs"),
        [
            ("list_orchestrator_tools", {}),
            ("list_orchestrator_tools_detailed", {}),
            ("thread_state", {"thread_id": "abc"}),
            ("chat", {"message": "hi"}),
        ],
    )
    def test_every_other_tool_rejects_unauthenticated(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tool_name: str,
        kwargs: dict[str, Any],
    ) -> None:
        monkeypatch.setenv("DIGI_MCP_REQUIRE_AUTH", "1")
        if tool_name == "chat":
            import digigraph.server as dg_server

            monkeypatch.setattr(dg_server, "app", _dummy_server_app())
        out = _call_tool(tool_name, None, **kwargs)
        assert "unauthorized" in out.lower()

    def test_every_registered_tool_enforces_auth(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGI_MCP_REQUIRE_AUTH", "1")
        import inspect

        from digigraph.mcp_server import create_mcp_server

        tools = create_mcp_server()._tool_manager.list_tools()
        assert tools
        for tool in tools:
            assert tool.context_kwarg is not None, tool.name
            source = inspect.getsource(tool.fn)
            assert "_authorize_mcp" in source, f"{tool.name} does not enforce MCP auth"
