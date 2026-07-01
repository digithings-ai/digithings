"""Unit tests for POST /v1/orchestrator_invoke (hub dispatch)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digisearch.server import app
from digisearch.search import add_chunks
from digisearch.core.models import Chunk
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
