"""Canonical digisearch pipelines (ingest, …)."""

from digisearch.pipeline.ingest import (
    IngestError,
    IngestResult,
    ingest_paths,
    ingest_source,
)

__all__ = [
    "IngestError",
    "IngestResult",
    "ingest_paths",
    "ingest_source",
]
