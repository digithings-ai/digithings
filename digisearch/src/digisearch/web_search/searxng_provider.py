"""SearXNG sidecar provider (primary) for #3853."""

from __future__ import annotations

import httpx

from digisearch.web_search.models import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
    apply_domain_filter,
)


class SearXNGWebSearchProvider:
    name = "searxng"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        client: httpx.Client | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout

    def search(self, req: WebSearchRequest) -> WebSearchResponse:
        params = {
            "q": req.query,
            "format": "json",
            "pageno": 1,
            "language": "en",
            "safesearch": 1,
        }
        close = False
        client = self._client
        if client is None:
            client = httpx.Client(timeout=self._timeout)
            close = True
        try:
            r = client.get(f"{self._base}/search", params=params)
            r.raise_for_status()
            items = (r.json().get("results", []) or [])[: req.max_results * 2]
        finally:
            if close:
                client.close()
        rows = [
            {
                "url": str(it.get("url", "")),
                "title": str(it.get("title", "")),
                "snippet": str(it.get("content", "")),
                "score": float(it.get("score", 0.0) or 0.0),
                "engine": str(it.get("engine", "")),
            }
            for it in items
        ]
        rows = apply_domain_filter(
            rows, include_domains=req.include_domains, exclude_domains=req.exclude_domains
        )
        rows = sorted(rows, key=lambda d: float(d.get("score", 0.0) or 0.0), reverse=True)
        results = [
            WebSearchResult(
                url=d["url"],
                title=d["title"],
                snippet=d["snippet"],
                score=float(d.get("score", 0.0) or 0.0),
                engine=str(d.get("engine", "searxng")),
            )
            for d in rows[: req.max_results]
            if d["url"]
        ]
        return WebSearchResponse(query=req.query, results=results, provider=self.name)
