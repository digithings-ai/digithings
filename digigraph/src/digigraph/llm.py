"""LLM client: OpenAI-compatible API (Ollama, LiteLLM, OpenAI). Phase 1+."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable

import logging

import yaml
from digismith.trace import traceable as _traceable
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

# Cap tool result text injected into the next LLM turn (full blobs stay in Digistore).
_MAX_TOOL_MESSAGE_CHARS = int(os.environ.get("DIGI_TOOL_MESSAGE_MAX_CHARS", "12000"))


def _compact_tool_message_content(msg_content: str) -> str:
    if len(msg_content) <= _MAX_TOOL_MESSAGE_CHARS:
        return msg_content
    return (
        msg_content[: _MAX_TOOL_MESSAGE_CHARS - 120].rstrip()
        + "\n...[truncated for LLM context; see Digistore/dataset_ref for full tool payloads]"
    )


def _normalize_tool_arguments(args_str: str | None) -> str:
    """Return valid JSON string for tool call arguments. Some models stream invalid JSON (incomplete, trailing comma)."""
    s = (args_str or "").strip()
    if not s:
        return "{}"
    try:
        json.loads(s)
        return s
    except json.JSONDecodeError:
        pass
    # Try common fixes: close unclosed brace, remove trailing comma
    fixed = s.rstrip()
    if fixed and not fixed.endswith("}"):
        if fixed.endswith(","):
            fixed = fixed[:-1] + "}"
        else:
            fixed = fixed + "}"
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


# Optional: override for Ollama / LiteLLM. Default OpenAI if unset.

# Per-request override: DigiChat forwards LiteLLM proxy key from DigiKey token exchange.
_lite_llm_proxy_override: ContextVar[str | None] = ContextVar(
    "lite_llm_proxy_override", default=None
)


def push_lite_llm_proxy_header(request: Any) -> object:
    """Parse ``X-LiteLLM-Proxy-Key``; return token for :func:`pop_lite_llm_proxy`."""
    # starlette Request: headers are case-insensitive
    raw = request.headers.get("x-litellm-proxy-key")
    val = raw.strip() if raw else None
    return _lite_llm_proxy_override.set(val)


def pop_lite_llm_proxy(token: object) -> None:
    _lite_llm_proxy_override.reset(token)  # type: ignore[arg-type]


# BYOK: per-request user-supplied API key. Never logged or persisted.
# Carries (key, provider) where provider is "openai" | "anthropic".
_byok_override: ContextVar[tuple[str, str] | None] = ContextVar("byok_override", default=None)


def push_byok_header(request: Any) -> object:
    """Parse ``X-BYOK-Key`` + ``X-BYOK-Provider``; return token for :func:`pop_byok`."""
    key = (request.headers.get("x-byok-key") or "").strip()
    provider = (request.headers.get("x-byok-provider") or "openai").strip().lower()
    val = (key, provider) if key else None
    return _byok_override.set(val)


def pop_byok(token: object) -> None:
    _byok_override.reset(token)  # type: ignore[arg-type]


def get_byok_override() -> tuple[str, str] | None:
    """Return (api_key, provider) if a BYOK override is active for this request, else None."""
    return _byok_override.get()


# External provider registry: provider_prefix -> base_url + api_key env var.
# Models using these providers are routed to their own OpenAI-compatible endpoint
# instead of the default OPENAI_API_BASE. Keys match the "provider/" prefix convention.
_EXTERNAL_PROVIDERS: dict[str, dict[str, str]] = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
    },
}

# Client cache: (api_key, base_url) -> OpenAI instance.
# Re-uses the underlying httpx connection pool across requests.
# Invalidated automatically when env vars change (cache key includes their values).
_client_cache: dict[tuple[str, str | None], OpenAI] = {}

# LLM response cache: sha256_key -> (response_str, expires_at).
# Only caches non-tool, non-streaming chat_completion calls.
# TTL configurable via DIGI_LLM_CACHE_TTL_SECONDS (default: 3600).
_llm_cache: dict[str, tuple[str, float]] = {}
_LLM_CACHE_MAXSIZE = 256


def _llm_cache_key(
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    response_format: dict[str, Any] | None = None,
    max_tokens: int | None = None,
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


def _llm_cache_ttl() -> float:
    try:
        return float(os.environ.get("DIGI_LLM_CACHE_TTL_SECONDS", "3600"))
    except ValueError:
        return 3600.0


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
    # Evict oldest entries when at capacity (simple FIFO approximation)
    if len(_llm_cache) >= _LLM_CACHE_MAXSIZE:
        oldest_key = next(iter(_llm_cache))
        del _llm_cache[oldest_key]
    _llm_cache[key] = (value, time.monotonic() + _llm_cache_ttl())


# test = minimal tokens (free tier); medium = balanced; best = largest.
# When DIGI_PROJECT_CONFIG is set, agents.llm_mode overrides DIGI_LLM_MODE.
def _get_llm_mode() -> str:
    """Resolve current LLM mode per request. Always reads env/config fresh to avoid global state."""
    if os.environ.get("DIGI_PROJECT_CONFIG"):
        try:
            from digigraph.project_config import DigiProjectConfig

            cfg = DigiProjectConfig.load()
            mode = cfg.get_llm_mode()
            if mode:
                return mode.lower().strip()
        except (ImportError, OSError, AttributeError, TypeError, ValueError) as e:
            logger.warning("Failed to load LLM mode from project config: %s", e)
    return os.environ.get("DIGI_LLM_MODE", "test").lower().strip()


_model_modes_cache: tuple[float, ModelModesConfig] | None = None


class ModelModesConfig(BaseModel):
    """Parsed ``model_modes.yaml``; unknown keys preserved for forward compatibility."""

    model_config = ConfigDict(extra="allow")

    default_model: str | None = None
    defaults: dict[str, str] = Field(default_factory=dict)
    phase_models: dict[str, str] = Field(default_factory=dict)


_EMPTY_MODEL_MODES = ModelModesConfig()


def _load_model_modes() -> ModelModesConfig:
    """Load model modes YAML (mtime-cached). ``DIGI_MODEL_MODES_FILE`` overrides filename."""
    global _model_modes_cache
    config_dir = os.environ.get("DIGI_CONFIG_PATH", "config")
    fname = (
        os.environ.get("DIGI_MODEL_MODES_FILE") or "model_modes.yaml"
    ).strip() or "model_modes.yaml"
    path = Path(config_dir) / fname
    if not path.exists():
        return _EMPTY_MODEL_MODES
    try:
        mtime = path.stat().st_mtime
    except OSError as e:
        logger.warning("Failed to stat model_modes.yaml: %s", e)
        return _EMPTY_MODEL_MODES
    if _model_modes_cache is not None and _model_modes_cache[0] == mtime:
        return _model_modes_cache[1]
    try:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        logger.warning("Failed to load model_modes.yaml: %s", e)
        return _EMPTY_MODEL_MODES
    try:
        cfg = ModelModesConfig.model_validate(raw)
    except ValidationError as e:
        logger.warning("Invalid model_modes.yaml: %s", e)
        return _EMPTY_MODEL_MODES
    _model_modes_cache = (mtime, cfg)
    return cfg


def _sleep_transient_retry(attempt: int, delay: float, *, max_delay: float = 300.0) -> float:
    """Sleep with jitter; return the next backoff delay (capped)."""
    jitter = random.uniform(0.0, delay * 0.25)
    wait = delay + jitter
    time.sleep(wait)
    return min(delay * 2, max_delay)


def get_model_for_mode() -> str:
    """Return the fallback model for phases without a phase_models entry.

    Atlas/Hermes phases all have explicit phase_models entries, so this is
    reached only by non-Atlas digigraph agent runners that don't supply a
    phase_slug. Resolution order:
    1. ``default_model`` in model_modes.yaml — optional explicit fallback.
    2. ``defaults[DIGI_LLM_MODE]`` — legacy mode-keyed fallback.
    3. ``"gpt-4o-mini"`` — hard last resort.
    """
    data = _load_model_modes()
    if data.default_model:
        return str(data.default_model)
    mode = _get_llm_mode()
    model = data.defaults.get(mode) or data.defaults.get("test")
    if model:
        return model
    return "gpt-4o-mini"


def _parse_provider_prefix(model: str) -> tuple[str | None, str]:
    """Split 'provider/model_id' into (provider, model_id) for known external providers.

    Returns (None, model) for Ollama-native model strings (including 'ollama-cloud/…').
    """
    if "/" in model:
        provider, _, model_id = model.partition("/")
        if provider in _EXTERNAL_PROVIDERS:
            return provider, model_id
    return None, model


def get_client_for_model(model: str) -> OpenAI:
    """Return the OpenAI client for the given model string (handles provider prefixes).

    Creates and caches a provider-specific client for 'groq/…' and 'gemini/…' models.
    Falls back to the default Ollama/LiteLLM client for all other model strings.
    Raises RuntimeError when the required API key env var is missing.
    """
    provider, _ = _parse_provider_prefix(model)
    if provider is None:
        return get_client()
    cached = _client_cache.get((provider, None))
    if cached is not None:
        return cached
    cfg = _EXTERNAL_PROVIDERS[provider]
    api_key = os.environ.get(cfg["api_key_env"], "").strip()
    if not api_key:
        raise RuntimeError(
            f"Model {model!r} requires env var {cfg['api_key_env']}. "
            f"See docs/atlas/token-budget.md for setup instructions."
        )
    client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    _client_cache[(provider, None)] = client
    return client


def get_model_for_phase(phase_slug: str) -> str | None:
    """Return the configured model for a phase slug (exact or prefix match), or None.

    Prefix match: a key ending in '-' (e.g. 'analyst-') matches any slug that
    starts with that prefix (e.g. 'analyst-AAPL', 'analyst-NVDA').
    Exact match wins over prefix match when both would apply.
    Returns None when the phase has no explicit override → caller uses get_model_for_mode().
    """
    data = _load_model_modes()
    phase_models = data.phase_models
    if phase_slug in phase_models:
        return phase_models[phase_slug]
    for key, mdl in phase_models.items():
        if key.endswith("-") and phase_slug.startswith(key):
            return mdl
    return None


def _openai_base_looks_like_direct_ollama(base_url: str | None) -> bool:
    """True when requests go to Ollama's built-in OpenAI-compatible server (not LiteLLM)."""
    if not base_url:
        return False
    u = base_url.strip().lower()
    if ":11434" in u:
        return True
    if os.environ.get("DIGI_DIRECT_OLLAMA_OPENAI", "").strip().lower() in ("1", "true", "yes"):
        return True
    return False


