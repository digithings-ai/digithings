"""Unit tests for the multilingual embedding provider + occ_tickets backfill (#4756)."""

from __future__ import annotations

import pytest
from digisearch.embedding.factory import (
    _build_raw_provider,
    resolve_embedding_pipeline,
    unwrap_embedding_provider,
)
from digisearch.embedding.providers import multilingual as multilingual_module
from digisearch.embedding.providers.multilingual import (
    MULTILINGUAL_DIMENSIONS,
    MULTILINGUAL_MODEL_ID,
    MultilingualEmbedder,
    get_default_multilingual_embedder,
)

from scripts.index_occ_tickets import SNAPSHOT_DATE, build_ticket_chunks

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_multilingual_singleton():
    multilingual_module._default_multilingual_singleton = None
    try:
        yield
    finally:
        multilingual_module._default_multilingual_singleton = None


def test_multilingual_embedder_reports_model_and_dimensions() -> None:
    provider = MultilingualEmbedder(embed_fn=lambda texts: [[0.5] * MULTILINGUAL_DIMENSIONS])
    assert provider.model_id == MULTILINGUAL_MODEL_ID
    assert provider.dimensions == MULTILINGUAL_DIMENSIONS == 384
    assert provider.embed([]) == []
    vectors = provider.embed(["hello"])
    assert len(vectors) == 1 and len(vectors[0]) == MULTILINGUAL_DIMENSIONS
    assert all(isinstance(x, float) for x in vectors[0])


def test_multilingual_default_singleton_is_shared() -> None:
    assert get_default_multilingual_embedder() is get_default_multilingual_embedder()


def test_factory_builds_multilingual_provider() -> None:
    provider = _build_raw_provider("multilingual", None)
    assert isinstance(provider, MultilingualEmbedder)


def test_factory_resolves_multilingual_pipeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path=None
) -> None:
    monkeypatch.setenv("DIGISEARCH_EMBEDDING_PROVIDER", "multilingual")
    monkeypatch.setenv("DIGISEARCH_EMBED_CACHE", "0")
    monkeypatch.delenv("DIGISEARCH_EMBED", raising=False)
    pipeline = resolve_embedding_pipeline()
    assert pipeline is not None
    assert isinstance(unwrap_embedding_provider(pipeline), MultilingualEmbedder)


def test_build_ticket_chunks_full_metadata_no_masking() -> None:
    ticket = {
        "id": 231,
        "number": "28312",
        "title": "Example ticket subject",
        "state": "open",
        "group": "Sitaas",
        "priority": "2 normal",
        "customer": "jane.doe@example.test",
        "customer_id": 7,
        "owner": "ada",
        "created_at": "2026-09-15T12:00:00.000Z",
        "updated_at": "2026-09-16T12:00:00.000Z",
    }
    articles = [
        {
            "id": 1,
            "sender": "Customer",
            "type": "web",
            "internal": False,
            "from": "jane.doe@example.test",
            "subject": "Login fails",
            "body": "<p>Cannot log in since Monday</p>",
            "created_at": "2026-09-15T12:00:00.000Z",
        },
        {
            "id": 2,
            "sender": "Agent",
            "type": "note",
            "internal": True,
            "from": "support@example.test",
            "body": "<p>internal-only note body</p>",
            "created_at": "2026-09-15T13:00:00.000Z",
        },
    ]
    chunks = build_ticket_chunks(ticket, articles, customer_name="Jane Doe")
    assert len(chunks) == 2
    first, second = chunks
    assert first.id == "zammad-231-1"
    assert first.doc_id == "zammad-ticket-231"
    # Full customer identity, filterable id, snapshot marker.
    assert first.metadata["customer"] == "jane.doe@example.test"
    assert first.metadata["customer_id"] == 7
    assert first.metadata["customer_name"] == "Jane Doe"
    assert first.metadata["snapshot_date"] == SNAPSHOT_DATE
    assert first.metadata["internal"] is False
    assert "***" not in first.content
    # Internal articles are indexed too (tagged, not omitted).
    assert second.metadata["internal"] is True
    assert "[internal]" in second.content
    assert "internal-only note body" in second.content
