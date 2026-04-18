"""DigiSearch composite research turn (agent graph + HTTP)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digisearch.agent.pipeline import run_research_turn
from digisearch.search import add_chunks
from digisearch.core.models import Chunk
from digisearch.server import app
from tests.digi_test_jwt import auth_headers


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


@pytest.mark.unit
def test_run_research_turn_aggregates_citations() -> None:
    idx = "__agent_turn__"
    add_chunks(idx, [
        Chunk(
            id="c1",
            content="Momentum factor details",
            doc_id="d1",
            embedding=None,
            metadata={"evidence_tier": "peer_reviewed", "title": "FactPaper"},
        ),
    ])
    out = run_research_turn({
        "user_message": "momentum",
        "index_name": idx,
        "top_k": 5,
    })
    assert out.get("error") is None
    assert out.get("service") == "digisearch"
    assert out.get("total", 0) >= 1
    assert out.get("rag_sources")
    assert "Momentum" in (out.get("formatted_context") or "")


@pytest.mark.unit
def test_api_v1_research_turn(client: TestClient) -> None:
    idx = "__agent_http__"
    add_chunks(idx, [
        Chunk(
            id="c2",
            content="Risk parity overview",
            doc_id="doc-rp",
            embedding=None,
            metadata={"sourceType": "PDF"},
        ),
    ])
    r = client.post(
        "/v1/research_turn",
        json={"user_message": "risk", "index_name": idx, "top_k": 3},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("service") == "digisearch"
    assert data.get("rag_sources")
