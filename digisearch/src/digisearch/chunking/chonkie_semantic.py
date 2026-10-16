"""Chonkie SemanticChunker backend — default for long-form document ingestion."""

from __future__ import annotations

from typing import Any  # score:allow untyped any — optional injected Chonkie SemanticChunker

from digisearch.chunking._convert import chonkie_chunks_to_digisearch
from digisearch.core.models import Chunk


class ChonkieSemanticChunker:
    """Wraps ``chonkie.SemanticChunker`` (SDPM-style semantic boundaries).

    Prefer this for SEC filings, research reports, and earnings transcripts so
    related reasoning context stays in the same chunk.
    """

    def __init__(
        self,
        *,
        embedding_model: str = "minishlab/potion-base-32M",
        threshold: float = 0.8,
        chunk_size: int = 2048,
        skip_window: int = 0,
        _inner: Any | None = None,
        **kwargs: Any,
    ) -> None:
        if _inner is not None:
            self._inner = _inner
            return
        try:
            from chonkie import SemanticChunker as _SemanticChunker
        except ImportError as exc:
            raise ImportError(
                "chonkie[semantic] is required for ChonkieSemanticChunker. "
                "Install digisearch[ingestion] (or pip install 'chonkie[semantic]')."
            ) from exc
        self._inner = _SemanticChunker(
            embedding_model=embedding_model,
            threshold=threshold,
            chunk_size=chunk_size,
            skip_window=skip_window,
            **kwargs,
        )

    def chunk(self, text: str) -> list[Chunk]:
        if not text or not text.strip():
            return []
        return chonkie_chunks_to_digisearch(
            list(self._inner.chunk(text)),
            backend="chonkie_semantic",
        )
