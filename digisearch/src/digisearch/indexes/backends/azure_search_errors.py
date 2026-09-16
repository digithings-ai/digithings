"""Isolated exception type for Azure AI Search workspace-isolation failures.

``AzureWorkspaceFilterError`` lives in its own module, decoupled from
``azure_search.py``, so it stays importable even when importing the heavier
``azure_search`` module fails (a missing optional ``azure-search-documents``
dependency, a broken transitive import, etc.).

It is deliberately **not** a subclass of ImportError/OSError/RuntimeError/TypeError/
ValueError. ``search/_stub.py``'s ``_BACKEND_ERRORS`` tuple lists exactly those and
``query_index`` catches that tuple to fall through to the next backend. A
workspace-scoped query that Azure cannot safely filter must fail loud rather than be
silently answered from Chroma (a different corpus / tenant) — the same precedent as
``VectorizeBackendError`` (``vectorize_errors.py``, #2219).
"""

from __future__ import annotations


class AzureWorkspaceFilterError(Exception):
    """Raised when a workspace-scoped Azure query cannot be safely applied.

    The index cannot express ``workspace_id`` as a filterable field, so running the
    query would return other tenants' documents. Refusing to run is the safe choice.
    """
