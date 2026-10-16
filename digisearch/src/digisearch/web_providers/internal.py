"""In-house provider: searxng with ddgs fallback (#3853, #4297, #4711).

This is what ``provider="auto"`` always resolves to — deliberately, even when
external keys are configured. It wraps :func:`digisearch.web_search.service.run_web_search`
rather than re-implementing search, failover, or fetch+extract enrichment.

``effort`` and ``purpose`` have no in-house equivalent yet (see the five parity
gaps in issue #4711) and are accepted-but-ignored so a single tool schema covers
every provider.
"""

from __future__ import annotations

from digisearch.web_providers.base import BaseWebProvider, WebProviderUnavailableError
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse


class InternalWebProvider(BaseWebProvider):
    provider_name = "internal"
    env_var = ""  # no key: `auto` must reach this provider regardless
    cost_hint = "free (searxng -> ddgs; install digisearch[web-search])"

    def is_configured(self) -> bool:
        """Report configuration from the optional extra, never an API key."""
        try:
            import digisearch.web_search.service  # noqa: F401
        except ImportError:
            return False
        return True

    def _search(self, req: WebSearchRequest) -> WebSearchResponse:
        try:
            from digisearch.web_search.service import run_web_search
        except ImportError as e:
            raise WebProviderUnavailableError(
                f"Install digisearch[web-search] for web_search: {e}"
            ) from e

        resp = run_web_search(
            WebSearchRequest(
                query=req.query,
                include_domains=req.include_domains,
                exclude_domains=req.exclude_domains,
                max_results=req.max_results,
                recency_days=req.recency_days,
            )
        )
        # `provider` names the *vendor* across the unified surface; the
        # searxng/ddgs backend that actually served it moves to `output.backend`
        # so callers can still tell which in-house engine ran.
        backend = resp.provider
        return resp.model_copy(
            update={
                "provider": self.provider_name,
                "output": {"backend": backend} if backend else None,
            }
        )


__all__ = ["InternalWebProvider"]
