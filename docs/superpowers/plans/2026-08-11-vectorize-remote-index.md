# Vectorize Remote Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the production digisearch vector index out of the Cloudflare Container to Cloudflare Vectorize, so the container queries a remote index instead of re-embedding the whole corpus on every ephemeral-disk cold boot.

**Architecture:** A new `VectorizeBackend(DigiIndex)` talks to the Vectorize v2 REST API. It registers into the existing `@register_backend` chain in `search/_stub.py` ahead of Chroma, so Vectorize wins when configured and Chroma remains the default everywhere else. A host-side script reads the already-verified notes from Supabase, chunks them through the same `SegmentAwareChunker` path production assumes, embeds with local MiniLM, and upserts. The container never ingests.

**Tech Stack:** Python 3.12, `httpx` (already a digisearch base dependency), stdlib dataclasses, pytest with `-m unit`, ruff at line-length 100.

**Source spec:** `docs/superpowers/specs/2026-08-11-vectorize-remote-index-design.md`

## Global Constraints

- **Vectorize v2 REST API, verified 2026-08-11** (do not guess these):
  - Query: `POST https://api.cloudflare.com/client/v4/accounts/{account_id}/vectorize/v2/indexes/{index_name}/query`, `Content-Type: application/json`, body `{"vector": [...], "topK": N, "returnMetadata": "all", "returnValues": false}`. **`returnMetadata` is a string enum `"none" | "indexed" | "all"` — NOT a boolean.**
  - Response: `{"success": bool, "result": {"count": N, "matches": [{"id", "score", "values", "metadata", "namespace"}]}, "errors": [...], "messages": [...]}`
  - Upsert: `POST .../vectorize/v2/indexes/{index_name}/upsert` as **`multipart/form-data` with form field name `vectors`** carrying **NDJSON** — one JSON object per line, `{"id": str, "values": [float], "metadata": {...}}`. It is NOT a plain JSON body.
  - Auth header on every call: `Authorization: Bearer <token>`
- **Vectorize limits:** max 1536 dimensions; metadata 10 KiB per vector; **max 10 metadata *indexes*, each indexing ≤64 bytes per vector**; topK ≤50 when returning metadata; HTTP batch upsert ≤5,000 vectors.
- **Embeddings are MiniLM, 384 dimensions.** Upsert and query MUST use the same model — this is the invariant that makes the index usable at all.
- **Two separate Vectorize indexes**, not namespaces: `digithings_docs` and `occ_help` (underscore form is canonical — verified live; see `docs/ops/vectorize-cutover.md`).
- `digisearch/src/digisearch/core/models.py` types are **stdlib dataclasses, not pydantic**. `Chunk(id, content, doc_id, embedding, metadata)`; `Result(chunk, score, source_doc, rank)`.
- `Chunk` is always constructed with all five fields as keywords including explicit `embedding=None`.
- ruff: line-length 100, target py312. Everything under `tests/` must be ruff-clean.
- **`tests/ds/` uses a per-test `@pytest.mark.unit` decorator** (not module-level `pytestmark`). `tests/scripts/` and `tests/dv/` use module-level `pytestmark = pytest.mark.unit`. Follow the directory you are writing in.
- All tests start with `from __future__ import annotations` and annotate `-> None`.
- **No test may make a real network call.** HTTP is injected as a callable seam, matching the existing style in `scripts/docs_onboard/` (`post_json`) and `digivault`'s `_FakeClient`.
- digi product names are lowercase in prose, docstrings, and commit messages.
- Never commit an API token. Tokens come from env only.

---

### Task 0: `MiniLMEmbedder` — a local 384-dim EmbeddingProvider

**Files:**
- Create: `digisearch/src/digisearch/embedding/providers/minilm.py`
- Test: `tests/ds/test_minilm_embedder.py`

**Interfaces:**
- Consumes: `EmbeddingProvider` from `digisearch/src/digisearch/embedding/base.py` (abstract `embed(self, texts: list[str]) -> list[list[float]]` and abstract property `dimensions -> int`).
- Produces: `MiniLMEmbedder()` with `embed()` and `dimensions == 384`, and module constant `MINILM_MODEL_ID = "all-MiniLM-L6-v2-384"`. Tasks 3 and 5 both depend on these exact names.

**Why this task exists:** the plan originally assumed a local MiniLM provider existed. It does not — digisearch's only concrete `EmbeddingProvider` is `OpenAIEmbedder`, because the Chroma backend embeds internally via chromadb's own default function and digisearch never calls a provider on that path. Verified available and correct: `chromadb.utils.embedding_functions.ONNXMiniLM_L6_V2()` returns 384-dim vectors and is the exact model Chroma uses today, so a Vectorize index built with it matches the corpus that was validated. chromadb is already a dependency; no new package.

- [ ] **Step 1: Write the failing test**

Create `tests/ds/test_minilm_embedder.py`:

```python
"""Tests for the local MiniLM embedding provider."""

from __future__ import annotations

import pytest

from digisearch.embedding.base import EmbeddingProvider
from digisearch.embedding.providers.minilm import MINILM_MODEL_ID, MiniLMEmbedder


@pytest.mark.unit
def test_minilm_is_an_embedding_provider() -> None:
    assert issubclass(MiniLMEmbedder, EmbeddingProvider)
    assert MINILM_MODEL_ID == "all-MiniLM-L6-v2-384"


@pytest.mark.unit
def test_minilm_dimensions_are_384_without_loading_the_model() -> None:
    assert MiniLMEmbedder().dimensions == 384


@pytest.mark.unit
def test_minilm_embeds_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def _fake_fn(texts: list[str]) -> list[list[float]]:
        calls.append(list(texts))
        return [[0.25] * 384 for _ in texts]

    embedder = MiniLMEmbedder(embed_fn=_fake_fn)
    out = embedder.embed(["a", "b"])
    assert calls == [["a", "b"]]
    assert len(out) == 2
    assert all(len(v) == 384 for v in out)


@pytest.mark.unit
def test_minilm_empty_input_returns_empty_without_calling_the_model() -> None:
    def _boom(_texts: list[str]) -> list[list[float]]:
        raise AssertionError("must not be called for empty input")

    assert MiniLMEmbedder(embed_fn=_boom).embed([]) == []
```

