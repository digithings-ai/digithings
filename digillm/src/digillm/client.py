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

import asyncio
import contextlib
import functools
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
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import (  # score:allow untyped any — OpenAI message dict payloads are heterogeneous
    Any,
    TypedDict,
)
from uuid import UUID, uuid4

from openai import OpenAI, Timeout
from openai.types.chat import ChatCompletion

from digillm.telemetry import (
    ArtifactRef,
    CacheStatus,
    CallPurpose,
    NoArtifactReason,
    ProviderAttemptOutcome,
    ProviderAttemptRecord,
    ProviderCallOutcome,
    ProviderCallRecord,
    RetryReason,
    TelemetryObserver,
    emit_telemetry,
)

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


def clear_byok() -> None:
    """Drop the BYOK override outright, without the token :func:`set_byok` returned.

    :func:`reset_byok` needs that token, and the token only exists in the frame that
    bound it. A worker thread running inside a *copy* of a request's context inherits
    the binding but never the token, so this is how such a worker drops its own copy
    when the work finishes -- see ``clear_byok_bindings`` in digigraph's ``llm_auth``.
    Calling it in the binding frame instead would clear the value but strand the
    parent's token, so prefer :func:`reset_byok` there.
    """
    _byok_override.set(None)


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
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1/",
        "api_key_env": "ANTHROPIC_API_KEY",
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


def is_registered_provider(prefix: str) -> bool:
    """True if ``prefix`` is a registered external provider (see :func:`register_provider`)."""
    return prefix in _EXTERNAL_PROVIDERS


def get_provider_api_key_env(prefix: str) -> str | None:
    """Return the API-key env var name for a registered provider, or ``None`` if unregistered.

    Lets callers (e.g. digigraph's request-model resolution) check whether a
    provider's key is configured *before* routing to it, without duplicating
    this registry or triggering :func:`get_client_for_model`'s ``RuntimeError``
    on a missing key.
    """
    cfg = _EXTERNAL_PROVIDERS.get(prefix)
    return cfg["api_key_env"] if cfg else None


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


# A provider's model id normally does not repeat the provider's own name, so the wire
# id is the litellm string minus exactly one routing prefix
# (``openrouter/anthropic/claude-sonnet-4`` -> ``anthropic/claude-sonnet-4``). A few ids
# break that assumption by *being* prefixed with their provider: OpenRouter's auto-router
# is itself called ``openrouter/auto``, so its litellm form carries the prefix twice and
# stripping one still has to leave one behind.
#
# Listing those ids here is what lets BOTH spellings land on the same wire id. Operators
# write the doubled ``openrouter/openrouter/auto`` (README, and the Atlas provider
# diagnostics under ``digiquant/scripts/atlas/``; no tier config lists it), but a BYOK
# caller cannot: :func:`digigraph.llm_auth.byok_routable_model` strips the provider's own
# prefix to a fixpoint and re-applies exactly one, by design — that fixpoint is what keeps
# the middleware and the resolver from disagreeing about a hostile header. So the single-
# prefix form is the only one BYOK can produce, and without this table it reached the wire
# as a bare ``auto``, which OpenRouter rejects. Fixing it here rather than in the
# normalizer keeps the credential-path invariant untouched.
_SELF_PREFIXED_MODELS: dict[str, frozenset[str]] = {
    "openrouter": frozenset({"auto"}),
}


def _wire_model(provider: str | None, model_id: str, model: str) -> str:
    """Return the model id to send to *provider*'s endpoint.

    ``model`` is the caller's full litellm string and ``(provider, model_id)`` its
    :func:`_parse_provider_prefix` split. Normally the wire id is ``model_id`` (one prefix
    stripped), but for an id listed in :data:`_SELF_PREFIXED_MODELS` the provider's name is
    part of the id itself, so it is restored. Both ``openrouter/auto`` and
    ``openrouter/openrouter/auto`` therefore reach the wire as ``openrouter/auto``.
    """
    if provider is None:
        return model
    if model_id in _SELF_PREFIXED_MODELS.get(provider, frozenset()):
        return f"{provider}/{model_id}"
    return model_id


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


