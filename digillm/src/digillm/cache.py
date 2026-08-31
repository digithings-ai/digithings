"""In-process response cache for non-tool, non-BYOK completions."""

from __future__ import annotations

import hashlib
import json
import os
import time

from digillm.types import ChatCompletionMessage, JsonSchemaResponseFormat

_response_cache: dict[str, tuple[str, float]] = {}
_RESPONSE_CACHE_MAXSIZE = 256


def llm_cache_ttl() -> float:
    """Return the configured response-cache TTL in seconds."""
    try:
        return float(os.environ.get("DIGI_LLM_CACHE_TTL_SECONDS", "3600"))
    except ValueError:
        return 3600.0


def llm_cache_key(
    model: str,
    messages: list[ChatCompletionMessage],
    temperature: float,
    response_format: JsonSchemaResponseFormat | None,
    max_tokens: int | None,
) -> str:
    """Return a stable key including controls that can alter the serving model."""
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": response_format,
            "max_tokens": max_tokens,
            "cost_controls": [
                os.environ.get("OPENROUTER_FALLBACK_MODELS", ""),
                os.environ.get("OPENROUTER_SORT", ""),
                os.environ.get("OPENROUTER_MAX_PROMPT_PRICE", ""),
                os.environ.get("OPENROUTER_MAX_COMPLETION_PRICE", ""),
            ],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def llm_cache_get(key: str) -> str | None:
    """Return a non-expired cached response, if present."""
    entry = _response_cache.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.monotonic() > expires_at:
        del _response_cache[key]
        return None
    return value


def llm_cache_set(key: str, value: str) -> None:
    """Store a response, evicting the oldest entry at capacity."""
    if len(_response_cache) >= _RESPONSE_CACHE_MAXSIZE:
        del _response_cache[next(iter(_response_cache))]
    _response_cache[key] = (value, time.monotonic() + llm_cache_ttl())


def clear_response_cache() -> None:
    """Clear cached response values."""
    _response_cache.clear()