Note `dimensions` must not load the ONNX model — the test asserts it works on a bare instance, and loading a model to answer a constant would make every construction slow.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/ds/test_minilm_embedder.py -m unit -v --tb=short`
Expected: FAIL with `ModuleNotFoundError: No module named 'digisearch.embedding.providers.minilm'`

- [ ] **Step 3: Write the provider**

Create `digisearch/src/digisearch/embedding/providers/minilm.py`:

```python
"""Local MiniLM embedding provider backed by chromadb's bundled ONNX model.

Wraps the same model the Chroma backend embeds with internally, so an index built
here is directly comparable to a Chroma-built one. No new dependency: chromadb is
already required for the Chroma backend.
"""

from __future__ import annotations

from collections.abc import Callable

from digisearch.embedding.base import EmbeddingProvider

#: Recorded in vector metadata so an index cannot silently mix embedding models.
MINILM_MODEL_ID = "all-MiniLM-L6-v2-384"

#: all-MiniLM-L6-v2 output width.
MINILM_DIMENSIONS = 384

EmbedFn = Callable[[list[str]], list[list[float]]]


class MiniLMEmbedder(EmbeddingProvider):
    """all-MiniLM-L6-v2 (384-dim) via chromadb's bundled ONNX runtime."""

    def __init__(self, embed_fn: EmbedFn | None = None) -> None:
        self._embed_fn = embed_fn

    def _fn(self) -> EmbedFn:
        if self._embed_fn is None:
            from chromadb.utils import embedding_functions

            self._embed_fn = embedding_functions.ONNXMiniLM_L6_V2()
        return self._embed_fn

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [list(vector) for vector in self._fn()(list(texts))]

    @property
    def dimensions(self) -> int:
        return MINILM_DIMENSIONS
```

The model is loaded lazily on first `embed()`, never in `__init__` or `dimensions`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ds/test_minilm_embedder.py -m unit -v --tb=short`
Expected: PASS (4 passed)

Run: `ruff check digisearch/src tests`
Expected: no findings.

- [ ] **Step 5: Commit**

```bash
git add digisearch/src/digisearch/embedding/providers/minilm.py tests/ds/test_minilm_embedder.py
git commit -m "feat(digisearch): add local MiniLM embedding provider

Refs #2201

digisearch had no local EmbeddingProvider — only OpenAIEmbedder — because
the Chroma backend embeds internally. Vectorize needs an explicit one for
both upsert and query. Wraps chromadb's bundled ONNXMiniLM_L6_V2 so the
model matches what Chroma already uses."
```

---

### Task 1: Prefix-scoped, paginated note listing on `SupabaseStore`

**Files:**
- Modify: `digivault/src/digivault/supabase_store.py`
- Test: `tests/dv/test_supabase_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SupabaseStore.list_notes(self, *, path_prefix: str | None = None, page_size: int = 500) -> list[dict[str, Any]]` returning raw rows with keys `vault_path`, `title`, `frontmatter`, `body_markdown`. Task 5 calls this.

**Why this is first and why it is not cosmetic:** `SupabaseStore` today offers only `sources()` (selects the ENTIRE table with no prefix filter and no pagination) and `search()` (FTS, server-clamped to ≤20 rows). `sources()` inherits PostgREST's default row cap — commonly 1000 — **silently**. The corpus is 1,279 + 328 = **1,607 notes**, so a naive read drops roughly 600 notes with no error. Pagination is the whole point of this task.

- [ ] **Step 1: Write the failing test**

Append to `tests/dv/test_supabase_store.py`:

```python
def test_list_notes_filters_by_prefix_and_paginates() -> None:
    rows = [
        {"vault_path": f"clients/digithings/n{i}", "title": f"n{i}",
         "frontmatter": {}, "body_markdown": "body"}
        for i in range(7)
    ] + [
        {"vault_path": "clients/other/x", "title": "x",
         "frontmatter": {}, "body_markdown": "body"}
    ]
    client = _FakeClient(rows)
    store = SupabaseStore(client)
    out = store.list_notes(path_prefix="clients/digithings", page_size=3)
    assert len(out) == 7
    assert all(r["vault_path"].startswith("clients/digithings/") for r in out)
    assert len(client.range_calls) >= 3


def test_list_notes_without_prefix_returns_all() -> None:
    rows = [{"vault_path": "a/b", "title": "t", "frontmatter": {}, "body_markdown": "x"}]
    store = SupabaseStore(_FakeClient(rows))
    assert len(store.list_notes()) == 1


def test_list_notes_stops_on_short_page() -> None:
    rows = [
        {"vault_path": f"p/n{i}", "title": "t", "frontmatter": {}, "body_markdown": "x"}
        for i in range(2)
    ]
    client = _FakeClient(rows)
    store = SupabaseStore(client)
    out = store.list_notes(path_prefix="p", page_size=500)
    assert len(out) == 2
    assert len(client.range_calls) == 1
```

Extend the existing `_FakeClient` / `_Query` doubles in that file so the new chained calls exist. `_Query` currently implements only `select()` and `execute()`; add:

```python
    def like(self, _column: str, pattern: str) -> "_Query":
        self._like = pattern
        return self

    def order(self, *_a: object, **_k: object) -> "_Query":
        return self

    def range(self, start: int, end: int) -> "_Query":
        self._client.range_calls.append((start, end))
        self._range = (start, end)
        return self
```

and have `execute()` apply `self._like` (translate a trailing `%` to `startswith`) then slice by `self._range`. Give `_FakeClient` a `self.range_calls: list[tuple[int, int]] = []` and pass itself into `_Query` so ranges are recorded.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/dv/test_supabase_store.py -m unit -v --tb=short`
Expected: FAIL with `AttributeError: 'SupabaseStore' object has no attribute 'list_notes'`

- [ ] **Step 3: Implement `list_notes`**

Add to `digivault/src/digivault/supabase_store.py`, after `sources()`:

```python
    def list_notes(
        self,
        *,
        path_prefix: str | None = None,
        page_size: int = 500,
    ) -> list[dict[str, Any]]:
        """Every note under ``path_prefix``, paginated.

        ``sources()`` cannot be used for this: it selects the whole table with no
        prefix filter and no pagination, so it silently truncates at PostgREST's
        server-side row cap. This pages explicitly with ``.range()`` and stops on
        the first short page.
        """
        prefix = (path_prefix or "").strip().strip("/")
        out: list[dict[str, Any]] = []
        start = 0
        while True:
            query = self._client.table(self._table).select(_SELECT)
            if prefix:
                query = query.like("vault_path", f"{prefix}%")
            page = query.order("vault_path").range(start, start + page_size - 1).execute()
            rows = list(getattr(page, "data", None) or [])
            for row in rows:
                vault_path = str(row.get("vault_path") or "").strip()
                if not vault_path:
                    continue
                if prefix and vault_path != prefix and not vault_path.startswith(prefix + "/"):
                    continue
                out.append(row)
            if len(rows) < page_size:
                return out
            start += page_size
