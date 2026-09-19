"""Service orchestration for #3853: search -> fetch via digifetch -> extract."""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Literal

import httpx
from digifetch import HttpFetcher, RateLimiter, RetryPolicy, with_retry
from pydantic import BaseModel, Field, ValidationError

from digisearch.web_search.ddgs_provider import DdgsWebSearchProvider
from digisearch.web_search.extractor import extract_markdown
from digisearch.web_search.models import (
    WebSearchConfigError,
    WebSearchProviderError,
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
)
from digisearch.web_search.searxng_provider import SearXNGWebSearchProvider

logger = logging.getLogger(__name__)


class WebSearchConfig(BaseModel):
    backend: Literal["auto", "searxng", "ddgs"] = "auto"
    searxng_url: str = "http://127.0.0.1:8080"
    fetch_max_pages: int = Field(default=3, ge=1, le=10)
    fetch_timeout: float = Field(default=15.0, gt=0)
    min_interval_s: float = Field(default=1.0, ge=0)
    # Operator-trusted hosts exempted from the digifetch SSRF address refusal
    # (e.g. a company egress proxy). Sourced from DIGISEARCH_FETCH_ALLOWED_HOSTS.
    fetch_allowed_hosts: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> WebSearchConfig:
        backend = os.environ.get("DIGISEARCH_WEB_SEARCH_BACKEND", "auto")
        allowed_hosts = tuple(
            host.strip().lower()
            for host in os.environ.get("DIGISEARCH_FETCH_ALLOWED_HOSTS", "").split(",")
            if host.strip()
        )
        try:
            return cls(
                backend=backend,
                searxng_url=os.environ.get("DIGISEARCH_SEARXNG_URL", "http://127.0.0.1:8080"),
                fetch_allowed_hosts=allowed_hosts,
            )
        except ValidationError as e:
            raise WebSearchConfigError(
                f"invalid DIGISEARCH_WEB_SEARCH_BACKEND={backend!r}: "
                "must be one of auto, searxng, ddgs"
            ) from e


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


#: Upstream statuses worth retrying: throttling, transient timeouts, 5xx.
_RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


#: Credentials and tokens in a provider URL must never reach a caller-visible
#: error string: httpx embeds the full request URL (userinfo, query) in
#: ``HTTPStatusError``/``TransportError`` text.
_URL_USERINFO_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.\-]*://)[^/@\s]+@")
#: Scheme-less userinfo (e.g. ``httpx.Proxy("user:pass@host")`` error text).
_URL_BARE_USERINFO_RE = re.compile(r"[^\s/@:]+:[^\s/@:]+@")
_URL_QUERY_RE = re.compile(r"\?[^\s'\"`)]*")


def _scrub_provider_detail(text: str) -> str:
    """Strip URL userinfo and query strings (secrets) from provider text."""
    text = _URL_USERINFO_RE.sub(r"\1***@", text)
    text = _URL_BARE_USERINFO_RE.sub("***@", text)
    return _URL_QUERY_RE.sub("?<redacted>", text)


