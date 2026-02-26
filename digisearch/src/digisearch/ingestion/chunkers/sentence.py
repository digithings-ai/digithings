"""SentenceChunker - sentence boundaries via nltk or spacy."""

from __future__ import annotations

from digisearch.core.models import DigiChunk, DigiDocument
from digisearch.ingestion.chunkers.base import Chunker

try:
    import nltk
    nltk.download("punkt", quiet=True)
    _NLTK_AVAILABLE = True
except ImportError:
    _NLTK_AVAILABLE = False


class SentenceChunker(Chunker):
    """Chunk by sentence boundaries. Uses nltk or simple fallback."""

    def __init__(self, max_sentences: int = 5) -> None:
        self.max_sentences = max_sentences

    def chunk(self, doc: DigiDocument) -> list[DigiChunk]:
        if _NLTK_AVAILABLE:
            sents = nltk.sent_tokenize(doc.content)
        else:
            sents = [s.strip() for s in doc.content.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        chunks: list[DigiChunk] = []
        for i in range(0, len(sents), self.max_sentences):
            batch = sents[i : i + self.max_sentences]
            content = " ".join(batch)
            chunks.append(
                DigiChunk(
                    id=f"{doc.id}_{i}",
                    content=content,
                    doc_id=doc.id,
                    embedding=None,
                    metadata={"chunk_index": i, "sentences": len(batch)},
                )
            )
        return chunks