```

The belt-and-suspenders re-check after the `like` mirrors `search()`'s existing client-side prefix filter, and stops `clients/digithings-archive` matching a `clients/digithings` prefix.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/dv/test_supabase_store.py -m unit -v --tb=short`
Expected: PASS, including the pre-existing `test_search_calls_rpc_and_returns_models` and `test_search_passes_path_prefix_to_rpc` (do not modify them).

- [ ] **Step 5: Commit**

```bash
git add digivault/src/digivault/supabase_store.py tests/dv/test_supabase_store.py
git commit -m "feat(digivault): add paginated, prefix-scoped list_notes

Refs #2201

sources() selects the whole table with no prefix and no pagination, so it
silently truncates at PostgREST's row cap. The onboard corpus is 1607 notes,
well past a 1000-row default, so a reader built on sources() would drop
~600 notes without error."
```

---

### Task 2: `VectorizeBackend` — construction and upsert

**Files:**
- Create: `digisearch/src/digisearch/indexes/backends/vectorize.py`
- Test: `tests/ds/test_vectorize_backend.py`

**Interfaces:**
- Consumes: `DigiIndex` from `digisearch/src/digisearch/indexes/base.py`; `Chunk`, `Query`, `Result` from `digisearch.core.models`.
- Produces: `VectorizeBackend(name: str, *, account_id: str, api_token: str, http_post: HttpPost | None = None, batch_size: int = 1000)`, and the module-level type alias `HttpPost = Callable[[str, dict[str, str], bytes, str], tuple[int, str]]` taking `(url, headers, body, content_type)` and returning `(status_code, response_text)`. Tasks 3, 4 and 5 all depend on these exact names.

- [ ] **Step 1: Write the failing test**

Create `tests/ds/test_vectorize_backend.py`:

```python
"""Tests for the Vectorize REST backend."""

from __future__ import annotations

import json

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
    backend = VectorizeBackend("digithings_docs", account_id="acct", api_token="tok", http_post=post)
    backend.add([_chunk(0), _chunk(1)])
    assert len(post.calls) == 1
    url, headers, body, content_type = post.calls[0]
    assert url.endswith("/accounts/acct/vectorize/v2/indexes/digithings_docs/upsert")
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/ds/test_vectorize_backend.py -m unit -v --tb=short`
Expected: FAIL with `ModuleNotFoundError: No module named 'digisearch.indexes.backends.vectorize'`

- [ ] **Step 3: Write the module and upsert half**

Create `digisearch/src/digisearch/indexes/backends/vectorize.py`:

```python
"""Cloudflare Vectorize backend for digisearch. Implements DigiIndex over the v2 REST API."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from digisearch.core.models import Chunk, Query, Result
from digisearch.indexes.base import DigiIndex

logger = logging.getLogger(__name__)

API_ROOT = "https://api.cloudflare.com/client/v4"

#: (url, headers, body, content_type) -> (status_code, response_text)
HttpPost = Callable[[str, dict[str, str], bytes, str], tuple[int, str]]

#: Vectorize caps HTTP batch upserts at 5000; stay well under to bound request size.
DEFAULT_BATCH_SIZE = 1000

#: Vectorize returns at most 50 matches when metadata is requested.
MAX_TOP_K = 50


def _default_http_post(
    url: str, headers: dict[str, str], body: bytes, content_type: str
) -> tuple[int, str]:
    import httpx

    response = httpx.post(
        url, headers={**headers, "Content-Type": content_type}, content=body, timeout=60.0
    )
    return response.status_code, response.text


def _multipart_ndjson(ndjson: str) -> tuple[bytes, str]:
    """Wrap NDJSON as multipart/form-data under the field name Vectorize expects."""
    boundary = f"----digisearch{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="vectors"; filename="vectors.ndjson"\r\n'
        "Content-Type: application/x-ndjson\r\n\r\n"
        f"{ndjson}\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    return body, f"multipart/form-data; boundary={boundary}"


class VectorizeBackend(DigiIndex):
    """Cloudflare Vectorize-backed DigiIndex. Remote index; nothing is stored locally."""

    def __init__(
        self,
        name: str,
        *,
        account_id: str,
        api_token: str,
        embedding_provider: object | None = None,
        http_post: HttpPost | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self.name = name
        self.embedding_provider = embedding_provider
        self._account_id = account_id
        self._api_token = api_token
        self._post = http_post or _default_http_post
        self._batch_size = batch_size

    def _url(self, action: str) -> str:
        return f"{API_ROOT}/accounts/{self._account_id}/vectorize/v2/indexes/{self.name}/{action}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_token}"}

    def add(self, chunks: list[Chunk]) -> None:
        start = time.perf_counter()
        vectors = [c for c in chunks if c.embedding is not None]
        if not vectors:
            return
        for offset in range(0, len(vectors), self._batch_size):
            batch = vectors[offset : offset + self._batch_size]
            ndjson = "\n".join(
                json.dumps(
                    {
                        "id": c.id,
                        "values": list(c.embedding or []),
                        "metadata": {"doc_id": c.doc_id, **dict(c.metadata)},
                    }
                )
                for c in batch
            )
            body, content_type = _multipart_ndjson(ndjson)
            status, text = self._post(self._url("upsert"), self._headers(), body, content_type)
            if status >= 300:
                logger.error(
                    "vectorize upsert failed",
                    extra={
                        "operation": "vectorize_upsert",
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                        "outcome": "error",
                        "collection": self.name,
                        "chunk_count": len(batch),
                        "status_code": status,
                    },
                )
                raise RuntimeError(f"vectorize upsert failed ({status}): {text[:500]}")
        logger.info(
            "vectorize upsert done",
            extra={
                "operation": "vectorize_upsert",
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "outcome": "ok",
                "collection": self.name,
                "chunk_count": len(vectors),
            },
        )

    def update(self, chunks: list[Chunk]) -> None:
        self.add(chunks)

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        body = json.dumps({"ids": list(ids)}).encode()
        status, text = self._post(
            self._url("delete_by_ids"), self._headers(), body, "application/json"
        )
        if status >= 300:
            raise RuntimeError(f"vectorize delete failed ({status}): {text[:500]}")

    def list_collections(self) -> list[str]:
        return [self.name]

    def snapshot(self, path: str) -> None:
        raise NotImplementedError("Vectorize is the system of record; it is not snapshotted here")

    def query(self, query: Query) -> list[Result]:
        raise NotImplementedError("implemented in the next task")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ds/test_vectorize_backend.py -m unit -v --tb=short`
