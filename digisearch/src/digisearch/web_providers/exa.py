"""Exa provider adapter (#4711) — wraps the existing :mod:`digisearch.web_exa` shim.

Read-only by design: ``web_exa`` stays the single owner of Exa's wire shapes,
auth, and error mapping. This adapter only translates the unified
:class:`~digisearch.web_search.models.WebSearchRequest` into ``exa_search`` /
``exa_contents`` / ``exa_answer`` arguments and normalises the results.
"""

from __future__ import annotations

from typing import Any, ClassVar

from digisearch.web_providers.base import (
    BaseWebProvider,
    WebProviderBadRequestError,
    WebProviderError,
    date_days_ago,
    rank_score,
)
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult

#: Exa's six-value type ladder collapses onto the tool's two effort tiers.
#: ``None`` keeps Exa's own default (``auto``).
_EFFORT_TO_SEARCH_TYPE = {"fast": "fast", "thorough": "deep"}


class ExaWebProvider(BaseWebProvider):
    provider_name: ClassVar[str] = "exa"
    env_var: ClassVar[str] = "EXA_API_KEY"
    cost_hint: ClassVar[str] = "~$7/1k searches (free signup credits)"
    supports_contents: ClassVar[bool] = True
    supports_answer: ClassVar[bool] = True
    supports_offset: ClassVar[bool] = True

    def _search(self, req: WebSearchRequest) -> WebSearchResponse:
        from digisearch import web_exa

        key = self.require_configured()
        search_type = _EFFORT_TO_SEARCH_TYPE.get(req.effort or "", "auto")
        try:
            data = web_exa.exa_search(
                req.query,
                search_type=search_type,
                num_results=req.max_results,
                offset=req.offset,
                include_domains=req.include_domains or None,
                exclude_domains=req.exclude_domains or None,
                start_published_date=_start_published_date(req.recency_days),
                api_key=key,
            )
        except (web_exa.ExaError, ValueError) as e:
            # ValueError covers ExaPageOutOfRangeError (a caller error: page past
            # the cap) — it subclasses ValueError, not ExaError, and must not
            # escape as a raw 500 from the route.
            raise _translate(e) from e

        extras: dict[str, Any] = {"search_type": data.search_type}
        if data.output:
            extras["synthesis"] = data.output
        return WebSearchResponse(
            query=req.query,
            results=[
                _to_result(row, i) for i, row in enumerate(data.results) if isinstance(row, dict)
            ],
            provider=self.provider_name,
            cost_dollars=data.cost_dollars,
            output=extras,
        )

    def fetch_contents(
        self,
        urls: list[str],
        *,
        text: bool = True,
        highlights: bool = False,
        summary: bool = False,
        highlight_query: str | None = None,
    ) -> dict[str, Any]:
        from digisearch import web_exa

        key = self.require_configured()
        try:
            return web_exa.exa_contents(
                urls,
                text=text,
                highlights=highlights,
                summary=summary,
                highlight_query=highlight_query,
                api_key=key,
            )
        except web_exa.ExaError as e:
            raise _translate(e) from e

    def answer(self, question: str) -> dict[str, Any]:
        from digisearch import web_exa

        key = self.require_configured()
        try:
            return web_exa.exa_answer(question, api_key=key)
        except web_exa.ExaError as e:
            raise _translate(e) from e


def _start_published_date(recency_days: int | None) -> str | None:
    """Map the unified ``recency_days`` window onto Exa ``startPublishedDate``.

    Exa filters on publish date (searxng/ddgs filter on index time), so this is
    an approximation — but the freshness window stays the same for callers
    switching providers instead of silently widening.
    """
    if recency_days is None:
        return None
    return date_days_ago(recency_days)


def _translate(exc: Exception) -> WebProviderError:
    """Turn an Exa-layer error into the shared provider error taxonomy.

    Mirrors ``base.request_json``: 401/403 are never retryable, 429/5xx are,
    and malformed 200 payloads (no status) are not — only transport errors
    are retryable with no status attached (#4711 review, MAJOR).
    """
    if isinstance(exc, ValueError):
        # Bad caller input (empty query, unknown type, page out of range).
        return WebProviderBadRequestError(str(exc))
    status = getattr(exc, "status_code", None)
    if status is not None:
        return WebProviderError(
            f"exa: {exc}",
            retryable=status == 429 or status >= 500,
            status_code=status,
        )
    message = str(exc)
    if "non-JSON" in message or "unexpected shape" in message:
        # A malformed 200 body — same treatment as base.require_dict.
        return WebProviderError(f"exa: {message}", retryable=False)
    return WebProviderError(f"exa: {exc}", retryable=True)  # transport error


def _to_result(row: dict[str, Any], position: int) -> WebSearchResult:
    highlights = row.get("highlights")
    snippet = ""
    if isinstance(highlights, list) and highlights:
        snippet = " ".join(str(h) for h in highlights if h)
    elif isinstance(row.get("text"), str):
        snippet = row["text"]
    score = row.get("score")
    return WebSearchResult(
        url=str(row.get("url") or ""),
        title=str(row.get("title") or ""),
        snippet=snippet,
        score=float(score) if isinstance(score, (int, float)) else rank_score(position),
        engine="exa",
        published_date=str(row.get("publishedDate") or ""),
        author=str(row.get("author") or ""),
    )


__all__ = ["ExaWebProvider"]
