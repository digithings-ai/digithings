"""Provider-agnostic, OpenAI-compatible LLM client.

Extracted from the mature ``digigraph.llm`` implementation and made standalone:
no FastAPI, no digigraph, no digismith hard dependencies. Speaks to any
OpenAI-compatible endpoint (LiteLLM proxy, Ollama, OpenRouter, OpenAI direct,
or a registered external provider) and provides:

- :func:`chat_completion` — single completion, with optional tools and/or
  json_schema structured output, transparent SHA-256 response caching, and
  retry/backoff on transient errors.
- :func:`get_client_for_model` — the single client entry point: routes a
  ``provider/model`` prefix to a registered provider client, otherwise the
  default ``OPENAI_API_BASE`` / ``OPENAI_API_KEY`` client. Honors per-request
  overrides set via the contextvar setters below.
- :func:`chat_completion_with_tools` — a non-streaming tool-calling loop.
- Per-request overrides via plain contextvars: :func:`set_proxy_key` /
  :func:`set_byok` (and the ``proxy_key`` / ``byok`` context managers).

The header parsing that feeds these contextvars lives in the consuming service
(e.g. digigraph's FastAPI middleware) — digillm never imports FastAPI nor
accepts ``Request`` objects.

Usage::

    from digillm import chat_completion

    text = chat_completion(
        "groq/llama-3.3-70b-versatile",
        [{"role": "user", "content": "Hello"}],
    )
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import random
import re
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import ContextVar
from typing import Any, TypedDict  # noqa: ANN401 — OpenAI message dict payloads are heterogeneous

from openai import OpenAI

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
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
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
    cache_key: tuple[str, str | None] = (api_key, base_url)
    client = _client_cache.get(cache_key)
    if client is None:
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url.rstrip("/")
        client = OpenAI(**kwargs)
        _client_cache[cache_key] = client
    return client


def get_client_for_model(model: str) -> OpenAI:
    """Return the OpenAI client for ``model`` (the single public client entry point).

    A ``provider/model_id`` prefix matching a registered external provider
    (``xai/``, ``gemini/``, ``groq/``, ``openrouter/``, plus any added via
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
    cached = _client_cache.get(provider)
    if cached is not None:
        return cached
    cfg = _EXTERNAL_PROVIDERS[provider]
    api_key = os.environ.get(cfg["api_key_env"], "").strip()
    if not api_key:
        raise RuntimeError(f"Model {model!r} requires env var {cfg['api_key_env']} to be set.")
    client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    _client_cache[provider] = client
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
    """Return a stable SHA-256 cache key for the given completion parameters."""
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": response_format,
            "max_tokens": max_tokens,
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


# ── Public API: chat_completion ────────────────────────────────────────────────


@_traceable("chat_completion")
def chat_completion(
    model: str,
    messages: list[ChatCompletionMessage],
    *,
    temperature: float = 0.2,
    tools: list[ToolDefinition] | None = None,
    tool_choice: str | ToolArguments = "auto",
    response_format: JsonSchemaResponseFormat | None = None,
    max_tokens: int | None = None,
) -> str | tuple[str, list[ToolCallDict] | None]:
    """Make a single chat completion.

    The model string is used as given: a registered ``provider/model_id`` prefix
    routes to that provider (and the bare ``model_id`` is sent on the wire);
    every other string is passed through unchanged to the default client. No
    hidden env/YAML model substitution happens here — use :func:`resolve_model`
    explicitly if you want mode-based selection.

    Behavior:
    - ``tools=None`` (default): returns the response content ``str``. Cached by a
      SHA-256 key of the request parameters (unless a BYOK override is active).
    - ``tools`` provided: returns ``(content, tool_calls)`` for a tool-calling
      loop; tool calls are never cached (they may have side effects).
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

    # Cache only tool-free, non-BYOK requests (BYOK keys must not pollute or read
    # the shared in-process cache; tool calls may have side effects).
    cache_key: str | None = None
    if not tools and _byok_override.get() is None:
        cache_key = _llm_cache_key(
            effective_model, messages, temperature, response_format, max_tokens
        )
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
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
    elif response_format is not None:
        # tools and response_format are mutually exclusive in the OpenAI API.
        kwargs["response_format"] = response_format

    r = _create_with_retry(client, **kwargs)
    if not r.choices:
        return ("", None) if tools else ""

    msg = r.choices[0].message
    content = (msg.content or "").strip()
    tool_calls = getattr(msg, "tool_calls", None)
    if tools and tool_calls:
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
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": name, "arguments": args or "{}"},
                }
            )
        return content, tc_list

    if cache_key and content:
        _llm_cache_set(cache_key, content)
    return content


# ── Public API: tool-calling loop ───────────────────────────────────────────────


def _extract_tool_call(tc: ToolCallDict) -> tuple[str, str]:
    """Return ``(name, raw_arguments_str)`` from a tool-call dict."""
    fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
    if isinstance(fn, dict):
        return fn.get("name", ""), fn.get("arguments", "{}")
    name = getattr(fn, "name", "") if fn else ""
    args = getattr(fn, "arguments", "{}") if fn else "{}"
    return name, args


@_traceable("chat_completion_with_tools")
def chat_completion_with_tools(
    model: str,
    messages: list[ChatCompletionMessage],
    tools: list[ToolDefinition],
    execute_tool: Callable[[str, ToolArguments], str | dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tool_rounds: int = 5,
    on_tool_step: Callable[[str, Any], None] | None = None,
    parallel_safe_tools: set[str] | None = None,
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

    Returns:
        The model's final response content.
    """
    current: list[ChatCompletionMessage] = list(messages)
    content = ""
    safe = parallel_safe_tools or set()

    for _ in range(max_tool_rounds):
        out = chat_completion(
            model, current, temperature=temperature, tools=tools, tool_choice="auto"
        )
        if isinstance(out, tuple):
            content, tool_calls = out
        else:
            return out or ""
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
        out = chat_completion(model, current, temperature=temperature)
        return (out if isinstance(out, str) else "") or ""
    return content or ""
