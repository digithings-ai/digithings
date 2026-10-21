"""Unit tests for the Workers AI bge-m3 embedder (custom endpoint + account path).

No network.

Two guarantees are pinned here.

1. The credential the provider holds never reaches an error: not in the
   message, not in the repr of the raised error, not in the rendered
   traceback. Every branch of the provider is covered, and the upstream error
   response is dropped from the chain rather than rendered.
2. The upstream payload stays where upstream put it, on the attributes of the
   chained cause. The provider renders the failure class, not the payload.

One path does not hold today and is pinned as a known gap:
``test_a_non_numeric_upstream_value_is_not_classified``.
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
    """The text a logger prints for this error: the messages of the chain.

    This models the rendered traceback without the frames -- the question is
    what the error carries, not where it was raised. It follows the same
    chain rules Python does: ``__cause__`` first, then ``__context__`` when
    the context is not suppressed.
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


def test_provider_for_normalises_the_model_id() -> None:
    """The model id is matched as the provider name is: case and whitespace."""
    assert provider_for("bge-m3", " @CF/BAAI/BGE-M3 ") is not None
    assert provider_for("bge-m3", " BGE-M3 ") is not None


def test_the_factory_names_match_the_names_provider_for_accepts() -> None:
    """FACTORY_NAMES declares the names the factory accepts; the two agree.

    Every declared name resolves, and a name that is not declared does not.
    """
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


def test_the_injected_embedder_refuses_a_384_dim_vector() -> None:
    """An injected embedder is checked like the HTTP one."""
    provider = WorkersAiEmbedder(embed_fn=lambda texts: [[0.25] * 384 for _ in texts])
    with pytest.raises(EmbeddingConfigError, match=r"workers ai embed failed \(dimensions\)"):
        provider.embed(["hello"])


def test_the_injected_embedder_refuses_a_wrong_vector_count() -> None:
    """One vector per text, on the injected path too."""
    provider = WorkersAiEmbedder(embed_fn=lambda texts: [[0.25] * BGE_M3_DIMENSIONS])
    with pytest.raises(EmbeddingConfigError, match=r"workers ai embed failed \(count\)"):
        provider.embed(["hello", "hallo"])


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
    assert SECRET not in repr(caught.value)
    assert SECRET not in _displayed(caught.value)


def test_missing_credentials_do_not_echo_a_configured_value() -> None:
    """The config error names the variable to set, never the value.

    The token is empty in these two cases, so the account id is the
    configured value that could leak.
    """
    # No token: the request cannot be authorised.
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


def test_the_environment_token_does_not_leak_into_the_config_error(monkeypatch) -> None:
    """The token usually comes from the environment; it must not reach an error."""
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", SECRET)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    provider = WorkersAiEmbedder()
    with pytest.raises(EmbeddingConfigError, match="CLOUDFLARE_ACCOUNT_ID") as caught:
        provider.embed(["hello"])
    assert SECRET not in str(caught.value)
    assert SECRET not in repr(caught.value)
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
    assert SECRET not in repr(error)
    assert SECRET not in _displayed(error)
    # The upstream response is not rendered: `from None` drops it from the
    # chain. It is still reachable as `__context__` -- upstream data, on
    # upstream's own object -- which is why the guarantee above is about the
    # rendered error and not about the object graph.
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    assert error.__context__ is not None


def test_the_network_error_names_only_the_failure_class() -> None:
    """A transport failure names the class; the reason stays available.

    The message is a literal: the provider never interpolates the credential
    into it. The reason is chained for diagnosis rather than swallowed.
    """

    def opener(_request):
        raise URLError(ConnectionRefusedError(61, "Connection refused"))

    provider = WorkersAiEmbedder(account_id="account", api_token=SECRET, opener=opener)
    with pytest.raises(EmbeddingConfigError) as caught:
        provider.embed(["hello"])
    error = caught.value
    assert str(error) == "workers ai embed failed (network)"
    assert SECRET not in str(error)
    assert SECRET not in repr(error)
    assert SECRET not in _displayed(error)
    assert isinstance(error.__cause__, URLError)
    assert "Connection refused" in str(error.__cause__)