def _provider_failure_fields(exc: Exception) -> tuple[int | None, bool]:
    """Best-effort ``(upstream_status, retryable)`` for a provider exception.

    httpx failures expose a response/status; ddgs failures do not, so classify
    those by name (the web-search extra is optional and stays un-imported here).
    ``RatelimitException`` is a *raised* ddgs failure only in 9.0.x — ddgs
    >=9.1 collapses non-200 provider responses (including 429s) into
    ``DDGSException("No results found.")``, which carries no status and is
    reported as a non-retryable hard failure rather than guessed at.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status, status in _RETRYABLE_STATUSES
    if isinstance(exc, httpx.TransportError):
        return None, True
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return status, status in _RETRYABLE_STATUSES
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "rate_limit" in name:
        # ddgs 9.0.x raised RatelimitException without an HTTP response; 429 is
        # its HTTP meaning, so surface it as the status hint. Newer ddgs
        # versions no longer raise it (see the DDGSException branch below).
        return 429, True
    if "timeout" in name or isinstance(exc, OSError):
        return None, True
    if "ddgsexception" in name:
        # ddgs >=9.1 raises this for any failed search, even a provider 429.
        # No status is recoverable, so retryability is not guessed.
        return None, False
    return None, False


def _format_provider_failure(name: str, exc: Exception) -> str:
    """Render one backend's failure as ``name: detail`` (secrets scrubbed).

    The upstream HTTP status, when the provider exposed one, is appended so a
    multi-backend failure message still carries each backend's real result
    instead of collapsing to the last backend alone.
    """
    status, _ = _provider_failure_fields(exc)
    detail = _scrub_provider_detail(str(exc) or type(exc).__name__)
    if status is not None and str(status) not in detail:
        detail = f"{detail} (HTTP {status})"
    return f"{name}: {detail}"


def _search_only(req: WebSearchRequest, config: WebSearchConfig) -> WebSearchResponse:
    """Run the configured backend, then fail over.

    ``searxng``/``ddgs`` run only the named backend; ``auto`` tries searxng
    first and ddgs second. Every backend failure is collected so the raised
    ``WebSearchProviderError`` names each backend and its actual error — a
    last-error-only message hid the primary's transport failure (#4297).
    ``retryable`` is true when any backend failed transiently (a transport,
    timeout, or retryable HTTP status), because the primary can recover on a
    later attempt; ``status_code`` is the first upstream status any backend
    exposed, primary-first, rather than the last backend's guess.

    A successful provider call that returns zero rows stays an honest
    ``ok=true`` response with ``results=[]``: an empty body is never turned
    into an error here. Only raised provider failures reach this failover.
    """
    order = [config.backend] if config.backend in ("searxng", "ddgs") else ["searxng", "ddgs"]
    failures: list[tuple[str, Exception]] = []
    for name in order:
        try:
            if name == "searxng":
                return SearXNGWebSearchProvider(base_url=config.searxng_url).search(req)
            return DdgsWebSearchProvider().search(req)
        except Exception as exc:
            failures.append((name, exc))
    if not failures:  # pragma: no cover - ``order`` is never empty
        raise WebSearchProviderError("all web-search backends failed")
    fields = [_provider_failure_fields(exc) for _, exc in failures]
    status = next((s for s, _ in fields if s is not None), None)
    retryable = any(retry for _, retry in fields)
    detail = "; ".join(_format_provider_failure(name, exc) for name, exc in failures)
    raise WebSearchProviderError(
        f"all web-search backends failed: {detail}",
        status_code=status,
        retryable=retryable,
    )


def search_web(req: WebSearchRequest, config: WebSearchConfig | None = None) -> WebSearchResponse:
    """Public retrieval wrapper: search only, no fetch enrichment.

    Resolves env config when *config* is None and returns the landed
    ``_search_only`` failover (``auto|searxng|ddgs``). Fetch enrichment
    stays with ``run_web_search``.
    """
    config = config or WebSearchConfig.from_env()
    return _search_only(req, config)


def run_web_search(
    req: WebSearchRequest, config: WebSearchConfig | None = None
) -> WebSearchResponse:
    config = config or WebSearchConfig.from_env()
    resp = _search_only(req, config)
    policy = RetryPolicy(attempts=2, base_delay=1.0, factor=2.0, max_delay=5.0)
    limiter = _limiter_for(config.min_interval_s)
    enriched: list[WebSearchResult] = []
    with HttpFetcher(
        timeout=config.fetch_timeout, allowed_hosts=config.fetch_allowed_hosts
    ) as fetcher:
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
            except Exception as exc:
                # Documented contract (#3853): one hit's fetch/extract failure
                # must not fail the whole search, so the original provider
                # snippet (a real search row, not fabricated content) is kept.
                # Reviewed under #4297: this is not a hidden provider failure —
                # the search backend already answered ok — so it is logged to
                # keep the degraded enrichment visible instead of silent.
                logger.warning(
                    "web_search enrichment failed for %s: %s",
                    _scrub_provider_detail(hit.url),
                    _scrub_provider_detail(str(exc) or type(exc).__name__),
                )
                enriched.append(hit)
    rest = resp.results[config.fetch_max_pages :]
    return WebSearchResponse(query=resp.query, results=enriched + rest, provider=resp.provider)
