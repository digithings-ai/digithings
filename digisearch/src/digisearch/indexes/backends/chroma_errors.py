"""Isolated exception for Chroma embedding-model identity mismatches.

Lives outside ``chroma.py`` so callers (and ``_stub``) can import the type without
pulling optional chromadb deps. Deliberately not a ``ValueError`` subclass —
``_stub._BACKEND_ERRORS`` includes ``ValueError`` and would otherwise swallow a
model mismatch into an empty search response.
"""

from __future__ import annotations


class EmbeddingModelMismatchError(Exception):
    """Raised when a Chroma collection's stored embedding identity disagrees with the provider."""