Expected: PASS (5 passed)

Run: `ruff check digisearch/src tests`
Expected: no findings.

- [ ] **Step 5: Commit**

```bash
git add digisearch/src/digisearch/indexes/backends/vectorize.py tests/ds/test_vectorize_backend.py
git commit -m "feat(digisearch): add VectorizeBackend upsert over the v2 REST API

Refs #2201

Upsert is multipart/form-data under field name 'vectors' carrying NDJSON,
not a plain JSON body — batched below the 5000-vector HTTP cap."
```

---

### Task 3: `VectorizeBackend.query`

**Files:**
- Modify: `digisearch/src/digisearch/indexes/backends/vectorize.py`
- Test: `tests/ds/test_vectorize_backend.py`

**Interfaces:**
- Consumes: `VectorizeBackend` and `HttpPost` from Task 2.
- Produces: a working `query(self, query: Query) -> list[Result]`. Task 4 depends on it.

**Behavioral requirement from the spec:** a query failure must surface as an error, NOT as zero results. `ChromaBackend.query` deliberately swallows errors and returns `[]`; **do not copy that here** — for a remote index, silent emptiness reads to a user as "the docs don't mention that."

- [ ] **Step 1: Write the failing test**

Append to `tests/ds/test_vectorize_backend.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/ds/test_vectorize_backend.py -m unit -v --tb=short`
Expected: FAIL with `NotImplementedError: implemented in the next task`

- [ ] **Step 3: Replace the `query` stub**

In `digisearch/src/digisearch/indexes/backends/vectorize.py`, replace the placeholder `query` with:

```python
    def query(self, query: Query) -> list[Result]:
        perf_start = time.perf_counter()
        vector = list(query.embedding or [])
        if not vector:
            # Chroma embeds query.text internally; a remote index cannot, so the
            # backend does it here rather than requiring every caller to remember.
            provider = self.embedding_provider or self._default_embedder()
            vector = provider.embed([query.text])[0]  # type: ignore[attr-defined]
        top_k = min(max(int(query.top_k), 1), MAX_TOP_K)
        payload: dict[str, Any] = {
            "vector": vector,
            "topK": top_k,
            "returnMetadata": "all",
            "returnValues": False,
        }
        status, text = self._post(
            self._url("query"), self._headers(), json.dumps(payload).encode(), "application/json"
        )
        if status >= 300:
            logger.error(
                "vectorize query failed",
                extra={
                    "operation": "vectorize_query",
                    "duration_ms": int((time.perf_counter() - perf_start) * 1000),
                    "outcome": "error",
                    "collection": self.name,
                    "top_k": top_k,
                    "status_code": status,
                },
            )
            raise RuntimeError(f"vectorize query failed ({status}): {text[:500]}")

        body = json.loads(text) if text else {}
        matches = ((body.get("result") or {}).get("matches")) or []
        out: list[Result] = []
        for rank, match in enumerate(matches):
            metadata = dict(match.get("metadata") or {})
            content = str(metadata.pop("content", ""))
            doc_id = str(metadata.pop("doc_id", ""))
            out.append(
                Result(
                    chunk=Chunk(
                        id=str(match.get("id", "")),
                        content=content,
                        doc_id=doc_id,
                        embedding=None,
                        metadata=metadata,
                    ),
                    score=float(match.get("score", 0.0)),
                    source_doc=None,
                    rank=rank,
                )
            )
        logger.info(
            "vectorize query done",
            extra={
                "operation": "vectorize_query",
                "duration_ms": int((time.perf_counter() - perf_start) * 1000),
                "outcome": "ok",
                "collection": self.name,
                "top_k": top_k,
                "result_count": len(out),
            },
        )
        return out
```

Add the lazy default so the backend works with no provider injected:

```python
    def _default_embedder(self) -> object:
        from digisearch.embedding.providers.minilm import MiniLMEmbedder

        return MiniLMEmbedder()
```

Note the round-trip contract this establishes: `add()` stores `doc_id` in metadata and the sync script (Task 5) stores `content` there too, because Vectorize returns only ids, scores and metadata — there is no document store behind it.

- [ ] **Step 4: Add `content` to the upsert metadata**

In `add()`, change the metadata dict so the chunk text survives the round trip:

```python
                        "metadata": {
                            "doc_id": c.doc_id,
                            "content": c.content,
                            **dict(c.metadata),
                        },
```

Update the Task 2 assertion in `test_add_posts_ndjson_multipart_to_upsert` to match by appending:

```python
    assert first["metadata"]["content"] == "content 0"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ds/test_vectorize_backend.py -m unit -v --tb=short`
Expected: PASS (10 passed)

Run: `ruff check digisearch/src tests`
Expected: no findings.

- [ ] **Step 6: Commit**

```bash
git add digisearch/src/digisearch/indexes/backends/vectorize.py tests/ds/test_vectorize_backend.py
git commit -m "feat(digisearch): implement VectorizeBackend.query

Refs #2201

Raises on a failed query rather than returning [] like the Chroma backend:
for a remote index, silent emptiness reads to a user as 'the docs don't
mention that'. Chunk text rides in vector metadata because Vectorize
returns only id/score/metadata."
```

---

### Task 4: Register Vectorize ahead of Chroma in the backend chain

**Files:**
- Modify: `digisearch/src/digisearch/search/_stub.py`
- Modify: `digisearch/src/digisearch/core/standard_hits.py`
- Test: `tests/ds/test_vectorize_selection.py` (create)

**Interfaces:**
- Consumes: `VectorizeBackend` from Tasks 2-3.
- Produces: `BACKEND_VECTORIZE = "vectorize"` importable from `digisearch.core.standard_hits`; a `_vectorize_backend` registered `_BackendFn`; `route_add_chunks` returning `BACKEND_VECTORIZE` when configured.

**Key mechanic:** `search/_stub.py` uses a `@register_backend` registry where **registration order is try order** (`_azure_backend` is defined first and wins, then `_chroma_backend`). Define `_vectorize_backend` **immediately before** `_chroma_backend` so Vectorize is tried first among the non-Azure backends.

- [ ] **Step 1: Write the failing test**

Create `tests/ds/test_vectorize_selection.py`:

