"""Pluggable retrieval backend protocol (#402).

``RetrievalBackend`` is the contract that lets digisearch swap vector / graph
retrieval implementations (pgvector default, LightRAG upgrade path, future
HippoRAG / custom backends) without changing caller code. Distinct from
:class:`~digisearch.indexes.base.DigiIndex` (chunk-level index ops used by the
HTTP ``/query`` router) — this protocol is document-oriented and async.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any  # score:allow untyped any — Document.metadata / RetrievalResult.metadata, Protocol, runtime_checkable

from digisearch.core.models import Document


@dataclass
class RetrievalResult:
    """One ranked hit from :meth:`RetrievalBackend.retrieve`."""

    document_id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = ""


@runtime_checkable
class RetrievalBackend(Protocol):
    """Swappable retrieval implementation.

    Callers depend only on this protocol. Concrete backends register in
    :mod:`digisearch.retrieval.registry` and are selected via
    ``DIGISEARCH_RETRIEVAL_BACKEND``.
    """

    async def index(self, documents: list[Document]) -> None:
        """Persist *documents* (embed + store) for later retrieval."""
        ...

    async def retrieve(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        """Return the top-*k* results for *query*, highest score first."""
        ...

    async def delete(self, document_ids: list[str]) -> None:
        """Remove documents (and their chunks/vectors) by id."""
        ...

    async def health(self) -> bool:
        """Return True when the backend is reachable and ready."""
        ...
