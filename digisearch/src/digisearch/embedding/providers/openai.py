"""OpenAI embedding provider."""

from __future__ import annotations

import os

from digisearch.embedding.base import EmbeddingProvider


class OpenAIEmbedder(EmbeddingProvider):
    """OpenAI text-embedding API."""

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url or os.environ.get("OPENAI_API_BASE")
        self._client: object | None = None

    @property
    def dimensions(self) -> int:
        if "text-embedding-3-small" in self.model:
            return 1536
        if "text-embedding-3-large" in self.model:
            return 3072
        if "text-embedding-ada-002" in self.model:
            return 1536
        return 1536  # default

    def _get_client(self) -> object:
        if self._client is None:
            from openai import OpenAI

            kw: dict = {"api_key": self._api_key}
            if self._base_url:
                kw["base_url"] = self._base_url
            self._client = OpenAI(**kw)
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        r = client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in r.data]