# ── Request timeout ───────────────────────────────────────────────────────────
# Calls were never actually unbounded: the OpenAI SDK substitutes its own
# ``httpx.Timeout(timeout=600, connect=5.0)`` whenever ``timeout`` is omitted. But that
# bound lived only in the SDK's constants module — invisible from this repo, unanswerable
# by an operator, and free to change under us on any dependency bump. #1734 burned 210
# minutes of a 240-minute CI job in unexplained silence and the first question asked was
# "what is our request timeout?"; nobody could answer it from the source. So the bound is
# now stated here and tunable without a code change.
#
# The defaults below are byte-identical to the SDK's, so this states the status quo rather
# than changing it. Note ``connect`` must stay separate: passing a bare ``600.0`` float
# would widen the connect timeout from 5s to 600s — a regression dressed as a fix.
#
# The full silence budget for one ``completion`` call is the product of three layers, not
# this value alone: SDK ``max_retries=2`` (3 HTTP attempts) x ``_create_with_retry``'s 12
# attempts, each attempt bounded by the read timeout below. Lowering this number is the
# only single-knob way to shrink that product; it is left at the SDK default because a
# large-context reasoning completion can legitimately run for minutes.
#
# Resolved once at import — matching the ``_EMPTY_RETRY_*`` idiom below — rather than per
# call: ``_client_cache`` is keyed on ``(api_key, base_url)`` only, so a call-time env read
# would hand a cached client its stale timeout and quietly falsify the cache's documented
# "recreated when env changes" contract.
_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("DIGILLM_REQUEST_TIMEOUT_SECONDS", "") or 600.0)
_CONNECT_TIMEOUT_SECONDS = float(os.environ.get("DIGILLM_CONNECT_TIMEOUT_SECONDS", "") or 5.0)
_REQUEST_TIMEOUT = Timeout(_REQUEST_TIMEOUT_SECONDS, connect=_CONNECT_TIMEOUT_SECONDS)


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
        return OpenAI(api_key=api_key, base_url=base_url, timeout=_REQUEST_TIMEOUT)

    api_key = _default_client_api_key()
    base_url = os.environ.get("OPENAI_API_BASE")
    normalized_base = base_url.rstrip("/") if base_url else None
    # Key on the normalized base so http://h/v1 and http://h/v1/ reuse one client.
    cache_key: tuple[str, str | None] = (api_key, normalized_base)
    client = _client_cache.get(cache_key)
    if client is None:
        kwargs: dict[str, Any] = {"api_key": api_key, "timeout": _REQUEST_TIMEOUT}
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

    When a BYOK override is active and its ``base_url`` matches the provider's
    endpoint, returns an *uncached* client with the user's key (never cached).

    Raises:
        RuntimeError: when a registered provider's API key env var is unset.
    """
    provider, _ = _parse_provider_prefix(model)
    byok_override = _byok_override.get()
    if provider is not None and byok_override:
        api_key, base_url = byok_override
        cfg = _EXTERNAL_PROVIDERS.get(provider)
        if cfg and base_url.rstrip("/") == cfg["base_url"].rstrip("/"):
            return OpenAI(api_key=api_key, base_url=base_url, timeout=_REQUEST_TIMEOUT)
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
    client = OpenAI(api_key=api_key, base_url=cfg["base_url"], timeout=_REQUEST_TIMEOUT)
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


# ── Physical-attempt telemetry ───────────────────────────────────────────────

_telemetry_observer: TelemetryObserver | None = None


def set_telemetry_observer(observer: TelemetryObserver | None) -> None:
    """Register a process-wide provider telemetry sink; pass ``None`` to disable."""
    global _telemetry_observer
    _telemetry_observer = observer


@dataclass
class ProviderCallContextHandle:
    """Mutable logical-call result and deferred-disposition handle."""

    last_call_id: UUID | None = None
    _pending_records: list[ProviderCallRecord] = field(default_factory=list, repr=False)

    def set_no_artifact_reason(self, reason: NoArtifactReason) -> bool:
        """Replace the latest deferred successful disposition when one exists."""
        if not self._pending_records:
            return False
        record = self._pending_records[-1]
        if record.outcome is not ProviderCallOutcome.SUCCEEDED:
            return False
        self._pending_records[-1] = record.model_copy(
            update={"artifacts": (), "no_artifact_reason": reason}
        )
        return True

    def finalize(self) -> None:
        """Deliver and clear all deferred logical records exactly once."""
        records = tuple(self._pending_records)
        self._pending_records.clear()
        observer = _telemetry_observer
        if observer is None:
            return
        for record in records:
            emit_telemetry(observer, record)


@dataclass(frozen=True)
class _ProviderCallMetadata:
    node_run_id: UUID
    purpose: CallPurpose
    parent_call_id: UUID | None
    artifacts: tuple[ArtifactRef, ...]
    no_artifact_reason: NoArtifactReason | None
    follow_up_purpose: CallPurpose | None
    follow_up_artifacts: tuple[ArtifactRef, ...]
    follow_up_no_artifact_reason: NoArtifactReason | None
    defer_finalization: bool
    handle: ProviderCallContextHandle


_provider_call_metadata: ContextVar[_ProviderCallMetadata | None] = ContextVar(
    "digillm_provider_call_metadata", default=None
)


@contextlib.contextmanager
def provider_call_context(
    *,
    node_run_id: UUID,
    purpose: CallPurpose,
    parent_call_id: UUID | None = None,
    artifacts: tuple[ArtifactRef, ...] = (),
    no_artifact_reason: NoArtifactReason | None = None,
    follow_up_purpose: CallPurpose | None = None,
    follow_up_artifacts: tuple[ArtifactRef, ...] = (),
    follow_up_no_artifact_reason: NoArtifactReason | None = None,
    defer_finalization: bool = False,
    handle: ProviderCallContextHandle | None = None,
) -> Iterator[ProviderCallContextHandle]:
    """Inject generic logical-call metadata without changing provider call signatures."""
    if bool(artifacts) == (no_artifact_reason is not None):
        raise ValueError("provide either artifacts or one no_artifact_reason")
    if follow_up_purpose is not None and bool(follow_up_artifacts) == (
        follow_up_no_artifact_reason is not None
    ):
        raise ValueError("provide either follow_up_artifacts or one follow_up_no_artifact_reason")
    call_handle = handle or ProviderCallContextHandle()
    token = _provider_call_metadata.set(
        _ProviderCallMetadata(
            node_run_id=node_run_id,
            purpose=purpose,
            parent_call_id=parent_call_id,
            artifacts=artifacts,
            no_artifact_reason=no_artifact_reason,
            follow_up_purpose=follow_up_purpose,
            follow_up_artifacts=follow_up_artifacts,
            follow_up_no_artifact_reason=follow_up_no_artifact_reason,
            defer_finalization=defer_finalization,
            handle=call_handle,
        )
    )
    try:
        yield call_handle
    finally:
        _provider_call_metadata.reset(token)


def detach_provider_call_context() -> None:
    """Drop the inherited logical-call metadata in the *current* context, token-free.

    For a thread running inside a :func:`contextvars.copy_context` snapshot taken to
    carry a request's *credentials* across the boundary. A copy propagates references
    rather than values, so the snapshot hands every fan-out worker the same mutable
    :class:`ProviderCallContextHandle`: they all write its ``last_call_id`` (leaving a
    follow-up call parented on whichever sibling happened to finish last) and all append
    to the one deferred-record list that ``finalize`` tuples and clears. A worker that
    inherited an empty context read ``None`` here, so this restores that *for this
    module's var*. It says nothing about a consumer's own logical-call vars, which the
    same snapshot carries and which can hold the same handle one layer up --
    :func:`set_fan_out_detach_hook` is how a consumer clears those alongside this one.

    Nesting fan-out calls under their parent's logical call is a separate feature, and a
    real one -- it needs a per-worker handle plus a merge at the join, not a shared
    handle written concurrently.
    """
    _provider_call_metadata.set(None)


@dataclass
class _AttemptScope:
    call_id: UUID
    requested_model: str
    started_at: datetime
    metadata: _ProviderCallMetadata | None
    next_attempt_number: int = 1
    next_retry_reason: RetryReason = RetryReason.NOT_APPLICABLE
    cache_status: CacheStatus = CacheStatus.UNAVAILABLE
    finalized: bool = False
    terminal_outcome: ProviderCallOutcome | None = None
    logical_error_type: str | None = None
    last_attempt_id: UUID | None = None

    def start(self) -> tuple[int, RetryReason, datetime]:
        attempt_number = self.next_attempt_number
        retry_reason = self.next_retry_reason
        self.next_attempt_number += 1
        self.next_retry_reason = RetryReason.UNKNOWN
        return attempt_number, retry_reason, datetime.now(UTC)


_attempt_scope: ContextVar[_AttemptScope | None] = ContextVar("digillm_attempt_scope", default=None)


@contextlib.contextmanager
def _logical_attempt_scope(requested_model: str = "unknown") -> Iterator[_AttemptScope]:
    existing = _attempt_scope.get()
    if existing is not None:
        yield existing
        return
    context_metadata = _provider_call_metadata.get()
    metadata = context_metadata
    if (
        context_metadata is not None
        and context_metadata.handle.last_call_id is not None
        and context_metadata.follow_up_purpose is not None
    ):
        metadata = _ProviderCallMetadata(
            node_run_id=context_metadata.node_run_id,
            purpose=context_metadata.follow_up_purpose,
            parent_call_id=context_metadata.handle.last_call_id,
            artifacts=context_metadata.follow_up_artifacts,
            no_artifact_reason=context_metadata.follow_up_no_artifact_reason,
            follow_up_purpose=context_metadata.follow_up_purpose,
            follow_up_artifacts=context_metadata.follow_up_artifacts,
            follow_up_no_artifact_reason=context_metadata.follow_up_no_artifact_reason,
            defer_finalization=context_metadata.defer_finalization,
            handle=context_metadata.handle,
        )
    scope = _AttemptScope(
        call_id=uuid4(),
        requested_model=requested_model,
        started_at=datetime.now(UTC),
        metadata=metadata,
    )
    if metadata is not None:
        metadata.handle.last_call_id = scope.call_id
    token = _attempt_scope.set(scope)
    try:
        yield scope
    finally:
        _attempt_scope.reset(token)


def _with_logical_attempt_scope(function: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if _attempt_scope.get() is not None:
            return function(*args, **kwargs)
        requested_model = str(args[0]) if args else str(kwargs.get("model") or "unknown")
        with _logical_attempt_scope(requested_model) as scope:
            try:
                result = function(*args, **kwargs)
            except (GeneratorExit, asyncio.CancelledError):
                _emit_logical_call(
                    scope,
                    scope.terminal_outcome or ProviderCallOutcome.CANCELLED,
                    error_type=scope.logical_error_type,
                )
                raise
            except Exception as error:
                _emit_logical_call(
                    scope,
                    scope.terminal_outcome or ProviderCallOutcome.FAILED,
                    error_type=scope.logical_error_type or type(error).__name__,
                )
                raise
            if scope.next_attempt_number > 1 or scope.cache_status is CacheStatus.HIT:
                _emit_logical_call(
                    scope,
                    scope.terminal_outcome or ProviderCallOutcome.SUCCEEDED,
                    error_type=scope.logical_error_type,
                )
            return result

    return wrapped


def _emit_logical_call(
    scope: _AttemptScope,
    outcome: ProviderCallOutcome,
    *,
    error_type: str | None = None,
) -> None:
    if scope.finalized:
        return
    scope.finalized = True
    observer = _telemetry_observer
    metadata = scope.metadata
    if observer is None or metadata is None:
        return
    try:
        artifacts = metadata.artifacts
        no_artifact_reason = metadata.no_artifact_reason
        if outcome is ProviderCallOutcome.FAILED:
            artifacts = ()
            no_artifact_reason = NoArtifactReason.CALL_FAILED
        elif outcome is ProviderCallOutcome.CANCELLED:
            artifacts = ()
            no_artifact_reason = NoArtifactReason.CALL_CANCELLED
            error_type = None
        record = ProviderCallRecord(
            call_id=scope.call_id,
            node_run_id=metadata.node_run_id,
            parent_call_id=metadata.parent_call_id,
            purpose=metadata.purpose,
            requested_model=scope.requested_model,
            cache_status=scope.cache_status,
            outcome=outcome,
            attempt_count=scope.next_attempt_number - 1,
            artifacts=artifacts,
            no_artifact_reason=no_artifact_reason,
            error_type=error_type,
            started_at=scope.started_at,
            finished_at=datetime.now(UTC),
        )
        if metadata.defer_finalization and outcome is ProviderCallOutcome.SUCCEEDED:
            metadata.handle._pending_records.append(record)
        else:
            emit_telemetry(observer, record)
    except Exception as telemetry_error:
        logger.debug("logical-call telemetry failed: %s", type(telemetry_error).__name__)


def _provider_name(provider: str | None) -> str:
    return provider or "default"


def _retry_reason(error: Exception) -> RetryReason:
    from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

    if isinstance(error, RateLimitError):
        return RetryReason.RATE_LIMIT
    if isinstance(error, APITimeoutError):
        return RetryReason.TIMEOUT
    if isinstance(error, APIConnectionError):
        return RetryReason.CONNECTION_ERROR
    if isinstance(error, InternalServerError):
        return RetryReason.SERVER_ERROR
    return RetryReason.UNKNOWN


def _optional_nonnegative_int(value: Any) -> int | None:
    # ``bool`` subclasses ``int``, so ``isinstance(False, int)`` is True. Treating False as 0
    # would invent a measured-zero token count when the provider omitted usage (#1989).
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _optional_attribute(value: Any, name: str) -> Any:
    try:
        return getattr(value, name, None)
    except Exception:
        return None


def _response_usage(response: Any) -> tuple[int | None, int | None, Decimal | None]:
    usage = _optional_attribute(response, "usage")
    prompt_tokens = _optional_attribute(usage, "prompt_tokens")
    if prompt_tokens is None:
        prompt_tokens = _optional_attribute(usage, "input_tokens")
    completion_tokens = _optional_attribute(usage, "completion_tokens")
    if completion_tokens is None:
        completion_tokens = _optional_attribute(usage, "output_tokens")
    cost = _optional_attribute(usage, "cost")
    if cost is None:
        extra = _optional_attribute(usage, "model_extra")
        if isinstance(extra, dict):
            cost = extra.get("cost")
    cost_usd: Decimal | None = None
    if cost is not None:
        try:
            parsed_cost = Decimal(str(cost))
        except (InvalidOperation, ValueError):
            pass
        else:
            if parsed_cost.is_finite() and parsed_cost >= 0:
                cost_usd = parsed_cost
    return (
        _optional_nonnegative_int(prompt_tokens),
        _optional_nonnegative_int(completion_tokens),
        cost_usd,
    )


@dataclass
class _StreamEvidence:
    model: str | None = None
    usage: Any = None

    def observe(self, chunk: Any) -> None:
        chunk_model = _optional_attribute(chunk, "model")
        if isinstance(chunk_model, str) and chunk_model:
            self.model = chunk_model
        chunk_usage = _optional_attribute(chunk, "usage")
        if chunk_usage is not None:
            self.usage = chunk_usage


def _emit_attempt(
    *,
    scope: _AttemptScope,
    attempt_number: int,
    retry_reason: RetryReason,
    provider: str,
    requested_model: str,
    started_at: datetime,
    outcome: ProviderAttemptOutcome,
    response: Any = None,
    error: Exception | None = None,
) -> None:
    attempt_id = uuid4()
    scope.last_attempt_id = attempt_id
    observer = _telemetry_observer
    if observer is None:
        return
    try:
        prompt_tokens, completion_tokens, cost_usd = _response_usage(response)
        served_model = _optional_attribute(response, "model")
        record = ProviderAttemptRecord(
            attempt_id=attempt_id,
            call_id=scope.call_id,
            attempt_number=attempt_number,
            provider=provider,
            requested_model=requested_model,
            served_model=served_model if isinstance(served_model, str) and served_model else None,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            outcome=outcome,
            retry_reason=retry_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            error_type=type(error).__name__ if error is not None else None,
        )
        emit_telemetry(observer, record)
    except Exception as telemetry_error:
        logger.debug("attempt telemetry failed: %s", type(telemetry_error).__name__)


def _wp1_join_fields() -> dict[str, Any]:
    """Soft-stamp fields for the glass-box usage observer (#2763)."""
    scope = _attempt_scope.get()
    if scope is None:
        return {}
    fields: dict[str, Any] = {"call_id": scope.call_id}
    if scope.last_attempt_id is not None:
        fields["attempt_id"] = scope.last_attempt_id
    if scope.metadata is not None and scope.metadata.node_run_id is not None:
        fields["node_run_id"] = scope.metadata.node_run_id
    return fields


def _responses_create_with_attempt(
    client: OpenAI,
    *,
    provider: str,
    requested_model: str,
    **kwargs: Any,
) -> Any:
    with _logical_attempt_scope() as scope:
        scope.cache_status = CacheStatus.BYPASSED
        attempt_number, retry_reason, started_at = scope.start()
        try:
            response = client.responses.create(**kwargs)
        except asyncio.CancelledError:
            scope.terminal_outcome = ProviderCallOutcome.CANCELLED
            _emit_attempt(
                scope=scope,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                provider=provider,
                requested_model=requested_model,
                started_at=started_at,
                outcome=ProviderAttemptOutcome.CANCELLED,
            )
            raise
        except Exception as error:
            scope.terminal_outcome = ProviderCallOutcome.FAILED
            scope.logical_error_type = type(error).__name__
            _emit_attempt(
                scope=scope,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                provider=provider,
                requested_model=requested_model,
                started_at=started_at,
                outcome=ProviderAttemptOutcome.FAILED,
                error=error,
            )
            raise
        _emit_attempt(
            scope=scope,
            attempt_number=attempt_number,
            retry_reason=retry_reason,
            provider=provider,
            requested_model=requested_model,
            started_at=started_at,
            outcome=ProviderAttemptOutcome.SUCCEEDED,
            response=response,
        )
        return response


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
        # Stamp WP1 join keys from the active attempt scope unless the caller already set them.
        for key, value in _wp1_join_fields().items():
            fields.setdefault(key, value)
        observer(**fields)
    except Exception as exc:  # telemetry must never break the LLM call
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
    time.sleep(delay + jitter)  # intentional blocking backoff
    return min(delay * 2, max_delay)


def _create_with_retry(
    client: OpenAI,
    *,
    _provider: str | None = None,
    _requested_model: str | None = None,
    _defer_success: bool = False,
    on_attempt: Callable[[], None] | None = None,
    **kwargs: Any,
) -> Any:
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
    with _logical_attempt_scope() as scope:
        requested_model = _requested_model or str(kwargs.get("model") or "unknown")
        provider = _provider_name(_provider)
        for attempt in range(max_attempts):
            attempt_number, retry_reason, started_at = scope.start()
            try:
                if on_attempt is not None:
                    on_attempt()
                response = client.chat.completions.create(**kwargs)
            except asyncio.CancelledError:
                scope.terminal_outcome = ProviderCallOutcome.CANCELLED
                _emit_attempt(
                    scope=scope,
                    attempt_number=attempt_number,
                    retry_reason=retry_reason,
                    provider=provider,
                    requested_model=requested_model,
                    started_at=started_at,
                    outcome=ProviderAttemptOutcome.CANCELLED,
                )
                raise
            except Exception as error:
                _emit_attempt(
                    scope=scope,
                    attempt_number=attempt_number,
                    retry_reason=retry_reason,
                    provider=provider,
                    requested_model=requested_model,
                    started_at=started_at,
                    outcome=ProviderAttemptOutcome.FAILED,
                    error=error,
                )
                if not isinstance(error, transient) or attempt >= max_attempts - 1:
                    raise
                scope.next_retry_reason = _retry_reason(error)
                logger.warning(
                    "%s (attempt %d/%d): backing off %.1fs before retry",
                    type(error).__name__,
                    attempt + 1,
                    max_attempts,
                    delay,
                )
                delay = _sleep_transient_retry(delay)
                continue
            if _defer_success:
                return response, scope, attempt_number, retry_reason, started_at
            _emit_attempt(
                scope=scope,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                provider=provider,
                requested_model=requested_model,
                started_at=started_at,
                outcome=ProviderAttemptOutcome.SUCCEEDED,
                response=response,
            )
            return response
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


def _openrouter_usage_cost(usage: Any) -> float | None:
    """Actual USD charged for a call, from OpenRouter's ``usage.cost`` when present.

    The OpenAI SDK is typed for OpenAI's schema, so an unknown ``cost`` field lands in
    pydantic ``model_extra`` rather than a typed attribute — check both. Returns ``None``
    when the provider/SDK does not surface cost so glass-box / WP1 paths never fabricate 0
    (#2763)."""
    if usage is None:
        return None
    cost = getattr(usage, "cost", None)
    if cost is None:
        extra = getattr(usage, "model_extra", None)
        if isinstance(extra, dict):
            cost = extra.get("cost")
    if cost is None:
        return None
    try:
        value = float(cost)
    except (TypeError, ValueError):
        return None
    # float() also accepts 'nan'/'inf'/negatives; a bad cost must not poison run-level
    # aggregation (one nan turns the whole run's cost_usd into nan).
    return value if math.isfinite(value) and value >= 0 else None


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
@_with_logical_attempt_scope
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
    effective_model = _wire_model(provider, model_id, model)
    usage_started = time.perf_counter()
    provider_attempts = 0

    def create_with_retry(call_kwargs: dict[str, Any]) -> ChatCompletion:
        def count_attempt() -> None:
            nonlocal provider_attempts
            provider_attempts += 1

        return _create_with_retry(
            client,
            _provider=provider,
            _requested_model=model,
            on_attempt=count_attempt,
            **call_kwargs,
        )

    # xAI Live Search rides the OpenAI-compatible client via ``extra_body`` and only
    # when the real xAI client is active (reaching here for an ``xai/`` model means its
    # key was set — get_client_for_model raises otherwise). It is time-sensitive and not
    # captured by the cache key, so a search request bypasses the cache like tool calls.
    xai_live_search = search_parameters is not None and provider == "xai"

    attempt_scope = _attempt_scope.get()
    cache_status = (
        CacheStatus.BYPASSED
        if tools or xai_live_search or _byok_override.get() is not None
        else CacheStatus.MISS
    )
    if attempt_scope is not None:
        attempt_scope.cache_status = cache_status

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
            if attempt_scope is not None:
                attempt_scope.cache_status = CacheStatus.HIT
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
        try:
            r = create_with_retry(kwargs)
        except Exception as exc:  # only the 410 case is soft; everything else re-raises
            # xAI deprecated Live Search (HTTP 410) in favour of the Agent Tools API
            # (:func:`web_search`). Fail soft: drop the deprecated extra_body and retry once
            # ungrounded so the phase/pipeline keeps producing instead of crashing.
            if getattr(exc, "status_code", None) != 410 or "extra_body" not in kwargs:
                raise
            logger.warning(
                "xAI rejected search_parameters (410 deprecated); retrying without Live Search"
            )
            kwargs.pop("extra_body", None)
            attempt_scope = _attempt_scope.get()
            if attempt_scope is not None:
                attempt_scope.next_retry_reason = RetryReason.UNKNOWN
            r = create_with_retry(kwargs)
    except Exception:
        _record_usage(
            kind=usage_kind,
            model=effective_model,
            ok=False,
            duration_ms=round((time.perf_counter() - usage_started) * 1000),
            retry_count=max(0, provider_attempts - 1),
        )
        raise

    # Empty-response self-heal. An empty body is transient; retry with backoff.
    # OPENROUTER_FALLBACK_MODELS (attached on the primary request above, not here) covers
    # provider errors via route=fallback — it does not swap models on an empty 200. Empty
    # retries re-ask the same model. A persistent blank falls through unchanged.
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
        time.sleep(_EMPTY_RETRY_DELAY)  # intentional short backoff on empty
        attempt_scope = _attempt_scope.get()
        if attempt_scope is not None:
            attempt_scope.next_retry_reason = RetryReason.EMPTY_RESPONSE
        try:
            r = create_with_retry(retry_kwargs)
        except Exception:
            _record_usage(
                kind=usage_kind,
                model=effective_model,
                ok=False,
                duration_ms=round((time.perf_counter() - usage_started) * 1000),
                retry_count=max(0, provider_attempts - 1),
            )
            raise

    _u = getattr(r, "usage", None)
    _details = getattr(_u, "prompt_tokens_details", None) if _u is not None else None
    _cached_raw = getattr(_details, "cached_tokens", None) if _details is not None else None
    _record_usage(
        kind=usage_kind,
        # Record the model OpenRouter actually served (``r.model``), not the request string
        # ("auto" / the allowlist), so cost telemetry reflects what was really billed.
        model=getattr(r, "model", None) or effective_model,
        prompt_tokens=_optional_nonnegative_int(getattr(_u, "prompt_tokens", None) if _u else None),
        completion_tokens=_optional_nonnegative_int(
            getattr(_u, "completion_tokens", None) if _u else None
        ),
        cached_tokens=_optional_nonnegative_int(_cached_raw),
        # Actual USD when reported; None when unknown — never fabricate 0 (#2763).
        cost=_openrouter_usage_cost(_u),
        duration_ms=round((time.perf_counter() - usage_started) * 1000),
        retry_count=max(0, provider_attempts - 1),
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
    except Exception as exc:  # grounding is best-effort; degrade gracefully
        logger.warning("openrouter_web_search failed (%s); continuing ungrounded", exc)
        return None

    if not resp.choices:
        return None
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        return None
    return text, _urls_from_grounding_text(text)


@_with_logical_attempt_scope
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
    started = time.perf_counter()
    try:
        client = get_client_for_model(model)
        resp = _responses_create_with_attempt(
            client,
            provider=provider,
            requested_model=model,
            model=model_id,
            input=[{"role": "user", "content": query}],
            tools=[tool],
        )
    except Exception as exc:  # grounding is best-effort; degrade gracefully
        logger.warning("web_search failed (%s); continuing ungrounded", exc)
        _record_usage(
            kind="web_search",
            model=model_id,
            ok=False,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
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
    _, _, cost_usd = _response_usage(resp)
    _record_usage(
        kind="web_search",
        model=model_id,
        cost=float(cost_usd) if cost_usd is not None else None,
        sources=len(sources),
        ok=True,
        duration_ms=round((time.perf_counter() - started) * 1000),
    )
    return text, sources


@_with_logical_attempt_scope
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
    started = time.perf_counter()
    try:
        client = get_client_for_model(model)
        resp = _responses_create_with_attempt(
            client,
            provider=provider,
            requested_model=model,
            model=model_id,
            input=[{"role": "user", "content": query}],
            tools=[{"type": "x_search", "max_search_results": max_results}],
        )
    except Exception as exc:  # grounding is best-effort; degrade gracefully
        logger.warning("x_search failed (%s); continuing ungrounded", exc)
        _record_usage(
            kind="x_search",
            model=model_id,
            ok=False,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        return None
    text = getattr(resp, "output_text", "") or ""
    sources = _urls_from_grounding_text(text)
    _, _, cost_usd = _response_usage(resp)
    _record_usage(
        kind="x_search",
        model=model_id,
        cost=float(cost_usd) if cost_usd is not None else None,
        sources=len(sources),
        ok=True,
        duration_ms=round((time.perf_counter() - started) * 1000),
    )
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


@_with_logical_attempt_scope
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
    effective_model = _wire_model(provider, model_id, model)

    kwargs: dict[str, Any] = {
        "model": effective_model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice

    stream, scope, attempt_number, retry_reason, started_at = _create_with_retry(
        client,
        _provider=provider,
        _requested_model=model,
        _defer_success=True,
        **kwargs,
    )
    content_parts: list[str] = []
    tool_calls_accum: dict[int, ToolCallDict] = {}
    evidence = _StreamEvidence()

    stream_iterator = iter(stream)
    while True:
        try:
            chunk = next(stream_iterator)
        except StopIteration:
            break
        except (GeneratorExit, asyncio.CancelledError):
            scope.terminal_outcome = ProviderCallOutcome.CANCELLED
            _emit_attempt(
                scope=scope,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                provider=_provider_name(provider),
                requested_model=model,
                started_at=started_at,
                outcome=ProviderAttemptOutcome.CANCELLED,
                response=evidence,
            )
            raise
        except Exception as error:
            scope.terminal_outcome = ProviderCallOutcome.FAILED
            scope.logical_error_type = type(error).__name__
            _emit_attempt(
                scope=scope,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                provider=_provider_name(provider),
                requested_model=model,
                started_at=started_at,
                outcome=ProviderAttemptOutcome.FAILED,
                response=evidence,
                error=error,
            )
            raise

        evidence.observe(chunk)
        try:
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
                    if (
                        accumulated
                        and piece.startswith(accumulated)
                        and len(piece) > len(accumulated)
                    ):
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
                    idx,
                    {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    },
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
        except (GeneratorExit, asyncio.CancelledError):
            scope.terminal_outcome = ProviderCallOutcome.CANCELLED
            _emit_attempt(
                scope=scope,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                provider=_provider_name(provider),
                requested_model=model,
                started_at=started_at,
                outcome=ProviderAttemptOutcome.CANCELLED,
                response=evidence,
            )
            raise
        except Exception:
            scope.terminal_outcome = ProviderCallOutcome.CANCELLED
            _emit_attempt(
                scope=scope,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                provider=_provider_name(provider),
                requested_model=model,
                started_at=started_at,
                outcome=ProviderAttemptOutcome.CANCELLED,
                response=evidence,
            )
            raise
    _emit_attempt(
        scope=scope,
        attempt_number=attempt_number,
        retry_reason=retry_reason,
        provider=_provider_name(provider),
        requested_model=model,
        started_at=started_at,
        outcome=ProviderAttemptOutcome.SUCCEEDED,
        response=evidence,
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


# ── Fan-out detach hook ─────────────────────────────────────────────────────────
# :func:`detach_provider_call_context` clears *this* module's logical-call var, but a
# consumer that layers its own logical-call ContextVar on top of it -- digigraph's
# ``usage._LOGICAL_CALL_CONTEXT`` does, and its value holds the very same mutable
# :class:`ProviderCallContextHandle` -- would still hand every parallel worker one
# shared handle through the credential snapshot. digillm is a leaf library and cannot
# reach into a consumer's module to clear it, exactly as it cannot write into a
# consumer's usage accumulator, so the consumer registers a callback here on the same
# terms: process-wide, no-op until registered, errors never break the tool call.

_fan_out_detach_hook: Callable[[], None] | None = None


def set_fan_out_detach_hook(hook: Callable[[], None] | None) -> None:
    """Register a callback run at the top of every parallel tool worker.

    Called inside the worker's own copied context, so it must clear caller-side
    logical-call state token-free (a copy carries values, never reset tokens) and must
    not touch credentials -- carrying those across the boundary is the whole point of
    the copy. Pass ``None`` to disable.
    """
    global _fan_out_detach_hook
    _fan_out_detach_hook = hook


def _detach_consumer_call_context() -> None:
    """Run the consumer's detach hook, if one is registered."""
    hook = _fan_out_detach_hook
    if hook is None:
        return
    try:
        hook()
    except Exception as exc:  # a broken hook must not fail the tool call
        logger.warning("fan-out detach hook raised, telemetry may be shared: %s", exc)


def _execute_tool_in_fan_out(
    execute_tool: Callable[[str, ToolArguments], str | dict[str, Any]],
    name: str,
    args: ToolArguments,
) -> str | dict[str, Any]:
    """Run one parallel tool call: credentials inherited, telemetry handles dropped."""
    detach_provider_call_context()
    _detach_consumer_call_context()
    return execute_tool(name, args)


@_traceable("run_tools")
def run_tools(
    model: str,
    messages: list[ChatCompletionMessage],
    tools: list[ToolDefinition],
    execute_tool: Callable[[str, ToolArguments], str | dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tool_rounds: int = 5,
    tool_choice: str | ToolArguments = "auto",
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
        tool_choice:  Passed to every turn's completion call ("auto" default;
            "required" forces a tool call every round). See :func:`completion`.
        on_tool_step: Optional callback invoked with ``("tool_call", {name,
            arguments})`` before each call and ``("tool_result", {name, content,
            ...})`` after. Also receives ``("round_boundary", {round_idx,
            narration})`` after each tool round that produced non-empty assistant
            narration — consumers may handle or ignore it. Tool-only rounds
            (empty narration) deliberately skip this event so callbacks stay
            ordered ``tool_call`` → ``tool_result`` without a vacuous boundary.
            With ``stream_deltas`` enabled, narration content deltas were already
            emitted before ``round_boundary``; without streaming,
            ``round_boundary`` is the only callback that exposes that narration.
            Receives ``("round_limit_exhausted", {max_tool_rounds})`` once when
            ``max_tool_rounds`` is exhausted (every round through the budget still
            returned tool_calls), immediately before a forced tool-free completion
            synthesizes the final answer from the full transcript -- including
            that last round's own tool results, which its own narration (written
            before those tools ran) cannot reflect.
        parallel_safe_tools: Optional set of tool names that may run concurrently;
            when *all* calls in a round are in this set (and there is more than
            one), they are dispatched in parallel. Defaults to fully sequential.
        stream_deltas: When True, each assistant turn is produced with
            ``stream=True`` and ``on_tool_step`` additionally receives
            ``("content", delta)`` for each answer chunk and ``("reasoning",
            delta)`` for each reasoning chunk (reasoning models). Defaults to
            False (one non-streaming call per turn); tool execution is unaffected
            either way. Exception: when ``tool_choice="required"``, a tool-enabled
            round's deltas are buffered and released as one end-of-round batch
            instead of live per-token, since a delta already streamed can't be
            un-streamed if that round then turns out to have no tool_calls and
            gets rejected (see ``_produce_turn``'s docstring below).
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

        When this turn is tool-enabled (``turn_tools`` set) and ``tool_choice ==
        "required"``, content/reasoning deltas are buffered instead of published live,
        released only once this turn's own ``tool_calls`` come back non-empty. A delta
        already streamed to ``on_tool_step`` can't be un-streamed, so once the caller's
        fail-closed check (below) rejects a turn that came back with no tool_calls,
        buffering is what keeps that turn's narration from ever reaching a consumer
        that would otherwise have shown it as an accepted answer. Trading live
        per-token delivery for that is only worth it under the explicit
        ``require_tool_calls`` opt-in floor -- the tool-free wrap-up completion
        (``turn_tools=None``) and the default ``tool_choice="auto"`` path are
        unaffected and keep streaming deltas live, per the round_boundary comment
        below.
        """
        if stream_deltas:
            if include_search and search_parameters is not None:
                # _stream_completion_one_turn doesn't forward search_parameters; warn so
                # streaming callers don't assume web grounding happened.
                logger.warning("Live Search not supported on the streaming tool loop; skipping")

            gate_required = bool(turn_tools) and tool_choice == "required"
            buffered: list[tuple[str, str]] = []

            def _on_content(delta: str) -> None:
                if on_tool_step is None or not delta:
                    return
                if gate_required:
                    buffered.append(("content", delta))
                else:
                    on_tool_step("content", delta)

            def _on_reasoning(delta: str) -> None:
                if on_tool_step is None or not delta:
                    return
                if gate_required:
                    buffered.append(("reasoning", delta))
                else:
                    on_tool_step("reasoning", delta)

            content, tool_calls = _stream_completion_one_turn(
                model,
                turn_messages,
                temperature=temperature,
                tools=turn_tools,
                tool_choice=tool_choice,
                on_content_delta=_on_content,
                on_reasoning_delta=_on_reasoning,
            )
            if gate_required and on_tool_step is not None and tool_calls:
                # Requirement satisfied this round -- release the buffered narration in
                # original order, same as the ungated live path would have delivered it.
                for kind, delta in buffered:
                    on_tool_step(kind, delta)
            # else (gate_required and no tool_calls): discard the buffer silently --
            # the caller raises immediately on seeing empty tool_calls (below), before
            # this content could otherwise be mistaken for an accepted answer.
            return content, tool_calls
        return _message_from_response(
            completion(
                model,
                turn_messages,
                temperature=temperature,
                tools=turn_tools,
                tool_choice=tool_choice,
                search_parameters=search_parameters if include_search else None,
            )
        )

    for round_idx in range(max_tool_rounds):
        # Live Search is billed per request — attach it only to the first turn so a
        # multi-round tool loop doesn't re-search (and re-bill) every round.
        content, tool_calls = _produce_turn(current, tools, include_search=round_idx == 0)
        if not tool_calls:
            if tool_choice == "required":
                # tool_choice="required" is a floor a deployment opted into (see
                # digigraph.tool_policy.require_tool_calls_for_workflow) specifically so a
                # tool-enabled turn can never silently answer without calling a tool. A
                # provider that honors tool_choice shouldn't reach this branch at all; one
                # that returns content anyway is a fail-open path we must not paper over by
                # returning that content as if it were a legitimate final answer.
                # NOTE: this does not extend to the tool-free wrap-up completion below (after
                # the round budget is exhausted) — that call passes tools=None, so neither
                # _produce_turn branch puts tool_choice on the wire for it.
                raise RuntimeError(
                    "run_tools: tool_choice='required' but the model returned no tool_calls "
                    f"in round {round_idx}"
                )
            return content or ""

        if on_tool_step is not None and content:
            # This round's content already streamed live via on_tool_step("content", ...)
            # inside _produce_turn, before tool_calls was known — that is unavoidable for
            # a live per-token stream (buffering the whole round to decide "is this
            # final" would delay the common single-round, no-tool-call case waiting on
            # a completion that was never provisional). What was missing is a signal,
            # emitted the moment tool_calls becomes known, marking that content as NOT
            # the final answer. Without it, a caller has no way to tell "the model
            # narrated its plan while also calling tools" apart from "this is the
            # answer" — confirmed in production (#2306 follow-up): a round's narration
            # ("I will load the full notes...") streamed as ordinary content and landed
            # directly in front of the next round's real answer with nothing between
            # them. Retroactive, not preventive — costs nothing extra token-wise, since
            # the content already streamed before this fires.
            #
            # Empty-narration tool rounds deliberately skip this callback: there is no
            # streamed content to demote, and emitting a vacuous boundary would reorder
            # consumer callbacks ahead of tool_call (see digigraph rag_stream tests).
            on_tool_step("round_boundary", {"round_idx": round_idx, "narration": content})

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
            # A pool worker starts with an *empty* context, so every ContextVar bound
            # per-request -- the BYOK key/base-url override above all (:func:`set_byok`)
            # -- reads as its default inside it. A parallel-safe tool that itself calls
            # an LLM would then bill the operator's key while the caller's was bound.
            # Copy per submit, never once for the batch: a single Context cannot be
            # entered concurrently and raises "is already entered" on the second thread.
            #
            # What the copy must NOT carry is the logical-call telemetry handle: a copy
            # propagates references, so all N workers would share one mutable handle and
            # race its ``last_call_id`` and deferred-record list. Hence the wrapper --
            # propagate credentials, not the mutable telemetry handle. It clears two
            # vars, not one: this module's, and (via the consumer's registered hook) any
            # logical-call var a consumer layers on top holding the same handle.
            with ThreadPoolExecutor(max_workers=len(parsed)) as executor:
                future_to_idx = {
                    executor.submit(
                        copy_context().run, _execute_tool_in_fan_out, execute_tool, name, args
                    ): i
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
                try:
                    result = execute_tool(name, args)
                except (RuntimeError, OSError, ValueError, TypeError, KeyError) as e:
                    # Mirror the parallel branch's except-tuple 3 lines above (line 167) —
                    # a raised exception here must become a recoverable tool result, not
                    # abort the whole run and discard every tool result already gathered
                    # this round.
                    result = {"content": str(e)}
                ordered.append(((tc_id, name, args), result))

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

    # Reaching here means every round through max_tool_rounds still returned tool_calls
    # (any round with no tool_calls returns early above) — the budget is genuinely
    # exhausted, not just "the model happened to stop." A forced tool-free completion
    # unconditionally follows below (see its own comment) — this log/signal always
    # precedes it.
    #
    # Guard against max_tool_rounds <= 0: `range(max_tool_rounds)` above is then empty,
    # so the for loop body never ran a single round — there is nothing to have
    # "exhausted." Firing the log/signal in that case would falsely claim the model
    # burned through a budget it was never given a chance to use.
    if max_tool_rounds > 0:
        logger.warning(
            "run_tools: exhausted max_tool_rounds=%d without the model returning an "
            "empty tool_calls response",
            max_tool_rounds,
        )
        if on_tool_step is not None:
            on_tool_step("round_limit_exhausted", {"max_tool_rounds": max_tool_rounds})

    # Force one more answer without tools, unconditionally -- not only when the last
    # round's own narration was empty. That narration is written *before* its
    # tool_calls are executed, so it can never reflect what those tools actually
    # returned; returning it directly would silently discard the tool results this
    # same round just appended to `current` (CodeRabbit follow-up review on PR #2361,
    # confirmed real: a round narrates a plan, calls a tool, the tool's result lands
    # in `current`, and the stale pre-execution narration used to be returned as if
    # it were the answer that used that result). Always synthesize from the full
    # transcript instead.
    #
    # `len(current) > len(messages)` is the max_tool_rounds<=0 guard from above: if no
    # round ever ran, there is no tool result to synthesize from, and `content` (used
    # in the fallback below) was never assigned this call.
    if len(current) > len(messages):
        current.append(
            {
                "role": "user",
                "content": "Based on the tool results above, provide a concise final answer.",
            }
        )
        final, _ = _produce_turn(current, None, include_search=False)
        return final or ""
    return content or ""
