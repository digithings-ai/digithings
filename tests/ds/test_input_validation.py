"""Pydantic v2 HTTP input-validation tests for DigiSearch request bodies."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DIGISEARCH_ALLOW_STUB", "1")
    from digisearch.server import app  # imported after env gate

    from tests.digi_test_jwt import auth_headers

    return TestClient(app, headers=auth_headers())


@pytest.mark.unit
class TestQueryValidation:
    """POST /query → QueryRequest (extra='forbid')."""

    def test_missing_required_text_returns_422(self, client: TestClient) -> None:
        r = client.post("/query", json={"top_k": 5})
        assert r.status_code == 422
        assert r.json().get("error", {}).get("code") == "validation_error"

    def test_extra_field_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/query",
            json={"text": "hi", "sneaky": "no"},
        )
        assert r.status_code == 422
        assert r.json().get("error", {}).get("code") == "validation_error"

    def test_top_k_out_of_range_returns_422(self, client: TestClient) -> None:
        r = client.post("/query", json={"text": "hi", "top_k": 9999})
        assert r.status_code == 422


@pytest.mark.unit
class TestIngestValidation:
    """POST /ingest → IngestRequest (extra='forbid')."""

    def test_missing_required_source_returns_422(self, client: TestClient) -> None:
        r = client.post("/ingest", json={"index_name": "default"})
        assert r.status_code == 422

    def test_extra_field_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/ingest",
            json={"source": "/tmp/x.pdf", "wrong": 1},
        )
        assert r.status_code == 422