```python
"""Backend selection: Vectorize wins over Chroma when configured."""

from __future__ import annotations

import pytest

from digisearch.core.models import Query
from digisearch.core.standard_hits import BACKEND_VECTORIZE
from digisearch.search import _stub


@pytest.mark.unit
def test_vectorize_selected_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VECTORIZE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("VECTORIZE_API_TOKEN", "tok")
    monkeypatch.setenv("CHROMA_PATH", "/tmp/should-be-ignored")

    captured: dict[str, object] = {}

    class _Stub:
        def __init__(self, name: str, **kwargs: object) -> None:
            captured["name"] = name
            captured["kwargs"] = kwargs

        def query(self, _q: Query) -> list[object]:
            return []

    monkeypatch.setattr(
        "digisearch.indexes.backends.vectorize.VectorizeBackend", _Stub, raising=True
    )
    response = _stub._vectorize_backend(Query(text="hi", top_k=3, embedding=[0.0] * 384), "occ_help")
    assert response is not None
    assert response.backend == BACKEND_VECTORIZE
    assert captured["name"] == "occ_help"


@pytest.mark.unit
def test_vectorize_inactive_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VECTORIZE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("VECTORIZE_API_TOKEN", raising=False)
    assert _stub._vectorize_backend(Query(text="hi", top_k=3), "i") is None


@pytest.mark.unit
def test_vectorize_registered_before_chroma() -> None:
    names = [fn.__name__ for fn in _stub._backends]
    assert "_vectorize_backend" in names
    assert names.index("_vectorize_backend") < names.index("_chroma_backend")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/ds/test_vectorize_selection.py -m unit -v --tb=short`
Expected: FAIL with `ImportError: cannot import name 'BACKEND_VECTORIZE'`

- [ ] **Step 3: Add the backend constant**

In `digisearch/src/digisearch/core/standard_hits.py`, alongside the existing `BACKEND_CHROMA` / `BACKEND_STUB` definitions, add:

```python
BACKEND_VECTORIZE = "vectorize"
```

- [ ] **Step 4: Register the query-path backend**

In `digisearch/src/digisearch/search/_stub.py`, update the import line to include the new constant:

```python
from digisearch.core.standard_hits import BACKEND_CHROMA, BACKEND_STUB, BACKEND_VECTORIZE
```

Then insert this function **immediately above** the existing `@register_backend def _chroma_backend(...)`:

```python
@register_backend
def _vectorize_backend(query: Query, index_name: str) -> SearchResponse | None:
    """Cloudflare Vectorize backend. Active when VECTORIZE_ACCOUNT_ID + VECTORIZE_API_TOKEN are set."""
    account_id = os.environ.get("VECTORIZE_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("VECTORIZE_API_TOKEN", "").strip()
    if not account_id or not api_token:
        return None
    from digisearch.indexes.backends.vectorize import VectorizeBackend

    backend = VectorizeBackend(index_name, account_id=account_id, api_token=api_token)
    results = backend.query(query)
    return SearchResponse(results=list(results), facets=None, backend=BACKEND_VECTORIZE)
```

Deliberately **not** wrapped in the `try/except _BACKEND_ERRORS` that `_chroma_backend` uses: a configured remote index that errors must surface, not fall through to Chroma or the stub and answer from a different (or empty) corpus.

- [ ] **Step 5: Route ingest to Vectorize too**

In `route_add_chunks` in the same file, insert this **before** the existing `chroma_path = os.environ.get("CHROMA_PATH")` line:

```python
    vectorize_account = os.environ.get("VECTORIZE_ACCOUNT_ID", "").strip()
    vectorize_token = os.environ.get("VECTORIZE_API_TOKEN", "").strip()
    if vectorize_account and vectorize_token:
        from digisearch.indexes.backends.vectorize import VectorizeBackend

        backend = VectorizeBackend(
            index_name, account_id=vectorize_account, api_token=vectorize_token
        )
        backend.add(chunks)
        return BACKEND_VECTORIZE
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ds/test_vectorize_selection.py tests/ds/ -m unit -v --tb=short`
Expected: PASS. The whole `tests/ds/` suite must stay green — Chroma selection is unchanged when `VECTORIZE_*` is unset, which the pre-existing tests cover.

Run: `ruff check digisearch/src tests`
Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add digisearch/src/digisearch/search/_stub.py digisearch/src/digisearch/core/standard_hits.py tests/ds/test_vectorize_selection.py
git commit -m "feat(digisearch): select Vectorize ahead of Chroma when configured

Refs #2201

Registration order is try order, so _vectorize_backend is defined directly
above _chroma_backend. Unlike Chroma it does not swallow errors: a
configured remote index that fails must surface rather than silently
answering from a different corpus."
```

---

### Task 5: `scripts/vectorize_sync.py` — Supabase → Vectorize

**Files:**
- Create: `scripts/vectorize_sync.py`
- Test: `tests/scripts/test_vectorize_sync.py` (create)

**Interfaces:**
- Consumes: `SupabaseStore.list_notes` (Task 1); `VectorizeBackend` (Tasks 2-3); `SegmentAwareChunker` from `digisearch.ingestion.chunkers.segment_aware`; `heading_segments` from `digisearch.ingestion.segmenters.heading`.
- Produces: `sync_corpus(notes, chunker, embedder, backend, *, model_id) -> int` returning the number of vectors upserted, plus a `main(argv)` CLI.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_vectorize_sync.py`:

```python
"""Tests for the Supabase -> Vectorize sync."""

from __future__ import annotations

from typing import Any  # score:allow untyped any — recording doubles hold open dicts

import pytest

from scripts.vectorize_sync import sync_corpus

pytestmark = pytest.mark.unit


class _StubEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.5] * 384 for _ in texts]

    @property
    def dimensions(self) -> int:
        return 384


class _RecordingBackend:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, chunks: list[Any]) -> None:
        self.added.extend(chunks)


def _note(path: str, body: str) -> dict[str, Any]:
    return {"vault_path": path, "title": path, "frontmatter": {}, "body_markdown": body}


def test_sync_embeds_and_upserts_every_chunk() -> None:
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    notes = [_note("clients/acme/a", "# A\n\nbody a\n"), _note("clients/acme/b", "# B\n\nbody b\n")]
    backend = _RecordingBackend()
    count = sync_corpus(
        notes, SegmentAwareChunker(), _StubEmbedder(), backend, model_id="minilm-384"
    )
    assert count == len(backend.added)
    assert count >= 2
    assert all(c.embedding is not None and len(c.embedding) == 384 for c in backend.added)


def test_sync_stamps_model_id_and_source_on_every_chunk() -> None:
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    backend = _RecordingBackend()
    sync_corpus(
        [_note("clients/acme/a", "# A\n\nbody\n")],
        SegmentAwareChunker(),
        _StubEmbedder(),
        backend,
        model_id="minilm-384",
    )
    assert all(c.metadata["embedding_model"] == "minilm-384" for c in backend.added)
    assert all(c.metadata["vault_path"] == "clients/acme/a" for c in backend.added)


def test_sync_skips_notes_with_empty_bodies() -> None:
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    backend = _RecordingBackend()
    count = sync_corpus(
        [_note("clients/acme/blank", "   ")],
        SegmentAwareChunker(),
        _StubEmbedder(),
        backend,
        model_id="m",
    )
    assert count == 0
    assert backend.added == []


def test_sync_ids_are_deterministic() -> None:
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    notes = [_note("clients/acme/a", "# A\n\nbody a\n")]
    first, second = _RecordingBackend(), _RecordingBackend()
    sync_corpus(notes, SegmentAwareChunker(), _StubEmbedder(), first, model_id="m")
    sync_corpus(notes, SegmentAwareChunker(), _StubEmbedder(), second, model_id="m")
    assert [c.id for c in first.added] == [c.id for c in second.added]
```

