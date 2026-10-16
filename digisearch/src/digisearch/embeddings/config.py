"""Central place for embedding model id, vector dimension, and version (re-embedding playbook)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EmbeddingModelSpec(BaseModel):
    """Describes one embedding configuration used for indexing and query."""

    model_id: str = Field(..., description="Provider model id, e.g. text-embedding-3-small")
    dimensions: int = Field(..., ge=1, description="Vector size produced by the model")
    version: str = Field(default="1", description="Logical version for index migration tracking")


def active_embedding_spec() -> EmbeddingModelSpec | None:
    """Return spec from env when configured (DIGISEARCH_EMBEDDING_MODEL, DIGISEARCH_EMBEDDING_DIM)."""
    import os

    mid = (os.environ.get("DIGISEARCH_EMBEDDING_MODEL") or "").strip()
    if not mid:
        return None
    dim_raw = (os.environ.get("DIGISEARCH_EMBEDDING_DIM") or "1536").strip()
    try:
        dim = int(dim_raw)
    except ValueError:
        dim = 1536
    ver = (os.environ.get("DIGISEARCH_EMBEDDING_VERSION") or "1").strip()
    return EmbeddingModelSpec(model_id=mid, dimensions=dim, version=ver)


__all__ = ["EmbeddingModelSpec", "active_embedding_spec"]
