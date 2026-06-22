"""Provider-agnostic, OpenAI-compatible LLM client.

Extracted from the mature ``digigraph.llm`` implementation and made standalone:
no FastAPI, no digigraph, no digismith hard dependencies. Speaks to any
OpenAI-compatible endpoint (LiteLLM proxy, Ollama, OpenRouter, OpenAI direct,
or a registered external provider) and provides:

- :func:`completion` — single completion (optional tools and/or json_schema
  structured output); returns the OpenAI ``ChatCompletion`` object, with
  transparent SHA-256 response caching and retry/backoff on transient errors.
- :func:`get_client_for_model` — the single client entry point: routes a
  ``provider/model`` prefix to a registered provider client, otherwise the
  default ``OPENAI_API_BASE`` / ``OPENAI_API_KEY`` client. Honors per-request
  overrides set via the contextvar setters below.
- :func:`run_tools` — an agentic tool-calling loop (optional streaming).
- Per-request overrides via plain contextvars: :func:`set_proxy_key` /
  :func:`set_byok` (and the ``proxy_key`` / ``byok`` context managers).

The header parsing that feeds these contextvars lives in the consuming service
(e.g. digigraph's FastAPI middleware) — digillm never imports FastAPI nor
accepts ``Request`` objects.

Usage::

    from digillm import completion

    resp = completion(
        "openrouter/mistral/mistral-7b",
        [{"role": "user", "content": "Hello"}],
    )
    text = resp.choices[0].message.content
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import math
import os
import random
import re
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import ContextVar
from typing import Any, TypedDict  # noqa: ANN401 — OpenAI message dict payloads are heterogeneous

from openai import OpenAI
from openai.types.chat import ChatCompletion

logger = logging.getLogger(__name__)

# Optional tracing: degrade to a no-op decorator when digismith is not installed.
try:
    from digismith.trace import traceable as _traceable  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised only when digismith is absent

    def _traceable(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """No-op stand-in for ``digismith.trace.traceable`` when digismith is absent."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return decorator


# Cap tool result text injected into the next LLM turn (full blobs stay upstream).
_MAX_TOOL_MESSAGE_CHARS = int(os.environ.get("DIGI_TOOL_MESSAGE_MAX_CHARS", "12000"))


# ── Type definitions ────────────────────────────────────────────────────────


class ToolCallFunction(TypedDict, total=False):
    """Function block on an assistant ``tool_call``."""

    name: str
    arguments: str


class ToolCallDict(TypedDict, total=False):
    """OpenAI assistant ``tool_call`` entry."""

    id: str
    type: str
    function: ToolCallFunction


class ChatCompletionMessage(TypedDict, total=False):
    """OpenAI chat message shape for ``chat.completions.create``."""

    role: str
    content: str | list[dict[str, Any]] | None
    name: str
    tool_call_id: str
    tool_calls: list[ToolCallDict]


class ToolFunctionSpec(TypedDict, total=False):
    """Function spec inside a :class:`ToolDefinition`."""

    name: str
    description: str
    parameters: dict[str, Any]


class ToolDefinition(TypedDict, total=False):
    """A single tool exposed to the model."""

    type: str
    function: ToolFunctionSpec


class JsonSchemaResponseFormat(TypedDict, total=False):
    """OpenAI ``response_format`` descriptor for json_schema structured output."""

    type: str
    json_schema: dict[str, Any]


ToolArguments = dict[str, Any]


# ── Per-request overrides (contextvars) ──────────────────────────────────────
# These are plain contextvar setters. The consuming service parses request
# headers (e.g. ``X-LiteLLM-Proxy-Key``, ``X-BYOK-Key``/``X-BYOK-Base-URL``) and
# calls these — digillm itself never touches FastAPI/Request objects.

# Proxy-key override: forwards a per-request LiteLLM proxy / bearer token used on
# the default (non-prefixed) client path.
_proxy_key_override: ContextVar[str | None] = ContextVar("digillm_proxy_key_override", default=None)

# BYOK (bring-your-own-key) override: a per-request (api_key, base_url) pair.
# Never logged or persisted; the resulting client is never cached.
_byok_override: ContextVar[tuple[str, str] | None] = ContextVar(
    "digillm_byok_override", default=None
)


def set_proxy_key(token: str | None) -> object:
    """Set the per-request proxy/bearer key override; return a reset token.

    Pass the returned token to :func:`reset_proxy_key` (typically in a
    ``finally`` block) to restore the previous value.
    """
    val = token.strip() if token else None
    return _proxy_key_override.set(val)


def reset_proxy_key(token: object) -> None:
    """Restore the proxy-key override to the value before :func:`set_proxy_key`."""
    _proxy_key_override.reset(token)  # type: ignore[arg-type]


def get_proxy_key() -> str | None:
    """Return the active per-request proxy-key override, or ``None``."""
    return _proxy_key_override.get()


def set_byok(api_key: str, base_url: str = "https://api.openai.com/v1") -> object:
    """Set a per-request BYOK ``(api_key, base_url)`` override; return a reset token.

    The BYOK client is never cached (user credentials must not accumulate in
    process memory) and bypasses the response cache. Pass the returned token to
    :func:`reset_byok` to restore the previous value.
    """
    val: tuple[str, str] | None = (api_key, base_url) if api_key else None
    return _byok_override.set(val)


def reset_byok(token: object) -> None:
    """Restore the BYOK override to the value before :func:`set_byok`."""
    _byok_override.reset(token)  # type: ignore[arg-type]


def get_byok() -> tuple[str, str] | None:
    """Return the active per-request BYOK ``(api_key, base_url)`` override, or ``None``."""
    return _byok_override.get()


@contextlib.contextmanager
def proxy_key(token: str | None) -> Iterator[None]:
    """Context manager: set the proxy-key override for the duration of the block."""
    tok = set_proxy_key(token)
    try:
        yield
    finally:
        reset_proxy_key(tok)


@contextlib.contextmanager
def byok(api_key: str, base_url: str = "https://api.openai.com/v1") -> Iterator[None]:
    """Context manager: set the BYOK override for the duration of the block."""
    tok = set_byok(api_key, base_url)
    try:
        yield
    finally:
        reset_byok(tok)


# ── Provider registry ─────────────────────────────────────────────────────────
# Maps a ``provider/`` model prefix to its OpenAI-compatible base_url + the env
# var holding its API key. Add providers here; no other code changes required.

_EXTERNAL_PROVIDERS: dict[str, dict[str, str]] = {
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "api_key_env": "XAI_API_KEY",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    },
}


