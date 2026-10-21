"""Query-side bge-m3 embedder. No network.

The provider's credential never reaches an error: every message names the
failure class (or the variable to set) only, and no configured credential value
appears in the message or in the text an operator sees.
"""

from __future__ import annotations

import io
import json
import traceback
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

#: The credential value that must never reach an error.
SECRET = "super-secret-token"
#: A configured account id: not a secret, but it must not be echoed either.
ACCOUNT_VALUE = "acct-9f3b"


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


def _displayed(exc: BaseException) -> str:
    """The exception text a logger prints: the message plus the displayed chain.

    Source lines are left out on purpose: the question is what the error
    carries, not where it was raised.
    """
    parts: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        parts.append("".join(traceback.format_exception_only(current)))
        if current.__cause__ is not None:
            current = current.__cause__
        elif current.__context__ is not None and not current.__suppress_context__:
            current = current.__context__
        else:
            current = None
    return "".join(parts)


def test_provider_for_accepts_only_bge_m3() -> None:
    """Only bge-m3 resolves here, and it ships one model id."""
    built = provider_for(BGE_M3_MODEL_ID, None)
    assert isinstance(built, WorkersAiEmbedder)
    assert provider_for("bge-m3", None) is not None
    assert provider_for("minilm", None) is None
    # The model may be named by either alias; any other model id is refused.
    assert provider_for("bge-m3", BGE_M3_MODEL_ID) is not None
    assert provider_for(BGE_M3_MODEL_ID, "bge-m3") is not None
    with pytest.raises(EmbeddingConfigError, match="single model"):
        provider_for("bge-m3", "text-embedding-3-small")


def test_provider_for_normalises_the_provider_name() -> None:
    """Case and surrounding whitespace do not change which provider is built."""
    assert provider_for("BGE-M3", None) is not None
    assert provider_for("  bge-m3  ", None) is not None
    assert provider_for(" @CF/BAAI/BGE-M3 ", None) is not None


def test_the_factory_names_match_the_names_provider_for_accepts() -> None:
    """FACTORY_NAMES declares the names the factory accepts; the two agree.

    Both directions are pinned: a name declared but not built, and a name built
    but not declared, are both drift.
    """
    assert BGE_M3_MODEL_ID in FACTORY_NAMES
    assert set(FACTORY_NAMES) == {BGE_M3_MODEL_ID, "bge-m3"}
    for name in FACTORY_NAMES:
        assert provider_for(name, None) is not None
    assert provider_for("minilm", None) is None