Determinism matters: Vectorize upserts by id, so a re-sync must overwrite the same vectors rather than accumulating duplicates — the same class of bug as #2122/#2138.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/scripts/test_vectorize_sync.py -m unit -v --tb=short`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.vectorize_sync'`

- [ ] **Step 3: Write the sync script**

Create `scripts/vectorize_sync.py`:

```python
#!/usr/bin/env python3
"""Sync onboard notes from Supabase ``architecture_notes`` into Cloudflare Vectorize.

Runs on an operator machine or in CI — never inside the Cloudflare Container, which
only ever queries. Chunking goes through the same SegmentAwareChunker path production
retrieval assumes, so the index matches the pipeline that was validated.

Apply::

    CORE_SUPABASE_URL=… CORE_SUPABASE_ANON_KEY=… \\
    VECTORIZE_ACCOUNT_ID=… VECTORIZE_API_TOKEN=… \\
      python3 scripts/vectorize_sync.py --prefix clients/digithings --index digithings_docs
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from typing import Any, Protocol  # score:allow untyped any — Supabase rows are open dicts

from digisearch.core.models import Chunk, Document, Segment

#: Identifies the embedding model in every vector's metadata. Upsert and query must
#: use the same model; the sync refuses to mix models within one index.
DEFAULT_MODEL_ID = "all-MiniLM-L6-v2-384"  # must equal MINILM_MODEL_ID from Task 0


class ModelMismatchError(RuntimeError):
    """Raised when an index already holds vectors from a different embedding model."""


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorSink(Protocol):
    def add(self, chunks: list[Chunk]) -> None: ...


class ChunkerProtocol(Protocol):
    def chunk(self, doc: Document) -> list[Chunk]: ...


def _vector_id(vault_path: str, chunk_index: int) -> str:
    """Deterministic id so a re-sync overwrites rather than duplicating."""
    digest = hashlib.sha1(vault_path.encode("utf-8")).hexdigest()[:24]
    return f"{digest}-{chunk_index:05d}"


def sync_corpus(
    notes: list[dict[str, Any]],
    chunker: ChunkerProtocol,
    embedder: Embedder,
    sink: VectorSink,
    *,
    model_id: str = DEFAULT_MODEL_ID,
) -> int:
    """Chunk, embed and upsert every note. Returns the number of vectors sent."""
    total = 0
    for note in notes:
        vault_path = str(note.get("vault_path") or "").strip()
        body = str(note.get("body_markdown") or "")
        if not vault_path or not body.strip():
            continue
        doc = Document(
            id=vault_path,
            content=body,
            source=f"vault://{vault_path}",
            doc_type="markdown",
            metadata={},
            segments=_segments_for(body),
        )
        chunks = chunker.chunk(doc)
        if not chunks:
            continue
        embeddings = embedder.embed([c.content for c in chunks])
        prepared: list[Chunk] = []
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
            prepared.append(
                Chunk(
                    id=_vector_id(vault_path, index),
                    content=chunk.content,
                    doc_id=vault_path,
                    embedding=list(embedding),
                    metadata={
                        **dict(chunk.metadata),
                        "vault_path": vault_path,
                        "title": str(note.get("title") or ""),
                        "embedding_model": model_id,
                    },
                )
            )
        sink.add(prepared)
        total += len(prepared)
    return total


def _segments_for(body: str) -> list[Segment]:
    from digisearch.ingestion.segmenters.heading import heading_segments

    return heading_segments(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, help="vault_path prefix, e.g. clients/digithings")
    parser.add_argument("--index", required=True, help="Vectorize index name, e.g. digithings_docs")
    parser.add_argument("--dry-run", action="store_true", help="Chunk and count; do not upsert.")
    args = parser.parse_args(argv)

    import os

    from digisearch.embedding.providers.minilm import MINILM_MODEL_ID, MiniLMEmbedder
    from digisearch.indexes.backends.vectorize import VectorizeBackend
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker
    from digivault.supabase_store import SupabaseStore

    notes = SupabaseStore.from_env().list_notes(path_prefix=args.prefix)
    print(f"{len(notes)} notes under {args.prefix!r}", file=sys.stderr)

    class _CountingSink:
        def __init__(self) -> None:
            self.count = 0

        def add(self, chunks: list[Chunk]) -> None:
            self.count += len(chunks)

    sink: VectorSink
    if args.dry_run:
        sink = _CountingSink()
    else:
        account_id = os.environ.get("VECTORIZE_ACCOUNT_ID", "").strip()
        api_token = os.environ.get("VECTORIZE_API_TOKEN", "").strip()
        if not account_id or not api_token:
            raise SystemExit("VECTORIZE_ACCOUNT_ID and VECTORIZE_API_TOKEN are required")
        sink = VectorizeBackend(args.index, account_id=account_id, api_token=api_token)

    total = sync_corpus(notes, SegmentAwareChunker(), MiniLMEmbedder(), sink, model_id=MINILM_MODEL_ID)
    print(f"{'would upsert' if args.dry_run else 'upserted'} {total} vectors → {args.index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`MiniLMEmbedder` and `MINILM_MODEL_ID` come from Task 0. The tests inject
`_StubEmbedder` and do not depend on either.

- [ ] **Step 4: Add the model-mismatch guard the spec requires**

The spec requires the sync to *refuse* to upsert into an index whose existing
vectors report a different embedding model — stamping `embedding_model` alone
only makes a mismatch detectable after the damage. Add the failing test first:

```python
def test_sync_refuses_to_mix_embedding_models() -> None:
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker

    from scripts.vectorize_sync import ModelMismatchError, assert_index_model

    class _ProbeBackend(_RecordingBackend):
        def query(self, _q: Any) -> list[Any]:
            class _R:
                metadata = {"embedding_model": "some-other-model-768"}

            class _Hit:
                chunk = _R()

            return [_Hit()]

    with pytest.raises(ModelMismatchError, match="some-other-model-768"):
        assert_index_model(_ProbeBackend(), model_id="all-MiniLM-L6-v2-384", dimensions=384)


