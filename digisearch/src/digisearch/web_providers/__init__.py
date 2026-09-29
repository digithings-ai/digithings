"""Cross-vendor web search providers (#4711).

digisearch exposes one ``web_search`` tool (HTTP ``POST /v1/web_search``,
orchestrator ``web_search``, MCP ``web_search``) whose ``provider`` field picks
the engine behind it:

===========  ==========================  ===================================
provider     key                         notes
===========  ==========================  ===================================
internal     (none)                      searxng -> ddgs; what ``auto`` means
exa          ``EXA_API_KEY``             neural search, answer, contents
tavily       ``TAVILY_API_KEY``          1,000 free credits/mo
parallel     ``PARALLEL_API_KEY``        declarative objective + excerpts
firecrawl    ``FIRECRAWL_API_KEY``       search + JS render to markdown
tinyfish     ``TINYFISH_API_KEY``        free search, NL ``purpose`` field
===========  ==========================  ===================================

This package is the deliberately *separate* paid alternative to the in-house
path in :mod:`digisearch.web_search` — the same relationship
:mod:`digisearch.websets.providers` sets up for websets. Nothing here reads an
environment variable at import time, and no provider silently substitutes for
another: ``auto`` is always ``internal``, and a named provider with no key fails
closed.
"""

from __future__ import annotations

from digisearch.web_providers.base import (
    BaseWebProvider,
    WebProviderBadRequestError,
    WebProviderCapabilityError,
    WebProviderError,
    WebProviderNotConfiguredError,
    WebProviderUnavailableError,
    rank_score,
)
from digisearch.web_providers.registry import (
    AUTO_PROVIDER,
    EXTERNAL_PROVIDER_ENV,
    PROVIDER_NAMES,
    UnknownProviderError,
    available_providers,
    configured_providers,
    get_provider,
    provider_enum_choices,
    resolve_provider_name,
)

__all__ = [
    "AUTO_PROVIDER",
    "EXTERNAL_PROVIDER_ENV",
    "PROVIDER_NAMES",
    "BaseWebProvider",
    "UnknownProviderError",
    "WebProviderBadRequestError",
    "WebProviderCapabilityError",
    "WebProviderError",
    "WebProviderNotConfiguredError",
    "WebProviderUnavailableError",
    "available_providers",
    "configured_providers",
    "get_provider",
    "provider_enum_choices",
    "rank_score",
    "resolve_provider_name",
]