def register_provider(prefix: str, base_url: str, api_key_env: str) -> None:
    """Register (or override) an external provider routed by ``prefix/model``.

    Args:
        prefix:      The ``provider/`` prefix to match (e.g. ``"mistral"``).
        base_url:    OpenAI-compatible base URL for the provider.
        api_key_env: Environment variable name holding the provider API key.
    """
    _EXTERNAL_PROVIDERS[prefix] = {"base_url": base_url, "api_key_env": api_key_env}


# ── Client cache ──────────────────────────────────────────────────────────────
# Keyed by provider name (external providers) or ``(api_key, base_url)`` for the
# default client. Reuses the underlying httpx connection pool across requests.
# Automatically invalidated when env vars change (their values are in the key).

_client_cache: dict[str | tuple[str, str | None], OpenAI] = {}


def _parse_provider_prefix(model: str) -> tuple[str | None, str]:
    """Split ``provider/model_id`` into ``(provider, model_id)`` for registered providers.

    Returns ``(None, model)`` for any model string whose prefix is not a
    registered external provider (the default client handles it).
    """
    if "/" in model:
        provider, _, model_id = model.partition("/")
        if provider in _EXTERNAL_PROVIDERS:
            return provider, model_id
    return None, model


def _default_client_api_key() -> str:
    """Bearer token for the default (non-prefixed) client.

    Priority (highest first):
    1. Per-request proxy-key override (:func:`set_proxy_key`).
    2. ``LITELLM_PROXY_API_KEY`` env var.
    3. ``OPENAI_API_KEY`` env var (``"not-set"`` if unset).
    """
    override = _proxy_key_override.get()
    if override:
        return override
    proxy = (os.environ.get("LITELLM_PROXY_API_KEY") or "").strip()
    if proxy:
        return proxy
    return os.environ.get("OPENAI_API_KEY", "not-set")


def get_client() -> OpenAI:
    """Return an OpenAI client for the default (non-prefixed) path.

    When a BYOK override is active, returns an *uncached* client pointed at the
    BYOK ``base_url`` with the BYOK key — user credentials must never accumulate
    in process memory. Otherwise returns a client cached by
    ``(api_key, base_url)`` so the httpx connection pool is reused; the cache key
    embeds both env-derived values so the client is recreated automatically when
    either changes (e.g. in tests).
    """
    byok_override = _byok_override.get()
    if byok_override:
        api_key, base_url = byok_override
        return OpenAI(api_key=api_key, base_url=base_url)

    api_key = _default_client_api_key()
    base_url = os.environ.get("OPENAI_API_BASE")
    normalized_base = base_url.rstrip("/") if base_url else None
    # Key on the normalized base so http://h/v1 and http://h/v1/ reuse one client.
    cache_key: tuple[str, str | None] = (api_key, normalized_base)
    client = _client_cache.get(cache_key)
    if client is None:
        kwargs: dict[str, Any] = {"api_key": api_key}
        if normalized_base:
            kwargs["base_url"] = normalized_base
        client = OpenAI(**kwargs)
        _client_cache[cache_key] = client
    return client


def get_client_for_model(model: str) -> OpenAI:
    """Return the OpenAI client for ``model`` (the single public client entry point).

    A ``provider/model_id`` prefix matching a registered external provider
    (``xai/``, ``gemini/``, ``openrouter/``, plus any added via
    :func:`register_provider`) yields a dedicated, cached client pointed at that
    provider's endpoint. Every other model string falls back to
    :func:`get_client` (the ``OPENAI_API_BASE`` / ``OPENAI_API_KEY`` path, which
    also honors the proxy-key and BYOK overrides).

    Raises:
        RuntimeError: when a registered provider's API key env var is unset.
    """
    provider, _ = _parse_provider_prefix(model)
    if provider is None:
        return get_client()
    cfg = _EXTERNAL_PROVIDERS[provider]
    api_key = os.environ.get(cfg["api_key_env"], "").strip()
    if not api_key:
        raise RuntimeError(f"Model {model!r} requires env var {cfg['api_key_env']} to be set.")
    # Key by (provider, api_key) so a rotated/changed key rebuilds the client,
    # honoring the env-change invalidation the cache promises.
    cache_key = (provider, api_key)
    cached = _client_cache.get(cache_key)
    if cached is not None:
        return cached
    client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    _client_cache[cache_key] = client
    return client


# ── Response cache ────────────────────────────────────────────────────────────
# SHA-256 keyed in-process cache for non-tool, non-BYOK chat completions.
# TTL configurable via DIGI_LLM_CACHE_TTL_SECONDS (default: 3600s).

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
    """Return a stable SHA-256 cache key for the given completion parameters.

    The OpenRouter cost-control env (allowlist + sort + price ceiling) is folded in: it changes
    which model actually serves the request, so a response cached under one routing regime must
    not be returned after those settings change.
    """
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
    # Evict oldest entry when at capacity (simple FIFO approximation).
    if len(_llm_cache) >= _LLM_CACHE_MAXSIZE:
        del _llm_cache[next(iter(_llm_cache))]
    _llm_cache[key] = (value, time.monotonic() + _llm_cache_ttl())


def clear_caches() -> None:
    """Clear the response cache and the client cache (primarily for tests)."""
    _llm_cache.clear()
    _client_cache.clear()


# ── Usage observer ──────────────────────────────────────────────────────────────
# digillm stays a leaf library (no digigraph/service imports), so it can't write into
# a consumer's per-run usage accumulator directly. Instead the consuming app registers
# an observer here; digillm calls it after each completion / grounding call. No-op
# until registered, and observer errors never break the LLM call.

_usage_observer: Callable[..., None] | None = None


def set_usage_observer(observer: Callable[..., None] | None) -> None:
    """Register a telemetry sink called after each completion / web_search / x_search.

    The observer is invoked with keyword fields: ``kind`` ("chat" | "web_search" |
    "x_search"), ``model``, and per-kind ``prompt_tokens`` / ``completion_tokens`` /
    ``sources`` / ``ok``. Pass ``None`` to disable. Observer errors are swallowed.
    """
    global _usage_observer
    _usage_observer = observer


def _record_usage(**fields: Any) -> None:
    """Forward a usage record to the registered observer (no-op / swallow if none)."""
    observer = _usage_observer
    if observer is None:
        return
    try:
        observer(**fields)
    except Exception as exc:  # noqa: BLE001 — telemetry must never break the LLM call
        logger.debug("usage observer raised: %s", exc)


# ── Tool-argument normalization ───────────────────────────────────────────────


