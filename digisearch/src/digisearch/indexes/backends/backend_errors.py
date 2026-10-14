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


class CorpusNotSeededError(SearchBackendError):
    """Raised when a query targets an index this boot's seed never populated.

    An unseeded collection answers every query with zero hits, which is
    indistinguishable from a genuinely empty result — the failure mode behind
    #5045, where production search looked broken for every index with /health
    still reporting ok. Distinguishing it lets the caller return an explicit
    error naming the index instead of an empty result that reads as an answer.

    Set by the stack's ``start_digisearch.sh`` from ``seed_chroma.sh``'s
    outcome via ``DIGISEARCH_UNSEEDED_INDEXES``. Absent or empty means seeded,
    so the guard is inert outside that deployment.
    """

    def __init__(self, indexes: list[str]) -> None:
        self.indexes = list(indexes)
        super().__init__(
            "corpus not seeded for index(es) "
            + ", ".join(self.indexes)
            + " — this boot's seed did not populate them, so the collection is "
            "empty. Returning no results would be indistinguishable from a "
            "genuine miss. See the container seed log; the next container boot "
            "retries."
        )