def resolve_effective_model(request_model: str) -> str:
    """``OLLAMA_MODEL`` or mode YAML or *request_model*, normalized for the active ``OPENAI_API_BASE``."""
    m = (os.environ.get("OLLAMA_MODEL") or "").strip() or get_model_for_mode() or request_model
    base = os.environ.get("OPENAI_API_BASE")
    if _openai_base_looks_like_direct_ollama(base) and m.startswith("ollama/"):
        return m[len("ollama/") :]
    return m


def _openai_client_api_key() -> str:
    """Bearer token for the OpenAI SDK (LiteLLM proxy or provider).

    When LiteLLM has ``LITELLM_MASTER_KEY`` set, set ``LITELLM_PROXY_API_KEY`` to that
    same master (or virtual) key so DigiGraph does not send the upstream ``OPENAI_API_KEY``.

    Request override priority (highest first):
    1. BYOK user-supplied key (``X-BYOK-Key`` header, OpenAI provider only).
    2. ``X-LiteLLM-Proxy-Key`` (DigiKey token field ``litellm_proxy_api_key`` via DigiChat).
    3. ``LITELLM_PROXY_API_KEY`` env var.
    4. ``OPENAI_API_KEY`` env var.
    """
    byok = _byok_override.get()
    if byok:
        key, provider = byok
        if provider == "openai":
            return key
        # TODO(byok): Anthropic pass-through not yet implemented in DigiGraph.
        # The Anthropic key arrives in the ContextVar but there is no code path that
        # injects it into an Anthropic SDK call. Fall through to the env-configured key.
    override = _lite_llm_proxy_override.get()
    if override:
        return override
    proxy = (os.environ.get("LITELLM_PROXY_API_KEY") or "").strip()
    if proxy:
        return proxy
    return os.environ.get("OPENAI_API_KEY", "not-set")


