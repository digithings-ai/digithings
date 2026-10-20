"""Unit tests for the Workers AI bge-m3 embedder (custom endpoint + account path)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from digisearch.embedding.factory import EmbeddingConfigError
from digisearch.embedding.providers import workers_ai as workers_ai_module
from digisearch.embedding.providers.workers_ai import (
    BGE_M3_DIMENSIONS,
    BGE_M3_MODEL_ID,
    WorkersAiEmbedder,
)
from digisearch.search._stub import _embedding_provider_for

pytestmark = pytest.mark.unit


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _opener(seen: list[Any], payload: dict[str, Any]):
    def opener(request):
        seen.append(request)
        return _Response(json.dumps(payload).encode())

    return opener


def _vectors() -> dict[str, Any]:
    return {"result": {"data": [[0.5] * BGE_M3_DIMENSIONS]}}


def test_custom_endpoint_is_used_and_needs_no_account_id(monkeypatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    seen: list[Any] = []
    provider = WorkersAiEmbedder(
        url="https://embed.example/embed",
        api_token="tok",
        opener=_opener(seen, _vectors()),
    )
    vectors = provider.embed(["hello"])
    assert len(vectors) == 1 and len(vectors[0]) == BGE_M3_DIMENSIONS
    assert len(seen) == 1
    assert seen[0].full_url == "https://embed.example/embed"
    assert seen[0].get_header("Authorization") == "Bearer tok"


def test_default_endpoint_still_needs_an_account_id(monkeypatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    provider = WorkersAiEmbedder(api_token="tok")
    with pytest.raises(EmbeddingConfigError, match="CLOUDFLARE_ACCOUNT_ID"):
        provider.embed(["hello"])


def test_default_endpoint_is_the_account_scoped_workers_ai_url(monkeypatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    seen: list[Any] = []
    provider = WorkersAiEmbedder(
        account_id="acct", api_token="tok", opener=_opener(seen, _vectors())
    )
    provider.embed(["hello"])
    assert seen[0].full_url == (
        f"https://api.cloudflare.com/client/v4/accounts/acct/ai/run/{BGE_M3_MODEL_ID}"
    )


def test_search_provider_uses_the_configured_embed_endpoint(monkeypatch) -> None:
    """The query side must not raise on the documented-preferred path."""
    monkeypatch.setenv("DIGISEARCH_WORKERS_AI_INDEXES", "occ")
    monkeypatch.setenv("DIGISEARCH_BGE_M3_EMBED_URL", "https://embed.example/embed")
    monkeypatch.setenv("DIGISEARCH_BGE_M3_EMBED_TOKEN", "tok")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    seen: list[Any] = []
    monkeypatch.setattr(workers_ai_module, "urlopen", _opener(seen, _vectors()))
    provider = _embedding_provider_for("occ", "acct", "vtok")
    assert isinstance(provider, WorkersAiEmbedder)
    vectors = provider.embed(["hello"])
    assert len(vectors) == 1
    assert seen[0].full_url == "https://embed.example/embed"
    assert seen[0].get_header("Authorization") == "Bearer tok"
