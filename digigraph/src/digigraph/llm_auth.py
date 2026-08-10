"""Per-request LLM auth funnel for digigraph's FastAPI service.

Relocated from the former monolithic ``digigraph.llm`` (#632 P2). Parses the
per-request auth headers digichat/digikey forward and feeds digillm's
provider-agnostic override contextvars:

- ``X-LiteLLM-Proxy-Key`` → :func:`digillm.set_proxy_key` (the LiteLLM Bearer used
  on the default client path).
- ``X-BYOK-Key`` / ``X-BYOK-Provider`` / ``X-BYOK-Model`` → :func:`digillm.set_byok` for
  OpenAI, OpenRouter, Gemini, and Anthropic — the entries in :data:`_BYOK_BASE_URLS`.
  A key for any other provider is REFUSED with a 400 by ``byok_header_context`` in
  server.py: digigraph has no call path that would spend it, so accepting one meant
  answering on the operator's credentials while the user believed theirs was active
  (#1873). Non-OpenAI BYOK requires ``X-BYOK-Model`` so the spend path never falls
  through to the operator key with an ambiguous model id.

digigraph keeps its own ``(key, provider)`` BYOK contextvar so
:func:`get_byok_override` still reports the provider tag — digillm's ``get_byok``
only carries ``(api_key, base_url)``.

Header parsing lives here, not in digillm: digillm never imports FastAPI nor
accepts ``Request`` objects.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, NamedTuple  # score:allow untyped any — Starlette Request kept loose

from digillm import reset_byok, reset_proxy_key, set_byok, set_proxy_key

# BYOK speaks directly to the provider (bypassing the LiteLLM proxy).
_OPENAI_BYOK_BASE_URL = "https://api.openai.com/v1"
_OPENROUTER_BYOK_BASE_URL = "https://openrouter.ai/api/v1"
_GEMINI_BYOK_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_ANTHROPIC_BYOK_BASE_URL = "https://api.anthropic.com/v1/"

# The one table: a provider here is routed to its own endpoint with the user's key.
_BYOK_BASE_URLS: dict[str, str] = {
    "openai": _OPENAI_BYOK_BASE_URL,
    "openrouter": _OPENROUTER_BYOK_BASE_URL,
    "gemini": _GEMINI_BYOK_BASE_URL,
    "anthropic": _ANTHROPIC_BYOK_BASE_URL,
}
BYOK_ROUTABLE_PROVIDERS = tuple(_BYOK_BASE_URLS)
# Providers that require X-BYOK-Model (OpenAI may use the mode default).
BYOK_MODEL_REQUIRED_PROVIDERS = frozenset({"openrouter", "gemini", "anthropic"})


def byok_provider_supported(provider: str) -> bool:
    """True when a BYOK key for *provider* is actually spent on that provider."""
    return provider.strip().lower() in _BYOK_BASE_URLS


def byok_model_required(provider: str) -> bool:
    """True when *provider* must send ``X-BYOK-Model`` to spend the user key."""
    return provider.strip().lower() in BYOK_MODEL_REQUIRED_PROVIDERS


# digigraph's own per-request BYOK record: (api_key, provider) where provider is
# "openai" | "anthropic" | "openrouter" | "gemini". Distinct from digillm's
# (api_key, base_url) override so get_byok_override() can still report the provider.
# Never logged or persisted.
_byok_override: ContextVar[tuple[str, str] | None] = ContextVar("dg_byok_override", default=None)
# BYOK model slug from X-BYOK-Model (e.g. openai/gpt-4o-mini, gemini/…). Never logged.
_byok_model_override: ContextVar[str | None] = ContextVar("dg_byok_model_override", default=None)


def push_lite_llm_proxy_header(request: Any) -> object:
    """Parse ``X-LiteLLM-Proxy-Key`` → digillm proxy-key override; return a token for pop.

    Pass the returned token to :func:`pop_lite_llm_proxy` (typically in a
    ``finally`` block) to restore the previous value.
    """
    raw = request.headers.get("x-litellm-proxy-key")
    val = raw.strip() if raw else None
    return set_proxy_key(val)


def pop_lite_llm_proxy(token: object) -> None:
    """Restore the digillm proxy-key override saved by :func:`push_lite_llm_proxy_header`."""
    reset_proxy_key(token)


class _ByokToken(NamedTuple):
    """Reset tokens for the digigraph + digillm BYOK overrides (opaque to callers)."""

    dg: object
    model: object
    llm: object | None


def _normalize_byok_model_slug(raw: str, provider: str) -> str:
    trimmed = raw.strip()
    prefix = f"{provider}/"
    if trimmed.startswith(prefix):
        return trimmed[len(prefix) :]
    if provider == "openrouter" and trimmed.startswith("openrouter/"):
        return trimmed[len("openrouter/") :]
    return trimmed


def push_byok_header(request: Any) -> _ByokToken:
    """Parse ``X-BYOK-Key`` / ``X-BYOK-Provider`` / ``X-BYOK-Model`` and bind BYOK overrides.

    Sets digigraph's ``(key, provider)`` contextvar (for :func:`get_byok_override`)
    and, for routable providers, feeds digillm's BYOK override so the LLM
    client talks directly to the provider with the user key. Reaching this function
    with an unroutable provider no longer happens over HTTP: ``byok_header_context``
    in server.py refuses those with a 400 first (#1873).

    Returns an opaque token for :func:`pop_byok` (use in a ``finally`` block).
    """
    key = (request.headers.get("x-byok-key") or "").strip()
    provider = (request.headers.get("x-byok-provider") or "openai").strip().lower()
    model_raw = (request.headers.get("x-byok-model") or "").strip()
    model_slug = _normalize_byok_model_slug(model_raw, provider) if model_raw else ""
    val = (key, provider) if key else None
    dg_token = _byok_override.set(val)
    model_token = _byok_model_override.set(model_slug or None)
    llm_token: object | None = None
    if val is not None:
        base_url = _BYOK_BASE_URLS.get(provider)
        if base_url is not None:
            llm_token = set_byok(key, base_url)
    return _ByokToken(dg=dg_token, model=model_token, llm=llm_token)


def pop_byok(token: _ByokToken) -> None:
    """Restore both BYOK overrides saved by :func:`push_byok_header`."""
    if token.llm is not None:
        reset_byok(token.llm)
    _byok_model_override.reset(token.model)
    _byok_override.reset(token.dg)


def get_byok_override() -> tuple[str, str] | None:
    """Return the active per-request BYOK ``(api_key, provider)`` override, or ``None``."""
    return _byok_override.get()


def get_byok_model_override() -> str | None:
    """Return the active BYOK model slug from ``X-BYOK-Model``, or ``None``."""
    return _byok_model_override.get()
