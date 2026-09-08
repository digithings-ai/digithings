"""digisearch client - unified orchestrator. DigiSearch.from_config()."""

from __future__ import annotations

from typing import Any

from digisearch.core.config import DigiSearchConfig
from digisearch.core.models import Document, Query, Result


class DigiSearch:
    """Unified DigiSearch client. Orchestrates indexes, embedding, search."""

    def __init__(self, config: DigiSearchConfig | None = None) -> None:
        self.config = config or DigiSearchConfig.from_env()
        self._indexes: dict[str, Any] = {}

    @classmethod
    def from_config(cls, path: str) -> "DigiSearch":
        """Load from YAML/TOML config file."""
        cfg = DigiSearchConfig.from_config(path)
        return cls(cfg)

    def get_index(self, name: str) -> Any | None:
        """Get configured index by name."""
        if name in self._indexes:
            return self._indexes[name]
        idx_cfg = self.config.get_index_config(name)
        if not idx_cfg:
            return None
        backend = idx_cfg.get("backend", "chroma")
        if backend == "chroma":
            try:
                from digisearch.indexes.backends.chroma import ChromaBackend

                persist = idx_cfg.get("persist_path")
                emb = self._get_embedder()
                idx = ChromaBackend(name=name, persist_path=persist, embedding_provider=emb)
                self._indexes[name] = idx
                return idx
            except ImportError:
                return None
        return None

    def _get_embedder(self) -> Any | None:
        """Resolve EmbeddingCache → BatchEmbedder → provider from config/env.

        Raises :class:`digisearch.embedding.factory.EmbeddingConfigError` when
        embed is explicitly configured but cannot be loaded (no silent no-op).
        """
        from digisearch.embedding.factory import resolve_embedding_pipeline

        return resolve_embedding_pipeline(self.config)

    def query(
        self, text: str, index_name: str = "default", top_k: int = 10, mode: str = "hybrid"
    ) -> list[Result]:
        """Search index. Uses configured backend or stub."""
        from digisearch.embedding.factory import normalize_query_mode

        mode = normalize_query_mode(mode)
        idx = self.get_index(index_name)
        if idx:
            q = Query(text=text, top_k=top_k, mode=mode)
            return idx.query(q)
        from digisearch.search._stub import query_index

        q = Query(text=text, top_k=top_k, mode=mode)
        return query_index(q, index_name=index_name).results

    def ingest(self, doc: Document, index_name: str = "default") -> int:
        """Index an already-chunked document. Returns chunks created.

        Filesystem parse → chunk → embed lives in
        :func:`digisearch.pipeline.ingest.ingest_source`. This method only
        writes ``doc.chunks`` to a configured DigiIndex or the backend router.
        """
        idx = self.get_index(index_name)
        if idx and doc.chunks:
            idx.add(doc.chunks)
            return len(doc.chunks)
        from digisearch.pipeline.ingest import index_chunks

        index_chunks(index_name, doc.chunks)
        return len(doc.chunks)

    def as_mcp_server(self) -> object:
        """Return MCP server exposing configured indexes. Use mcp.run() to start."""
        from digisearch.mcp_server import create_mcp_with_indexes

        return create_mcp_with_indexes(self)
