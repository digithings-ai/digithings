"""Lightweight LLM client — provider routing, structured output, retry + caching.

Supports any OpenAI-compatible provider via the ``provider/model`` prefix convention:

    xai/grok-4.3-latest     → XAI_API_KEY    → https://api.x.ai/v1
    gemini/gemini-2.5-flash  → GEMINI_API_KEY → Google OpenAI-compat endpoint
    groq/llama-3.3-70b       → GROQ_API_KEY   → https://api.groq.com/openai/v1

Any model string without a known prefix is passed directly to the OpenAI client
configured via OPENAI_API_KEY + OPENAI_API_BASE (LiteLLM proxy, local Ollama, etc.).

Usage::

    from digibase.llm import chat_completion

    result = chat_completion(
        "xai/grok-4.3-latest",
        [{"role": "user", "content": "Hello"}],
    )

    # Structured output
    result = chat_completion(
        "gemini/gemini-2.5-flash",
        messages,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "MySchema", "schema": {...}, "strict": True},
        },
    )
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
from typing import Any, TypedDict

from openai import OpenAI

logger = logging.getLogger(__name__)


# ── Provider registry ─────────────────────────────────────────────────────────
# Maps the ``provider/`` prefix in a model string to its API endpoint and key.
# Add new providers here; no other code changes required.

_EXTERNAL_PROVIDERS: dict[str, dict[str, str]] = {
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "api_key_env": "XAI_API_KEY",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
    },
}

# ── Client cache ──────────────────────────────────────────────────────────────
# Keyed by provider name (for external providers) or (api_key, base_url) for
# the default client.  Reuses the underlying httpx connection pool.

_client_cache: dict[str | tuple[str, str | None], OpenAI] = {}

# ── Response cache ────────────────────────────────────────────────────────────
# SHA-256 keyed in-process cache for non-tool chat completions.

_llm_cache: dict[str, tuple[str, float]] = {}
_LLM_CACHE_MAXSIZE = 256


def _llm_cache_ttl() -> float:
    try:
        return float(os.environ.get("DIGI_LLM_CACHE_TTL_SECONDS", "3600"))
    except ValueError:
        return 3600.0


def _llm_cache_key(
    model: str,
    messages: list[ChatCompletionMessage],
    temperature: float,
    response_format: JsonSchemaResponseFormat | None,
    max_tokens: int | None,
) -> str:
    payload = json.dumps(
        {"model": model, "messages": messages, "temperature": temperature,
         "response_format": response_format, "max_tokens": max_tokens},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _llm_cache_get(key: str) -> str | None:
    entry = _llm_cache.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.monotonic() > expires_at:
        del _llm_cache[key]
        return None
    return value


def _llm_cache_set(key: str, value: str) -> None:
    if len(_llm_cache) >= _LLM_CACHE_MAXSIZE:
        del _llm_cache[next(iter(_llm_cache))]
    _llm_cache[key] = (value, time.monotonic() + _llm_cache_ttl())


# ── Type definitions ──────────────────────────────────────────────────────────

class ChatCompletionMessage(TypedDict, total=False):
    role: str
    content: str | list[dict[str, Any]] | None
    name: str
    tool_call_id: str


class JsonSchemaResponseFormat(TypedDict, total=False):
    type: str
    json_schema: dict[str, Any]


# ── Client helpers ────────────────────────────────────────────────────────────

def _parse_provider_prefix(model: str) -> tuple[str | None, str]:
    """Split ``provider/model_id`` into (provider, model_id) for registered providers."""
    if "/" in model:
        provider, _, model_id = model.partition("/")
        if provider in _EXTERNAL_PROVIDERS:
            return provider, model_id
    return None, model


def get_client_for_model(model: str) -> OpenAI:
    """Return a cached OpenAI client for the given model string.

    External-provider models (``xai/…``, ``gemini/…``, ``groq/…``) get a
    dedicated client pointing at the provider's API endpoint.  All other
    model strings fall back to the default client (``OPENAI_API_BASE`` /
    ``OPENAI_API_KEY`` — LiteLLM proxy, local Ollama, vanilla OpenAI).

    Raises ``RuntimeError`` when the required env var for an external provider
    is missing.
    """
    provider, _ = _parse_provider_prefix(model)
    if provider is None:
        # Default client: LiteLLM proxy / Ollama / bare OpenAI
        api_key = os.environ.get("OPENAI_API_KEY", "not-set")
        base_url = os.environ.get("OPENAI_API_BASE")
        cache_key: str | tuple[str, str | None] = (api_key, base_url)
        client = _client_cache.get(cache_key)
        if client is None:
            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url.rstrip("/")
            client = OpenAI(**kwargs)
            _client_cache[cache_key] = client
        return client

    cached = _client_cache.get(provider)
    if cached is not None:
        return cached
    cfg = _EXTERNAL_PROVIDERS[provider]
    api_key = os.environ.get(cfg["api_key_env"], "").strip()
    if not api_key:
        raise RuntimeError(
            f"Model {model!r} requires env var {cfg['api_key_env']} to be set."
        )
    client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    _client_cache[provider] = client
    return client


# ── Retry ─────────────────────────────────────────────────────────────────────

def _sleep_backoff(attempt: int, delay: float, *, max_delay: float = 300.0) -> float:
    jitter = random.uniform(0.0, delay * 0.25)
    time.sleep(delay + jitter)  # noqa: S110
    return min(delay * 2, max_delay)


def _create_with_retry(client: OpenAI, **kwargs: Any) -> Any:
    """Call ``client.chat.completions.create`` with exponential backoff on transient errors.

    Retries on 429, 5xx, connection errors, and timeouts.
    Non-transient errors (auth, bad request) propagate immediately.
    """
    from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
    transient = (RateLimitError, InternalServerError, APIConnectionError, APITimeoutError)
    max_attempts = 12
    delay = 5.0
    for attempt in range(max_attempts):
        try:
            return client.chat.completions.create(**kwargs)
        except transient as exc:
            if attempt >= max_attempts - 1:
                raise
            logger.warning(
                "%s (attempt %d/%d): backing off %.1fs",
                type(exc).__name__, attempt + 1, max_attempts, delay,
            )
            delay = _sleep_backoff(attempt, delay)
    raise RuntimeError("chat completion failed after all retry attempts")  # never reached


# ── Public API ────────────────────────────────────────────────────────────────

def chat_completion(
    model: str,
    messages: list[ChatCompletionMessage],
    *,
    temperature: float = 0.2,
    response_format: JsonSchemaResponseFormat | None = None,
    max_tokens: int | None = None,
) -> str:
    """Make a chat completion and return the response content string.

    Args:
        model:           Model string, optionally with a provider prefix
                         (e.g. ``"xai/grok-4.3-latest"``).
        messages:        OpenAI-style message list.
        temperature:     Sampling temperature (default 0.2).
        response_format: Structured output descriptor.  Supported on xAI,
                         Gemini (OpenAI-compat endpoint), and OpenAI.
        max_tokens:      Optional token cap.

    Returns:
        Response content string.
    """
    provider, model_id = _parse_provider_prefix(model)
    if provider is not None:
        cfg = _EXTERNAL_PROVIDERS[provider]
        if not os.environ.get(cfg["api_key_env"], "").strip():
            raise RuntimeError(
                f"Model {model!r} requires env var {cfg['api_key_env']} to be set."
            )
    client = get_client_for_model(model)
    effective_model = model_id if provider is not None else model

    cache_key = _llm_cache_key(effective_model, messages, temperature, response_format, max_tokens)
    cached = _llm_cache_get(cache_key)
    if cached is not None:
        logger.debug("LLM cache hit: model=%s key=%s…", effective_model, cache_key[:8])
        return cached

    kwargs: dict[str, Any] = {
        "model": effective_model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if response_format is not None:
        kwargs["response_format"] = response_format

    r = _create_with_retry(client, **kwargs)
    if not r.choices:
        return ""
    content = (r.choices[0].message.content or "").strip()
    if content:
        _llm_cache_set(cache_key, content)
    return content
