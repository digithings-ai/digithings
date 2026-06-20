"""Edit-mode retrieval tools (spec §5.6, §6.1)."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digiquant.olympus.research_retrieval import ResearchRetriever

__all__ = [
    "PriorDocumentFetcher",
    "QueryResearch",
    "ResearchRetriever",
    "StubPriorDocumentFetcher",
    "StubQueryResearch",
]


class PriorDocumentFetcher(Protocol):
    def fetch_prior_document(
        self,
        document_key: str,
        *,
        section_path: str | None = None,
        as_of_date: date | None = None,
    ) -> dict[str, Any]:
        """Return materialized prior body (or section) for edit-mode prompts."""


class QueryResearch(Protocol):
    def query_research(
        self,
        *,
        document_key: str | None = None,
        as_of_date: date | None = None,
        segment: str | None = None,
    ) -> dict[str, Any]:
        """Unified research retrieval backed by documents + daily_snapshots."""


class StubPriorDocumentFetcher:
    """In-memory prior document store for unit tests and dry runs."""

    def __init__(
        self,
        documents: dict[tuple[str, date | None], dict[str, Any]],
    ) -> None:
        self._documents = documents

    def fetch_prior_document(
        self,
        document_key: str,
        *,
        section_path: str | None = None,
        as_of_date: date | None = None,
    ) -> dict[str, Any]:
        key = (document_key, as_of_date)
        if key not in self._documents:
            key = (document_key, None)
        body = self._documents.get(key, {})
        if section_path is None:
            return body
        cur: Any = body
        for token in section_path.strip("/").split("/"):
            if not token:
                continue
            if isinstance(cur, dict):
                cur = cur.get(token, {})
            else:
                return {}
        return cur if isinstance(cur, dict) else {"value": cur}


class StubQueryResearch:
    """In-memory research query stub."""

    def __init__(self, rows: dict[tuple[str, date | None], dict[str, Any]]) -> None:
        self._rows = rows

    def query_research(
        self,
        *,
        document_key: str | None = None,
        as_of_date: date | None = None,
        segment: str | None = None,
    ) -> dict[str, Any]:
        del segment
        if document_key is None:
            return {}
        key = (document_key, as_of_date)
        if key in self._rows:
            return self._rows[key]
        return self._rows.get((document_key, None), {})
