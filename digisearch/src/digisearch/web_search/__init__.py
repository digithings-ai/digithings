"""digisearch.web_search package."""

from digisearch.web_search.citation import Citation, normalize_url
from digisearch.web_search.models import (
    WebSearchConfigError,
    WebSearchErrorResponse,
    WebSearchProviderError,
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
    apply_domain_filter,
)

__all__ = [
    "Citation",
    "WebSearchConfigError",
    "WebSearchErrorResponse",
    "WebSearchProviderError",
    "WebSearchRequest",
    "WebSearchResponse",
    "WebSearchResult",
    "apply_domain_filter",
    "normalize_url",
]