def _normalize_tool_arguments(args_str: str | None) -> str:
    """Return a valid JSON string for tool-call arguments.

    Some models stream invalid JSON (incomplete, trailing comma). Falls back to
    ``"{}"`` when the value cannot be repaired.
    """
    s = (args_str or "").strip()
    if not s:
        return "{}"
    try:
        json.loads(s)
        return s
    except json.JSONDecodeError:
        pass
    fixed = s.rstrip()
    if fixed and not fixed.endswith("}"):
        fixed = fixed[:-1] + "}" if fixed.endswith(",") else fixed + "}"
    try:
        json.loads(fixed)
        return fixed
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r",\s*}", "}", fixed)
    fixed = re.sub(r",\s*]", "]", fixed)
    try:
        json.loads(fixed)
        return fixed
    except json.JSONDecodeError:
        return "{}"


def _compact_tool_message_content(msg_content: str) -> str:
    """Truncate oversized tool-result text before injecting it into the next turn."""
    if len(msg_content) <= _MAX_TOOL_MESSAGE_CHARS:
        return msg_content
    return (
        msg_content[: _MAX_TOOL_MESSAGE_CHARS - 80].rstrip()
        + "\n...[truncated for LLM context; full tool payload retained upstream]"
    )


# ── Retry ─────────────────────────────────────────────────────────────────────


def _sleep_transient_retry(delay: float, *, max_delay: float = 300.0) -> float:
    """Sleep ``delay`` plus up to 25% jitter; return the next (doubled, capped) delay."""
    jitter = random.uniform(0.0, delay * 0.25)
    time.sleep(delay + jitter)  # noqa: S110 — intentional blocking backoff
    return min(delay * 2, max_delay)


def _create_with_retry(client: OpenAI, **kwargs: Any) -> Any:
    """Call ``client.chat.completions.create`` with backoff on transient errors.

    Retries on ``RateLimitError`` (429), ``InternalServerError`` (5xx),
    ``APIConnectionError`` (TCP/DNS/proxy blips) and ``APITimeoutError``. Other
    exceptions (auth, bad-request) propagate immediately. Backoff starts at 5s,
    doubles per attempt, caps at 300s, with up to 25% jitter to avoid
    thundering-herd retries; ~12 attempts ≈ a 30-minute budget.
    """
    from openai import (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )

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
                "%s (attempt %d/%d): backing off %.1fs before retry",
                type(exc).__name__,
                attempt + 1,
                max_attempts,
                delay,
            )
            delay = _sleep_transient_retry(delay)
    raise RuntimeError("chat completion failed after all retry attempts")  # pragma: no cover


# Empty-response self-heal: a 200-OK with no usable output (empty ``choices`` / blank
# content and no tool_calls) is a transient provider hiccup — the one that aborted the
# #726 baseline. Under the 25-analyst fan-out with OPENROUTER_COST_QUALITY_TRADEOFF=10
# (all-cheapest routing), empty completions became a storm (#814). Defaults raised:
#   DIGILLM_EMPTY_RETRY_MAX     2 → 4  (more healing attempts before giving up)
#   DIGILLM_EMPTY_RETRY_BACKOFF 2s → 5s  (longer pause lets the provider recover)
# If still empty after all retries, the response is returned unchanged (callers stay
# graceful: completion_text → "" and the node/chain fail-soft handles a persistent blank).
#
# DIGILLM_EMPTY_RETRY_DELAY is accepted as a back-compat alias for DIGILLM_EMPTY_RETRY_BACKOFF
# (avoids a breaking change for operators who pinned the old name; new name wins if both set).
_EMPTY_RETRY_MAX = int(os.environ.get("DIGILLM_EMPTY_RETRY_MAX", "4") or 4)
_backoff_raw = (
    os.environ.get("DIGILLM_EMPTY_RETRY_BACKOFF", "").strip()
    or os.environ.get("DIGILLM_EMPTY_RETRY_DELAY", "").strip()
    or "5.0"
)
_EMPTY_RETRY_DELAY = float(_backoff_raw)

# Valid OpenRouter provider.sort values; an unknown value 400s (not transient), so we drop it.
_OPENROUTER_SORTS = ("price", "throughput", "latency")


def _is_empty_completion(resp: Any) -> bool:
    """A completion with no usable output: no choices, or blank content AND no tool_calls."""
    choices = getattr(resp, "choices", None)
    if not choices:
        return True
    message = getattr(choices[0], "message", None)
    content = (getattr(message, "content", None) or "").strip()
    tool_calls = getattr(message, "tool_calls", None)
    return not content and not tool_calls


def _openrouter_usage_cost(usage: Any) -> float:
    """Actual USD charged for a call, from OpenRouter's ``usage.cost`` (always present on its
    responses). The OpenAI SDK is typed for OpenAI's schema, so an unknown ``cost`` field lands
    in pydantic ``model_extra`` rather than a typed attribute — check both. Returns 0.0 for any
    provider/SDK that doesn't surface it, so non-OpenRouter calls record no cost."""
    if usage is None:
        return 0.0
    cost = getattr(usage, "cost", None)
    if cost is None:
        extra = getattr(usage, "model_extra", None)
        if isinstance(extra, dict):
            cost = extra.get("cost")
    if cost is None:
        return 0.0
    try:
        value = float(cost)
    except (TypeError, ValueError):
        return 0.0
    # float() also accepts 'nan'/'inf'/negatives; a bad cost must not poison run-level
    # aggregation (one nan turns the whole run's cost_usd into nan). Clamp to a sane 0.0.
    return value if math.isfinite(value) and value >= 0 else 0.0


def _openrouter_fallback_models() -> list[str]:
    """``OPENROUTER_FALLBACK_MODELS`` (comma-separated) — the cheap-model allowlist OpenRouter
    routes/falls-back across (keeps automatic selection, but only among affordable models)."""
    raw = os.environ.get("OPENROUTER_FALLBACK_MODELS", "").strip()
    return [m.strip() for m in raw.split(",") if m.strip()]


