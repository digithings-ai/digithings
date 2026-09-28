"""Firecrawl provider adapter (#4711).

Docs: https://docs.firecrawl.dev — ``POST https://api.firecrawl.dev/v2/search``
with ``Authorization: Bearer <FIRECRAWL_API_KEY>``. Firecrawl searches *and*
renders (JS → markdown), so its edge is page extraction rather than ranking
depth: there is no ``search_depth`` knob and ``effort`` is accepted but unused.

Credits: 1 credit = 1 page, a search of up to 10 results costs 2 credits.
"""

from __future__ import annotations

from typing import Any, ClassVar

from digisearch.web_providers.base import (
    BaseWebProvider,
    rank_score,
    request_json,
    require_dict,
)
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult

API_URL = "https://api.firecrawl.dev/v2/search"

#: recency_days -> Firecrawl ``tbs`` recency bucket.
_TBS_BY_RECENCY = ((1, "d"), (7, "w"), (31, "m"), (365, "y"))


class FirecrawlWebProvider(BaseWebProvider):
    provider_name: ClassVar[str] = "firecrawl"
    env_var: ClassVar[str] = "FIRECRAWL_API_KEY"
    cost_hint: ClassVar[str] = "1,000 free credits/mo; search ≈ 2 credits"

    def _search(self, req: WebSearchRequest) -> WebSearchResponse:
        key = self.require_configured()
        body: dict[str, Any] = {"query": req.query, "limit": req.max_results}
        # includeDomains and excludeDomains are mutually exclusive upstream.
        if req.include_domains:
            body["includeDomains"] = req.include_domains
        elif req.exclude_domains:
            body["excludeDomains"] = req.exclude_domains
        tbs = _tbs(req.recency_days)
        if tbs:
            body["tbs"] = tbs

        data = require_dict(
            "firecrawl",
            request_json(
                "firecrawl",
                method="POST",
                url=API_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json_body=body,
            ),
        )
        results = _normalise(data.get("data"))[: req.max_results]
        return WebSearchResponse(
            query=req.query,
            results=results,
            provider=self.provider_name,
            output={"success": data.get("success", True)},
        )


def _tbs(recency_days: int | None) -> str | None:
    if recency_days is None:
        return None
    for ceiling, bucket in _TBS_BY_RECENCY:
        if recency_days <= ceiling:
            return f"qdr:{bucket}"
    return None


def _normalise(payload: Any) -> list[WebSearchResult]:
    """Flatten ``data.web`` + ``data.news`` into one ranked result list.

    A ``scrapeOptions`` request returns an array of full pages instead of the
    grouped object; that shape is handled too so adding scraping later does not
    silently return zero rows.
    """
    if isinstance(payload, list):
        return [
            WebSearchResult(
                url=str(row.get("url") or ""),
                title=str(row.get("title") or ""),
                snippet=str(row.get("description") or row.get("markdown") or ""),
                score=rank_score(i),
                engine="firecrawl",
            )
            for i, row in enumerate(payload)
            if isinstance(row, dict)
        ]
    if not isinstance(payload, dict):
        return []
    out: list[WebSearchResult] = []
    position = 0
    for row in payload.get("web") or []:
        if not isinstance(row, dict):
            continue
        out.append(
            WebSearchResult(
                url=str(row.get("url") or ""),
                title=str(row.get("title") or ""),
                snippet=str(row.get("description") or ""),
                score=rank_score(position),
                engine="firecrawl",
                published_date=str(row.get("date") or ""),
            )
        )
        position += 1
    for row in payload.get("news") or []:
        if not isinstance(row, dict):
            continue
        out.append(
            WebSearchResult(
                url=str(row.get("url") or ""),
                title=str(row.get("title") or ""),
                snippet=str(row.get("snippet") or ""),
                score=rank_score(position),
                engine="firecrawl",
                # Firecrawl returns a relative age ("3 months ago"), not a date.
                published_date=str(row.get("date") or ""),
            )
        )
        position += 1
    return out


__all__ = ["FirecrawlWebProvider"]
