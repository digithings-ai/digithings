"""Shared exception for a configured search backend that fails to serve a query.

Lives outside ``search/_stub.py`` so the concrete backends and the router can both
import it without a cycle. Deliberately NOT a subclass of
ImportError/OSError/RuntimeError/TypeError/ValueError: ``_stub._BACKEND_ERRORS`` lists
exactly those, and ``query_index`` catches that tuple to fall through to the next
backend. A backend that IS configured must surface its failure to the caller instead
of being silently answered from a different corpus -- the same rule
``VectorizeBackendError`` already follows.

Unlike ``VectorizeBackendError`` (a remote authoritative index), Chroma/Azure remain
optional local backends, so this type is raised for *serving* failures while their
"not configured" paths still return ``None`` and let the router continue.
"""

from __future__ import annotations


class SearchBackendError(Exception):
    """Raised when a configured search backend (Chroma, Azure) fails to serve a query."""