def _openrouter_provider_prefs() -> dict[str, Any]:
    """OpenRouter ``provider`` routing preferences from env (all opt-in; empty when unset):

    - ``OPENROUTER_SORT`` → ``provider.sort`` (e.g. ``price`` routes to the cheapest endpoint).
    - ``OPENROUTER_MAX_PROMPT_PRICE`` / ``OPENROUTER_MAX_COMPLETION_PRICE`` (USD per 1M tokens)
      → ``provider.max_price``, a hard ceiling that structurally excludes flagship-tier models
      *by price* without naming them — the requested "exclude expensive, keep auto" control.
    """
    prefs: dict[str, Any] = {}
    sort = os.environ.get("OPENROUTER_SORT", "").strip()
    if sort:
        # OpenRouter accepts a fixed sort enum; an invalid value would 400 (not a transient/410
        # error, so it would crash the call). Drop an unknown value with a warning instead.
        if sort in _OPENROUTER_SORTS:
            prefs["sort"] = sort
        else:
            logger.warning(
                "ignoring invalid OPENROUTER_SORT=%r (allowed: %s)", sort, _OPENROUTER_SORTS
            )
    max_price: dict[str, float] = {}
    for key, env_name in (
        ("prompt", "OPENROUTER_MAX_PROMPT_PRICE"),
        ("completion", "OPENROUTER_MAX_COMPLETION_PRICE"),
    ):
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            logger.warning("ignoring non-numeric %s=%r", env_name, raw)
            continue
        # float() also accepts 'inf'/'nan'/negatives; a price ceiling must be finite and > 0.
        if not math.isfinite(value) or value <= 0:
            logger.warning("ignoring out-of-range %s=%r (need a finite price > 0)", env_name, raw)
            continue
        max_price[key] = value
    if max_price:
        prefs["max_price"] = max_price
    return prefs


def _openrouter_require_parameters() -> bool:
    """Default-ON: ask OpenRouter to route ONLY to providers that actually support the
    parameters this request sends (``response_format`` json_schema, ``tools``).

    Without ``provider.require_parameters``, the Auto Router can select a provider/model that
    silently DROPS an unsupported param (e.g. a tiny model that ignores json_schema) and
    returns an EMPTY body — which is exactly how the pipeline degraded after the #717
    auto-router migration (every structured-output / tool call came back empty). Setting it
    true makes OpenRouter skip those providers and pick a capable one (still the cheapest
    capable one under any ``max_price`` ceiling). Disable with ``OPENROUTER_REQUIRE_PARAMETERS=0``."""
    return os.environ.get("OPENROUTER_REQUIRE_PARAMETERS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "",
    )


def _openrouter_allowed_models() -> list[str]:
    """``OPENROUTER_ALLOWED_MODELS`` (comma-separated) — the Auto Router's candidate pool.

    Constrains ``openrouter/auto`` to select ONLY from this curated set of reasoning +
    structured-output-capable models (exact slugs and/or ``provider/*`` wildcards), via the
    OpenRouter ``auto-router`` plugin. This keeps per-prompt auto-selection but fences out
    models that don't honor strict structured outputs (e.g. ``google/gemini-2.5-flash-lite``,
    which the bare Auto Router kept picking → loose/empty JSON, #802). Empty = unconstrained."""
    raw = os.environ.get("OPENROUTER_ALLOWED_MODELS", "").strip()
    return [m.strip() for m in raw.split(",") if m.strip()]


