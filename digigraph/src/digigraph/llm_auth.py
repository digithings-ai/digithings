"""Per-request LLM auth funnel for DigiGraph's FastAPI service.

Relocated from the former monolithic ``digigraph.llm`` (#632 P2). Parses the
per-request auth headers DigiChat/DigiKey forward and feeds digillm's
provider-agnostic override contextvars:

- ``X-LiteLLM-Proxy-Key`` → :func:`digillm.set_proxy_key` (the LiteLLM Bearer used
  on the default client path).
- ``X-BYOK-Key`` / ``X-BYOK-Provider`` → :func:`digillm.set_byok` for OpenAI BYOK
  (a direct api.openai.com client). Anthropic BYOK is intentionally *not* wired
  into the OpenAI client path — it falls through to the env-configured key,
  preserving the legacy behavior (DigiGraph has no Anthropic SDK call path yet).

DigiGraph keeps its own ``(key, provider)`` BYOK contextvar so
:func:`get_byok_override` still reports the provider tag — digillm's ``get_byok``
only carries ``(api_key, base_url)``.

Header parsing lives here, not in digillm: digillm never imports FastAPI nor
accepts ``Request`` objects.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, NamedTuple  # noqa: ANN401 — Starlette Request kept loose

from digillm import reset_byok, reset_proxy_key, set_byok, set_proxy_key

# OpenAI BYOK speaks directly to OpenAI (bypassing the LiteLLM proxy).
_OPENAI_BYOK_BASE_URL = "https://api.openai.com/v1"

# DigiGraph's own per-request BYOK record: (api_key, provider) where provider is
# "openai" | "anthropic". Distinct from digillm's (api_key, base_url) override so
# get_byok_override() can still report the provider. Never logged or persisted.
_byok_override: ContextVar[tuple[str, str] | None] = ContextVar("dg_byok_override", default=None)


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
    """Reset tokens for the DigiGraph + digillm BYOK overrides (opaque to callers)."""

    dg: object
    llm: object | None


def push_byok_header(request: Any) -> _ByokToken:
    """Parse ``X-BYOK-Key`` / ``X-BYOK-Provider`` and bind the per-request BYOK override.

    Sets DigiGraph's ``(key, provider)`` contextvar (for :func:`get_byok_override`)
    and, for the OpenAI provider, feeds digillm's BYOK override so the LLM client
    talks directly to api.openai.com with the user key. Anthropic keys are stored
    on DigiGraph's contextvar only (no OpenAI-client override) — they fall through
    to the env-configured credentials, as before.

    Returns an opaque token for :func:`pop_byok` (use in a ``finally`` block).
    """
    key = (request.headers.get("x-byok-key") or "").strip()
    provider = (request.headers.get("x-byok-provider") or "openai").strip().lower()
    val = (key, provider) if key else None
    dg_token = _byok_override.set(val)
    llm_token: object | None = None
    if val is not None and provider == "openai":
        llm_token = set_byok(key, _OPENAI_BYOK_BASE_URL)
    return _ByokToken(dg=dg_token, llm=llm_token)


def pop_byok(token: _ByokToken) -> None:
    """Restore both BYOK overrides saved by :func:`push_byok_header`."""
    if token.llm is not None:
        reset_byok(token.llm)
    _byok_override.reset(token.dg)


def get_byok_override() -> tuple[str, str] | None:
    """Return the active per-request BYOK ``(api_key, provider)`` override, or ``None``."""
    return _byok_override.get()