def test_sync_allows_matching_or_empty_index() -> None:
    from scripts.vectorize_sync import assert_index_model

    class _EmptyBackend:
        def query(self, _q: Any) -> list[Any]:
            return []

    assert_index_model(_EmptyBackend(), model_id="m", dimensions=384)
```

Run: `.venv/bin/python -m pytest tests/scripts/test_vectorize_sync.py -m unit -v --tb=short`
Expected: FAIL with `ImportError: cannot import name 'assert_index_model'`

Then add to `scripts/vectorize_sync.py`:

```python
def assert_index_model(backend: Any, *, model_id: str, dimensions: int) -> None:
    """Refuse to upsert into an index whose existing vectors used a different model.

    A silent model mismatch does not error — it degrades retrieval, because the
    query vector and the stored vectors no longer share a space. Probing one
    existing vector is cheap insurance.
    """
    from digisearch.core.models import Query as DsQuery

    try:
        hits = backend.query(DsQuery(text="", top_k=1, embedding=[0.0] * dimensions))
    except Exception:  # noqa: BLE001 - an unreachable or empty index must not block a first sync
        return
    for hit in hits:
        existing = str(getattr(hit.chunk, "metadata", {}).get("embedding_model") or "").strip()
        if existing and existing != model_id:
            raise ModelMismatchError(
                f"index already holds vectors from {existing!r}; refusing to upsert {model_id!r}. "
                "Delete and recreate the index, or sync with the original model."
            )
```

Call it from `main()` immediately after the sink is constructed, before `sync_corpus`, guarded so `--dry-run` skips it:

```python
    if not args.dry_run:
        assert_index_model(sink, model_id=DEFAULT_MODEL_ID, dimensions=384)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/scripts/test_vectorize_sync.py -m unit -v --tb=short`
Expected: PASS (6 passed)

Run: `ruff check scripts tests`
Expected: no findings.

- [ ] **Step 6: Commit**

```bash
git add scripts/vectorize_sync.py tests/scripts/test_vectorize_sync.py
git commit -m "feat: add Supabase -> Vectorize corpus sync

Refs #2201

Vector ids are deterministic (sha1 of vault_path + chunk index) so a
re-sync overwrites rather than duplicating — the same failure #2122/#2138
describe for the Chroma path."
```

---

### Task 6: Cloudflare container wiring

**Files:**
- Modify: `frontend/digithings-stack-cloudflare/src/index.ts`
- Modify: `frontend/digithings-stack-cloudflare/container/entrypoint.sh`
- Modify: `frontend/digithings-stack-cloudflare/container/seed_chroma.sh`
- Modify: `frontend/digithings-stack-cloudflare/container/start_digisearch.sh`
- Modify: `frontend/digithings-stack-cloudflare/wrangler.toml`
- Modify: `frontend/digithings-stack-cloudflare/README.md`

**Interfaces:**
- Consumes: the `VECTORIZE_ACCOUNT_ID` / `VECTORIZE_API_TOKEN` env contract from Task 4.
- Produces: a production container that queries Vectorize and performs no boot seeding.

**The trap this task exists to avoid:** the container env is an **explicit whitelist** in `src/index.ts`. A `wrangler secret put VECTORIZE_API_TOKEN` alone would populate the Worker but **never reach the container**. Both the `envVars` object and the `Env` interface must be edited or nothing works.

- [ ] **Step 1: Forward the new vars to the container**

In `frontend/digithings-stack-cloudflare/src/index.ts`, add to the `envVars` object literal (alongside the existing `CHROMA_PATH` / `DIGISEARCH_INDEX` entries):

```ts
      VECTORIZE_ACCOUNT_ID: env.VECTORIZE_ACCOUNT_ID ?? "",
      VECTORIZE_API_TOKEN: env.VECTORIZE_API_TOKEN ?? "",
```

and to the `Env` interface:

```ts
  VECTORIZE_ACCOUNT_ID?: string;
  VECTORIZE_API_TOKEN?: string;
```

- [ ] **Step 2: Stop exporting CHROMA_PATH when Vectorize is configured**

In `container/entrypoint.sh`, replace the unconditional `export CHROMA_PATH="$DATA_CHROMA"` line with:

```sh
# Vectorize is a remote index: exporting CHROMA_PATH would make _stub.py's
# Chroma branch win and answer from an empty local index instead.
if [ -n "${VECTORIZE_ACCOUNT_ID:-}" ] && [ -n "${VECTORIZE_API_TOKEN:-}" ]; then
  unset CHROMA_PATH
  echo "digithings-stack: Vectorize configured; skipping local chroma"
else
  export CHROMA_PATH="$DATA_CHROMA"
fi
```

Keep the `mkdir -p "$DATA_CHROMA" ...` line as-is; the directory is harmless and `DATA_CHROMA` is still referenced under `set -eu`.

- [ ] **Step 3: Make the seed oneshot a no-op under Vectorize**

At the top of `container/seed_chroma.sh`, immediately after the `set -eu` line and the `DATA_CHROMA=` assignment, add:

```sh
if [ -n "${VECTORIZE_ACCOUNT_ID:-}" ] && [ -n "${VECTORIZE_API_TOKEN:-}" ]; then
  echo "digithings-stack: Vectorize configured; skipping chroma seed"
  exit 0
fi
```

And in `container/start_digisearch.sh`, immediately after its `DATA_CHROMA=` assignment, add the same guard so it does not wait 180s for a marker that will never be written:

```sh
if [ -n "${VECTORIZE_ACCOUNT_ID:-}" ] && [ -n "${VECTORIZE_API_TOKEN:-}" ]; then
  echo "digithings-stack: Vectorize configured; starting digisearch without seed wait"
  exec uvicorn digisearch.server:app --host 127.0.0.1 --port 8002
fi
```

- [ ] **Step 4: Document the secrets**

In `wrangler.toml`, add to the existing `# Secrets (wrangler secret put)` comment block:

```
#   VECTORIZE_ACCOUNT_ID      # Cloudflare account id owning the Vectorize indexes
#   VECTORIZE_API_TOKEN       # Vectorize access; prefer a read-scoped token if available
```

