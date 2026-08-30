"""Cloudflare Vectorize backend for digisearch. Implements DigiIndex over the v2 REST API."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from digisearch.core.models import Chunk, Query, Result
from digisearch.indexes.backends.vectorize_errors import (
    VectorizeBackendError as VectorizeBackendError,
)
from digisearch.indexes.base import DigiIndex

logger = logging.getLogger(__name__)

API_ROOT = "https://api.cloudflare.com/client/v4"

#: (url, headers, body, content_type) -> (status_code, response_text)
HttpPost = Callable[[str, dict[str, str], bytes, str], tuple[int, str]]

#: Vectorize caps HTTP batch upserts at 5000; stay well under to bound request size.
DEFAULT_BATCH_SIZE = 1000

#: Vectorize returns at most 50 matches when metadata is requested.
MAX_TOP_K = 50

# `VectorizeBackendError` is defined in `vectorize_errors.py`, not here, and re-exported
# above (the redundant `as VectorizeBackendError` alias marks that deliberately, so
# ruff's F401 doesn't flag it as unused) -- see that module's docstring for why: it
# must stay importable even when importing *this* module fails.


#: Process-wide singleton for the default embedder, shared across every
#: `VectorizeBackend` instance. `_vectorize_backend` in `_stub.py` constructs a
#: fresh `VectorizeBackend` on every query (no production call site injects
#: `embedding_provider` or populates `Query.embedding`), so per-instance
#: memoization alone still reloads the ONNX model on every single query. The
#: default embedder is stateless and identical for every caller, so sharing it
#: process-wide is safe. This cache is for the *default* embedder only -- an
#: *injected* `embedding_provider` always stays on `self.embedding_provider`
#: (per-instance) and is never read from or written into this global.
_default_embedder_singleton: object | None = None


def _get_default_embedder() -> object:
    """Return the module-level default embedder, constructing it at most once
    per process (see `_default_embedder_singleton`)."""
    global _default_embedder_singleton
    if _default_embedder_singleton is None:
        from digisearch.embedding.providers.minilm import MiniLMEmbedder

        _default_embedder_singleton = MiniLMEmbedder()
    return _default_embedder_singleton


def _default_http_post(
    url: str, headers: dict[str, str], body: bytes, content_type: str
) -> tuple[int, str]:
    import httpx

    response = httpx.post(
        url, headers={**headers, "Content-Type": content_type}, content=body, timeout=60.0
    )
    return response.status_code, response.text


def _parse_response_body(text: str) -> dict[str, Any]:
    """Best-effort JSON parse of a Vectorize response body; ``{}`` on anything else.

    A non-JSON body (e.g. an HTML error page on a transport-level failure) must
    not raise out of the parser itself — the caller still needs to fall through
    to its own status-code-based error message.
    """
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _raise_if_vectorize_failed(operation: str, status: int, text: str) -> dict[str, Any]:
    """Raise ``RuntimeError`` if a Vectorize response failed; else return its body.

    Checks both the HTTP status *and* the body-level ``success``/``result``
    fields: Vectorize can answer HTTP 200 with an application-level failure
    (``success: false``, ``result: null``), which a status-only check misses.
    Never includes the API token — callers only pass ``status``/``text``, and
    the token is never echoed back in a Vectorize response body.
    """
    body = _parse_response_body(text)
    if status < 300 and body.get("success") is not False and body.get("result") is not None:
        return body
    errors = body.get("errors") or []
    detail = json.dumps(errors)[:500] if errors else text[:500]
    raise RuntimeError(f"vectorize {operation} failed ({status}): {detail}")


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
        if not chunks:
            return

        unembedded = [c for c in chunks if c.embedding is None]
        if unembedded:
            provider = self.embedding_provider or self._default_embedder()
            embeddings = provider.embed([c.content for c in unembedded])  # type: ignore[attr-defined]
            for chunk, embedding in zip(unembedded, embeddings, strict=True):
                chunk.embedding = [float(v) for v in embedding]

        vectors = [c for c in chunks if c.embedding is not None]
        skipped = len(chunks) - len(vectors)
        if skipped:
            raise RuntimeError(
                f"vectorize upsert skipped {skipped} of {len(chunks)} chunks with no embedding"
            )
        if not vectors:
            raise RuntimeError("vectorize upsert received chunks but wrote nothing (no embeddings)")
        for offset in range(0, len(vectors), self._batch_size):
            batch = vectors[offset : offset + self._batch_size]
            ndjson = "\n".join(
                json.dumps(
                    {
                        "id": c.id,
                        # float(v) guards against a numpy dtype (e.g. float32) reaching
                        # json.dumps — Chunk.embedding is typed list[float], but that is
                        # not runtime-enforced, and non-plain floats raise TypeError here.
                        # Iterate the embedding directly (never `or []`) — the filter
                        # above already guarantees c.embedding is not None, and `or`
                        # would truthiness-check it first, which raises ValueError for
                        # a numpy array with more than one element.
                        "values": [float(v) for v in c.embedding],
                        # doc_id and content last so the canonical values always win over
                        # caller-supplied metadata["doc_id"]/["content"]. Vectorize returns
                        # only id/score/metadata on query, so content rides here too — there
                        # is no document store behind this backend to reconstruct it from.
                        "metadata": {
                            **dict(c.metadata),
                            "doc_id": c.doc_id,
                            "content": c.content,
                        },
                    }
                )
                for c in batch
            )
            body, content_type = _multipart_ndjson(ndjson)
            status, text = self._post(self._url("upsert"), self._headers(), body, content_type)
            try:
                _raise_if_vectorize_failed("upsert", status, text)
            except RuntimeError:
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
                raise
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
        start = time.perf_counter()
        body = json.dumps({"ids": list(ids)}).encode()
        status, text = self._post(
            self._url("delete_by_ids"), self._headers(), body, "application/json"
        )
        try:
            _raise_if_vectorize_failed("delete", status, text)
        except RuntimeError:
            logger.error(
                "vectorize delete failed",
                extra={
                    "operation": "vectorize_delete",
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "outcome": "error",
                    "collection": self.name,
                    "id_count": len(ids),
                    "status_code": status,
                },
            )
            raise

    def list_collections(self) -> list[str]:
        return [self.name]

    def snapshot(self, path: str) -> None:
        raise NotImplementedError("Vectorize is the system of record; it is not snapshotted here")

    def _default_embedder(self) -> object:
        """Return the process-wide default embedder, constructed at most once
        per process regardless of how many `VectorizeBackend` instances exist.

        Not called from `__init__` — building an ONNX model eagerly would pay
        the load cost even for backends that never hit this path (an injected
        `embedding_provider` or a caller that always supplies `Query.embedding`).
        Module-level rather than per-instance: a fresh `VectorizeBackend` is
        constructed on every query in production (see `_stub._vectorize_backend`),
        so per-instance memoization alone would still reload the model every call.
        """
        return _get_default_embedder()

    def query(self, query: Query) -> list[Result]:
        perf_start = time.perf_counter()
        vector = list(query.embedding or [])
        if not vector:
            # Chroma embeds query.text internally; a remote index cannot, so the
            # backend does it here rather than requiring every caller to remember.
            provider = self.embedding_provider or self._default_embedder()
            vector = provider.embed([query.text])[0]  # type: ignore[attr-defined]
        requested_top_k = max(int(query.top_k), 1)
        top_k = min(requested_top_k, MAX_TOP_K)
        if requested_top_k > MAX_TOP_K:
            # I4: silent truncation here is exactly what lets a caller like
            # `digisearch_fetch_all` believe a 50-result page is a complete result
            # set. This does not by itself fix pagination against Vectorize (that
            # needs the caller to know too — see `_stub.py` / `server.py`), but it
            # makes the clamp visible in logs rather than swallowed entirely.
            logger.warning(
                "vectorize query top_k clamped from %d to %d (Vectorize returns at most "
                "%d matches with metadata per query)",
                requested_top_k,
                top_k,
                MAX_TOP_K,
                extra={
                    "operation": "vectorize_query",
                    "outcome": "clamped",
                    "collection": self.name,
                    "requested_top_k": requested_top_k,
                    "top_k": top_k,
                },
            )
        payload: dict[str, Any] = {
            "vector": vector,
            "topK": top_k,
            "returnMetadata": "all",
            "returnValues": False,
        }
        status, text = self._post(
            self._url("query"), self._headers(), json.dumps(payload).encode(), "application/json"
        )
        try:
            body = _raise_if_vectorize_failed("query", status, text)
        except RuntimeError:
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
            raise
        # `_raise_if_vectorize_failed` already treats a missing `result` as a
        # failure, so `result` here is always a dict.
        matches = (body.get("result") or {}).get("matches") or []
        out: list[Result] = []
        for rank, match in enumerate(matches):
            raw_metadata = match.get("metadata")
            metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
            content = str(metadata.pop("content", ""))
            doc_id = str(metadata.pop("doc_id", ""))
            raw_score = match.get("score")
            out.append(
                Result(
                    chunk=Chunk(
                        id=str(match.get("id", "")),
                        content=content,
                        doc_id=doc_id,
                        embedding=None,
                        metadata=metadata,
                    ),
                    score=float(raw_score) if raw_score is not None else 0.0,
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