def _openrouter_cost_quality_tradeoff() -> int | None:
    """``OPENROUTER_COST_QUALITY_TRADEOFF`` — the Auto Router plugin's 0-10 dial (0 = always the
    most capable model, 10 = cheapest; OpenRouter default 7). Returns None (use the default) when
    unset or out of range."""
    raw = os.environ.get("OPENROUTER_COST_QUALITY_TRADEOFF", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        logger.warning("ignoring non-integer OPENROUTER_COST_QUALITY_TRADEOFF=%r", raw)
        return None
    if not 0 <= value <= 10:
        logger.warning("ignoring out-of-range OPENROUTER_COST_QUALITY_TRADEOFF=%r (need 0-10)", raw)
        return None
    return value


def _uses_openrouter_server_tools(tools: list[Any] | None) -> bool:
    """True when every tool is an OpenRouter server tool (``openrouter:*``).

    Server tools (e.g. ``openrouter:web_search``) are executed by OpenRouter, not the
    underlying model provider. ``provider.require_parameters`` must NOT be set for those
    requests — it filters to providers that declare support for the tool param, which
    excludes all providers for server tools → HTTP 404 "Server tool request failed".
    """
    if not tools:
        return False
    for tool in tools:
        ttype = tool.get("type", "") if isinstance(tool, dict) else getattr(tool, "type", "")
        if not (isinstance(ttype, str) and ttype.startswith("openrouter:")):
            return False
    return True


def _with_openrouter_cost_controls(kwargs: dict[str, Any], provider: str | None) -> dict[str, Any]:
    """Merge OpenRouter routing controls into ``extra_body`` for an ``openrouter/`` request:

    - ``provider.require_parameters`` (default ON) — only route to providers that support the
      request's params (response_format / tools), so the Auto Router never lands on a provider
      that drops them and returns an empty body (the post-#717 failure mode). FORCED ON for any
      request that actually carries ``response_format`` or ``tools``, regardless of the global
      ``OPENROUTER_REQUIRE_PARAMETERS`` toggle: the toggle exists to allow plain-prose requests
      onto cheaper providers that ignore harmless extra params, but a structured-output / tool
      request that lands on a provider which drops the param comes back EMPTY — an operator must
      not be able to footgun that off. (OpenRouter structured-outputs docs pair ``strict:true``
      with ``require_parameters`` to keep routing on capable providers.) SKIPPED when the Auto
      Router pool is constrained (below): the curated pool is the capability guarantee, and
      applying both filters compounds to an empty set → 404 (#802).
    - the Auto Router candidate pool (``OPENROUTER_ALLOWED_MODELS`` → ``plugins[auto-router]
      .allowed_models``, with optional ``cost_quality_tradeoff``) — keeps ``openrouter/auto``'s
      per-prompt selection but constrains it to a curated set of reasoning + structured-output
      capable models, so it stops landing on incapable models like gemini-2.5-flash-lite (#802).
      Only applied to ``openrouter/auto`` requests (the plugin is meaningless on a pinned model).
    - a cheap-model allowlist with fallback routing (``OPENROUTER_FALLBACK_MODELS`` →
      ``models`` + ``route=fallback``), price-sorted endpoints, and an optional hard price
      ceiling (``provider.max_price``) — keeps automatic selection but bounds it to affordable
      models (flagships excluded by price, not by name).

    No-op for non-OpenRouter providers and when nothing (incl. require_parameters) is active.
    Merges with (never clobbers) an existing ``extra_body`` (e.g. the xAI ``search_parameters``
    branch)."""
    if provider != "openrouter":
        return kwargs
    fallbacks = _openrouter_fallback_models()
    prefs = _openrouter_provider_prefs()
    allowed_models = _openrouter_allowed_models()
    # Constrain the Auto Router to a curated capable pool only for the auto router itself.
    constrain_auto = bool(allowed_models) and (kwargs.get("model") or "").endswith("/auto")
    # Structured-output (json_schema) and tool requests empty-fail without require_parameters, so
    # force it for them even when the global toggle is off; plain-prose requests honor the toggle.
    tools = kwargs.get("tools")
    server_tools_only = _uses_openrouter_server_tools(tools)
    structured = kwargs.get("response_format") is not None or (
        bool(tools) and not server_tools_only
    )
    # allowed_models SUPERSEDES require_parameters: the curated pool is already the capability
    # guarantee, and applying BOTH filters compounds to an empty set → OpenRouter 404
    # "No models match your request and model restrictions" (#802). So when we constrain the auto
    # router, drop require_parameters; otherwise keep the #798 behavior (forced for structured/tool).
    require_params = (
        (not constrain_auto)
        and (not server_tools_only)
        and (_openrouter_require_parameters() or structured)
    )
    if not fallbacks and not prefs and not require_params and not constrain_auto:
        return kwargs
    merged = dict(kwargs)
    extra = dict(merged.get("extra_body") or {})
    if fallbacks:
        extra["models"] = fallbacks
        extra["route"] = "fallback"
    # Auto Router candidate-pool constraint — only meaningful for the auto router itself.
    if constrain_auto:
        plugin: dict[str, Any] = {"id": "auto-router", "allowed_models": allowed_models}
        tradeoff = _openrouter_cost_quality_tradeoff()
        if tradeoff is not None:
            plugin["cost_quality_tradeoff"] = tradeoff
        # Replace any prior auto-router plugin, preserve other plugins (e.g. web search).
        others = [p for p in (extra.get("plugins") or []) if p.get("id") != "auto-router"]
        extra["plugins"] = [*others, plugin]
    provider_prefs = {**(extra.get("provider") or {})}
    if require_params:
        provider_prefs["require_parameters"] = True
    for key, value in prefs.items():
        # Deep-merge the nested max_price dict so a caller-set ceiling key (e.g. only
        # ``completion``) survives when env sets the other (``prompt``), rather than the
        # whole sub-dict being overwritten.
        if key == "max_price" and isinstance(provider_prefs.get("max_price"), dict):
            provider_prefs["max_price"] = {**provider_prefs["max_price"], **value}
        else:
            provider_prefs[key] = value
    if provider_prefs:
        extra["provider"] = provider_prefs
    merged["extra_body"] = extra
    return merged


# Back-compat alias: the empty-retry path historically called the fallback-only form.
_with_openrouter_fallback = _with_openrouter_cost_controls


# ── Public API: chat_completion ────────────────────────────────────────────────


@_traceable("completion")
def completion(
    model: str,
    messages: list[ChatCompletionMessage],
    *,
    temperature: float = 0.2,
    tools: list[ToolDefinition] | None = None,
    tool_choice: str | ToolArguments = "auto",
    response_format: JsonSchemaResponseFormat | None = None,
    max_tokens: int | None = None,
    search_parameters: dict[str, Any] | None = None,
    usage_kind: str = "chat",
) -> ChatCompletion:
    """Single chat completion — mirrors ``litellm.completion`` / OpenAI's ``chat.completions.create``.

    The model string is used as given: a registered ``provider/model_id`` prefix
    routes to that provider (and the bare ``model_id`` is sent on the wire);
    every other string is passed through unchanged to the default client. No
    hidden env/YAML model substitution happens here — use :func:`resolve_model`
    explicitly if you want mode-based selection.

    Behavior:
    - Returns the OpenAI ``ChatCompletion`` object — read
      ``resp.choices[0].message.content`` and ``.tool_calls``.
    - Tool-free, non-BYOK requests are cached by a SHA-256 key of the request
      parameters (the serialized response is stored and rehydrated on a hit, so
      the return type is always a ``ChatCompletion``). ``tools`` requests are
      never cached (they may have side effects).
    - ``response_format``: OpenAI-compatible json_schema structured-output
      descriptor, e.g. ``{"type": "json_schema", "json_schema": {"name": ...,
      "schema": {...}}}``. Mutually exclusive with ``tools`` (ignored when
      ``tools`` is non-empty). Providers without json_schema support silently
      ignore it, so an in-prompt schema remains the primary contract there.

    Raises:
        RuntimeError: when a registered provider's API key env var is unset.
    """
    provider, model_id = _parse_provider_prefix(model)
    client = get_client_for_model(model)
    effective_model = model_id if provider is not None else model

    # xAI Live Search rides the OpenAI-compatible client via ``extra_body`` and only
    # when the real xAI client is active (reaching here for an ``xai/`` model means its
    # key was set — get_client_for_model raises otherwise). It is time-sensitive and not
    # captured by the cache key, so a search request bypasses the cache like tool calls.
    xai_live_search = search_parameters is not None and provider == "xai"

    # Cache only tool-free, search-free, non-BYOK requests (BYOK keys must not pollute or
    # read the shared in-process cache; tool calls / live search may have side effects).
    cache_key: str | None = None
    if not tools and not xai_live_search and _byok_override.get() is None:
        cache_key = _llm_cache_key(
            effective_model, messages, temperature, response_format, max_tokens
        )
        cached = _llm_cache_get(cache_key)
        if cached is not None:
            logger.debug("LLM cache hit: model=%s key=%s…", effective_model, cache_key[:8])
            return ChatCompletion.model_validate_json(cached)

    kwargs: dict[str, Any] = {
        "model": effective_model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
    elif response_format is not None:
        # tools and response_format are mutually exclusive in the OpenAI API.
        kwargs["response_format"] = response_format
    if xai_live_search:
        kwargs["extra_body"] = {"search_parameters": search_parameters}
    elif search_parameters is not None:
        logger.debug("search_parameters ignored for non-xAI model %s", effective_model)

    # Bound OpenRouter's automatic selection to affordable models on the PRIMARY request
    # (cheap-model allowlist + price ceiling); a no-op unless the OPENROUTER_* env is set.
    kwargs = _with_openrouter_cost_controls(kwargs, provider)

    try:
        r: ChatCompletion = _create_with_retry(client, **kwargs)
    except Exception as exc:  # noqa: BLE001 — only the 410 case is soft; everything else re-raises
        # xAI deprecated Live Search (HTTP 410) in favour of the Agent Tools API
        # (:func:`web_search`). Fail soft: drop the deprecated extra_body and retry once
        # ungrounded so the phase/pipeline keeps producing instead of crashing.
        if getattr(exc, "status_code", None) == 410 and "extra_body" in kwargs:
            logger.warning(
                "xAI rejected search_parameters (410 deprecated); retrying without Live Search"
            )
            kwargs.pop("extra_body", None)
            r = _create_with_retry(client, **kwargs)
        else:
            raise

    # Empty-response self-heal. An empty body is transient; retry with backoff. The first
    # retry also adds OpenRouter provider-fallback routing for openrouter/ models (a flaky
    # primary is swapped out); other providers just re-ask the same model. A persistent
    # blank falls through unchanged so downstream stays graceful (no crash).
    empty_attempts = 0
    while _is_empty_completion(r) and empty_attempts < _EMPTY_RETRY_MAX:
        empty_attempts += 1
        retry_kwargs = (
            _with_openrouter_fallback(kwargs, provider) if empty_attempts == 1 else kwargs
        )
        logger.warning(
            "empty completion from %s (empty-retry %d/%d); backing off %.1fs",
            effective_model,
            empty_attempts,
            _EMPTY_RETRY_MAX,
            _EMPTY_RETRY_DELAY,
        )
        time.sleep(_EMPTY_RETRY_DELAY)  # noqa: S110 — intentional short backoff on empty
        r = _create_with_retry(client, **retry_kwargs)

    _u = getattr(r, "usage", None)
    _cached_tokens = getattr(getattr(_u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    _record_usage(
        kind=usage_kind,
        # Record the model OpenRouter actually served (``r.model``), not the request string
        # ("auto" / the allowlist), so cost telemetry reflects what was really billed.
        model=getattr(r, "model", None) or effective_model,
        prompt_tokens=getattr(_u, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(_u, "completion_tokens", 0) or 0,
        cached_tokens=_cached_tokens,
        # Actual USD charged. OpenRouter always includes ``usage.cost`` on its responses
        # (usage accounting is on by default); the OpenAI SDK keeps unknown fields in
        # ``model_extra``. Other providers don't report it → 0.0.
        cost=_openrouter_usage_cost(_u),
    )
    # Cache the serialized response (tool-free, non-BYOK, non-empty content) so a
    # future hit rehydrates a ChatCompletion — keeping the return type consistent.
    if cache_key is not None and r.choices and (r.choices[0].message.content or "").strip():
        _llm_cache_set(cache_key, r.model_dump_json())
    return r


# Inline ``(url)`` / ``[text](url)`` citations in grounding summaries.
_INLINE_URL_RE = re.compile(r"\((https?://[^\s)]+)\)")
_MD_LINK_URL_RE = re.compile(r"\[[^\]]*\]\((https?://[^\s)]+)\)")


def _urls_from_grounding_text(text: str) -> list[str]:
    urls: list[str] = []
    for pat in (_MD_LINK_URL_RE, _INLINE_URL_RE):
        for url in pat.findall(text):
            if url not in urls:
                urls.append(url)
    return urls


def openrouter_web_search(
    model: str,
    query: str,
    *,
    allowed_domains: list[str] | None = None,
    max_results: int = 8,
    engine: str = "exa",
) -> tuple[str, list[str]] | None:
    """Run OpenRouter web search grounding and return ``(summary_text, source_urls)``.

    ``:online`` models and native-search providers (``perplexity/*``) use built-in web
    search via a plain completion. Other models fall back to the server-side
    ``openrouter:web_search`` tool (Exa by default).

    Returns ``None`` when the model isn't OpenRouter, ``OPENROUTER_API_KEY`` is
    unset, or the call fails (fail-soft).
    """
    provider, model_id = _parse_provider_prefix(model)
    if provider != "openrouter":
        logger.debug("openrouter_web_search skipped: %s is not an OpenRouter model", model)
        return None
    if not os.environ.get(_EXTERNAL_PROVIDERS["openrouter"]["api_key_env"], "").strip():
        logger.debug("openrouter_web_search skipped: OPENROUTER_API_KEY not set")
        return None

    messages: list[ChatCompletionMessage] = [
        {
            "role": "system",
            "content": (
                "You are a market-research assistant. Use web search to gather current "
                "facts, then reply with concise bullet points and inline markdown citations "
                "linking each claim to its source URL."
            ),
        },
        {"role": "user", "content": query},
    ]
    try:
        # ``:online`` and native-search (perplexity) models use built-in web search —
        # do NOT attach ``openrouter:web_search`` (404 on endpoints that lack the tool).
        if ":online" in model_id or model_id.startswith("perplexity/"):
            resp = completion(
                model,
                messages,
                temperature=0.2,
                usage_kind="web_search",
            )
        else:
            tool_params: dict[str, Any] = {
                "engine": engine,
                "max_results": max(1, min(max_results, 25)),
                "search_context_size": "medium",
            }
            if allowed_domains:
                tool_params["allowed_domains"] = list(allowed_domains)
            tools: list[dict[str, Any]] = [
                {"type": "openrouter:web_search", "parameters": tool_params}
            ]
            resp = completion(
                model,
                messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
                usage_kind="web_search",
            )
    except Exception as exc:  # noqa: BLE001 — grounding is best-effort; degrade gracefully
        logger.warning("openrouter_web_search failed (%s); continuing ungrounded", exc)
        _record_usage(kind="web_search", model=model_id, ok=False)
        return None

    if not resp.choices:
        return None
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        return None
    return text, _urls_from_grounding_text(text)


def web_search(
    model: str,
    query: str,
    *,
    allowed_domains: list[str] | None = None,
    max_results: int = 8,
) -> tuple[str, list[str]] | None:
    """Run an xAI Agent-Tools ``web_search`` via the Responses API and return grounding.

    Returns ``(summary_text, source_urls)`` where ``summary_text`` is the model's cited
    summary (inline ``[[n]](url)`` citations) and ``source_urls`` are the URLs the search
    surfaced. xAI-only — returns ``None`` for non-xAI models (or when ``XAI_API_KEY`` is
    unset), and fails soft (``None``) on any API error so callers degrade to ungrounded
    research rather than crash.

    A read-only grounding *pre-pass*: callers inject the returned summary into their prompt,
    then run their normal completion. Replaces the deprecated chat-completions
    ``search_parameters`` Live Search (HTTP 410).
    """
    provider, model_id = _parse_provider_prefix(model)
    if provider != "xai":
        logger.debug("web_search skipped: %s is not an xAI model", model)
        return None
    api_key = os.environ.get(_EXTERNAL_PROVIDERS["xai"]["api_key_env"], "").strip()
    if not api_key:
        logger.debug("web_search skipped: XAI_API_KEY not set")
        return None
    tool: dict[str, Any] = {"type": "web_search", "max_search_results": max_results}
    if allowed_domains:
        tool["filters"] = {"allowed_domains": list(allowed_domains)}
    try:
        client = get_client_for_model(model)
        resp = client.responses.create(
            model=model_id,
            input=[{"role": "user", "content": query}],
            tools=[tool],
        )
    except Exception as exc:  # noqa: BLE001 — grounding is best-effort; degrade gracefully
        logger.warning("web_search failed (%s); continuing ungrounded", exc)
        _record_usage(kind="web_search", model=model_id, ok=False)
        return None
    text = getattr(resp, "output_text", "") or ""
    sources: list[str] = []
    for item in getattr(resp, "output", None) or []:
        action = getattr(item, "action", None)
        srcs = getattr(action, "sources", None) if action is not None else None
        for s in srcs or []:
            url = getattr(s, "url", None) or (s.get("url") if isinstance(s, dict) else None)
            if url and url not in sources:
                sources.append(url)
    _record_usage(kind="web_search", model=model_id, sources=len(sources), ok=True)
    return text, sources


def x_search(
    model: str,
    query: str,
    *,
    max_results: int = 12,
) -> tuple[str, list[str]] | None:
    """Run an xAI Agent-Tools ``x_search`` (X / Twitter) via the Responses API.

    Returns ``(summary_text, source_urls)``. Unlike :func:`web_search`, x_search carries
    citations **inline** in ``output_text`` as ``[[n]](url)`` (its ``output[]`` items are
    ``custom_tool_call``, not ``action.sources``), so URLs are regex-extracted from the
    text. xAI-only; returns ``None`` for non-xAI models / unset key, and fails soft
    (``None``) on any API error.
    """
    provider, model_id = _parse_provider_prefix(model)
    if provider != "xai":
        logger.debug("x_search skipped: %s is not an xAI model", model)
        return None
    if not os.environ.get(_EXTERNAL_PROVIDERS["xai"]["api_key_env"], "").strip():
        logger.debug("x_search skipped: XAI_API_KEY not set")
        return None
    try:
        client = get_client_for_model(model)
        resp = client.responses.create(
            model=model_id,
            input=[{"role": "user", "content": query}],
            tools=[{"type": "x_search", "max_search_results": max_results}],
        )
    except Exception as exc:  # noqa: BLE001 — grounding is best-effort; degrade gracefully
        logger.warning("x_search failed (%s); continuing ungrounded", exc)
        _record_usage(kind="x_search", model=model_id, ok=False)
        return None
    text = getattr(resp, "output_text", "") or ""
    sources = _urls_from_grounding_text(text)
    _record_usage(kind="x_search", model=model_id, sources=len(sources), ok=True)
    return text, sources


# ── Public API: tool-calling loop ───────────────────────────────────────────────


def _extract_tool_call(tc: ToolCallDict) -> tuple[str, str]:
    """Return ``(name, raw_arguments_str)`` from a tool-call dict."""
    fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
    if isinstance(fn, dict):
        return fn.get("name", ""), fn.get("arguments", "{}")
    name = getattr(fn, "name", "") if fn else ""
    args = getattr(fn, "arguments", "{}") if fn else "{}"
    return name, args


def _message_from_response(resp: ChatCompletion) -> tuple[str, list[ToolCallDict] | None]:
    """Extract ``(content, tool_calls)`` from a :func:`completion` response.

    Adapts the ``ChatCompletion`` object that :func:`completion` now returns into
    the ``(content, tool_calls|None)`` shape the tool loop consumes.
    """
    if not resp.choices:
        return "", None
    msg = resp.choices[0].message
    content = (msg.content or "").strip()
    tool_calls = getattr(msg, "tool_calls", None)
    if not tool_calls:
        return content, None
    tc_list: list[ToolCallDict] = []
    for tc in tool_calls:
        fn = tc.function
        if isinstance(fn, dict):
            name = fn.get("name", "")
            args = fn.get("arguments", "{}")
        else:
            name = getattr(fn, "name", "") or ""
            args = getattr(fn, "arguments", "{}")
        tc_list.append(
            {"id": tc.id, "type": "function", "function": {"name": name, "arguments": args or "{}"}}
        )
    return content, tc_list


def _stream_completion_one_turn(
    model: str,
    messages: list[ChatCompletionMessage],
    *,
    temperature: float = 0.2,
    tools: list[ToolDefinition] | None = None,
    tool_choice: str | ToolArguments = "auto",
    on_content_delta: Callable[[str], None] | None = None,
    on_reasoning_delta: Callable[[str], None] | None = None,
) -> tuple[str, list[ToolCallDict] | None]:
    """Run one ``stream=True`` completion, accumulating content and tool calls.

    Routes the client exactly like :func:`chat_completion` (a registered
    ``provider/`` prefix selects that provider; every other model uses the default
    client), so streaming honors the same provider registry and proxy-key/BYOK
    overrides. Calls ``on_content_delta(piece)`` for each new content chunk and
    ``on_reasoning_delta(piece)`` for each ``reasoning_content`` chunk (reasoning
    models). Returns ``(content, tool_calls)``: ``tool_calls`` is ``None`` when the
    model called no tool (caller returns the content), else the accumulated calls
    for the caller to run before looping.
    """
    provider, model_id = _parse_provider_prefix(model)
    client = get_client_for_model(model)
    effective_model = model_id if provider is not None else model

    kwargs: dict[str, Any] = {
        "model": effective_model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice

    stream = _create_with_retry(client, **kwargs)
    content_parts: list[str] = []
    tool_calls_accum: dict[int, ToolCallDict] = {}

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if not delta:
            continue

        reasoning_piece = getattr(delta, "reasoning_content", None)
        if reasoning_piece is not None and on_reasoning_delta:
            on_reasoning_delta(str(reasoning_piece))

        if getattr(delta, "content", None):
            piece = delta.content or ""
            accumulated = "".join(content_parts)
            content_parts.append(piece)
            # Some providers resend the full message in the final chunk; emit only
            # the new suffix so callers never see duplicated content.
            if on_content_delta and piece:
                if accumulated and piece.startswith(accumulated) and len(piece) > len(accumulated):
                    piece = piece[len(accumulated) :]
                elif accumulated and piece == accumulated:
                    piece = ""
                if piece:
                    on_content_delta(piece)

        for tc in getattr(delta, "tool_calls", None) or []:
            idx = getattr(tc, "index", None)
            if idx is None:
                continue
            acc = tool_calls_accum.setdefault(
                idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
            )
            if getattr(tc, "id", None):
                acc["id"] = tc.id
            fn = getattr(tc, "function", None)
            if fn:
                if getattr(fn, "name", None):
                    acc["function"]["name"] = (acc["function"]["name"] or "") + (fn.name or "")
                if getattr(fn, "arguments", None):
                    acc["function"]["arguments"] = (acc["function"]["arguments"] or "") + (
                        fn.arguments or ""
                    )

    content = "".join(content_parts).strip()
    if not tool_calls_accum:
        return content, None
    tc_list: list[ToolCallDict] = []
    for i in sorted(tool_calls_accum):
        acc = tool_calls_accum[i]
        tc_list.append(
            {
                "id": acc["id"],
                "type": "function",
                "function": {
                    "name": acc["function"]["name"],
                    "arguments": _normalize_tool_arguments(acc["function"].get("arguments", "{}")),
                },
            }
        )
    return content, tc_list


@_traceable("run_tools")
def run_tools(
    model: str,
    messages: list[ChatCompletionMessage],
    tools: list[ToolDefinition],
    execute_tool: Callable[[str, ToolArguments], str | dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tool_rounds: int = 5,
    on_tool_step: Callable[[str, Any], None] | None = None,
    parallel_safe_tools: set[str] | None = None,
    stream_deltas: bool = False,
    search_parameters: dict[str, Any] | None = None,
) -> str:
    """Run a non-streaming tool-calling loop until the model returns a final answer.

    Args:
        model:        Model string (provider-prefix routing applies).
        messages:     Initial conversation.
        tools:        Tool definitions exposed to the model.
        execute_tool: ``execute_tool(name, arguments) -> str | {"content": str, ...}``.
        temperature:  Sampling temperature.
        max_tool_rounds: Maximum tool rounds before forcing a final answer.
        on_tool_step: Optional callback invoked with ``("tool_call", {name,
            arguments})`` before each call and ``("tool_result", {name, content,
            ...})`` after.
        parallel_safe_tools: Optional set of tool names that may run concurrently;
            when *all* calls in a round are in this set (and there is more than
            one), they are dispatched in parallel. Defaults to fully sequential.
        stream_deltas: When True, each assistant turn is produced with
            ``stream=True`` and ``on_tool_step`` additionally receives
            ``("content", delta)`` for each answer chunk and ``("reasoning",
            delta)`` for each reasoning chunk (reasoning models). Defaults to
            False (one non-streaming call per turn); tool execution is unaffected
            either way.
        search_parameters: Optional xAI Live Search descriptor (see
            :func:`completion`). Attached only to the **first** tool round so a
            multi-round loop doesn't re-search (and re-bill); ignored on the
            streaming path (warns once).

    Returns:
        The model's final response content.
    """
    current: list[ChatCompletionMessage] = list(messages)
    content = ""
    safe = parallel_safe_tools or set()

    def _produce_turn(
        turn_messages: list[ChatCompletionMessage],
        turn_tools: list[ToolDefinition] | None,
        *,
        include_search: bool = False,
    ) -> tuple[str, list[ToolCallDict] | None]:
        """Produce one assistant turn as ``(content, tool_calls|None)``.

        Streams content/reasoning deltas to ``on_tool_step`` when ``stream_deltas`` is
        set; otherwise makes a single non-streaming call. ``include_search`` attaches
        ``search_parameters`` to this turn (first round only).
        """
        if stream_deltas:
            if include_search and search_parameters is not None:
                # _stream_completion_one_turn doesn't forward search_parameters; warn so
                # streaming callers don't assume web grounding happened.
                logger.warning("Live Search not supported on the streaming tool loop; skipping")

            def _on_content(delta: str) -> None:
                if on_tool_step and delta:
                    on_tool_step("content", delta)

            def _on_reasoning(delta: str) -> None:
                if on_tool_step and delta:
                    on_tool_step("reasoning", delta)

            return _stream_completion_one_turn(
                model,
                turn_messages,
                temperature=temperature,
                tools=turn_tools,
                tool_choice="auto",
                on_content_delta=_on_content,
                on_reasoning_delta=_on_reasoning,
            )
        return _message_from_response(
            completion(
                model,
                turn_messages,
                temperature=temperature,
                tools=turn_tools,
                tool_choice="auto",
                search_parameters=search_parameters if include_search else None,
            )
        )

    for round_idx in range(max_tool_rounds):
        # Live Search is billed per request — attach it only to the first turn so a
        # multi-round tool loop doesn't re-search (and re-bill) every round.
        content, tool_calls = _produce_turn(current, tools, include_search=round_idx == 0)
        if not tool_calls:
            return content or ""

        asst_entries: list[ToolCallDict] = []
        for tc in tool_calls:
            name, args_str = _extract_tool_call(tc)
            asst_entries.append(
                {
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {"name": name, "arguments": _normalize_tool_arguments(args_str)},
                }
            )
        current.append(
            {"role": "assistant", "content": content or None, "tool_calls": asst_entries}
        )

        # Parse (tool_call_id, name, args-dict) for each requested call.
        parsed: list[tuple[str, str, ToolArguments]] = []
        for tc in tool_calls:
            name, args_str = _extract_tool_call(tc)
            normalized = _normalize_tool_arguments(
                args_str if isinstance(args_str, str) else str(args_str)
            )
            try:
                args = json.loads(normalized)
            except json.JSONDecodeError as e:
                logger.warning("Bad tool arguments (name=%s): %s — using {}", name, e)
                args = {}
            parsed.append((tc.get("id", ""), name, args))

        run_parallel = len(parsed) > 1 and all(name in safe for (_, name, _) in parsed)
        if run_parallel:
            results: dict[int, str | dict[str, Any]] = {}
            with ThreadPoolExecutor(max_workers=len(parsed)) as executor:
                future_to_idx = {
                    executor.submit(execute_tool, name, args): i
                    for i, (_, name, args) in enumerate(parsed)
                }
                for future in as_completed(future_to_idx):
                    i = future_to_idx[future]
                    try:
                        results[i] = future.result()
                    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as e:
                        results[i] = {"content": str(e)}
            ordered = [(parsed[i], results[i]) for i in range(len(parsed))]
        else:
            ordered = []
            for tc_id, name, args in parsed:
                if on_tool_step is not None:
                    on_tool_step("tool_call", {"name": name, "arguments": args})
                ordered.append(((tc_id, name, args), execute_tool(name, args)))

        for (tc_id, name, args), result in ordered:
            if on_tool_step is not None:
                if run_parallel:
                    on_tool_step("tool_call", {"name": name, "arguments": args})
                payload = {
                    "name": name,
                    **(result if isinstance(result, dict) else {"content": result}),
                }
                on_tool_step("tool_result", payload)
            msg_content = (
                result.get("content", str(result)) if isinstance(result, dict) else str(result)
            )
            current.append(
                {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": _compact_tool_message_content(msg_content),
                }
            )

    # Hit max rounds with no final content: force one more answer without tools.
    if not content and len(current) > len(messages):
        current.append(
            {
                "role": "user",
                "content": "Based on the tool results above, provide a concise final answer.",
            }
        )
        final, _ = _produce_turn(current, None, include_search=False)
        return final or ""
    return content or ""