In `README.md`, replace the boot-sequence bullet describing the chroma seed wait with a note that when `VECTORIZE_*` is set the container performs no seeding and queries the remote index, and that container disk is ephemeral so nothing is persisted locally either way.

- [ ] **Step 5: Verify the shell scripts still parse**

Run:

```bash
sh -n frontend/digithings-stack-cloudflare/container/entrypoint.sh
sh -n frontend/digithings-stack-cloudflare/container/seed_chroma.sh
sh -n frontend/digithings-stack-cloudflare/container/start_digisearch.sh
```
Expected: no output from any of the three.

Run: `cd frontend/digithings-stack-cloudflare && npx tsc --noEmit -p tsconfig.json`
Expected: no errors. (If the package has no `tsconfig.json`, run `npx wrangler deploy --dry-run` instead and expect it to complete without type errors.)

Run: `make doc-check`
Expected: no broken internal links.

- [ ] **Step 6: Commit**

```bash
git add frontend/digithings-stack-cloudflare/
git commit -m "feat(stack): wire Vectorize into the Cloudflare container

Refs #2201

The container env is an explicit whitelist, so VECTORIZE_* must be added to
both envVars and the Env interface or a wrangler secret never reaches the
container. With Vectorize configured the container stops exporting
CHROMA_PATH and performs no boot seeding at all."
```

---

### Task 7: Surface `vectorize` as a reported backend and update ARCHITECTURE.md

**Files:**
- Modify: `digisearch/src/digisearch/server.py`
- Modify: `digisearch/ARCHITECTURE.md`
- Test: `tests/ds/test_vectorize_selection.py`

**Interfaces:**
- Consumes: `BACKEND_VECTORIZE` from Task 4.
- Produces: nothing downstream — terminal task.

- [ ] **Step 1: Write the failing test**

Append to `tests/ds/test_vectorize_selection.py`:

```python
@pytest.mark.unit
def test_query_response_documents_vectorize_backend() -> None:
    from digisearch.server import QueryResponse

    field = QueryResponse.model_fields["backend"]
    assert "vectorize" in str(field.description)


@pytest.mark.unit
def test_real_backend_check_accepts_vectorize(monkeypatch: pytest.MonkeyPatch) -> None:
    from digisearch.server import _require_real_search_backend

    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    monkeypatch.delenv("DIGISEARCH_ALLOW_STUB", raising=False)
    monkeypatch.setenv("VECTORIZE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("VECTORIZE_API_TOKEN", "tok")
    _require_real_search_backend()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/ds/test_vectorize_selection.py -m unit -v --tb=short`
Expected: FAIL — the description assertion fails, and `_require_real_search_backend` raises because it only recognises Azure and Chroma.

- [ ] **Step 3: Update the server**

In `digisearch/src/digisearch/server.py`, update the `backend` field description on `QueryResponse` to read:

```python
        description="Index backend that served the query: vectorize | azure_ai_search | chroma | stub",
```

In `_require_real_search_backend()`, treat a configured Vectorize as a real backend by returning early before the existing Azure/Chroma checks:

```python
    if os.environ.get("VECTORIZE_ACCOUNT_ID", "").strip() and os.environ.get(
        "VECTORIZE_API_TOKEN", ""
    ).strip():
        return
```

and extend the final error message so it names the new option:

```python
            "digisearch requires a real backend: set VECTORIZE_ACCOUNT_ID+VECTORIZE_API_TOKEN, "
            "AZURE_SEARCH_* or CHROMA_PATH/CHROMA_HOST, "
```

(keep the rest of that string unchanged).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ds/ -m unit -v --tb=short`
Expected: PASS, whole suite green.

- [ ] **Step 5: Update ARCHITECTURE.md**

In `digisearch/ARCHITECTURE.md`, locate each place the backends are enumerated (the component/status table, the backends section, and the public-surface table) and add `VectorizeBackend` / `vectorize` alongside Chroma and Azure. Then add a subsection under the backends section:

```markdown
#### Vectorize (remote index)

`indexes/backends/vectorize.py` implements `DigiIndex` over the Cloudflare
Vectorize v2 REST API. It is selected ahead of Chroma whenever
`VECTORIZE_ACCOUNT_ID` and `VECTORIZE_API_TOKEN` are set, and is what the
production Cloudflare Container uses.

It exists because Cloudflare Container disk is ephemeral: a container-local
index has to be rebuilt on every cold boot, which for the onboard corpus means
re-embedding roughly 1,500 chunks each wake. With Vectorize the container holds
no corpus and only queries.

Two operational notes. Upsert and query MUST use the same embedding model
(MiniLM, 384 dimensions) — every vector records `embedding_model` in its
metadata so a mismatch is detectable. And unlike `ChromaBackend.query`, which
returns `[]` on error, this backend raises: for a remote index a silent empty
result is indistinguishable to a user from "the docs do not mention that".

Chunk text rides in vector metadata (`content`), because Vectorize returns only
ids, scores and metadata — there is no document store behind it.
```

Verify each claim against the code you actually wrote rather than against this
plan's prose.

- [ ] **Step 6: Verify and commit**

Run: `make doc-check`
Expected: no broken internal links.

Run: `ruff check digisearch/src scripts tests`
Expected: no findings.

```bash
git add digisearch/src/digisearch/server.py digisearch/ARCHITECTURE.md tests/ds/test_vectorize_selection.py
git commit -m "feat(digisearch): report vectorize as a backend and document it

Refs #2201"
```

---

## After the plan

Deliberately **not** in this plan:

1. **Creating the Vectorize indexes and running the first sync.** That is an operator step needing a Cloudflare API token: create `digithings_docs` and `occ_help` with **384 dimensions** and cosine metric, then run `scripts/vectorize_sync.py --dry-run` for each prefix before applying. The spec requires a manual live check (fixture index → upsert → query → verify segment metadata → delete) before production cutover.
2. **Deploying.** Production only picks this up after a `wrangler deploy` **and** the secrets being set. Note the image must be rebuilt — `docker compose up` reuses a baked image, which already caused one silently invalid live test.
3. **Retiring the baked seed corpus.** `container/seed/` stays for local and offline use; this plan only stops production depending on it.
4. **The digivault half.** Keyword search still reads Supabase and has its own three production blockers (missing `supabase` extra in the image, `entrypoint.sh` re-defaulting an empty `DIGIVAULT_ROOT`, and the same `envVars` whitelist gap). Task 1 here adds `list_notes` to `SupabaseStore` but does not address those.
5. **A read-scoped API token.** The spec flags preferring one if Cloudflare supports it; check at Task 6 time, since the token reaching the container currently carries index write access.
