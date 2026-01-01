"""Index backend factory for the swappable digisearch vector stores.

The factory is deliberately small: it constructs the backends that implement the
``DigiIndex`` contract (``sqlite`` and ``chroma``). Azure and Vectorize keep
their existing function-level routing in :mod:`digisearch.search._stub`, because
they are remote query adapters rather than local index stores.
"""

from __future__ import annotations

import os

from digisearch.backend_require import selected_index_backend
from digisearch.indexes.base import DigiIndex

_LOCAL_BACKENDS = frozenset({"sqlite", "chroma"})


def get_index(
    name: str,
    *,
    backend: str | None = None,
    embedding_provider: object | None = None,
    persist_path: str | None = None,
    db_path: str | None = None,
    chroma_host: str | None = None,
    chroma_port: int = 8000,
) -> DigiIndex:
    """Build the selected local index backend.

    Selection order: explicit ``backend=``, then ``DIGISEARCH_INDEX_BACKEND``
    (via :func:`selected_index_backend`), then the legacy Chroma path/host, then
    the SQLite default.
    """
    selected = (backend or selected_index_backend() or "").strip().lower()
    if not selected:
        selected = (
            "chroma" if os.environ.get("CHROMA_PATH") or os.environ.get("CHROMA_HOST") else "sqlite"
        )
    if selected == "sqlite":
        from digisearch.indexes.backends.sqlite_exact import SQLiteExactBackend

        return SQLiteExactBackend(
            name,
            db_path=db_path or persist_path,
            embedding_provider=embedding_provider,
        )
    if selected == "chroma":
        from digisearch.indexes.backends.chroma import ChromaBackend

        return ChromaBackend(
            name=name,
            persist_path=persist_path,
            embedding_provider=embedding_provider,
            chroma_host=chroma_host,
            chroma_port=chroma_port,
        )
    raise ValueError(
        f"local index backend must be one of {sorted(_LOCAL_BACKENDS)}; got {selected!r}. "
        "Azure and Vectorize are routed by digisearch.search._stub."
    )
