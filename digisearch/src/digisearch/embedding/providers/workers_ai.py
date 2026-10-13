"""Query embedder for Workers AI ``@cf/baai/bge-m3`` (1024-dim).

The same model id is written into vector metadata by the corpus-index worker.
Do not mix these vectors with 384-dim MiniLM indexes. The API token is read
from the environment and is never included in an error string.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from digisearch.embedding.base import EmbeddingProvider
from digisearch.embedding.factory import EmbeddingConfigError

BGE_M3_MODEL_ID = "@cf/baai/bge-m3"
BGE_M3_DIMENSIONS = 1024
FACTORY_NAMES = frozenset({BGE_M3_MODEL_ID, "bge-m3"})

EmbedFn = Callable[[list[str]], list[list[float]]]
Opener = Callable[[Request], Any]


class WorkersAiEmbedder(EmbeddingProvider):
    """bge-m3 via the Workers AI REST API, or an injected function in tests."""

    model_id: str = BGE_M3_MODEL_ID

    def __init__(
        self,
        embed_fn: EmbedFn | None = None,
        account_id: str | None = None,
        api_token: str | None = None,
        opener: Opener | None = None,
        url: str | None = None,
    ) -> None:
        self._url = (url or "").strip()
        self._embed_fn = embed_fn
        self._account_id = (
            account_id if account_id is not None else os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        ).strip()
        self._api_token = (
            api_token if api_token is not None else os.environ.get("CLOUDFLARE_API_TOKEN", "")
        ).strip()
        self._opener = opener or urlopen

    @property
    def dimensions(self) -> int:
        return BGE_M3_DIMENSIONS

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._embed_fn is not None:
            return _check(self._embed_fn(texts), len(texts))
        if self._url and self._api_token:
            pass
        elif not self._account_id or not self._api_token:
            raise EmbeddingConfigError(
                "Workers AI embedder needs CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN"
            )
        url = self._url or (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self._account_id}/ai/run/{BGE_M3_MODEL_ID}"
        )
        payload = json.dumps({"text": texts}).encode()
        request = Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
                # Cloudflare's bot rules answer 403 to the default Python-urllib UA.
                "User-Agent": "digisearch-workers-ai/1.0",
            },
            method="POST",
        )
        try:
            with self._opener(request) as response:
                raw = response.read()
        except HTTPError as exc:
            raise EmbeddingConfigError(f"workers ai embed failed ({exc.code})") from None
        except URLError as exc:
            raise EmbeddingConfigError("workers ai embed failed (network)") from exc
        try:
            parsed = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EmbeddingConfigError("workers ai embed failed (response)") from exc
        result = parsed.get("result", parsed) if isinstance(parsed, dict) else {}
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, list):
            raise EmbeddingConfigError("workers ai embed failed (response)")
        vectors = [[float(value) for value in row] for row in data]
        return _check(vectors, len(texts))


def provider_for(name: str, model: str | None) -> WorkersAiEmbedder | None:
    """Return an embedder when *name* is bge-m3, else None.

    ``factory._build_raw_provider`` calls this before its unknown-provider error.
    A different model id is a configuration error, not a silent fallback.
    """
    lowered = name.strip().lower()
    if lowered not in ("@cf/baai/bge-m3", "bge-m3"):
        return None
    if model is not None and model.strip().lower() not in ("@cf/baai/bge-m3", "bge-m3"):
        raise EmbeddingConfigError(
            f"embedding provider {name!r} ships a single model "
            f"({BGE_M3_MODEL_ID!r}); got model {model!r}"
        )
    return WorkersAiEmbedder()


def _check(vectors: list[list[float]], expected: int) -> list[list[float]]:
    if len(vectors) != expected:
        raise EmbeddingConfigError("workers ai embed failed (count)")
    for row in vectors:
        if len(row) != BGE_M3_DIMENSIONS:
            raise EmbeddingConfigError("workers ai embed failed (dimensions)")
    return vectors
