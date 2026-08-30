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
    backend = VectorizeBackend(
        "digithings-docs", account_id="acct", api_token="tok", http_post=post
    )
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
    assert first["metadata"]["content"] == "content 0"


@pytest.mark.unit
def test_add_batches_at_batch_size() -> None:
    post = _RecordingPost()
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post, batch_size=2)
    backend.add([_chunk(i) for i in range(5)])
    assert len(post.calls) == 3


@pytest.mark.unit
def test_add_embeds_chunks_without_embeddings() -> None:
    post = _RecordingPost()
    embedded: list[str] = []

    class _StubProvider:
        def embed(self, texts: list[str]) -> list[list[float]]:
            embedded.extend(texts)
            return [[0.1, 0.2, 0.3] for _ in texts]

        @property
        def dimensions(self) -> int:
            return 3

    backend = VectorizeBackend(
        "i", account_id="a", api_token="t", http_post=post, embedding_provider=_StubProvider()
    )
    plain = Chunk(id="c9", content="needs embedding", doc_id="d", embedding=None, metadata={})
    backend.add([plain])
    assert embedded == ["needs embedding"]
    assert len(post.calls) == 1


@pytest.mark.unit
def test_add_raises_on_http_error() -> None:
    post = _RecordingPost(status=403, body='{"success": false, "errors": [{"message": "nope"}]}')
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    with pytest.raises(RuntimeError, match="vectorize upsert failed"):
        backend.add([_chunk(0)])


@pytest.mark.unit
def test_add_raises_on_http_200_application_level_failure() -> None:
    """C1 repro: HTTP 200 with a `success: false` body must raise, not return
    normally as if the vectors were written."""
    post = _RecordingPost(
        status=200,
        body='{"success": false, "result": null, "errors": [{"code": 1004, '
        '"message": "index dimension mismatch"}]}',
    )
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    with pytest.raises(RuntimeError, match="index dimension mismatch"):
        backend.add([_chunk(0)])


@pytest.mark.unit
def test_add_raises_on_http_200_with_null_result_and_no_errors_field() -> None:
    """C1 repro variant: `result: null` alone (no `success` or `errors` keys) must
    still be treated as a failure, not a silently-empty success."""
    post = _RecordingPost(status=200, body='{"result": null}')
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    with pytest.raises(RuntimeError, match="vectorize upsert failed"):
        backend.add([_chunk(0)])


@pytest.mark.unit
def test_add_never_puts_the_api_token_in_the_error_message() -> None:
    post = _RecordingPost(
        status=200, body='{"success": false, "result": null, "errors": [{"message": "boom"}]}'
    )
    backend = VectorizeBackend("i", account_id="a", api_token="super-secret-token", http_post=post)
    with pytest.raises(RuntimeError) as exc_info:
        backend.add([_chunk(0)])
    assert "super-secret-token" not in str(exc_info.value)


@pytest.mark.unit
def test_delete_raises_on_http_error() -> None:
    post = _RecordingPost(status=403, body='{"success": false, "errors": [{"message": "nope"}]}')
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    with pytest.raises(RuntimeError, match="vectorize delete failed"):
        backend.delete(["c0"])


@pytest.mark.unit
def test_delete_raises_on_http_200_application_level_failure() -> None:
    """C1 repro: HTTP 200 with a `success: false` body must raise, not return
    normally as if the ids were deleted."""
    post = _RecordingPost(
        status=200, body='{"success": false, "result": null, "errors": [{"message": "boom"}]}'
    )
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    with pytest.raises(RuntimeError, match="boom"):
        backend.delete(["c0"])


@pytest.mark.unit
def test_delete_succeeds_on_normal_response() -> None:
    post = _RecordingPost(body=json.dumps({"success": True, "result": {"mutationId": "abc"}}))
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    backend.delete(["c0", "c1"])
    assert len(post.calls) == 1
    body = json.loads(post.calls[0][2])
    assert body["ids"] == ["c0", "c1"]


@pytest.mark.unit
def test_delete_empty_is_a_noop() -> None:
    post = _RecordingPost()
    VectorizeBackend("i", account_id="a", api_token="t", http_post=post).delete([])
    assert post.calls == []


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


@pytest.mark.unit
def test_add_keeps_canonical_content_over_spoofed_metadata() -> None:
    post = _RecordingPost()
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    chunk = Chunk(
        id="c0",
        content="real content",
        doc_id="d1",
        embedding=[0.1, 0.2],
        metadata={"content": "spoofed content"},
    )
    backend.add([chunk])
    _, _, body, _ = post.calls[0]
    lines = [ln for ln in body.decode().splitlines() if ln.startswith('{"id"')]
    parsed = json.loads(lines[0])
    assert parsed["metadata"]["content"] == "real content"


