---
type: library-guide
title: digillm Library
description: digillm provider-agnostic LLM client — routing, tool loop, cache, structured output, MCP server, and telemetry.
tags: [digillm, llm, openai-compatible, library]
sources:
 - id: openwiki-source-404f95ee629d95d7c5c2422a
   resource: repo://digillm/ARCHITECTURE.md
 - id: openwiki-source-3b0f3d164015c293da5dd7f8
   resource: repo://digillm/src/digillm/client.py
 - id: openwiki-source-662707e0deb8d4a37c70adca
   resource: repo://digillm/src/digillm/telemetry.py
verified:
  - by: openwiki/0.5.0
    at: 2026-09-19T12:20:11.463Z
generated: { by: "openwiki/0.5.0", at: "2026-09-19T12:20:11.463Z" }
---

# digillm Library

digillm is the single home for LLM client code in the monorepo: a standalone,
provider-agnostic library speaking to any OpenAI-compatible endpoint. **House
default** when `CHEAPERINFERENCE_API_KEY` is set is
[Cheaper Inference](../../docs/providers/cheaperinference.md) (hosted LiteLLM
alternative); otherwise OpenRouter. Force OpenRouter with
`DIGI_HOUSE_UPSTREAM=openrouter`. LiteLLM remains the local swap layer via
`OPENAI_API_BASE` on a trusted-proxy allowlist. No FastAPI; no hard dependency on
digismith. Hard deps are `openai>=1.0` + `pydantic>=2`; mode resolution, tracing,
MCP, and dev tools ride extras. Consumers: twelve-x now; digigraph and
digisearch migrate later.

## Provider routing

`register_provider(prefix, base_url, api_key_env)` maps `provider/` model prefixes
to vendor endpoints. Four providers are built-in: `xai`, `gemini`, `openrouter`,
`anthropic`. `get_client_for_model()` is the single client entry point, resolving
per request across these paths in priority order:

1. **Cheaper Inference catalog hit** — when `CHEAPERINFERENCE_API_KEY` is set and
   the model is mapped in `_CHEAPERINFERENCE_HOUSE_SLUG_TO_BARE`, the bare CI
   catalog id reaches a direct CI client. A catalog miss (sonar, `:online`,
   anthropic, grok-4.3/4.6) fails fast with `RuntimeError` — no silent OpenRouter
   fallback.
2. **LiteLLM proxy** — when `OPENAI_API_BASE` canonicalizes to a trusted-proxy
   base (default `:4000` loopback URLs, overridable via
   `DIGILLM_TRUSTED_LITELLM_BASES`), *every* call routes through `get_client()`.
   Registered prefixes stay on the wire as LiteLLM `model_name` keys.
3. **OpenRouter CLI rewrite** — when `OPENAI_API_BASE` contains
   `openrouter.ai`, house `anthropic/` and `openrouter/` stay on the default
   client (not api.anthropic.com); `gemini/` and `xai/` use their vendor
   clients.
4. **Direct vendor** — a registered `provider/model_id` prefix opens a vendor
   client cached by `(provider, api_key)`. A missing API key raises
   `RuntimeError` fail-fast.
5. **Default client** — every other model string uses `get_client()`, cached by
   `(api_key, base_url)`.

### BYOK and proxy-key overrides

Per-request credentials are scoped via contextvars (`overrides.py`), never
process-global:

- **`set_proxy_key(token)`** / **`proxy_key(token)`** context manager — sets a
  per-request bearer key. Priority: proxy override → `LITELLM_PROXY_API_KEY` →
  `OPENAI_API_KEY` → dev sentinel (`sk-no-key-required`, only for declared
  trusted LiteLLM bases).
- **`set_byok(api_key, base_url)`** / **`byok(api_key, base_url)`** context
  manager — bring-your-own-key. On a LiteLLM proxy path, the user's key rides
  `extra_body.api_key` / `extra_body.api_base` (clientside credentials) with
  `cache: {no-cache, no-store}`; `api_base` is validated against the five
  `config/byok-providers.json` catalog hosts. Without a declared proxy, BYOK
  returns an uncached client at the user's endpoint.
- **`clear_byok()`** — drops the BYOK override token-free for fan-out workers
  inside a `copy_context()` snapshot.

BYOK always bypasses the in-process response cache.

### Cheaper Inference house routing

