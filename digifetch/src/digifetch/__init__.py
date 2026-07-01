"""DigiFetch — the shared web-scraping / headless-fetch engine for DigiThings.

A standalone **library** (no FastAPI, no port, no service coupling) extracting
the *reusable* parts of twelve-x's scrapers: headless-browser session lifecycle,
composable retry/backoff, min-interval rate limiting, and an httpx fetch/download
path with a Playwright→HTTP cookie hand-off. Site-specific logic (login flows,
selectors, URLs, HTML parsing, PDF extraction) stays in the consumer.

Built per explicit request **ahead of** the single-consumer trigger: today the
only consumer is twelve-x, so the interface is validated against one use case
and should be expected to evolve when a second consumer appears (YAGNI).

Public API
----------
- :class:`RetryPolicy`, :func:`with_retry` — composable retry/backoff.
- :class:`RateLimiter` — minimum-interval polite-scraping gate.
- :class:`HttpFetcher`, :class:`FetchResult`, :class:`DownloadResult`,
  :func:`cookies_from_playwright`, :data:`DEFAULT_TIMEOUT`,
  :class:`DownloadTooLargeError` — the non-browser fetch/download seam.
- :func:`browser_session`, :class:`BrowserConfig`, :class:`Page`,
  :class:`BrowserContext`, :class:`BrowserNotAvailableError` — the headless
  browser seam (requires the ``digifetch[browser]`` extra).

Import cost
-----------
Importing ``digifetch`` pulls only ``pydantic`` + ``httpx`` (the light fetch
seam). Playwright is **never** imported at import time: the browser symbols are
resolved lazily via :pep:`562` ``__getattr__`` and the ``playwright`` import is
deferred to :func:`browser_session` call-time. So ``import digifetch`` succeeds
on a machine with no browser installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from digifetch.http import (
    DEFAULT_TIMEOUT,
    DownloadResult,
    DownloadTooLargeError,
    FetchResult,
    HttpFetcher,
    cookies_from_playwright,
)
from digifetch.ratelimit import RateLimiter
from digifetch.retry import RetryPolicy, with_retry

if TYPE_CHECKING:
    # Type-checkers see these eagerly; at runtime they resolve lazily via
    # __getattr__ so the playwright-touching module is only imported on demand.
    from digifetch.browser import (
        BrowserConfig,
        BrowserContext,
        BrowserNotAvailableError,
        Page,
        browser_session,
    )

__version__ = "0.1.0"

# Browser symbols live in digifetch.browser. That module does not import
# playwright at import time either, but we expose its names lazily so the public
# surface mirrors the digibase.connectors pattern and keeps a single, documented
# place where the browser seam is wired in.
_BROWSER_EXPORTS = frozenset(
    {
        "BrowserConfig",
        "BrowserContext",
        "BrowserNotAvailableError",
        "Page",
        "browser_session",
    }
)

__all__ = [
    "DEFAULT_TIMEOUT",
    "BrowserConfig",
    "BrowserContext",
    "BrowserNotAvailableError",
    "DownloadResult",
    "DownloadTooLargeError",
    "FetchResult",
    "HttpFetcher",
    "Page",
    "RateLimiter",
    "RetryPolicy",
    "__version__",
    "browser_session",
    "cookies_from_playwright",
    "with_retry",
]


def __getattr__(name: str) -> Any:  # noqa: ANN401 — PEP 562 lazy re-export shim
    """Resolve browser-seam symbols lazily (PEP 562).

    Keeps ``import digifetch`` free of any browser import while still letting
    ``from digifetch import browser_session`` work.
    """
    if name in _BROWSER_EXPORTS:
        from digifetch import browser

        value = getattr(browser, name)
        globals()[name] = value  # cache so subsequent lookups skip this shim
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
