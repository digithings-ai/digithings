"""Tests for Vectorize ingest routing via route_add_chunks."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from digisearch.core.models import Chunk
from digisearch.indexes.backends.vectorize import VectorizeBackend
from digisearch.search._stub import route_add_chunks


class _RecordingPost:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str], bytes, str]] = []

    def __call__(
        self, url: str, headers: dict[str, str], body: bytes, content_type: str
    ) -> tuple[int, str]:
        self.calls.append((url, headers, body, content_type))
        return 200, json.dumps({"success": True, "result": {}})


class _StubProvider:
    def __init__(self) -> None:
        self.embedded: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embedded.extend(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]

    @property
    def dimensions(self) -> int:
        return 3


@pytest.mark.unit
def test_route_add_chunks_vectorize_embeds_unembedded_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unembedded ingest chunks must be embedded and upserted, not silently dropped."""
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)

    post = _RecordingPost()
    provider = _StubProvider()
    chunks = [
        Chunk(id="c0", content="hello vectorize", doc_id="d0", embedding=None, metadata={}),
    ]

    original_init = VectorizeBackend.__init__

    def _init_with_recording_post(self: VectorizeBackend, name: str, **kwargs: object) -> None:
        kwargs["http_post"] = post
        kwargs["embedding_provider"] = provider
        original_init(self, name, **kwargs)  # type: ignore[arg-type]

    with patch.object(VectorizeBackend, "__init__", _init_with_recording_post):
        backend_name = route_add_chunks("docs", chunks)

    assert backend_name == "vectorize"
    assert provider.embedded == ["hello vectorize"]
    assert len(post.calls) == 1
