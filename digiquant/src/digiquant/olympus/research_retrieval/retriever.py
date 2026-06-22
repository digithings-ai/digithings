"""In-process retriever implementing edit-mode retrieval protocols."""

from __future__ import annotations

from datetime import date
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.research_retrieval.blinding import RetrievalPhase
from digiquant.olympus.research_retrieval.cache import ResearchCache
from digiquant.olympus.research_retrieval.queries import (
    extract_section,
    query_portfolio,
    query_research,
)


class ResearchRetriever:
    """Supabase-backed ``query_research`` + ``fetch_prior_document`` implementation."""

    def __init__(
        self,
        *,
        client: SupabaseClient,
        run_date: date,
        phase: RetrievalPhase = "atlas_edit",
        cache: ResearchCache | None = None,
        watchlist: tuple[str, ...] = (),
    ) -> None:
        self._client = client
        self._run_date = run_date
        self._phase = phase
        self._cache = cache
        self._watchlist = watchlist

    def query_research(
        self,
        *,
        document_key: str | None = None,
        as_of_date: date | None = None,
        segment: str | None = None,
    ) -> dict[str, Any]:
        return query_research(
            self._client,
            run_date=self._run_date,
            document_key=document_key,
            as_of_date=as_of_date,
            segment=segment,
            phase=self._phase,
            cache=self._cache,
        )

    def fetch_prior_document(
        self,
        document_key: str,
        *,
        section_path: str | None = None,
        as_of_date: date | None = None,
    ) -> dict[str, Any]:
        result = self.query_research(document_key=document_key, as_of_date=as_of_date)
        if "error" in result:
            return {}
        payload = result.get("payload")
        if not isinstance(payload, dict):
            return {}
        return extract_section(payload, section_path)

    def query_portfolio(
        self,
        *,
        as_of_date: date | None = None,
        ticker: str | None = None,
    ) -> dict[str, Any]:
        return query_portfolio(
            self._client,
            run_date=self._run_date,
            phase=self._phase,
            as_of_date=as_of_date,
            ticker=ticker,
            watchlist=self._watchlist,
        )
