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
        # Lazily constructed on first use when embedding_provider is not injected
        # and Query.embedding is absent; memoized so the ONNX model loads at most
        # once per backend instance rather than once per query.
        self._lazy_default_embedder: object | None = None

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

    def _default_embedder(self) -> object:
        """Return the memoized default embedder, constructing it at most once.

        Not called from `__init__` — building an ONNX model eagerly would pay
        the load cost even for backends that never hit this path (an injected
        `embedding_provider` or a caller that always supplies `Query.embedding`).
        """
        if self._lazy_default_embedder is None:
            from digisearch.embedding.providers.minilm import MiniLMEmbedder

            self._lazy_default_embedder = MiniLMEmbedder()
        return self._lazy_default_embedder

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
        result = body.get("result")
        # Vectorize can answer HTTP 200 with an application-level failure body
        # (`success: false`, `result: null`) — the HTTP-status check above does
        # not see this. This is the one failure mode this backend exists to
        # surface rather than swallow, so a missing/failed result raises here too.
        if body.get("success") is False or result is None:
            errors = body.get("errors") or []
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
            raise RuntimeError(f"vectorize query failed ({status}): {json.dumps(errors)[:500]}")
        matches = (result or {}).get("matches") or []
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
