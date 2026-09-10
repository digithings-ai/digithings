"""Service orchestration for #3853: search -> fetch via digifetch -> extract."""

from __future__ import annotations

import os

from digifetch import HttpFetcher, RateLimiter, RetryPolicy, with_retry
from pydantic import BaseModel

from digisearch.web_search.ddgs_provider import DdgsWebSearchProvider
from digisearch.web_search.extractor import extract_markdown
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult
from digisearch.web_search.searxng_provider import SearXNGWebSearchProvider


class WebSearchConfig(BaseModel):
    backend: str = "auto"
    searxng_url: str = "http://127.0.0.1:8080"
    fetch_max_pages: int = 3
    fetch_timeout: float = 15.0
    min_interval_s: float = 1.0

    @classmethod
    def from_env(cls) -> WebSearchConfig:
        return cls(
            backend=os.environ.get("DIGISEARCH_WEB_SEARCH_BACKEND", "auto"),
            searxng_url=os.environ.get("DIGISEARCH_SEARXNG_URL", "http://127.0.0.1:8080"),
        )


_limiter = RateLimiter(min_interval=1.0)


def _search_only(req: WebSearchRequest, config: WebSearchConfig) -> WebSearchResponse:
    last: Exception | None = None
    order = [config.backend] if config.backend in ("searxng", "ddgs") else ["searxng", "ddgs"]
    for name in order:
        try:
            if name == "searxng":
                return SearXNGWebSearchProvider(base_url=config.searxng_url).search(req)
            return DdgsWebSearchProvider().search(req)
        except Exception as exc:
            last = exc
            continue
    raise RuntimeError(f"all web-search backends failed: {last}")


def run_web_search(
    req: WebSearchRequest, config: WebSearchConfig | None = None
) -> WebSearchResponse:
    config = config or WebSearchConfig.from_env()
    resp = _search_only(req, config)
    fetcher = HttpFetcher(timeout=config.fetch_timeout)
    policy = RetryPolicy(attempts=2, base_delay=1.0, factor=2.0, max_delay=5.0)
    enriched: list[WebSearchResult] = []
    for hit in resp.results[: config.fetch_max_pages]:
        try:
            _limiter.acquire()
            fetched = with_retry(
                lambda: fetcher.fetch(hit.url), policy, description="web_search fetch"
            )
            md = extract_markdown(fetched.text or "", url=hit.url)
            enriched.append(hit.model_copy(update={"snippet": md[:2000] if md else hit.snippet}))
        except Exception:
            enriched.append(hit)
    rest = resp.results[config.fetch_max_pages :]
    return WebSearchResponse(query=resp.query, results=enriched + rest, provider=resp.provider)