`cheaperinference_house_preferred()` returns `True` when
`CHEAPERINFERENCE_API_KEY` is set, unless overridden by `DIGI_HOUSE_UPSTREAM` or
`CHEAPERINFERENCE_HOUSE`. When preferred, `_effective_model_id()` translates
mapped OpenRouter house slugs to CI bare catalog ids. A catalog miss raises
`RuntimeError` — the caller must remap the pin or set
`DIGI_HOUSE_UPSTREAM=openrouter`.

The LiteLLM proxy path is excluded from CI direct routing: proxy overlays handle
model name merging separately.

## Completion and tool loop

### `completion`

```python
completion(
    model: str,
    messages: list[ChatCompletionMessage],
    *,
    temperature: float = 0.2,
    tools: list[ToolDefinition] | None = None,
    tool_choice: str | ToolArguments = "auto",
    response_format: JsonSchemaResponseFormat | None = None,
    max_tokens: int | None = None,
    usage_kind: str = "chat",
) -> ChatCompletion
```

Returns an OpenAI `ChatCompletion` object. Tool-free, non-BYOK requests are
cached by SHA-256 of the request parameters; cached responses rehydrate as
`ChatCompletion`. `tools` and `response_format` are mutually exclusive (raises
`ValueError`).

Banned models (`ollama/qwen3:8b` and suffixed variants case-insensitive) are
rejected with `ValueError` before any provider call — digillm is the central
source of truth for the #3078 house policy.

**Empty-response self-heal**: a 200-OK with no usable output triggers retries
(`DIGILLM_EMPTY_RETRY_MAX`, default 4; `DIGILLM_EMPTY_RETRY_BACKOFF`, default
5s). A persistent blank returns unchanged — callers stay graceful.

### `run_tools`

```python
run_tools(
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
) -> str
```

Non-streaming tool-calling loop. `parallel_safe_tools` enables concurrent
dispatch via `ThreadPoolExecutor` with per-worker `copy_context()` snapshots
that propagate credentials but drop the mutable telemetry handle. Tool result
text is capped at `DIGI_TOOL_MESSAGE_MAX_CHARS` (default 12000) before
injection into the next turn.

