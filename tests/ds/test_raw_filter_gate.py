"""Raw OData filter must be rejected at the server when the index disallows it (#3909).

Defect 3: `POST /query` and `/v1/research_turn` accepted a raw `filter` regardless of the
configured index's ``allow_raw_filter``; only Azure re-gated it. Per digisearch/AGENTS.md,
raw OData is opt-in and only safe for trusted callers.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from digisearch.core.models import Chunk
from digisearch.search import add_chunks
from digisearch.server import app
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


@pytest.fixture
def write_index_config(tmp_path: Path) -> Callable[[bool], str]:
    """Write a one-index config YAML and return its path."""

    def _write(allow_raw_filter: bool) -> str:
        path = tmp_path / f"index-{allow_raw_filter}.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "index_name": "default",
                    "allow_raw_filter": allow_raw_filter,
                }
            ),
            encoding="utf-8",
        )
        return str(path)

    return _write


@pytest.mark.unit
def test_query_rejects_raw_filter_when_index_disallows(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    write_index_config: Callable[[bool], str],
) -> None:
    monkeypatch.setenv("DIGISEARCH_INDEX_CONFIG", write_index_config(False))
    r = client.post(
        "/query",
        json={
            "text": "anything",
            "index_name": "default",
            "filter": "sourceType eq 'EXCHANGE'",
        },
    )
    assert r.status_code == 400, r.text
    assert "raw" in r.text.lower()


@pytest.mark.unit
def test_query_allows_raw_filter_when_index_permits(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    write_index_config: Callable[[bool], str],
) -> None:
    monkeypatch.setenv("DIGISEARCH_INDEX_CONFIG", write_index_config(True))
    r = client.post(
        "/query",
        json={
            "text": "anything",
            "index_name": "default",
            "filter": "sourceType eq 'EXCHANGE'",
        },
    )
    assert r.status_code == 200, r.text


@pytest.mark.unit
def test_query_rejects_raw_filter_by_default_when_no_config(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DIGISEARCH_INDEX_CONFIG", raising=False)
    monkeypatch.delenv("DIGISEARCH_CONFIG_PATH", raising=False)
    r = client.post(
        "/query",
        json={
            "text": "anything",
            "index_name": "default",
            "filter": "sourceType eq 'EXCHANGE'",
        },
    )
    assert r.status_code == 400, r.text


@pytest.mark.unit
def test_research_turn_rejects_raw_filter_when_index_disallows(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    write_index_config: Callable[[bool], str],
) -> None:
    add_chunks(
        "__raw_filter_research__",
        [
            Chunk(
                id="rf1",
                content="Risk parity overview",
                doc_id="rf-doc",
                embedding=None,
                metadata={},
            )
        ],
    )
    monkeypatch.setenv("DIGISEARCH_INDEX_CONFIG", write_index_config(False))
    r = client.post(
        "/v1/research_turn",
        json={
            "user_message": "risk",
            "index_name": "__raw_filter_research__",
            "top_k": 3,
            "filter": "sourceType eq 'EXCHANGE'",
        },
    )
    assert r.status_code == 400, r.text
    assert "raw" in r.text.lower()
