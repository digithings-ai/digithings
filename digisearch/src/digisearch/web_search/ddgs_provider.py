"""ddgs embedded provider (MIT fallback, zero infra) for #3853."""

from __future__ import annotations

from digisearch.web_search.models import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
    apply_domain_filter,
    recency_days_to_ddgs_timelimit,
)

try:
    from ddgs import DDGS
except Exception:  # pragma: no cover - import guard for unit envs
    DDGS = None  # type: ignore[assignment]


class DdgsUnavailableError(RuntimeError):
    pass


class DdgsWebSearchProvider:
    """DuckDuckGo-scrape provider via ddgs with auto-backend failover."""

    name = "ddgs"

    def search(self, req: WebSearchRequest) -> WebSearchResponse:
        if DDGS is None:
            raise DdgsUnavailableError("ddgs package not installed")
        rows: list[dict] = []
        timelimit = recency_days_to_ddgs_timelimit(req.recency_days)
        with DDGS() as ddgs:
            # Over-fetch like the searxng provider so post-filtering still
            # leaves up to max_results rows; capped again below.
            found = ddgs.text(req.query, max_results=req.max_results * 2, timelimit=timelimit) or []
            for row in found:
                rows.append(
                    {
                        "url": str(row.get("href", "")),
                        "title": str(row.get("title", "")),
                        "snippet": str(row.get("body", "")),
                    }
                )
        rows = apply_domain_filter(
            rows, include_domains=req.include_domains, exclude_domains=req.exclude_domains
        )
        results = [
            WebSearchResult(url=r["url"], title=r["title"], snippet=r["snippet"], engine="ddgs")
            for r in rows[: req.max_results]
            if r["url"]
        ]
        return WebSearchResponse(query=req.query, results=results, provider=self.name)
