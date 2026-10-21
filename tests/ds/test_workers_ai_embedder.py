"""Unit tests for the Workers AI bge-m3 embedder (custom endpoint + account path).

No network. Token values must not appear in errors.
"""

from __future__ import annotations

import io
import json
from email.message import Message
from typing import Any
from urllib.error import HTTPError, URLError

import pytest
from digisearch.embedding.factory import EmbeddingConfigError, _build_raw_provider
from digisearch.embedding.providers import workers_ai as workers_ai_module
from digisearch.embedding.providers.workers_ai import (
    BGE_M3_DIMENSIONS,
    BGE_M3_MODEL_ID,
    FACTORY_NAMES,
    WorkersAiEmbedder,
    provider_for,
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


def test_provider_for_accepts_only_bge_m3() -> None:
    """Only bge-m3 resolves here, and it ships one model id."""
    built = provider_for("@cf/baai/bge-m3", None)
    assert isinstance(built, WorkersAiEmbedder)
    assert provider_for("bge-m3", None) is not None
    assert provider_for("minilm", None) is None
    with pytest.raises(EmbeddingConfigError, match="single model"):
        provider_for("bge-m3", "text-embedding-3-small")


def test_factory_builds_bge_m3_before_the_unknown_provider_error() -> None:
    """bge-m3 is built, not reported as an unknown provider."""
    built = _build_raw_provider("@cf/baai/bge-m3", None)
    assert isinstance(built, WorkersAiEmbedder)
    assert isinstance(_build_raw_provider("bge-m3", None), WorkersAiEmbedder)
    with pytest.raises(EmbeddingConfigError, match="unknown embedding provider"):
        _build_raw_provider("not-a-provider", None)


def test_injected_embedder_reports_1024_and_the_model_id() -> None:
    """The dimension contract: bge-m3 vectors are 1024-dim, never 384."""
    provider = WorkersAiEmbedder(embed_fn=lambda texts: [[0.25] * BGE_M3_DIMENSIONS for _ in texts])
    assert provider.model_id == "@cf/baai/bge-m3"
    assert provider.model_id == BGE_M3_MODEL_ID
    assert provider.dimensions == 1024
    assert BGE_M3_MODEL_ID in FACTORY_NAMES
    assert provider.embed([]) == []
    vectors = provider.embed(["hello", "hallo"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 1024


def test_missing_credentials_do_not_echo_a_token() -> None:
    """The config error names the variable, never the value."""
    # No account id: the account-scoped path cannot be built.
    provider = WorkersAiEmbedder(account_id="", api_token="super-secret-token")
    with pytest.raises(EmbeddingConfigError, match="CLOUDFLARE_API_TOKEN") as caught:
        provider.embed(["hello"])
    assert "super-secret-token" not in str(caught.value)

    # No token at all: the token-only path cannot be called.
    provider = WorkersAiEmbedder(account_id="acct", api_token="")
    with pytest.raises(EmbeddingConfigError, match="CLOUDFLARE_API_TOKEN") as caught:
        provider.embed(["hello"])
    assert "super-secret-token" not in str(caught.value)

    # A configured endpoint does not change that: the token is still required.
    provider = WorkersAiEmbedder(url="https://embed.example/embed", account_id="acct", api_token="")
    with pytest.raises(EmbeddingConfigError, match="CLOUDFLARE_API_TOKEN") as caught:
        provider.embed(["hello"])
    assert "super-secret-token" not in str(caught.value)


def test_the_environment_token_does_not_leak_into_the_config_error(monkeypatch) -> None:
    """The token usually comes from the environment; it must not reach an error."""
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "super-secret-token")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    provider = WorkersAiEmbedder()
    with pytest.raises(EmbeddingConfigError, match="CLOUDFLARE_ACCOUNT_ID") as caught:
        provider.embed(["hello"])
    assert "super-secret-token" not in str(caught.value)


def test_http_error_hides_the_body_and_the_token() -> None:
    """An upstream 401 must not carry the body or the token into the error."""
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


def test_network_error_hides_the_reason() -> None:
    """A network failure must not carry the underlying reason into the error."""

    def opener(_request):
        raise URLError("super-secret-token user@example.com")

    provider = WorkersAiEmbedder(
        account_id="account", api_token="super-secret-token", opener=opener
    )
    with pytest.raises(
        EmbeddingConfigError, match=r"workers ai embed failed \(network\)"
    ) as caught:
        provider.embed(["user@example.com"])
    assert "super-secret-token" not in str(caught.value)
    assert "user@example.com" not in str(caught.value)


def test_parses_a_result_payload() -> None:
    provider = WorkersAiEmbedder(
        account_id="account",
        api_token="token",
        opener=_opener([], _vectors()),
    )
    vectors = provider.embed(["Guten Tag"])
    assert len(vectors) == 1
    assert len(vectors[0]) == BGE_M3_DIMENSIONS


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
