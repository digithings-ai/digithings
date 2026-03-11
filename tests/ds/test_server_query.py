"""Unit tests for DigiSearch POST /query API (filter, columns, response_mode, summary)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digisearch.server import app
from digisearch.search import add_chunks
from digisearch.core.models import Chunk


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def indexed_results(client: TestClient) -> None:
    """Put chunks in stub index so /query returns something."""
    idx = "__unit_test_api__"
    for i in range(3):
        add_chunks(idx, [
            Chunk(
                id=f"c{i}",
                content=f"Content {i}",
                doc_id=f"d{i}",
                embedding=None,
                metadata={"sourceType": "EXCHANGE", "fromAddress": f"u{i}@test.com"},
            ),
        ])


@pytest.mark.unit
def test_query_accepts_filter_columns_response_mode(client: TestClient, indexed_results: None) -> None:
    """POST /query accepts filter, filters, columns, response_mode, summarize_if_over."""
    r = client.post(
        "/query",
        json={
            "text": "Content",
            "index_name": "__unit_test_api__",
            "top_k": 10,
            "filter": None,
            "filters": [{"field": "sourceType", "op": "eq", "value": "EXCHANGE"}],
            "columns": ["sourceType", "fromAddress"],
            "response_mode": "full",
            "summarize_if_over": 100,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert "query" in data
    assert "total" in data
    assert data.get("summary") is None  # full mode, no threshold exceeded


@pytest.mark.unit
def test_query_response_mode_summary_returns_summary(client: TestClient, indexed_results: None) -> None:
    """When response_mode=summary, response includes summary with data_summary and text_summary."""
    r = client.post(
        "/query",
        json={
            "text": "Content",
            "index_name": "__unit_test_api__",
            "top_k": 10,
            "response_mode": "summary",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert "summary" in data
    summary = data["summary"]
    assert isinstance(summary, dict)
    assert "data_summary" in summary
    assert summary["data_summary"]["total_rows"] >= 0
    assert "counts" in summary["data_summary"]
    assert "text_summary" in summary


@pytest.mark.unit
def test_query_summarize_if_over_returns_summary(client: TestClient, indexed_results: None) -> None:
    """When result count > summarize_if_over, response includes summary."""
    r = client.post(
        "/query",
        json={
            "text": "Content",
            "index_name": "__unit_test_api__",
            "top_k": 10,
            "summarize_if_over": 1,
        },
    )
    assert r.status_code == 200
    data = r.json()
    # We have 3 chunks matching; 3 > 1 so summary should be present
    assert data.get("total", 0) >= 1
    if data["total"] > 1:
        assert "summary" in data
        assert isinstance(data["summary"], dict)
