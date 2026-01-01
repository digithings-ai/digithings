"""Unofficial grokipedia.com JSON client for digisearch MCP (spike).

Read-only wrappers around the public JSON APIs the site itself calls. This is
**not** an official xAI / grokipedia product integration.

robots.txt (probed 2026-10-02) currently has ``User-agent: *`` / ``Disallow: /api/``.
The public site JS still calls these APIs. Treat this as unofficial/third-party
use: polite rate limits, no HTML scrape of ``/page/{slug}``, spike only — HOLD
hatch for a One/Chris legal/product call before any production attach.

Live endpoints (same probe):

* search — ``GET /api/full-text-search?query=&limit=``
* get_page — ``GET /api/page-preview?slug=`` (``/api/page`` 404s; page-preview is SoT)
"""

from digisearch.grokipedia.client import (
    CONTENT_CAP,
    DEFAULT_LIMIT,
    MIN_INTERVAL_S,
    USER_AGENT,
    GrokipediaClient,
)
from digisearch.grokipedia.models import (
    GrokipediaError,
    GrokipediaPage,
    GrokipediaPageResponse,
    GrokipediaSearchHit,
    GrokipediaSearchResponse,
)
from digisearch.grokipedia.tools import grokipedia_get_page, grokipedia_search

__all__ = [
    "CONTENT_CAP",
    "DEFAULT_LIMIT",
    "MIN_INTERVAL_S",
    "USER_AGENT",
    "GrokipediaClient",
    "GrokipediaError",
    "GrokipediaPage",
    "GrokipediaPageResponse",
    "GrokipediaSearchHit",
    "GrokipediaSearchResponse",
    "grokipedia_get_page",
    "grokipedia_search",
]