_MATCHES = json.dumps(
    {
        "success": True,
        "result": {
            "count": 2,
            "matches": [
                {
                    "id": "c1",
                    "score": 0.91,
                    "metadata": {
                        "doc_id": "d1",
                        "content": "first chunk",
                        "segment_label": "page:12",
                        "source_url": "https://x/y.pdf",
                    },
                },
                {
                    "id": "c2",
                    "score": 0.42,
                    "metadata": {"doc_id": "d1", "content": "second chunk"},
                },
            ],
        },
        "errors": [],
    }
)


@pytest.mark.unit
def test_query_maps_matches_to_results() -> None:
    from digisearch.core.models import Query as DsQuery

    post = _RecordingPost(body=_MATCHES)
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    results = backend.query(DsQuery(text="hello", top_k=5, embedding=[0.2] * 384))

    url, _headers, body, content_type = post.calls[0]
    assert url.endswith("/indexes/i/query")
    assert content_type == "application/json"
    sent = json.loads(body)
    assert sent["topK"] == 5
    assert sent["returnMetadata"] == "all"
    assert sent["vector"] == [0.2] * 384

    assert [r.chunk.id for r in results] == ["c1", "c2"]
    assert results[0].score == 0.91
    assert results[0].rank == 0
    assert results[0].chunk.content == "first chunk"
    assert results[0].chunk.doc_id == "d1"
    assert results[0].chunk.metadata["segment_label"] == "page:12"


@pytest.mark.unit
def test_query_clamps_top_k_to_vectorize_max() -> None:
    from digisearch.core.models import Query as DsQuery

    post = _RecordingPost(body=_MATCHES)
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    backend.query(DsQuery(text="x", top_k=500, embedding=[0.0] * 384))
    assert json.loads(post.calls[0][2])["topK"] == 50


@pytest.mark.unit
def test_query_logs_a_warning_when_top_k_is_clamped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """I4 repro: a clamped top_k must be visible in logs, not silently swallowed."""
    from digisearch.core.models import Query as DsQuery

    post = _RecordingPost(body=_MATCHES)
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    with caplog.at_level("WARNING"):
        backend.query(DsQuery(text="x", top_k=100, embedding=[0.0] * 384))
    assert any("clamped" in record.getMessage() for record in caplog.records)


@pytest.mark.unit
def test_query_does_not_warn_when_top_k_is_within_the_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from digisearch.core.models import Query as DsQuery

    post = _RecordingPost(body=_MATCHES)
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    with caplog.at_level("WARNING"):
        backend.query(DsQuery(text="x", top_k=10, embedding=[0.0] * 384))
    assert not any("clamped" in record.getMessage() for record in caplog.records)


@pytest.mark.unit
def test_query_raises_on_http_error_instead_of_returning_empty() -> None:
    from digisearch.core.models import Query as DsQuery

    post = _RecordingPost(status=500, body='{"success": false, "errors": [{"message": "boom"}]}')
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    with pytest.raises(RuntimeError, match="vectorize query failed"):
        backend.query(DsQuery(text="x", top_k=3, embedding=[0.0] * 384))


@pytest.mark.unit
def test_query_embeds_text_when_no_embedding_supplied() -> None:
    from digisearch.core.models import Query as DsQuery

    class _StubProvider:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.7] * 384 for _ in texts]

        @property
        def dimensions(self) -> int:
            return 384

    post = _RecordingPost(body=_MATCHES)
    backend = VectorizeBackend(
        "i", account_id="a", api_token="t", http_post=post, embedding_provider=_StubProvider()
    )
    backend.query(DsQuery(text="what is digikey", top_k=3))
    assert json.loads(post.calls[0][2])["vector"] == [0.7] * 384


@pytest.mark.unit
def test_query_prefers_a_precomputed_embedding_over_the_provider() -> None:
    from digisearch.core.models import Query as DsQuery

    class _ShouldNotRun:
        def embed(self, _texts: list[str]) -> list[list[float]]:
            raise AssertionError("must not embed when Query.embedding is present")

        @property
        def dimensions(self) -> int:
            return 384

    post = _RecordingPost(body=_MATCHES)
    backend = VectorizeBackend(
        "i", account_id="a", api_token="t", http_post=post, embedding_provider=_ShouldNotRun()
    )
    backend.query(DsQuery(text="x", top_k=3, embedding=[0.1] * 384))
    assert json.loads(post.calls[0][2])["vector"] == [0.1] * 384


