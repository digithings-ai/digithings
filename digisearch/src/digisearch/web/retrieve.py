"""Sole adaptation seam over the landed ``digisearch.web_search`` surface (#4064).

Every Phase B web research module consumes provider results only through
this module. The Task 0 ``service``/``fetch`` imports stay inside the
``_live``/``_fetch`` seam functions so ``import digisearch.web`` works on a
base install with no digifetch / ``[web-search]`` extra present. This module
never calls the pipeline URL-ingest path, which indexes: doing so would mix
fetched web pages into the local corpus (R3).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from digisearch.web.grounding_models import WebResearchError
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult

__all__ = ["FetchedPage", "fetch_pages", "live_search"]


class FetchedPage(BaseModel):
    """One fetched web page as extracted markdown (never indexed)."""

    model_config = ConfigDict(extra="forbid")

    url: str
    title: str = ""
    markdown: str = ""


def _live(query: str, top_n: int) -> WebSearchResponse:
    """Run one query against the Task 0 search wrapper."""
    from digisearch.web_search.service import search_web

    return search_web(WebSearchRequest(query=query, max_results=top_n))


def live_search(query: str, *, top_n: int) -> list[WebSearchResult]:
    """Search the live web and return landed ``WebSearchResult`` rows.

    Rows carry the landed ``{url,title,snippet,score,engine}`` shape — never
    a ``highlights`` key. Raises :class:`WebResearchError` on any failure.
    """
    try:
        return _live(query, top_n).results
    except Exception as exc:
        raise WebResearchError(f"web search failed: {exc}") from exc


def _fetch(hits: list[WebSearchResult], top_n: int) -> list[FetchedPage]:
    """Fetch up to *top_n* hits as non-indexed markdown pages.

    Pages whose markdown extracts empty are dropped. Raises
    :class:`WebResearchError` on any fetch failure.
    """
    from digisearch.web_search.fetch import fetch_markdown

    pages: list[FetchedPage] = []
    for hit in hits[:top_n]:
        try:
            markdown = fetch_markdown(hit.url)
        except Exception as exc:
            raise WebResearchError(f"fetch failed for {hit.url}: {exc}") from exc
        if markdown:
            pages.append(FetchedPage(url=hit.url, title=hit.title, markdown=markdown))
    return pages


def fetch_pages(hits: list[WebSearchResult], *, top_n: int) -> list[FetchedPage]:
    """Fetch up to *top_n* hits as markdown pages; the pages are never indexed."""
    try:
        return _fetch(hits, top_n)
    except WebResearchError:
        raise
    except Exception as exc:
        raise WebResearchError(f"web fetch failed: {exc}") from exc