def get_client() -> OpenAI:
    """Return a cached OpenAI client for the current API key / OPENAI_API_BASE values.

    BYOK OpenAI keys bypass LiteLLM and speak directly to api.openai.com. BYOK clients
    are never cached — user keys must not accumulate in server memory.

    For non-BYOK requests, the cache key includes both env var values so the client is
    recreated automatically if either changes at runtime (e.g. in tests). Reusing the
    client shares its httpx connection pool, avoiding per-request TCP handshakes.
    """
    byok = _byok_override.get()
    if byok:
        key, provider = byok
        if provider == "openai":
            # Don't cache BYOK clients: user keys are personal credentials and must not
            # accumulate in server memory across requests.
            return OpenAI(api_key=key, base_url="https://api.openai.com/v1")

    api_key = _openai_client_api_key()
    base_url = os.environ.get("OPENAI_API_BASE")
    cache_key = (api_key, base_url)
    client = _client_cache.get(cache_key)
    if client is None:
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url.rstrip("/")
        client = OpenAI(**kwargs)
        _client_cache[cache_key] = client
    return client


def _create_with_retry(client: Any, **kwargs: Any) -> Any:
    """Call client.chat.completions.create with backoff on transient errors.

    Retries on:
    - ``RateLimitError`` (429) — model-side throughput cap (Ollama/Groq).
    - ``InternalServerError`` (5xx, including Gemini's "503 high demand"
      response) — provider-side transient unavailability.
    - ``APIConnectionError`` — TCP / DNS / proxy blips.
    - ``APITimeoutError`` — request timeout from the OpenAI client.

    Other exceptions (auth, bad-request, malformed-prompt) propagate
    immediately so the caller sees the real error instead of a long
    pointless wait.

    Backoff: starts at 5s, doubles per attempt, capped at 300s. Jitter
    of up to 25%% on top to avoid thundering-herd retries when many
    parallel phase-7C/7CD nodes hit the same 503 simultaneously. Total
    budget at the default 12 attempts is roughly 30 minutes — long
    enough to ride out a typical Google/Groq incident.
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
            kind = type(exc).__name__
            logger.warning(
                "%s (attempt %d/%d): backing off %.1fs before retry",
                kind,
                attempt + 1,
                max_attempts,
                delay,
            )
            delay = _sleep_transient_retry(attempt, delay)


@_traceable("chat_completion")
def chat_completion(
    model: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] = "auto",
    response_format: dict[str, Any] | None = None,
    max_tokens: int | None = None,
) -> str | tuple[str, list[dict[str, Any]] | None]:
    """
    Chat completion. When tools=None: returns content string (backward compatible).
    When tools provided: returns (content, tool_calls) for tool-calling loop.

    Provider routing: model strings with a 'provider/model_id' prefix (e.g.
    'groq/llama-3.1-8b-instant', 'gemini/gemini-2.0-flash') are routed to
    the corresponding external provider client. If the required API key env
    var is not set, falls back to the default Ollama client with a warning.
    All other model strings use the existing Ollama/LiteLLM path.

    response_format: OpenAI-compatible structured-output descriptor, e.g.
        ``{"type": "json_schema", "json_schema": {"name": "Foo", "schema": {...}}}``.
        Mutually exclusive with ``tools`` — ignored when tools is non-empty.
        Providers: Gemini Flash (OpenAI-compat endpoint) and OpenAI support
        json_schema. Ollama / LiteLLM silently ignore unknown fields, so the
        prompt-embedded OUTPUT_SCHEMA block remains the primary contract.
    """
    provider, model_id = _parse_provider_prefix(model)
    if provider is not None:
        cfg = _EXTERNAL_PROVIDERS[provider]
        api_key = os.environ.get(cfg["api_key_env"], "").strip()
        if api_key:
            client = get_client_for_model(model)
            effective_model = model_id
        else:
            logger.warning(
                "Provider %r key (%s) not configured; falling back to Ollama for this call",
                provider,
                cfg["api_key_env"],
            )
            client = get_client()
            effective_model = resolve_effective_model(get_model_for_mode())
    elif model.startswith("ollama-cloud/"):
        # Strip provider prefix: Ollama Cloud API expects bare model names (e.g. "deepseek-v4-flash:cloud").
        # resolve_effective_model is NOT used here — it would substitute get_model_for_mode() instead.
        client = get_client()
        effective_model = model[len("ollama-cloud/") :]
    else:
        client = get_client()
        effective_model = resolve_effective_model(model)
    # Check cache for tool-free requests (tool calls have side effects; don't cache them)
    cache_key: str | None = None
    if not tools:
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
    elif response_format:
        # tools and response_format are mutually exclusive in the OpenAI API.
        kwargs["response_format"] = response_format
    r = _create_with_retry(client, **kwargs)
    if not r.choices:
        return "" if not tools else ("", None)
    msg = r.choices[0].message
    content = (msg.content or "").strip()
    tool_calls = getattr(msg, "tool_calls", None)
    if tools and tool_calls:
        tc_list = []
        for tc in tool_calls:
            fn = tc.function
            name = getattr(fn, "name", "") or (fn.get("name", "") if isinstance(fn, dict) else "")
            args = (
                getattr(fn, "arguments", "{}")
                if not isinstance(fn, dict)
                else fn.get("arguments", "{}")
            )
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


def _stream_completion_one_turn(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] = "auto",
    on_content_delta: Callable[[str], None] | None = None,
    on_reasoning_delta: Callable[[str], None] | None = None,
) -> tuple[str, list[dict[str, Any]] | None]:
    """
    One completion with stream=True. Accumulates content and tool_calls; calls on_content_delta(delta)
    for each content chunk and on_reasoning_delta(delta) for each reasoning_content chunk when present.
    Returns (content, tool_calls or None). When tool_calls is not None, caller should run tools and loop.
    """
    effective_model = resolve_effective_model(model)
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
    tool_calls_accum: dict[
        int, dict[str, Any]
    ] = {}  # index -> {id, type, function: {name, arguments}}

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if not delta:
            continue
        try:
            reasoning_piece = getattr(delta, "reasoning_content", None)
            if reasoning_piece is not None and on_reasoning_delta:
                on_reasoning_delta(str(reasoning_piece) if reasoning_piece else "")
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to process reasoning_content delta: %s", e)
        if getattr(delta, "content", None):
            piece = delta.content or ""
            accumulated = "".join(content_parts)
            content_parts.append(piece)
            # Some providers send the full message again in the last chunk; only emit the new part to avoid duplicate
            if on_content_delta and piece:
                if accumulated and piece.startswith(accumulated) and len(piece) > len(accumulated):
                    piece = piece[len(accumulated) :]
                elif accumulated and piece == accumulated:
                    piece = ""
                if piece:
                    on_content_delta(piece)
        tool_calls = getattr(delta, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                idx = getattr(tc, "index", None)
                if idx is None:
                    continue
                if idx not in tool_calls_accum:
                    tool_calls_accum[idx] = {
                        "id": getattr(tc, "id", "") or "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                acc = tool_calls_accum[idx]
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
    if tool_calls_accum:
        indices = sorted(tool_calls_accum.keys())
        tc_list = []
        for i in indices:
            acc = tool_calls_accum[i]
            args_raw = acc["function"].get("arguments", "{}")
            tc_list.append(
                {
                    "id": acc["id"],
                    "type": acc["type"],
                    "function": {
                        "name": acc["function"]["name"],
                        "arguments": _normalize_tool_arguments(args_raw),
                    },
                }
            )
        return content, tc_list
    return content, None


@_traceable("chat_completion_with_tools")
def chat_completion_with_tools(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    execute_tool: Callable[[str, dict[str, Any]], str],
    *,
    temperature: float = 0.2,
    max_tool_rounds: int = 5,
    on_tool_step: Callable[[str, Any], None] | None = None,
) -> str:
    """
    Run a tool-calling loop until the model returns a final response.
    execute_tool(name: str, arguments: dict) -> str | dict.
    When on_tool_step is set, calls it with ("tool_call", {name, arguments}) before
    execute_tool and ("tool_result", {content: result, ...}) after. When streaming, emits
    ("content", delta_str) for each token of the final answer and ("reasoning", delta_str) for
    each reasoning_content chunk when the model provides it (e.g. reasoning/thinking models).
    """
    client = get_client()
    current = list(messages)
    content = ""
    use_streaming = on_tool_step is not None

    def do_one_turn():
        if use_streaming:

            def on_delta(delta: str) -> None:
                if on_tool_step and delta:
                    on_tool_step("content", delta)

            def on_reasoning(delta: str) -> None:
                if on_tool_step and delta:
                    on_tool_step("reasoning", delta)

            return _stream_completion_one_turn(
                client,
                model,
                current,
                temperature=temperature,
                tools=tools,
                tool_choice="auto",
                on_content_delta=on_delta,
                on_reasoning_delta=on_reasoning,
            )
        out = chat_completion(
            model, current, temperature=temperature, tools=tools, tool_choice="auto"
        )
        if isinstance(out, tuple):
            return out
        return (out or "", None)

    for _ in range(max_tool_rounds):
        out = do_one_turn()
        if isinstance(out, tuple):
            content, tool_calls = out
        else:
            return (out or "") if isinstance(out, str) else ""
        if not tool_calls:
            return content or ""
        asst_entries = []
        for tc in tool_calls:
            fn = tc.get("function") if isinstance(tc, dict) else {}
            if isinstance(fn, dict):
                name = fn.get("name", "")
                args_str = fn.get("arguments", "{}")
            else:
                name = getattr(fn, "name", "") if fn else ""
                args_str = getattr(fn, "arguments", "{}") if fn else "{}"
            asst_entries.append(
                {
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {"name": name, "arguments": _normalize_tool_arguments(args_str)},
                }
            )
        asst: dict[str, Any] = {
            "role": "assistant",
            "content": content or None,
            "tool_calls": asst_entries,
        }
        current.append(asst)
        # Parse (tc, name, args) for each tool call
        parsed: list[tuple[dict, str, dict]] = []
        for tc in tool_calls:
            fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
            if isinstance(fn, dict):
                name = fn.get("name", "")
                args_str = fn.get("arguments", "{}")
            else:
                name = getattr(fn, "name", "") if fn else ""
                args_str = getattr(fn, "arguments", "{}") if fn else "{}"
            args_str = _normalize_tool_arguments(
                args_str if isinstance(args_str, str) else str(args_str)
            )
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError as e:
                logger.warning(
                    "Failed to parse tool arguments as JSON (name=%s): %s — using {}", name, e
                )
                args = {}
            parsed.append((tc, name, args))
        # Run in parallel only when all calls are delegate/parallel_safe tools
        try:
            from digigraph.orchestration.registry import list_tool_names

            parallel_safe = set(list_tool_names("parallel_safe"))
        except ImportError as e:
            logger.debug("Could not load parallel_safe tool list: %s", e)
            parallel_safe = set()
        all_parallel_safe = len(parsed) > 1 and all(
            name in parallel_safe for (_, name, _) in parsed
        )
        if all_parallel_safe:
            with ThreadPoolExecutor(max_workers=len(parsed)) as executor:
                future_to_idx = {
                    executor.submit(execute_tool, name, args): i
                    for i, (_, name, args) in enumerate(parsed)
                }
                results: dict[int, str | dict[str, Any]] = {}
                for future in as_completed(future_to_idx):
                    i = future_to_idx[future]
                    try:
                        results[i] = future.result()
                    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as e:
                        results[i] = {"content": str(e)}
            for i, (tc, name, args) in enumerate(parsed):
                result = results[i]
                if on_tool_step is not None:
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
                        "tool_call_id": tc["id"],
                        "content": _compact_tool_message_content(msg_content),
                    }
                )
        else:
            for tc, name, args in parsed:
                if on_tool_step is not None:
                    on_tool_step("tool_call", {"name": name, "arguments": args})
                result = execute_tool(name, args)
                if on_tool_step is not None:
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
                        "tool_call_id": tc["id"],
                        "content": _compact_tool_message_content(msg_content),
                    }
                )
    # Hit max rounds with no final content: force one more call without tools
    if not content and len(current) > len(messages):
        current.append(
            {
                "role": "user",
                "content": "Based on the search results above, provide a concise summary for the user.",
            }
        )
        if use_streaming:

            def on_delta(delta: str) -> None:
                if on_tool_step and delta:
                    on_tool_step("content", delta)

            def on_reasoning(delta: str) -> None:
                if on_tool_step and delta:
                    on_tool_step("reasoning", delta)

            out, _ = _stream_completion_one_turn(
                client,
                model,
                current,
                temperature=temperature,
                on_content_delta=on_delta,
                on_reasoning_delta=on_reasoning,
            )
            return (out or "") or ""
        out = chat_completion(model, current, temperature=temperature)
        return (out if isinstance(out, str) else "") or ""
    return content or ""
