"""SentenceChunker - sentence boundaries via nltk or spacy."""

from __future__ import annotations

from digisearch.core.models import Chunk, Document
from digisearch.ingestion.chunkers.base import Chunker

try:
    import nltk as _nltk_module
    _NLTK_AVAILABLE = True
except ImportError:
    _nltk_module = None  # type: ignore[assignment]
    _NLTK_AVAILABLE = False

# Downloaded lazily on first chunk() call to avoid startup latency and network access at import time.
_nltk_ready = False


def _ensure_nltk_data() -> None:
    global _nltk_ready
    if not _NLTK_AVAILABLE or _nltk_ready:
        return
    _nltk_module.download("punkt", quiet=True)
    _nltk_module.download("punkt_tab", quiet=True)
    _nltk_ready = True


class SentenceChunker(Chunker):
    """Chunk by sentence boundaries. Uses nltk or simple fallback."""

    def __init__(self, max_sentences: int = 5) -> None:
        self.max_sentences = max_sentences

    def chunk(self, doc: Document) -> list[Chunk]:
        _ensure_nltk_data()
        if _NLTK_AVAILABLE:
            sents = _nltk_module.sent_tokenize(doc.content)
        else:
            sents = [s.strip() for s in doc.content.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        chunks: list[Chunk] = []
        for i in range(0, len(sents), self.max_sentences):
            batch = sents[i : i + self.max_sentences]
            content = " ".join(batch)
            chunks.append(
                Chunk(
                    id=f"{doc.id}_{i}",
                    content=content,
                    doc_id=doc.id,
                    embedding=None,
                    metadata={"chunk_index": i, "sentences": len(batch)},
                )
            )
        return chunks
