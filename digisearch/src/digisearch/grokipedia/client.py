"""Read-only grokipedia.com JSON client (spike; unofficial public endpoints).

Checked 2026-10-01: ``https://grokipedia.com/robots.txt`` is::

    User-agent: *
    Disallow: /api/

Live HTTP therefore requires ``DIGISEARCH_GROKIPEDIA_ALLOW_API=1`` (or
``allow_api=True`` on the constructor). Unit tests inject ``httpx.MockTransport``
and never touch the network. Prefer these JSON endpoints over HTML scrape.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from typing import Any, Callable
from urllib.parse import urlencode

import httpx
from pydantic import ValidationError

from digisearch.grokipedia.models import (
    GrokipediaPage,
    GrokipediaSearchHit,
    GrokipediaSearchResponse,
    GrokipediaTypeaheadResponse,
)

DEFAULT_BASE_URL = "https://grokipedia.com"
SEARCH_PATH = "/api/full-text-search"
PAGE_PATH = "/api/page"
TYPEAHEAD_PATH = "/api/typeahead"

#: Identifying UA required by this spike (never a generic python-httpx default).
USER_AGENT = (
    "digithings-digisearch/0.1 (+https://github.com/digithings-ai/digithings; grokipedia spike)"
)

#: Honor "<= ~30 req/min" from the spike brief.
DEFAULT_MAX_REQUESTS = 30
DEFAULT_WINDOW_SECONDS = 60.0

MIN_LIMIT = 1
MAX_SEARCH_LIMIT = 50
MAX_TYPEAHEAD_LIMIT = 20
DEFAULT_SEARCH_LIMIT = 10
DEFAULT_TYPEAHEAD_LIMIT = 8

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_EM_RE = re.compile(r"</?em>", re.IGNORECASE)
_UNSAFE_SLUG = re.compile(r"[\\/?#]")


class GrokipediaError(RuntimeError):
    """Transport or payload failure talking to the unofficial grokipedia JSON API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class GrokipediaRobotsError(GrokipediaError):
    """Live ``/api/`` is opt-in because robots.txt currently Disallow: /api/."""

    def __init__(self) -> None:
        super().__init__(
            "grokipedia robots.txt Disallow: /api/ (checked 2026-10-01). "
            "Endpoints are public/unofficial JSON, not a documented partner API. "
            "Set DIGISEARCH_GROKIPEDIA_ALLOW_API=1 to opt in.",
            retryable=False,
        )


