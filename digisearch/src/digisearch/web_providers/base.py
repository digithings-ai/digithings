"""Cross-vendor web search provider seam (#4711).

digisearch used to expose two separate web-search surfaces: the first-party
searxng→ddgs tool behind ``POST /v1/web_search`` and a second, EXA-only tool
behind ``POST /v1/digisearch_web_search``. #4711 collapses them into a single
``web_search`` tool with a swappable ``provider``.

Contract:

- ``auto`` resolves to ``internal`` **unconditionally** — no API key can
  silently redirect the default path away from the in-house tool.
- Naming an external provider explicitly requires its key. A missing key fails
  closed with :class:`WebProviderNotConfiguredError`; it never falls back to a
  different provider.
- Nothing reads an environment variable at import time.

Transport is ``httpx`` (already in the base install) — no vendor SDKs.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import httpx

from digisearch.web_search.models import WebSearchRequest, WebSearchResponse

#: Shared upstream timeout for every vendor call (matches EXA_TIMEOUT_S).
DEFAULT_TIMEOUT_S = 30.0


class WebProviderError(RuntimeError):
    """A configured provider failed at the transport / API level.

    Mirrors :class:`digisearch.web_search.models.WebSearchProviderError` so the
    HTTP route can render both the same way: a provider-level failure is a
    #4192 soft envelope (HTTP 200 + ``retryable``/``status_code``), never a 500.
    """

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


class WebProviderNotConfiguredError(WebProviderError):
    """The named provider has no API key set.

    Fail-closed and never retryable: retrying without a key cannot help.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=None, retryable=False)


class WebProviderUnavailableError(WebProviderError):
    """The provider is selected but its optional dependency is not installed.

    Distinct from :class:`WebProviderNotConfiguredError` so the route can keep
    answering 503 ``Install digisearch[web-search] …`` for the internal
    provider's optional extra instead of a "key is not set" message.
    """


class WebProviderCapabilityError(WebProviderError):
    """The provider exists but does not implement the asked-for capability."""


class WebProviderBadRequestError(WebProviderError):
    """The caller's request is invalid for this provider (page past cap, …).

    Distinct from an upstream 400 so routes can answer a real 400 instead of
    folding caller error into the #4192 soft envelope meant for provider outages.
    """


class BaseWebProvider:
    """Shared plumbing for every provider: config, HTTP, and result mapping."""

    #: Registry key, e.g. ``"tavily"``.
    provider_name: ClassVar[str] = ""
    #: Env var holding the API key. Empty means the provider needs no key.
    env_var: ClassVar[str] = ""
    #: Human billing hint surfaced in the tool manifest description.
    cost_hint: ClassVar[str] = ""
    #: Whether ``fetch_contents`` / ``answer`` are implemented (EXA in v1).
    supports_contents: ClassVar[bool] = False
    supports_answer: ClassVar[bool] = False
    #: Whether the provider can page past ``max_results`` via ``offset``.
    supports_offset: ClassVar[bool] = False

    def is_configured(self) -> bool:
        """Read the env var **at call time** so key-less installs stay inert."""
        if not self.env_var:
            return True
        return bool(os.environ.get(self.env_var, "").strip())

    def require_configured(self) -> str:
        """Return the API key or raise the fail-closed not-configured error."""
        if not self.env_var:
            return ""
        key = os.environ.get(self.env_var, "").strip()
        if not key:
            raise WebProviderNotConfiguredError(
                f"{self.env_var} is not set for provider {self.provider_name}"
            )
        return key

    def search(self, req: WebSearchRequest) -> WebSearchResponse:
        """Public entry point: apply shared guards, then delegate."""
        if req.offset and not self.supports_offset:
            raise WebProviderCapabilityError(
                f"provider {self.provider_name} does not support offset paging"
            )
        return self._search(req)

    def _search(self, req: WebSearchRequest) -> WebSearchResponse:
        raise NotImplementedError

    def fetch_contents(
        self,
        urls: list[str],
        *,
        text: bool = True,
        highlights: bool = False,
        summary: bool = False,
        highlight_query: str | None = None,
    ) -> dict[str, Any]:
        raise WebProviderCapabilityError(
            f"provider {self.provider_name} does not support fetch_contents"
        )

    def answer(self, question: str) -> dict[str, Any]:
        raise WebProviderCapabilityError(f"provider {self.provider_name} does not support answer")

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<{type(self).__name__} provider={self.provider_name}>"


def date_days_ago(days: int) -> str:
    """ISO date (``YYYY-MM-DD``) ``days`` before now — for vendor date filters."""
    return (datetime.now(tz=UTC).date() - timedelta(days=days)).isoformat()


def rank_score(position: int) -> float:
    """Rank-derived stand-in score for vendors whose API returns none.

    Position is 0-based: the top hit scores 1.0 and each rank below loses 0.01.
    It is *not* a relevance probability — it only keeps ``WebSearchResult.score``
    meaningful for callers that sort on it.
    """
    return round(max(0.0, 1.0 - 0.01 * max(0, position)), 4)


def request_json(
    provider_name: str,
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> Any:
    """Call a vendor API and decode JSON, mapping failures to WebProviderError.

    One mapping for every vendor keeps the #4192 soft-envelope contract
    uniform: 429 and 5xx are retryable, 401/403 means the key is wrong.
    """
    try:
        resp = httpx.request(
            method,
            url,
            headers=headers,
            json=json_body,
            params=params,
            timeout=timeout,
        )
    except httpx.TimeoutException as e:
        raise WebProviderError(f"{provider_name} request timed out: {e}", retryable=True) from e
    except httpx.HTTPError as e:
        raise WebProviderError(f"{provider_name} request failed: {e}", retryable=True) from e

    if resp.status_code in (401, 403):
        raise WebProviderError(
            f"{provider_name} rejected the API key ({resp.status_code}) — check its key.",
            status_code=resp.status_code,
            retryable=False,
        )
    if resp.status_code == 429:
        raise WebProviderError(
            f"{provider_name} rate limited this key (429) — back off and retry.",
            status_code=429,
            retryable=True,
        )
    if resp.status_code >= 400:
        raise WebProviderError(
            f"{provider_name} request failed ({resp.status_code}): {resp.text[:500]}",
            status_code=resp.status_code,
            retryable=resp.status_code >= 500,
        )
    try:
        data = resp.json()
    except ValueError as e:
        raise WebProviderError(
            f"{provider_name} returned non-JSON",
            status_code=resp.status_code,
            retryable=False,
        ) from e
    return data


def require_dict(provider_name: str, data: Any) -> dict[str, Any]:
    """Narrow a decoded vendor payload to a dict, failing loud otherwise."""
    if not isinstance(data, dict):
        raise WebProviderError(
            f"{provider_name} returned unexpected shape (expected object)",
            retryable=False,
        )
    return data
