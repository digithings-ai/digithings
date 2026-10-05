"""Read-only httpx client for grokipedia.com JSON APIs.

``/api/page`` 404s (probed 2026-10-02). ``get_page`` uses ``/api/page-preview``,
which is what the public site JS calls. Never scrapes ``/page/{slug}`` HTML.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from digibase.http_client import sync_client

from digisearch.grokipedia.models import (
    GrokipediaError,
    GrokipediaPage,
    GrokipediaPageResponse,
    GrokipediaSearchHit,
    GrokipediaSearchResponse,
)
from digisearch.grokipedia.rate_limit import PoliteLimiter

logger = logging.getLogger(__name__)

USER_AGENT = "digithings-digisearch-grokipedia/0.1 (+https://github.com/digithings-ai/digithings)"
ACCEPT = "application/json"
DEFAULT_BASE_URL = "https://grokipedia.com"
SEARCH_PATH = "/api/full-text-search"
PAGE_PREVIEW_PATH = "/api/page-preview"
MIN_INTERVAL_S = 0.3
CONTENT_CAP = 8000
DEFAULT_LIMIT = 10
MAX_LIMIT = 25
DEFAULT_TIMEOUT = 15.0
TRUNCATION_MARKER = "\n\n[truncated: {omitted} chars omitted]"

_RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def _truncate_content(content: str, cap: int) -> tuple[str, bool]:
    if cap <= 0 or len(content) <= cap:
        return content, False
    omitted = len(content) - cap
    return content[:cap] + TRUNCATION_MARKER.format(omitted=omitted), True


def _error(
    message: str,
    *,
    status_code: int | None = None,
    retryable: bool = False,
) -> GrokipediaError:
    return GrokipediaError(error=message, status_code=status_code, retryable=retryable)


def _normalize_slug(slug: str) -> str | GrokipediaError:
    text = slug.strip()
    if not text:
        return _error("slug is required")
    if "://" in text or text.startswith("/") or text.lower().startswith("page/"):
        return _error("slug must be a page slug, not a URL or /page/ path")
    return text


class GrokipediaClient:
    """Polite, injectable client. HTTP/network failures become error models."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        limiter: PoliteLimiter | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        content_cap: int = CONTENT_CAP,
        min_interval: float = MIN_INTERVAL_S,
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or sync_client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": ACCEPT},
        )
        if http_client is not None:
            # Tests inject a MockTransport client; still stamp polite headers.
            self._client.headers["User-Agent"] = USER_AGENT
            self._client.headers["Accept"] = ACCEPT
        self._limiter = limiter or PoliteLimiter(min_interval=min_interval)
        self._content_cap = content_cap

    def close(self) -> None:
        if self._owns_client and not self._client.is_closed:
            self._client.close()

    def search(
        self, query: str, limit: int = DEFAULT_LIMIT
    ) -> GrokipediaSearchResponse | GrokipediaError:
        text = query.strip()
        if not text:
            return _error("query is required")
        capped = max(1, min(int(limit), MAX_LIMIT))
        payload = self._get(SEARCH_PATH, {"query": text, "limit": str(capped)})
        if isinstance(payload, GrokipediaError):
            return payload
        raw_results = payload.get("results")
        hits: list[GrokipediaSearchHit] = []
        if isinstance(raw_results, list):
            for item in raw_results:
                if isinstance(item, dict):
                    hits.append(GrokipediaSearchHit.model_validate(item))
        total = payload.get("totalCount", payload.get("total_count"))
        total_count = total if isinstance(total, int) else None
        return GrokipediaSearchResponse(query=text, results=hits, total_count=total_count)

    def get_page(
        self, slug: str, include_content: bool = True
    ) -> GrokipediaPageResponse | GrokipediaError:
        normalized = _normalize_slug(slug)
        if isinstance(normalized, GrokipediaError):
            return normalized
        params: dict[str, str] = {"slug": normalized}
        if include_content:
            params["includeContent"] = "true"
        else:
            # Site uses content=0 for the short preview card.
            params["content"] = "0"
        payload = self._get(PAGE_PREVIEW_PATH, params)
        if isinstance(payload, GrokipediaError):
            return payload
        found = bool(payload.get("found"))
        raw_page = payload.get("page")
        page: GrokipediaPage | None = None
        if isinstance(raw_page, dict):
            page = GrokipediaPage.model_validate(raw_page)
            content, truncated = _truncate_content(page.content, self._content_cap)
            page = page.model_copy(update={"content": content, "truncated": truncated})
        return GrokipediaPageResponse(found=found, page=page)

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any] | GrokipediaError:
        self._limiter.acquire()
        try:
            response = self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            logger.info("grokipedia timeout on %s: %s", path, exc)
            return _error(f"timeout talking to grokipedia ({path})", retryable=True)
        except httpx.TransportError as exc:
            logger.info("grokipedia transport error on %s: %s", path, exc)
            return _error(f"transport error talking to grokipedia ({path})", retryable=True)
        except httpx.HTTPError as exc:
            logger.info("grokipedia http error on %s: %s", path, exc)
            return _error(f"http error talking to grokipedia ({path})", retryable=True)

        status = response.status_code
        if status >= 400:
            retryable = status in _RETRYABLE_STATUSES
            return _error(
                f"grokipedia HTTP {status} on {path}",
                status_code=status,
                retryable=retryable,
            )
        try:
            body = response.json()
        except ValueError:
            return _error(f"grokipedia returned non-JSON on {path}", status_code=status)
        if not isinstance(body, dict):
            return _error(f"grokipedia returned a non-object JSON body on {path}")
        return body
