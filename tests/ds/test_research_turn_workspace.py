"""research_turn workspace scoping (#3909 defect 2).

The research path previously ran `build_query_filters(...)` without `workspace_id`
and built `Query(...)` without `workspace_id`, so multi-tenant deployments silently
retrieved across tenants on `/v1/research_turn`, the orchestrator
`digisearch_research_delegate` tool, and the MCP research tool. This file pins the
direct-pipeline and HTTP scoping behavior.
"""

from __future__ import annotations

import pytest
from digisearch.agent.pipeline import run_research_turn
from digisearch.core.models import Chunk
from digisearch.search import add_chunks
from digisearch.server import app
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


@pytest.mark.unit
def test_run_research_turn_scopes_to_workspace() -> None:
    idx = "__agent_turn_ws__"
    add_chunks(
        idx,
        [
            Chunk(
                id="ws-a-1",
                content="Momentum alpha details",
                doc_id="doc-a",
                embedding=None,
                metadata={"workspace_id": "ws-a"},
            ),
            Chunk(
                id="ws-b-1",
                content="Momentum beta details",
                doc_id="doc-b",
                embedding=None,
                metadata={"workspace_id": "ws-b"},
            ),
        ],
    )
    out = run_research_turn(
        {
            "user_message": "momentum",
            "index_name": idx,
            "top_k": 10,
            "workspace_id": "ws-a",
        }
    )
    assert out.get("error") is None
    doc_ids = {r.get("doc_id") for r in out.get("results", [])}
    assert doc_ids == {"doc-a"}


@pytest.mark.unit
def test_api_v1_research_turn_scopes_to_workspace(client: TestClient) -> None:
    idx = "__agent_http_ws__"
    add_chunks(
        idx,
        [
            Chunk(
                id="http-a-1",
                content="Risk parity alpha",
                doc_id="http-a",
                embedding=None,
                metadata={"workspace_id": "ws-a"},
            ),
            Chunk(
                id="http-b-1",
                content="Risk parity beta",
                doc_id="http-b",
                embedding=None,
                metadata={"workspace_id": "ws-b"},
            ),
        ],
    )
    r = client.post(
        "/v1/research_turn",
        json={
            "user_message": "risk parity",
            "index_name": idx,
            "top_k": 10,
            "workspace_id": "ws-a",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("total", 0) == 1
    hits = data.get("results", [])
    assert hits and all(h.get("metadata", {}).get("workspace_id") == "ws-a" for h in hits)