def test_a_malformed_response_body_is_not_echoed() -> None:
    """A body that is not JSON is reported by class, never by content.

    The body carries the credential, as an upstream echo would. The decode
    error is chained for diagnosis; its text names the failing position, and
    the raw payload stays on the cause, where upstream put it.
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
    assert isinstance(error.__cause__, json.JSONDecodeError)
    assert SECRET not in str(error.__cause__)


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
    assert isinstance(error.__cause__, UnicodeDecodeError)
    assert SECRET not in str(error.__cause__)


def test_a_non_numeric_upstream_value_is_not_classified() -> None:
    """A body that is not numeric fails unclassified -- a known gap.

    The provider converts the vectors itself and does not wrap the
    conversion, so the upstream value reaches the operator verbatim in a
    ValueError. The provider's own credential is not involved -- it travels
    in a header -- but an upstream body that echoed it would be echoed here
    too. Pinned so the gap is visible; classifying this failure will fail
    this test on purpose.
    """
    body = b'{"result": {"data": [["upstream-value"]]}}'

    def opener(_request):
        return _Response(body)

    provider = WorkersAiEmbedder(account_id="account", api_token=SECRET, opener=opener)
    with pytest.raises(ValueError) as caught:
        provider.embed(["hello"])
    assert not isinstance(caught.value, EmbeddingConfigError)


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


def test_a_response_without_a_result_key_still_parses() -> None:
    """A body that carries the vectors at the top level is still read."""
    payload = {"data": [[0.5] * BGE_M3_DIMENSIONS]}

    def opener(_request):
        return _Response(json.dumps(payload).encode())

    provider = WorkersAiEmbedder(account_id="account", api_token=SECRET, opener=opener)
    vectors = provider.embed(["hello"])
    assert len(vectors) == 1
    assert len(vectors[0]) == BGE_M3_DIMENSIONS


def test_a_non_object_response_is_refused() -> None:
    """A body that is not an object at all is reported by class."""

    def opener(_request):
        return _Response(b"[]")

    provider = WorkersAiEmbedder(account_id="account", api_token=SECRET, opener=opener)
    with pytest.raises(EmbeddingConfigError, match=r"workers ai embed failed \(response\)"):
        provider.embed(["hello"])


def test_a_response_with_the_wrong_number_of_vectors_is_refused() -> None:
    """More vectors than texts: no more."""
    payload = {"result": {"data": [[0.5] * BGE_M3_DIMENSIONS, [0.5] * BGE_M3_DIMENSIONS]}}
    provider = WorkersAiEmbedder(
        account_id="account", api_token=SECRET, opener=_opener([], payload)
    )
    with pytest.raises(EmbeddingConfigError) as caught:
        provider.embed(["hello"])
    assert str(caught.value) == "workers ai embed failed (count)"


def test_a_response_with_too_few_vectors_is_refused() -> None:
    """Fewer vectors than texts: no fewer."""
    payload = {"result": {"data": []}}
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


def test_an_over_long_response_is_refused() -> None:
    """A vector wider than 1024 is refused too: the width is not a minimum."""
    payload = {"result": {"data": [[0.5] * 2048]}}
    provider = WorkersAiEmbedder(
        account_id="account", api_token=SECRET, opener=_opener([], payload)
    )
    with pytest.raises(EmbeddingConfigError) as caught:
        provider.embed(["hello"])
    assert str(caught.value) == "workers ai embed failed (dimensions)"


def test_parses_a_result_payload() -> None:
    provider = WorkersAiEmbedder(
        account_id="account",
        api_token="token",
        opener=_opener([], _vectors()),
    )
    vectors = provider.embed(["Guten Tag"])
    assert len(vectors) == 1
    assert len(vectors[0]) == BGE_M3_DIMENSIONS
    # The values are the ones upstream sent, not zeros and not truncated.
    assert vectors[0][0] == 0.5
    assert vectors[0][-1] == 0.5


def test_custom_endpoint_is_used_and_needs_no_account_id(monkeypatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    seen: list[Any] = []
    provider = WorkersAiEmbedder(
        url="https://embed.example/embed",
        api_token=" tok ",
        opener=_opener(seen, _vectors()),
    )
    vectors = provider.embed(["hello"])
    assert len(vectors) == 1 and len(vectors[0]) == BGE_M3_DIMENSIONS
    assert len(seen) == 1
    assert seen[0].full_url == "https://embed.example/embed"
    # The token is trimmed, the request is a POST, and the texts are the body.
    assert seen[0].get_header("Authorization") == "Bearer tok"
    assert seen[0].get_method() == "POST"
    assert json.loads(seen[0].data) == {"text": ["hello"]}


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
    """The dedicated embed endpoint and its own token are used.

    The query side must not raise on the documented-preferred path, and it
    must not fall back to the Vectorize token: the embed endpoint exists so
    the Vectorize token does not need Workers AI permission.
    """
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


def test_search_provider_falls_back_when_the_embed_token_is_missing(monkeypatch) -> None:
    """The embed endpoint needs its own token; without one the account path is used."""
    monkeypatch.setenv("DIGISEARCH_WORKERS_AI_INDEXES", "occ")
    monkeypatch.setenv("DIGISEARCH_BGE_M3_EMBED_URL", "https://embed.example/embed")
    monkeypatch.delenv("DIGISEARCH_BGE_M3_EMBED_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    seen: list[Any] = []
    monkeypatch.setattr(workers_ai_module, "urlopen", _opener(seen, _vectors()))
    provider = _embedding_provider_for("occ", "acct", "vtok")
    assert isinstance(provider, WorkersAiEmbedder)
    provider.embed(["hello"])
    assert seen[0].full_url == (
        f"https://api.cloudflare.com/client/v4/accounts/acct/ai/run/{BGE_M3_MODEL_ID}"
    )
    assert seen[0].get_header("Authorization") == "Bearer vtok"