def test_factory_builds_bge_m3_before_the_unknown_provider_error() -> None:
    """bge-m3 is built, not reported as an unknown provider."""
    built = _build_raw_provider(BGE_M3_MODEL_ID, None)
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
    vectors = provider.embed(["hello", "hallo"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 1024


def test_an_empty_batch_never_reaches_the_network() -> None:
    """An empty batch is answered locally: no request, no vectors."""
    seen: list[Any] = []
    provider = WorkersAiEmbedder(
        account_id=ACCOUNT_VALUE,
        api_token=SECRET,
        opener=_opener(seen, _vectors()),
    )
    assert provider.embed([]) == []
    assert seen == []


def test_missing_credentials_do_not_echo_a_token() -> None:
    """The config error names the variable to set, never the value."""
    # No account id: the account-scoped path cannot be built. The token is set
    # here, so this is where a token leak would show.
    provider = WorkersAiEmbedder(account_id="", api_token=SECRET)
    with pytest.raises(EmbeddingConfigError, match="CLOUDFLARE_ACCOUNT_ID") as caught:
        provider.embed(["hello"])
    assert SECRET not in str(caught.value)
    assert SECRET not in _displayed(caught.value)

    # No token: the request cannot be authorised. The token is empty here, so
    # the account id is the configured value that could leak.
    provider = WorkersAiEmbedder(account_id=ACCOUNT_VALUE, api_token="")
    with pytest.raises(EmbeddingConfigError, match="CLOUDFLARE_API_TOKEN") as caught:
        provider.embed(["hello"])
    assert ACCOUNT_VALUE not in str(caught.value)

    # A configured endpoint does not change that: the token is still required.
    provider = WorkersAiEmbedder(
        url="https://embed.example/embed", account_id=ACCOUNT_VALUE, api_token=""
    )
    with pytest.raises(EmbeddingConfigError, match="CLOUDFLARE_API_TOKEN") as caught:
        provider.embed(["hello"])
    assert ACCOUNT_VALUE not in str(caught.value)
    assert "embed.example" not in str(caught.value)


def test_the_environment_token_does_not_leak_into_the_config_error(monkeypatch) -> None:
    """The token usually comes from the environment; it must not reach an error."""
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", SECRET)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    provider = WorkersAiEmbedder()
    with pytest.raises(EmbeddingConfigError, match="CLOUDFLARE_ACCOUNT_ID") as caught:
        provider.embed(["hello"])
    assert SECRET not in str(caught.value)
    assert SECRET not in _displayed(caught.value)


def test_http_error_hides_the_body_and_the_token() -> None:
    """An upstream 401 must not carry the body or the token into the error."""

    def opener(_request):
        raise HTTPError(
            "https://api.cloudflare.com/ai",
            401,
            "denied",
            hdrs=Message(),
            fp=io.BytesIO(b"super-secret-token user@example.com"),
        )

    provider = WorkersAiEmbedder(account_id=ACCOUNT_VALUE, api_token=SECRET, opener=opener)
    with pytest.raises(EmbeddingConfigError) as caught:
        provider.embed(["user@example.com"])
    error = caught.value
    assert str(error) == "workers ai embed failed (401)"
    assert SECRET not in str(error)
    assert "user@example.com" not in str(error)
    assert ACCOUNT_VALUE not in str(error)
    assert SECRET not in _displayed(error)
    # The upstream response is dropped from the chain (`from None`), so a body
    # that echoes the credential never rides along.
    assert error.__cause__ is None
    assert error.__suppress_context__ is True


def test_the_network_error_names_only_the_failure_class() -> None:
    """A transport failure names the class; the reason stays available.

    The credential is sent in the Authorization header, so a transport reason
    cannot carry it. The reason is chained for diagnosis rather than swallowed.
    """

    def opener(_request):
        raise URLError(ConnectionRefusedError(61, "Connection refused"))

    provider = WorkersAiEmbedder(account_id="account", api_token=SECRET, opener=opener)
    with pytest.raises(EmbeddingConfigError) as caught:
        provider.embed(["hello"])
    error = caught.value
    assert str(error) == "workers ai embed failed (network)"
    assert SECRET not in str(error)
    assert SECRET not in _displayed(error)
    assert isinstance(error.__cause__, URLError)
    assert "Connection refused" in str(error.__cause__)


def test_a_malformed_response_body_is_not_echoed() -> None:
    """A body that is not JSON is reported by class, never by content.

    The body carries the credential, as an upstream echo would: the response
    branch must not put it in the message, in the repr of the error, or in the
    traceback a logger prints.
    """
    body = b'{"data": "super-secret-token"'

    def opener(_request):
        return _Response(body)

    provider = WorkersAiEmbedder(account_id="account", api_token=SECRET, opener=opener)
    with pytest.raises(EmbeddingConfigError) as caught:
        provider.embed(["hello"])
    error = caught.value
    assert str(error) == "workers ai embed failed (response)"
    assert SECRET not in str(error)
    assert SECRET not in repr(error)
    assert SECRET not in _displayed(error)
    # The decode error is chained for diagnosis; its text names the failing
    # position, never the payload.
    assert isinstance(error.__cause__, json.JSONDecodeError)
    assert SECRET not in str(error.__cause__)
    assert SECRET not in repr(error.__cause__)


def test_an_undecodable_response_body_is_not_echoed() -> None:
    """A body that is not UTF-8 is reported by class, never by content."""
    body = b"super-secret-token\xff"

    def opener(_request):
        return _Response(body)

    provider = WorkersAiEmbedder(account_id="account", api_token=SECRET, opener=opener)
    with pytest.raises(EmbeddingConfigError) as caught:
        provider.embed(["hello"])
    error = caught.value
    assert str(error) == "workers ai embed failed (response)"
    assert SECRET not in str(error)
    assert SECRET not in repr(error)
    assert SECRET not in _displayed(error)
    # The decode error is chained for diagnosis; its text names the failing
    # position, never the payload.
    assert isinstance(error.__cause__, UnicodeDecodeError)
    assert SECRET not in str(error.__cause__)


def test_a_response_with_the_wrong_number_of_vectors_is_refused() -> None:
    """One vector per text: no more and no fewer."""
    payload = {"result": {"data": [[0.5] * BGE_M3_DIMENSIONS, [0.5] * BGE_M3_DIMENSIONS]}}
    provider = WorkersAiEmbedder(
        account_id="account", api_token=SECRET, opener=_opener([], payload)
    )
    with pytest.raises(EmbeddingConfigError) as caught:
        provider.embed(["hello"])
    assert str(caught.value) == "workers ai embed failed (count)"


def test_a_384_dim_response_is_refused() -> None:
    """A 384-dim vector must not enter a 1024-dim index."""
    payload = {"result": {"data": [[0.5] * 384]}}
    provider = WorkersAiEmbedder(
        account_id="account", api_token=SECRET, opener=_opener([], payload)
    )
    with pytest.raises(EmbeddingConfigError) as caught:
        provider.embed(["hello"])
    assert str(caught.value) == "workers ai embed failed (dimensions)"


def test_a_response_without_a_data_list_is_refused() -> None:
    """A well-formed body of the wrong shape is reported by class."""
    payload = {"result": {"data": "upstream-body-marker"}}

    def opener(_request):
        return _Response(json.dumps(payload).encode())

    provider = WorkersAiEmbedder(account_id="account", api_token=SECRET, opener=opener)
    with pytest.raises(EmbeddingConfigError) as caught:
        provider.embed(["hello"])
    error = caught.value
    assert str(error) == "workers ai embed failed (response)"
    assert "upstream-body-marker" not in str(error)
    assert SECRET not in str(error)
    assert SECRET not in repr(error)
    assert SECRET not in _displayed(error)


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
