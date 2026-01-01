"""Provider registry for the unified ``web_search`` tool (#4711).

Two rules, both load-bearing:

1. **``auto`` always means the in-house tool.** :func:`resolve_provider_name`
   maps an empty / ``auto`` name to ``internal`` without ever consulting an env
   var, so configuring an external key can never silently reroute the default
   path away from searxng→ddgs.
2. **An explicitly named provider is fail-closed.** Naming ``tavily`` without
   ``TAVILY_API_KEY`` raises :class:`WebProviderNotConfiguredError`; there is no
   fallback to whichever provider happens to be configured.

Environment variables are read at call time (never import time), so a key added
after the process starts is picked up and a key-less install stays inert.
"""

from __future__ import annotations

from typing import Any  # score:allow untyped any — heterogeneous provider metadata

from digisearch.web_providers.base import (
    BaseWebProvider,
    WebProviderBadRequestError,
    WebProviderCapabilityError,
    WebProviderError,
    WebProviderNotConfiguredError,
    WebProviderUnavailableError,
)
from digisearch.web_providers.exa import ExaWebProvider
from digisearch.web_providers.firecrawl import FirecrawlWebProvider
from digisearch.web_providers.internal import InternalWebProvider
from digisearch.web_providers.parallel import ParallelWebProvider
from digisearch.web_providers.tavily import TavilyWebProvider
from digisearch.web_providers.tinyfish import TinyfishWebProvider

#: Every selectable provider, in `auto`-free manual selection order.
PROVIDER_NAMES: tuple[str, ...] = (
    "internal",
    "exa",
    "tavily",
    "parallel",
    "firecrawl",
    "tinyfish",
)

#: External provider -> env var that gates it. ``internal`` is absent on
#: purpose: it needs no key and must stay reachable regardless.
EXTERNAL_PROVIDER_ENV: dict[str, str] = {
    "exa": "EXA_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "parallel": "PARALLEL_API_KEY",
    "firecrawl": "FIRECRAWL_API_KEY",
    "tinyfish": "TINYFISH_API_KEY",
}

_REGISTRY: dict[str, type[BaseWebProvider]] = {
    "internal": InternalWebProvider,
    "exa": ExaWebProvider,
    "tavily": TavilyWebProvider,
    "parallel": ParallelWebProvider,
    "firecrawl": FirecrawlWebProvider,
    "tinyfish": TinyfishWebProvider,
}

#: Sentinel accepted anywhere a provider name is: no key consulted, ever.
AUTO_PROVIDER = "auto"


class UnknownProviderError(ValueError):
    """The requested provider name is not one of :data:`PROVIDER_NAMES`.

    A ``ValueError`` so every existing ``except ValueError`` call site keeps
    treating an unknown name as invalid input (HTTP 400 / orchestrator
    ``ok:false``), distinct from a provider that exists but has no key.
    """


def resolve_provider_name(name: str | None) -> str:
    """Normalise a caller-supplied provider name.

    ``""`` / ``None`` / ``"auto"`` -> ``"internal"`` **unconditionally**; a real
    name is lowercased and validated. No env var is consulted here.
    """
    if name is None or not str(name).strip():
        return "internal"
    cleaned = str(name).strip().lower()
    if cleaned == AUTO_PROVIDER:
        return "internal"
    if cleaned not in _REGISTRY:
        raise UnknownProviderError(
            f"unknown provider {name!r} (choose from: {', '.join(PROVIDER_NAMES)})"
        )
    return cleaned


def get_provider(name: str | None) -> BaseWebProvider:
    """Resolve a provider instance. Does **not** check whether it is configured."""
    return _REGISTRY[resolve_provider_name(name)]()


def configured_providers() -> list[str]:
    """Providers usable right now: always ``internal``, plus keyed externals."""
    return [n for n in PROVIDER_NAMES if get_provider(n).is_configured()]


def provider_enum_choices(name: str | None = None) -> list[str]:
    """Enum values for the tool manifest.

    ``auto`` (the unconditional default) and ``internal`` are always offered;
    an external provider only appears once its key exists, so an operator is
    never shown a choice that would 503.
    """
    if name is not None:
        return [resolve_provider_name(name)]
    return [AUTO_PROVIDER, *configured_providers()]


def available_providers() -> dict[str, dict[str, Any]]:
    """Describe every provider for docs/manifest introspection."""
    return {
        name: {
            "env_var": EXTERNAL_PROVIDER_ENV.get(name, ""),
            "configured": get_provider(name).is_configured(),
            "cost_hint": _REGISTRY[name].cost_hint,
            "supports_contents": _REGISTRY[name].supports_contents,
            "supports_answer": _REGISTRY[name].supports_answer,
            "supports_offset": _REGISTRY[name].supports_offset,
        }
        for name in PROVIDER_NAMES
    }


__all__ = [
    "AUTO_PROVIDER",
    "EXTERNAL_PROVIDER_ENV",
    "PROVIDER_NAMES",
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
    "resolve_provider_name",
]