class GrokipediaRateLimitError(GrokipediaError):
    """Local 30/min budget exhausted, or upstream returned 429."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message, status_code=status_code, retryable=True)


class GrokipediaNotFoundError(GrokipediaError):
    def __init__(self, slug: str) -> None:
        super().__init__(f"grokipedia page not found: {slug!r}", status_code=404)


class SlidingWindowLimiter:
    """Thread-safe sliding window; default 30 requests / 60 seconds."""

    def __init__(
        self,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock or time.monotonic
        self._times: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        now = self._clock()
        with self._lock:
            cutoff = now - self.window_seconds
            while self._times and self._times[0] <= cutoff:
                self._times.popleft()
            if len(self._times) >= self.max_requests:
                raise GrokipediaRateLimitError(
                    f"grokipedia local rate limit ({self.max_requests} req / "
                    f"{int(self.window_seconds)}s) exhausted — back off."
                )
            self._times.append(now)


def allow_api_from_env(environ: dict[str, str] | None = None) -> bool:
    """True when the operator opted into unofficial ``/api/`` despite robots.txt."""
    env = environ if environ is not None else os.environ
    return env.get("DIGISEARCH_GROKIPEDIA_ALLOW_API", "").strip().lower() in _TRUTHY


def clamp_limit(limit: int, *, maximum: int) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if value < MIN_LIMIT:
        return MIN_LIMIT
    if value > maximum:
        return maximum
    return value


def _clean_snippet(snippet: str) -> str:
    return re.sub(r"\s+", " ", _EM_RE.sub("", snippet)).strip()


def _page_url(slug: str) -> str:
    return f"{DEFAULT_BASE_URL}/page/{slug}"


def _validate_slug(slug: str) -> str:
    cleaned = slug.strip()
    if not cleaned:
        raise ValueError("slug is required")
    if _UNSAFE_SLUG.search(cleaned) or ".." in cleaned:
        raise ValueError(f"invalid grokipedia slug: {slug!r}")
    return cleaned


def _hit_from_payload(raw: dict[str, Any]) -> GrokipediaSearchHit:
    hit = GrokipediaSearchHit.model_validate(raw)
    if not hit.slug:
        raise GrokipediaError("grokipedia hit missing slug")
    snippet = _clean_snippet(hit.snippet)
    url = hit.url or _page_url(hit.slug)
    return hit.model_copy(update={"snippet": snippet, "url": url, "title": hit.title or hit.slug})


class GrokipediaClient:
    """Thin GET client for search / page / typeahead. JSON only; no HTML scrape."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        allow_api: bool | None = None,
        limiter: SlidingWindowLimiter | None = None,
        timeout: float = 15.0,
        owns_client: bool | None = None,
    ) -> None:
        self._allow_api = allow_api_from_env() if allow_api is None else allow_api
        self._limiter = limiter or SlidingWindowLimiter()
        if http_client is None:
            self._http = httpx.Client(
                timeout=timeout,
                follow_redirects=False,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            self._owns_client = True
        else:
            self._http = http_client
            self._owns_client = False if owns_client is None else owns_client

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> GrokipediaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def search(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> GrokipediaSearchResponse:
        text = query.strip()
        if not text:
            raise ValueError("query is required")
        capped = clamp_limit(limit, maximum=MAX_SEARCH_LIMIT)
        payload = self._get(SEARCH_PATH, {"query": text, "limit": str(capped)})
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raw_results = []
        hits: list[GrokipediaSearchHit] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            try:
                hits.append(_hit_from_payload(item))
            except (ValidationError, GrokipediaError):
                continue
        total = payload.get("totalCount", payload.get("total_count"))
        total_count = total if isinstance(total, int) else None
        return GrokipediaSearchResponse(query=text, results=hits, total_count=total_count)

    def get_page(self, slug: str) -> GrokipediaPage:
        cleaned = _validate_slug(slug)
        payload = self._get(PAGE_PATH, {"slug": cleaned, "includeContent": "true"})
        page_raw = payload.get("page") if isinstance(payload.get("page"), dict) else payload
        if not isinstance(page_raw, dict):
            raise GrokipediaError("grokipedia page payload was not a JSON object")
        merged = {**page_raw, "slug": page_raw.get("slug") or cleaned}
        page = GrokipediaPage.model_validate(merged)
        return page.model_copy(
            update={
                "slug": page.slug or cleaned,
                "title": page.title or cleaned,
                "url": page.url or _page_url(page.slug or cleaned),
            }
        )

    def typeahead(
        self, query: str, limit: int = DEFAULT_TYPEAHEAD_LIMIT
    ) -> GrokipediaTypeaheadResponse:
        text = query.strip()
        if not text:
            raise ValueError("query is required")
        capped = clamp_limit(limit, maximum=MAX_TYPEAHEAD_LIMIT)
        payload = self._get(TYPEAHEAD_PATH, {"query": text, "limit": str(capped)})
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raw_results = []
        hits: list[GrokipediaSearchHit] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            try:
                hits.append(_hit_from_payload(item))
            except (ValidationError, GrokipediaError):
                continue
        return GrokipediaTypeaheadResponse(query=text, results=hits)

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if not self._allow_api:
            raise GrokipediaRobotsError()
        self._limiter.acquire()
        url = f"{DEFAULT_BASE_URL}{path}?{urlencode(params)}"
        try:
            response = self._http.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
        except httpx.TimeoutException as exc:
            raise GrokipediaError("grokipedia request timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise GrokipediaError(f"grokipedia transport error: {exc}", retryable=True) from exc
        if response.status_code == 429:
            raise GrokipediaRateLimitError("grokipedia returned 429 — back off.", status_code=429)
        if response.status_code == 404:
            slug = params.get("slug", path)
            raise GrokipediaNotFoundError(slug)
        if response.status_code >= 400:
            raise GrokipediaError(
                f"grokipedia HTTP {response.status_code}",
                status_code=response.status_code,
                retryable=response.status_code >= 500,
            )
        content_type = (response.headers.get("content-type") or "").lower()
        if "html" in content_type and "json" not in content_type:
            raise GrokipediaError(
                "grokipedia returned HTML; this spike uses JSON /api/ only (no scrape)."
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise GrokipediaError(
                "grokipedia returned non-JSON; this spike uses JSON /api/ only (no scrape)."
            ) from exc
        if not isinstance(body, dict):
            raise GrokipediaError("grokipedia JSON root was not an object")
        return body


_shared: GrokipediaClient | None = None
_shared_lock = threading.Lock()


def get_shared_client() -> GrokipediaClient:
    """Process-wide client so MCP tools share the 30/min budget."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = GrokipediaClient()
        return _shared


def reset_shared_client() -> None:
    """Test seam: drop the process-wide client."""
    global _shared
    with _shared_lock:
        if _shared is not None:
            _shared.close()
        _shared = None
