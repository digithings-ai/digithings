"""Read-only grokipedia.com JSON API spike (unofficial; robots Disallow: /api/)."""

from digisearch.grokipedia.client import (
    USER_AGENT,
    GrokipediaClient,
    GrokipediaError,
    GrokipediaNotFoundError,
    GrokipediaRateLimitError,
    GrokipediaRobotsError,
    allow_api_from_env,
    get_shared_client,
    reset_shared_client,
)
from digisearch.grokipedia.models import (
    GrokipediaPage,
    GrokipediaSearchHit,
    GrokipediaSearchResponse,
    GrokipediaTypeaheadResponse,
)

__all__ = [
    "GrokipediaClient",
    "GrokipediaError",
    "GrokipediaNotFoundError",
    "GrokipediaPage",
    "GrokipediaRateLimitError",
    "GrokipediaRobotsError",
    "GrokipediaSearchHit",
    "GrokipediaSearchResponse",
    "GrokipediaTypeaheadResponse",
    "USER_AGENT",
    "allow_api_from_env",
    "get_shared_client",
    "reset_shared_client",
]
