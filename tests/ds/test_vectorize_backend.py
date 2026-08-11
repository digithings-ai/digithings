"""Tests for the Vectorize REST backend."""

from __future__ import annotations

import json

import numpy as np
import pytest
from digisearch.core.models import Chunk
from digisearch.indexes.backends.vectorize import VectorizeBackend


class _RecordingPost:
    """HttpPost double: records calls, returns a canned success response."""

    def __init__(self, status: int = 200, body: str | None = None) -> None:
        self.calls: list[tuple[str, dict[str, str], bytes, str]] = []
        self._status = status
        self._body = body if body is not None else json.dumps({"success": True, "result": {}})

    def __call__(
        self, url: str, headers: dict[str, str], body: bytes, content_type: str
    ) -> tuple[int, str]:
        self.calls.append((url, headers, body, content_type))
        return self._status, self._body


def _chunk(i: int) -> Chunk:
    return Chunk(
        id=f"c{i}",
        content=f"content {i}",
        doc_id="d1",
        embedding=[0.1] * 384,
        metadata={"source_url": "repo://x/y.md", "segment_label": "page:1"},
    )


@pytest.mark.unit
def test_add_posts_ndjson_multipart_to_upsert() -> None:
    post = _RecordingPost()
    backend = VectorizeBackend("digithings-docs", account_id="acct", api_token="tok", http_post=post)
    backend.add([_chunk(0), _chunk(1)])
    assert len(post.calls) == 1
    url, headers, body, content_type = post.calls[0]
    assert url.endswith("/accounts/acct/vectorize/v2/indexes/digithings-docs/upsert")
    assert headers["Authorization"] == "Bearer tok"
    assert content_type.startswith("multipart/form-data; boundary=")
    assert b'name="vectors"' in body
    lines = [ln for ln in body.decode().splitlines() if ln.startswith('{"id"')]
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["id"] == "c0"
    assert len(first["values"]) == 384
    assert first["metadata"]["segment_label"] == "page:1"


@pytest.mark.unit
def test_add_batches_at_batch_size() -> None:
    post = _RecordingPost()
    backend = VectorizeBackend(
        "i", account_id="a", api_token="t", http_post=post, batch_size=2
    )
    backend.add([_chunk(i) for i in range(5)])
    assert len(post.calls) == 3


@pytest.mark.unit
def test_add_skips_chunks_without_embeddings() -> None:
    post = _RecordingPost()
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    plain = Chunk(id="c9", content="x", doc_id="d", embedding=None, metadata={})
    backend.add([plain])
    assert post.calls == []


@pytest.mark.unit
def test_add_raises_on_http_error() -> None:
    post = _RecordingPost(status=403, body='{"success": false, "errors": [{"message": "nope"}]}')
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    with pytest.raises(RuntimeError, match="vectorize upsert failed"):
        backend.add([_chunk(0)])


@pytest.mark.unit
def test_add_empty_is_a_noop() -> None:
    post = _RecordingPost()
    VectorizeBackend("i", account_id="a", api_token="t", http_post=post).add([])
    assert post.calls == []


@pytest.mark.unit
def test_add_accepts_numpy_array_embedding() -> None:
    post = _RecordingPost()
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    chunk = Chunk(
        id="c0",
        content="x",
        doc_id="d1",
        embedding=np.array([0.1, 0.2, 0.3], dtype=np.float32),
        metadata={},
    )
    backend.add([chunk])
    assert len(post.calls) == 1
    _, _, body, _ = post.calls[0]
    lines = [ln for ln in body.decode().splitlines() if ln.startswith('{"id"')]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    # json.loads yields Python floats; re-encoding must succeed and every value
    # must be a genuine Python float, not a numpy scalar hiding behind __float__.
    assert json.dumps(parsed)
    assert all(type(v) is float for v in parsed["values"])


@pytest.mark.unit
def test_add_keeps_canonical_doc_id_over_spoofed_metadata() -> None:
    post = _RecordingPost()
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    chunk = Chunk(
        id="c0",
        content="x",
        doc_id="real-doc-id",
        embedding=[0.1, 0.2],
        metadata={"doc_id": "spoofed-doc-id"},
    )
    backend.add([chunk])
    _, _, body, _ = post.calls[0]
    lines = [ln for ln in body.decode().splitlines() if ln.startswith('{"id"')]
    parsed = json.loads(lines[0])
    assert parsed["metadata"]["doc_id"] == "real-doc-id"
