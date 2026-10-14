"""Query-side bge-m3 embedder. No network. Token values must not appear in errors."""

from __future__ import annotations

import json

import pytest
from digisearch.embedding.factory import EmbeddingConfigError
from digisearch.embedding.providers.workers_ai import (
    BGE_M3_DIMENSIONS,
    BGE_M3_MODEL_ID,
    FACTORY_NAMES,
    WorkersAiEmbedder,
)

pytestmark = pytest.mark.unit


def test_provider_for_accepts_only_bge_m3() -> None:
    from digisearch.embedding.providers.workers_ai import provider_for

    built = provider_for("@cf/baai/bge-m3", None)
    assert isinstance(built, WorkersAiEmbedder)
    assert provider_for("bge-m3", None) is not None
    assert provider_for("minilm", None) is None
    with pytest.raises(EmbeddingConfigError, match="single model"):
        provider_for("bge-m3", "text-embedding-3-small")


def test_factory_builds_bge_m3_before_the_unknown_provider_error() -> None:
    from digisearch.embedding.factory import _build_raw_provider

    built = _build_raw_provider("@cf/baai/bge-m3", None)
    assert isinstance(built, WorkersAiEmbedder)
    assert isinstance(_build_raw_provider("bge-m3", None), WorkersAiEmbedder)
    with pytest.raises(EmbeddingConfigError, match="unknown embedding provider"):
        _build_raw_provider("not-a-provider", None)


def test_injected_embedder_reports_1024_and_the_model_id() -> None:
    provider = WorkersAiEmbedder(
        embed_fn=lambda texts: [[0.25] * BGE_M3_DIMENSIONS for _ in texts]
    )
    assert provider.model_id == "@cf/baai/bge-m3"
    assert provider.model_id == BGE_M3_MODEL_ID
    assert provider.dimensions == 1024
    assert BGE_M3_MODEL_ID in FACTORY_NAMES
    assert provider.embed([]) == []
    vectors = provider.embed(["hello", "hallo"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 1024


def test_missing_credentials_do_not_echo_a_token() -> None:
    provider = WorkersAiEmbedder(account_id="", api_token="super-secret-token")
    with pytest.raises(EmbeddingConfigError, match="CLOUDFLARE_API_TOKEN") as caught:
        provider.embed(["hello"])
    assert "super-secret-token" not in str(caught.value)


def test_http_error_hides_the_body_and_the_token() -> None:
    import io
    from email.message import Message
    from urllib.error import HTTPError

    secret = "super-secret-token"

    def opener(_request):
        raise HTTPError(
            "https://api.cloudflare.com/ai",
            401,
            "denied",
            hdrs=Message(),
            fp=io.BytesIO(b"super-secret-token user@example.com"),
        )

    provider = WorkersAiEmbedder(account_id="account", api_token=secret, opener=opener)
    with pytest.raises(EmbeddingConfigError, match=r"workers ai embed failed \(401\)") as caught:
        provider.embed(["user@example.com"])
    assert secret not in str(caught.value)
    assert "user@example.com" not in str(caught.value)


def test_parses_a_result_payload() -> None:
    class Response:
        def read(self) -> bytes:
            payload = {"result": {"data": [[0.5] * BGE_M3_DIMENSIONS]}}
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    provider = WorkersAiEmbedder(
        account_id="account",
        api_token="token",
        opener=lambda _request: Response(),
    )
    vectors = provider.embed(["Guten Tag"])
    assert len(vectors) == 1
    assert len(vectors[0]) == BGE_M3_DIMENSIONS


def test_stub_uses_workers_ai_only_for_listed_indexes(monkeypatch) -> None:
    from digisearch.embedding.providers.workers_ai import WorkersAiEmbedder
    from digisearch.search import _stub

    monkeypatch.setenv("DIGISEARCH_WORKERS_AI_INDEXES", "occ-tickets, other-bge")
    monkeypatch.setattr(_stub, "_resolved_embedding_provider", lambda: "default")
    got = _stub._embedding_provider_for("occ-tickets", "acct", "tok")
    assert isinstance(got, WorkersAiEmbedder)
    assert _stub._embedding_provider_for("occ_help", "acct", "tok") == "default"


def test_stub_prefers_worker_embed_url(monkeypatch) -> None:
    from digisearch.search import _stub

    monkeypatch.setenv("DIGISEARCH_WORKERS_AI_INDEXES", "occ-tickets")
    monkeypatch.setenv("DIGISEARCH_BGE_M3_EMBED_URL", "https://corpus-index.example/embed")
    monkeypatch.setenv("DIGISEARCH_BGE_M3_EMBED_TOKEN", "t")
    got = _stub._embedding_provider_for("occ-tickets", "", "")
    assert got._url == "https://corpus-index.example/embed"
