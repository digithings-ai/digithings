"""Service orchestration for #3853: search -> fetch via digifetch -> extract."""

from __future__ import annotations

import os
import threading
from typing import Literal

from digifetch import HttpFetcher, RateLimiter, RetryPolicy, with_retry
from pydantic import BaseModel, Field

from digisearch.web_search.ddgs_provider import DdgsWebSearchProvider
from digisearch.web_search.extractor import extract_markdown
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult
from digisearch.web_search.searxng_provider import SearXNGWebSearchProvider


class WebSearchConfig(BaseModel):
    backend: Literal["auto", "searxng", "ddgs"] = "auto"
    searxng_url: str = "http://127.0.0.1:8080"
    fetch_max_pages: int = Field(default=3, ge=1, le=10)
    fetch_timeout: float = Field(default=15.0, gt=0)
    min_interval_s: float = Field(default=1.0, ge=0)

    @classmethod
    def from_env(cls) -> WebSearchConfig:
        return cls(
            backend=os.environ.get("DIGISEARCH_WEB_SEARCH_BACKEND", "auto"),
            searxng_url=os.environ.get("DIGISEARCH_SEARXNG_URL", "http://127.0.0.1:8080"),
        )


_DEFAULT_MIN_INTERVAL_S = 1.0

# Process-wide fetch throttle. One limiter per interval value, shared by all
# requests in this process: concurrent web_search calls serialize on acquire()
# instead of bursting the fetched sites. Tradeoff: a slow fetch holds the slot
# for every other request (head-of-line blocking), so the p50 fetch+extract
# budget (< 5s in the eval harness) must cover the worst-case wait, not just
# one fetch. Deliberately not per-request (a fresh limiter per call would
# throttle nothing) and not redesigned here (see I6).
_limiter = RateLimiter(min_interval=_DEFAULT_MIN_INTERVAL_S)
_limiters: dict[float, RateLimiter] = {}
_limiters_lock = threading.Lock()


def _limiter_for(min_interval_s: float) -> RateLimiter:
    """Return the shared process-wide limiter for the given interval."""
    if min_interval_s == _DEFAULT_MIN_INTERVAL_S:
        return _limiter
    with _limiters_lock:
        limiter = _limiters.get(min_interval_s)
        if limiter is None:
            limiter = RateLimiter(min_interval=min_interval_s)
            _limiters[min_interval_s] = limiter
        return limiter


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
    policy = RetryPolicy(attempts=2, base_delay=1.0, factor=2.0, max_delay=5.0)
    limiter = _limiter_for(config.min_interval_s)
    enriched: list[WebSearchResult] = []
    with HttpFetcher(timeout=config.fetch_timeout) as fetcher:
        for hit in resp.results[: config.fetch_max_pages]:
            try:
                limiter.acquire()
                fetched = with_retry(
                    lambda: fetcher.fetch(hit.url), policy, description="web_search fetch"
                )
                md = extract_markdown(fetched.text or "", url=hit.url)
                enriched.append(
                    hit.model_copy(update={"snippet": md[:2000] if md else hit.snippet})
                )
            except Exception:
                enriched.append(hit)
    rest = resp.results[config.fetch_max_pages :]
    return WebSearchResponse(query=resp.query, results=enriched + rest, provider=resp.provider)