@pytest.mark.unit
def test_query_raises_on_http_200_application_level_failure() -> None:
    """FINDING 1 repro: HTTP 200 with a `success: false` body must raise, not
    silently return an empty list — the exact failure mode this backend exists
    to prevent."""
    from digisearch.core.models import Query as DsQuery

    post = _RecordingPost(
        status=200, body='{"success": false, "result": null, "errors": [{"message": "boom"}]}'
    )
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    with pytest.raises(RuntimeError, match="boom"):
        backend.query(DsQuery(text="x", top_k=3, embedding=[0.0] * 384))


@pytest.mark.unit
def test_query_constructs_default_embedder_at_most_once() -> None:
    """FINDING 2 repro: 3 queries with no injected provider must construct the
    default MiniLMEmbedder exactly once, not once per query."""
    from digisearch.core.models import Query as DsQuery

    construction_count = 0

    class _StubEmbedder:
        def __init__(self) -> None:
            nonlocal construction_count
            construction_count += 1

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.5] * 384 for _ in texts]

        @property
        def dimensions(self) -> int:
            return 384

    post = _RecordingPost(body=_MATCHES)
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    import digisearch.embedding.providers.minilm as minilm_module

    original = minilm_module.MiniLMEmbedder
    minilm_module.MiniLMEmbedder = _StubEmbedder  # type: ignore[misc]
    try:
        for _ in range(3):
            backend.query(DsQuery(text="no embedding here", top_k=3))
    finally:
        minilm_module.MiniLMEmbedder = original  # type: ignore[misc]

    assert construction_count == 1, f"expected 1 construction, got {construction_count}"


@pytest.mark.unit
def test_default_embedder_singleton_is_thread_safe() -> None:
    """#2225: concurrent cold-cache callers must construct MiniLMEmbedder once.

    Without a lock, N threads can all observe None and each pay an ONNX load.
    Slow the stub constructor so the race window is real under CI.
    """
    import threading
    import time

    import digisearch.embedding.providers.minilm as minilm_module
    import digisearch.indexes.backends.vectorize as vectorize_module

    construction_count = 0
    barrier = threading.Barrier(8)

    class _SlowStubEmbedder:
        def __init__(self) -> None:
            nonlocal construction_count
            time.sleep(0.05)
            construction_count += 1

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.5] * 384 for _ in texts]

        @property
        def dimensions(self) -> int:
            return 384

    original = minilm_module.MiniLMEmbedder
    minilm_module.MiniLMEmbedder = _SlowStubEmbedder  # type: ignore[misc]
    vectorize_module._default_embedder_singleton = None
    results: list[object] = []
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            barrier.wait(timeout=5)
            results.append(vectorize_module._get_default_embedder())
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
    finally:
        minilm_module.MiniLMEmbedder = original  # type: ignore[misc]
        vectorize_module._default_embedder_singleton = None

    assert not errors, f"worker errors: {errors}"
    assert construction_count == 1, f"expected 1 construction, got {construction_count}"
    assert len(results) == 8
    assert all(r is results[0] for r in results)


@pytest.mark.unit
def test_query_treats_non_dict_metadata_as_empty() -> None:
    """FINDING 3 repro: a match with non-dict metadata (e.g. a string) must not
    raise ValueError from `dict(match.get("metadata") or {})`."""
    from digisearch.core.models import Query as DsQuery

    bad_matches = json.dumps(
        {
            "success": True,
            "result": {
                "count": 1,
                "matches": [{"id": "c1", "score": 0.5, "metadata": "not-a-dict"}],
            },
            "errors": [],
        }
    )
    post = _RecordingPost(body=bad_matches)
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    results = backend.query(DsQuery(text="x", top_k=3, embedding=[0.0] * 384))
    assert len(results) == 1
    assert results[0].chunk.metadata == {}
    assert results[0].chunk.content == ""
    assert results[0].chunk.doc_id == ""


@pytest.mark.unit
def test_query_treats_null_score_as_zero() -> None:
    """FINDING 3 repro: a match with `score: null` must not raise TypeError from
    `float(match.get("score", 0.0))` — a `.get` default only applies when the key
    is missing, not when its value is None."""
    from digisearch.core.models import Query as DsQuery

    null_score_matches = json.dumps(
        {
            "success": True,
            "result": {
                "count": 1,
                "matches": [{"id": "c1", "score": None, "metadata": {"doc_id": "d1"}}],
            },
            "errors": [],
        }
    )
    post = _RecordingPost(body=null_score_matches)
    backend = VectorizeBackend("i", account_id="a", api_token="t", http_post=post)
    results = backend.query(DsQuery(text="x", top_k=3, embedding=[0.0] * 384))
    assert len(results) == 1
    assert results[0].score == 0.0
