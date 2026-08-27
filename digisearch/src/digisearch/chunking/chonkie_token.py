"""Chonkie TokenChunker backend — for short news / alerts."""

from __future__ import annotations

from typing import Any  # score:allow untyped any — optional injected Chonkie TokenChunker

from digisearch.chunking._convert import chonkie_chunks_to_digisearch
from digisearch.core.models import Chunk


class ChonkieTokenChunker:
    """Wraps ``chonkie.TokenChunker`` for fixed-size token windows.

    Prefer this for short news wires and alerts where semantic similarity adds
    little value and latency matters.
    """

    def __init__(
        self,
        *,
        tokenizer: str = "character",
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        _inner: Any | None = None,
        **kwargs: Any,
    ) -> None:
        if _inner is not None:
            self._inner = _inner
            return
        try:
            from chonkie import TokenChunker as _TokenChunker
        except ImportError as exc:
            raise ImportError(
                "chonkie is required for ChonkieTokenChunker. "
                "Install digisearch[ingestion] (or pip install chonkie)."
            ) from exc
        self._inner = _TokenChunker(
            tokenizer=tokenizer,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            **kwargs,
        )

    def chunk(self, text: str) -> list[Chunk]:
        if not text or not text.strip():
            return []
        return chonkie_chunks_to_digisearch(list(self._inner.chunk(text)))
