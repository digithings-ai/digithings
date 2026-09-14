"""Unit tests for POST /v1/orchestrator_invoke (hub dispatch)."""

from __future__ import annotations

import pytest
from digisearch.core.models import Chunk
from digisearch.search import add_chunks
from digisearch.server import app
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


@pytest.fixture
def indexed(client: TestClient) -> None:
    idx = "__orch_invoke__"
    for i in range(5):
        add_chunks(
            idx,
            [
                Chunk(
                    id=f"o{i}",
                    content=f"Orchestrator doc {i}",
                    doc_id=f"d{i}",
                    embedding=None,
                    metadata={"workspace_id": "ws-a"},
                ),
            ],
        )


@pytest.mark.unit
def test_orchestrator_invoke_digisearch(client: TestClient, indexed: None) -> None:
    r = client.post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digisearch",
            "arguments": {"query": "Orchestrator", "index_name": "__orch_invoke__", "top_k": 2},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("tool") == "digisearch"
    assert len(body.get("data", {}).get("results", [])) <= 2


@pytest.mark.unit
def test_orchestrator_invoke_fetch_all_respects_cap(
    client: TestClient, indexed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGISEARCH_FETCH_ALL_DEFAULT_MAX", "3")
    monkeypatch.setenv("DIGISEARCH_FETCH_ALL_HARD_CEILING", "5")
    r = client.post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digisearch_fetch_all",
            "arguments": {
                "query": "Orchestrator",
                "index_name": "__orch_invoke__",
                "max_results": 100,
            },
        },
    )
    assert r.status_code == 200
    data = r.json().get("data") or {}
    assert data.get("total", 0) <= 5
    assert data.get("possibly_truncated") is False


@pytest.mark.unit
def test_orchestrator_invoke_fetch_all_flags_vectorize_clamp_truncation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I4 repro: a Vectorize page capped at MAX_TOP_K must set `possibly_truncated`
    rather than silently reporting the collected result set as complete."""
    import digisearch.server as server_module
    from digisearch.indexes.backends.vectorize import MAX_TOP_K

    def _fake_run_query(req: object) -> server_module.QueryResponse:
        results = [{"id": f"r{i}"} for i in range(MAX_TOP_K)]
        return server_module.QueryResponse(
            results=results,
            query=getattr(req, "text", ""),
            index_name=getattr(req, "index_name", "any"),
            total=len(results),
            backend="vectorize",
        )

    monkeypatch.setattr(server_module, "run_query", _fake_run_query)

    r = client.post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digisearch_fetch_all",
            "arguments": {"query": "x", "index_name": "any", "max_results": 1000},
        },
    )
    assert r.status_code == 200
    data = r.json().get("data") or {}
    assert data.get("possibly_truncated") is True
    assert data.get("total") == MAX_TOP_K


@pytest.mark.unit
def test_orchestrator_invoke_unknown_tool(client: TestClient) -> None:
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "not_a_real_tool", "arguments": {}},
    )
    assert r.status_code == 400
    body = r.json()
    msg = body.get("detail") or body.get("error", {}).get("message", "")
    assert "Unknown orchestrator tool" in msg


def _fake_web_search_run(monkeypatch: pytest.MonkeyPatch) -> list:
    import digisearch.web_search.service as svc_module
    from digisearch.web_search.models import WebSearchResponse

    seen: list = []

    def _fake_run(req):
        seen.append(req)
        return WebSearchResponse(query=req.query, results=[], provider="searxng")

    monkeypatch.setattr(svc_module, "run_web_search", _fake_run)
    return seen


@pytest.mark.unit
def test_orchestrator_invoke_web_search_clamps_max_results(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _fake_web_search_run(monkeypatch)
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "web_search", "arguments": {"query": "etf flows", "max_results": 100}},
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True
    assert seen and seen[0].max_results == 10


@pytest.mark.unit
def test_orchestrator_invoke_web_search_coerces_int_like(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _fake_web_search_run(monkeypatch)
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "web_search", "arguments": {"query": "etf flows", "max_results": "6"}},
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True
    assert seen and seen[0].max_results == 6


@pytest.mark.unit
def test_orchestrator_invoke_web_search_rejects_bad_max_results(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _fake_web_search_run(monkeypatch)
    for bad in (True, "garbage", 2.5, [4]):
        r = client.post(
            "/v1/orchestrator_invoke",
            json={"tool": "web_search", "arguments": {"query": "etf flows", "max_results": bad}},
        )
        assert r.status_code == 200, bad
        body = r.json()
        assert body.get("ok") is False, bad
        assert "max_results" in (body.get("error") or ""), bad
    assert seen == []


@pytest.mark.unit
def test_orchestrator_invoke_web_search_invalid_query_is_ok_false(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _fake_web_search_run(monkeypatch)
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "web_search", "arguments": {"query": "x" * 501}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert "query" in (body.get("error") or "")
    assert seen == []


@pytest.mark.unit
def test_orchestrator_invoke_web_search_bad_backend_is_ok_false(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bad DIGISEARCH_WEB_SEARCH_BACKEND must fail closed (ok:False), never 500."""
    monkeypatch.setenv("DIGISEARCH_WEB_SEARCH_BACKEND", "bogus")
    r = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "web_search", "arguments": {"query": "etf flows"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert "bogus" in (body.get("error") or "")


@pytest.mark.unit
def test_v1_web_search_bad_backend_is_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bad DIGISEARCH_WEB_SEARCH_BACKEND must fail closed-loud (503), never 500."""
    monkeypatch.setenv("DIGISEARCH_WEB_SEARCH_BACKEND", "bogus")
    r = client.post("/v1/web_search", json={"query": "etf flows"})
    assert r.status_code == 503
    assert "bogus" in r.text


@pytest.mark.unit
def test_orchestrator_failing_web_search_surfaced_fail_hard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failing web_search surfaces fail-hard through execute()/registry (#3871).

    Pins actual surfacing: the registry execute path does not catch tool
    failures, so a downed web_search raises instead of returning an envelope.
    Patches the public call_digisearch_web_search wrapper, never the private one.
    """
    from digigraph.orchestration import builtin  # noqa: F401 - registration
    from digigraph.orchestration import web_search_tools as ws_mod
    from digigraph.orchestration.registry import ToolContext, execute

    def _down(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("down")

    monkeypatch.setattr(ws_mod, "call_digisearch_web_search", _down)
    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={"enable_web_search": True},
        allowed_tool_names=frozenset({ws_mod.WEB_SEARCH_TOOL_NAME}),
    )
    with pytest.raises(RuntimeError, match="down"):
        execute(ws_mod.WEB_SEARCH_TOOL_NAME, {"query": "x"}, ctx)