**Same-tool error breaker** (#3078): after `DIGILLM_SAME_TOOL_ERROR_LIMIT`
(default 2) consecutive same-tool+same-error failures, `run_tools` raises
`RuntimeError`. Any successful tool call resets the streak.

When `max_tool_rounds` is exhausted, a forced tool-free completion synthesizes
the final answer from the full transcript — never returns stale
pre-tool-execution narration.

**Streaming** (`stream_deltas=True`): each assistant turn uses `stream=True`.
Content/reasoning deltas are delivered live via `on_tool_step("content", delta)`
and `on_tool_step("reasoning", delta)`. When `tool_choice="required"`, deltas
are buffered and released only when tool calls confirm the turn was valid;
discarded if the turn returns no tool calls.

### `structured_completion`

```python
structured_completion(
    model: str,
    messages: list[ChatCompletionMessage],
    output_type: type[T],
    *,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    strict: bool = True,
) -> T  # validated Pydantic instance
```

Builds a json_schema `response_format` from `output_type`, calls `completion`,
strips markdown fences, narrows to the outermost `{...}`, and validates with
`output_type.model_validate`. When `strict=True`, the schema is normalized via
the OpenAI SDK's `openai.lib._pydantic.to_strict_json_schema` — plain
`model_json_schema()` does not satisfy strict-schema providers because it omits
default-valued fields from `required` and may not set `additionalProperties:
false`.

### `resolve_model`

```python
resolve_model(
    mode: str,
    modes: dict[str, str] | None = None,
    *,
    path: str | Path | None = None,
    default: str | None = None,
) -> str
```

Opt-in test/medium/best mode resolution. Takes an explicit `{mode: model}`
mapping or a YAML path (flat or `defaults:` sub-mapping). Requires PyYAML
(`[modes]` extra) for the path branch. Hardcodes no config location.

### Retry and concurrency

`_create_with_retry` wraps `client.chat.completions.create` with exponential
backoff (5s start, doubling, 300s cap, 25% jitter) on `RateLimitError`,
`InternalServerError`, `APIConnectionError`, and `APITimeoutError`. Attempts cap
at `DIGILLM_PROVIDER_MAX_ATTEMPTS` (default 12; daily pipeline sets 2).

`DIGILLM_MAX_CONCURRENT_CALLS` (default 8) caps in-flight logical calls via a
process-wide `BoundedSemaphore`, smoothing fan-out bursts. The semaphore is held
for the full logical call including backoffs.

Every client is constructed with an explicit `httpx.Timeout(600, connect=5.0)`
(#1734), overridable via `DIGILLM_REQUEST_TIMEOUT_SECONDS` and
`DIGILLM_CONNECT_TIMEOUT_SECONDS` — read once at import to preserve the
client-cache contract.

## Cache

`cache.py` provides an in-process response cache keyed by SHA-256 of `(model,
messages, temperature, response_format, max_tokens)`. TTL is set by
`DIGI_LLM_CACHE_TTL_SECONDS` (default 3600). Max 256 entries; oldest is evicted
at capacity. Cached responses are serialized and rehydrated as `ChatCompletion`
on hit, keeping the return type consistent.

Cache is bypassed when tools are present or a BYOK override is active — tool
calls may have side effects, and BYOK keys must not pollute or read the shared
cache. `clear_caches()` clears both the response cache and the client cache
(primarily for tests).

## MCP server

`python -m digillm.mcp_server` exposes the serializable slice of digillm as an
MCP server (`[mcp]` extra, `mcp>=1.2,<2`). Exposes one tool:

- **`complete`** — single chat completion with optional `max_tokens` and
  optional JSON-schema response contract. Returns `{"content": str, "model":
  str}`.

`run_tools` and `structured_completion` stay library-only — they need a
caller-side `execute_tool` callable / Pydantic model class that cannot cross the
MCP boundary.

**Transport and trust model**: defaults to streamable HTTP on
`127.0.0.1:8768` (`DIGILLM_MCP_PORT` override, `--host` for wider bind).
`--stdio` suits Claude Desktop. Loopback-only by design — no supervisord
program, stack slot, or Worker route. A wider bind needs gateway auth since
callers spend the operator key. Per-request BYOK/proxy-key contextvars do not
cross the MCP boundary.

## Telemetry

`telemetry.py` defines strict, frozen Pydantic v2 models (`extra="forbid"`) for
provider-agnostic observability:

| Model | Scope | Key fields |
|-------|-------|------------|
| `NodeRunRecord` | One execution of a graph node | `node_run_id`, `run_id`, `node_name`, `fanout_key`, `outcome`, `artifacts` |
| `ProviderCallRecord` | One logical invocation | `call_id`, `node_run_id`, `parent_call_id`, `purpose`, `requested_model`, `cache_status`, `outcome`, `attempt_count`, `artifacts`, `no_artifact_reason`, `error_type` |
| `ProviderAttemptRecord` | One physical provider request | `attempt_id`, `call_id`, `attempt_number`, `provider`, `requested_model`, `served_model`, `outcome`, `retry_reason`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `error_type` |

All timestamps must be UTC. Token usage and cost are nullable — unavailable
provider evidence is never represented as zero. Prompts, responses, search text,
API keys, secrets, and raw exception messages are never fields on any contract;
only a sanitized `error_type` (the exception class name) may be recorded.

A logical cache hit has `attempt_count=0`. A successful non-cache call requires
at least one physical attempt. The first attempt's `retry_reason` is always
`NOT_APPLICABLE`; retry attempts require a closed `RetryReason`.

`call_id` links physical attempts to their logical call. `parent_call_id` chains
follow-up calls (e.g., tool selection → tool result synthesis). `fanout_key` is
opaque to digillm — the producer supplies a bounded label (1–200 chars) that
digillm never interprets.

### Observer delivery

`set_telemetry_observer(observer)` registers one process-wide synchronous sink.
`emit_telemetry` catches sink failures and optionally reports only the record
UUID and exception class via `on_failure` — telemetry never aborts caller work.
Observers receive records but own buffering and persistence.

Logical-call metadata is supplied via `provider_call_context(...)`, a context
manager that injects `node_run_id`, `purpose`, `parent_call_id`, `artifacts`, and
`no_artifact_reason` without changing provider call signatures. The context is
optional; calls without it retain physical-attempt behavior but do not fabricate
a required node identity. Deferred finalization (`defer_finalization=True`)
buffers successful logical records so consumers can append a validation-rejected
disposition before delivery.

`detach_provider_call_context()` drops inherited logical-call metadata for
fan-out workers inside `copy_context()` snapshots. Consumers that layer their
own logical-call ContextVar register a `set_fan_out_detach_hook(fn)` to clear
it alongside.

### Usage observer

`set_usage_observer(callback)` installs one process-level best-effort sink called
after each completion. The observer receives `kind` (default `"chat"`;
`"web_search"`, `"empty_retry"`, etc.), `model`, `prompt_tokens`,
`completion_tokens`, `ok`, `duration_ms`, `retry_count`, and cost. Observer
errors are swallowed.

## Public API surface

```python
from digillm import (
    # Completion and tools
    completion, run_tools, structured_completion,
    # Model resolution
    resolve_model,
    # Provider routing
    get_client, get_client_for_model, register_provider,
    is_registered_provider, get_provider_api_key_env,
    # Per-request credential overrides
    set_proxy_key, reset_proxy_key, get_proxy_key, proxy_key,
    set_byok, reset_byok, get_byok, byok, clear_byok,
    # Cheaper Inference
    cheaperinference_house_preferred, cheaperinference_bare_id_for_house_slug,
    # Telemetry
    set_telemetry_observer, set_usage_observer,
    provider_call_context, detach_provider_call_context,
    set_fan_out_detach_hook,
    # Cache
    clear_caches,
    # Telemetry types
    ArtifactRef, CacheStatus, CallPurpose, NoArtifactReason,
    NodeRunRecord, ProviderCallRecord, ProviderAttemptRecord,
    emit_telemetry,
)
```

## Environment variables

| Var | Purpose |
|-----|---------|
| `OPENAI_API_BASE` / `OPENAI_API_KEY` | Default client endpoint + key |
| `CHEAPERINFERENCE_API_KEY` | House Cheaper Inference routing (auto-enabled when set) |
| `CHEAPERINFERENCE_API_BASE` | CI endpoint override (default `https://api.cheaperinference.com/v1`) |
| `DIGI_HOUSE_UPSTREAM` | Force `openrouter`/`or` or `cheaperinference`/`ci` |
| `CHEAPERINFERENCE_HOUSE` | `0`/`false`/`no`/`off` to disable CI; `1`/`true`/`yes`/`on` to enable |
| `DIGILLM_TRUSTED_LITELLM_BASES` | Comma-separated proxy allowlist replacing the default `:4000` URLs |
| `LITELLM_PROXY_API_KEY` | Proxy bearer (below per-request override, above `OPENAI_API_KEY`) |
| `XAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` | Vendor API keys |
| `DIGILLM_REQUEST_TIMEOUT_SECONDS` | Read timeout per HTTP attempt (default 600) |
| `DIGILLM_CONNECT_TIMEOUT_SECONDS` | Connect timeout (default 5) |
| `DIGILLM_PROVIDER_MAX_ATTEMPTS` | Total attempts per logical call (default 12; pipeline: 2) |
| `DIGILLM_MAX_CONCURRENT_CALLS` | Max in-flight provider calls (default 8) |
| `DIGILLM_EMPTY_RETRY_MAX` | Empty-response retry count (default 4; pipeline: 1) |
| `DIGILLM_EMPTY_RETRY_BACKOFF` | Empty-response backoff seconds (default 5.0) |
| `DIGI_LLM_CACHE_TTL_SECONDS` | Response-cache TTL (default 3600) |
| `DIGI_TOOL_MESSAGE_MAX_CHARS` | Tool-result text cap (default 12000) |
| `DIGILLM_SAME_TOOL_ERROR_LIMIT` | Consecutive same-error limit (default 2) |
| `DIGILLM_MCP_PORT` | MCP server port (default 8768) |
| `DIGILLM_MCP_HOST` | MCP server bind host (default `127.0.0.1`) |

## Intentionally out of scope

- **No vendor search tooling.** No `openrouter_web_search`, Exa, xAI Live
  Search, Responses-API helpers, or provider `extra_body` preference dials.
  Grounding prompts belong to consumers (e.g. `digigraph.llm_client`).
- **No fallback chain.** Provider errors surface fail-fast — no silent
  model/provider fallback.
- **No FastAPI / service coupling.** digillm never imports FastAPI or accepts
  `Request` objects.
- **MCP hosting is loopback-only.** No stack slot, supervisord program, or
  Worker route.
- **Tracing is optional.** `@traceable` from digismith degrades to a no-op
  when digismith is absent (`[trace]` extra).
