# digillm – Architecture

`digillm` is the **single home for all LLM client / API-wrapper / tooling code**
in the digithings monorepo. It is a standalone, **provider-agnostic** library
extracted from the mature `digigraph.llm` implementation. It speaks to any
OpenAI-compatible endpoint and carries **no FastAPI / service coupling** and no
hard dependency on `digismith`.

Consumers: **twelve-x** adopts it now; **digigraph** and **digisearch** migrate
to it later (their current in-tree LLM modules are superseded by this package).

## Non-negotiables

- Python 3.12, Pydantic v2, full type hints, ruff line-length 100.
- Hard deps: `openai>=1.0`, `pydantic>=2` only.
- Optional extras: `[modes]` (PyYAML, for path-based mode resolution),
  `[trace]` (digismith, for LangSmith tracing), `[dev]` (pytest, ruff, pyyaml).
- No `import fastapi`; no `Request` objects anywhere in this package.

## Module map

| Module | Responsibility |
|--------|----------------|
| `digillm/types.py` | Shared TypedDict request, tool-call, tool-definition, and JSON-schema response payload shapes. |
| `digillm/overrides.py` | Per-request proxy-key and BYOK contextvars, reset helpers, and context managers. |
| `digillm/cache.py` | SHA-256 response-cache keying, TTL/eviction, and cache clearing. |
| `digillm/client.py` | Compatibility import surface plus provider registry/routing, retry/backoff, completion/search, telemetry runtime, and the tool-calling loop. |
| `digillm/structured.py` | `structured_completion` (json_schema → validated Pydantic model) and `resolve_model` (opt-in test/medium/best resolution). |
| `digillm/telemetry.py` | Strict provider-agnostic records for node runs, logical calls, physical attempts, artifact references, and fail-soft observer delivery. |
| `digillm/__init__.py` | Public API surface (re-exports). |

## Public API

```python
from digillm import (
  ArtifactRef, CacheStatus, CallPurpose, NodeRunRecord,
  ProviderCallRecord, ProviderAttemptRecord, TelemetryObserver, emit_telemetry,
    chat_completion, chat_completion_with_tools, structured_completion,
    get_client_for_model, get_client, register_provider, resolve_model,
    set_proxy_key, reset_proxy_key, get_proxy_key, proxy_key,   # proxy override
    set_byok, reset_byok, get_byok, byok, clear_byok,           # BYOK override
    set_fan_out_detach_hook,                                    # consumer detach hook
    clear_caches,
)
```

### Provider telemetry contracts

`NodeRunRecord`, `ProviderCallRecord`, and `ProviderAttemptRecord` separate graph work, one
logical invocation, and each physical provider request. All are frozen Pydantic v2 models with
`extra="forbid"`, producer-supplied stable UUIDs, closed lifecycle/retry enums, timezone-aware
UTC event times, and deterministic serialization. `ArtifactRef` carries identity and version only;
it never contains an artifact payload.

A logical cache hit has `attempt_count=0`. A successful non-cache call has at least one physical
attempt, and each retry after attempt 1 requires a closed `RetryReason`. Token usage and cost are
nullable: unavailable provider evidence is never represented as zero. Prompts, responses, search
text, API keys, secrets, and raw exceptions are not fields on any contract; only a sanitized
exception type may be recorded.

`TelemetryObserver` is an injectable synchronous sink boundary. `emit_telemetry` catches sink
failures and optionally reports only the record UUID and exception class, so telemetry cannot abort
the caller's portfolio work. The module starts no threads, opens no connections, and writes no
files on import. Task #1951 defines the vocabulary; Task #1955 adds the physical-attempt producer.
Task #1963 adds logical-call lifecycle and parentage. Full run/node/agent/ticker propagation and
the durable digiquant writer remain separate follow-up tasks.

### Logical provider-call instrumentation

**Purpose:** emit one terminal `ProviderCallRecord` for each logical invocation, including cache
hits, tool-loop turns, grounding, and structured repair. **Reason:** physical attempts prove that
transport work occurred but cannot explain why it existed, whether a cache answered it, which
call caused a follow-up, or what consumed the result. **Intent:** connect provider work to generic
research purpose and artifact disposition without importing digigraph, dashboard, ticker, or
portfolio semantics into this leaf library. **System contribution:** consumers can reconcile
logical research operations with physical reliability and cost evidence while preserving the
existing provider behavior.

`provider_call_context(...)` supplies a real `node_run_id`, closed `CallPurpose`, optional parent,
and exactly one successful disposition: immutable `ArtifactRef` values or a typed
`NoArtifactReason`. The context is optional. Calls without it retain incumbent aggregate and
physical-attempt behavior but do not fabricate a required node identity. Mutable call IDs, attempt
counters, retry reasons, and tool-follow-up lineage remain context-local; the registered observer
is process-wide so worker-thread attempts remain visible.

The outermost public invocation owns finalization. Nested wrappers, including OpenRouter search
through `completion()`, contribute to that one logical call rather than double-counting it. Each
tool-loop turn receives a fresh call ID and attempt counter; a follow-up references the preceding
selection call. Cache hits are successful zero-attempt calls with `CacheStatus.HIT`; direct search,
tool, live-search, and BYOK paths are explicitly bypassed. Failures and cancellations override any
prospective artifact disposition with `CALL_FAILED` or `CALL_CANCELLED`, and failures retain only
the sanitized exception class.

Consumers that validate a successful response after the provider wrapper returns may request
deferred finalization. The context handle buffers only successful logical records, permits the
latest success to receive its final no-artifact reason, and then delivers each record exactly once.
Failed and cancelled calls are already authoritative at the provider boundary and emit immediately.
This lets structured consumers append rejected output as `VALIDATION_REJECTED` instead of first
recording it as consumed and attempting a later correction.

Logical telemetry is observational and fail-soft. Record construction, optional provider evidence,
and observer delivery cannot alter cache ordering, retries/backoff, routing, tool execution,
return values, or raised exceptions. Unknown purpose or disposition must use the closed `UNKNOWN`
value rather than being silently omitted. Rollback is to stop injecting `provider_call_context`;
physical attempts and strict contracts remain intact. Task 1.5 owns durable buffering, flush, and
reconciliation.

`NodeRunRecord.fanout_key` (#1978) is an optional, bounded (1–200) label naming which fan-out item
one node execution was for. It is **opaque to digillm**: the producer supplies the string and this
package never interprets it. It is deliberately not called `ticker` — digigraph owns that
vocabulary, and `extra="forbid"` plus a test pin that boundary. A node with no fan-out cursor has no
key: absent, never `""` and never fabricated.

### Physical provider-attempt instrumentation

**Purpose:** emit one typed `ProviderAttemptRecord` for every provider request visible at
`digillm`'s transport boundary. **Reason:** aggregate usage counters collapse retries, failures,
latency, served-model identity, and missing evidence, so provider reliability and cost cannot be
reconciled. **Intent:** observe the incumbent provider behavior without changing retry counts,
backoff, routing, cache order, provider selection, response parsing, or exceptions. **System
contribution:** later dashboard persistence and reconciliation can distinguish provider-attempt
effects from logical-call, node, and portfolio effects.

`set_telemetry_observer(observer)` registers one process-wide sink, matching the existing startup
registration used by usage telemetry and ensuring provider calls made in worker threads remain
visible. The mutable logical-call UUID, attempt number, and next retry reason are held in a
`ContextVar`, so concurrent invocations cannot share counters. Passing `None` disables emission.
Observer failure, optional SDK metadata access, record construction, and delivery are all fail-soft;
none can alter the provider result or raised exception. Prompt/response/search payloads, secrets,
and exception messages never enter the record.

The attempt producer covers:

- each repository-visible `client.chat.completions.create(...)` invocation, including transient
  retries and empty-response retries under one generated call UUID;
- `client.responses.create(...)` in xAI web and X search; OpenRouter search delegates to
  `completion()` and is therefore counted once;
- streaming from request initiation through iterator exhaustion, recording success and final usage
  only after exhaustion, failure on iteration errors, and cancellation on generator or asyncio
  cancellation;
- served model, token usage, and cost only when the SDK/provider supplies valid evidence; missing or
  malformed optional evidence remains `None`, never zero.

The OpenAI SDK's default `max_retries=2` remains enabled. Those internal HTTP retries occur below
the repository-visible `create(...)` boundary and are opaque to this instrumentation. Therefore an
attempt record means one observable SDK invocation, not proof of exactly one HTTP exchange. A
canary test locks the SDK setting in place; changing or disabling it requires a separate measured
decision. Cache hits produce no physical attempt record.

digiquant migration `067_olympus_provider_telemetry.sql` owns the private normalized storage. Event
times remain producer facts; the database adds `recorded_at` as its write clock. That schema is not
part of `digillm` and does not create a persistence dependency for other consumers.

### `chat_completion`

```python
chat_completion(
    model: str,
    messages: list[ChatCompletionMessage],
    *,
    temperature: float = 0.2,
    tools: list[ToolDefinition] | None = None,
    tool_choice: str | dict = "auto",
    response_format: JsonSchemaResponseFormat | None = None,
    max_tokens: int | None = None,
) -> str | tuple[str, list[ToolCallDict] | None]
```

- `tools=None` → returns the content `str` (response-cached unless BYOK active).
- `tools` set → returns `(content, tool_calls)` for a tool loop (never cached).
- `response_format` → OpenAI json_schema structured output (mutually exclusive
  with `tools`).
- **The `model` argument is used as given** — a registered `provider/model_id`
  prefix routes to that provider and the bare `model_id` is sent on the wire;
  any other string is passed through unchanged. There is **no hidden env/YAML
  model substitution** (that was a digigraph deployment behavior; here mode
  selection is the explicit, opt-in `resolve_model`).
- **Self-prefixed model ids** (`_SELF_PREFIXED_MODELS` → `_wire_model`). Stripping
  one prefix assumes a provider's model id never repeats the provider's own name.
  OpenRouter's auto-router breaks that: its id *is* `openrouter/auto`, so its
  litellm form carries the prefix twice (`openrouter/openrouter/auto` — the form
  operators write in the README and in the research provider diagnostics under
  `digiquant/scripts/research/`; no tier config lists it) and stripping one still has
  to leave one behind. Ids listed in the table are restored after the
  split, so **both spellings reach the wire as `openrouter/auto`**.

  This matters for BYOK, which can only produce the single-prefix form:
  `digigraph.llm_auth.byok_routable_model` strips the provider's own prefix to a
  *fixpoint* and re-applies exactly one, and that fixpoint is load-bearing — it is
  what stops the middleware and the resolver disagreeing about a hostile header. So
  the seam was fixed here rather than in the normalizer, leaving the credential-path
  invariant untouched. Before this, a BYOK auto-router request reached the wire as a
  bare `auto`, which OpenRouter rejects, and the `endswith("/auto")` test that gates
  the #802 curated candidate pool silently never fired for it either.
- **Empty-response self-heal.** A 200-OK with no usable output (empty `choices` /
  blank content and no `tool_calls`) is treated as a transient provider hiccup and
  retried with a short backoff (`DIGILLM_EMPTY_RETRY_MAX` / `DIGILLM_EMPTY_RETRY_DELAY`).
  For `openrouter/` models, `OPENROUTER_FALLBACK_MODELS` attaches provider-fallback
  routing (`extra_body.models` + `route=fallback`) on the **primary** request via
  `_with_openrouter_cost_controls`; it does **not** swap models on an empty `200`
  (fallback routing fires on provider errors only). Empty retries re-ask the same
  model. A persistent blank is returned unchanged (callers stay graceful).

### `chat_completion_with_tools`

```python
chat_completion_with_tools(
    model, messages, tools,
    execute_tool: Callable[[str, dict], str | dict],
    *,
    temperature=0.2, max_tool_rounds=5,
    on_tool_step: Callable[[str, Any], None] | None = None,
    parallel_safe_tools: set[str] | None = None,
) -> str
```

Non-streaming loop. `parallel_safe_tools` replaces digigraph's import of
`digigraph.orchestration.registry.list_tool_names("parallel_safe")`: when *all*
tool calls in a round are in this set (and there is more than one), they run
concurrently; otherwise calls run sequentially.

Each concurrent call is submitted as `copy_context().run(_execute_tool_in_fan_out, ...)`.
A pool worker starts with an *empty* context, so an override bound by `set_byok` /
`set_proxy_key` reads as `None` inside a bare submit — and a parallel-safe tool that
calls an LLM itself would then bill the wrong key. The copy is taken **per submit**:
a single `Context` cannot be entered by two threads and raises `RuntimeError: cannot
enter context ... is already entered` in the second.

What the copy must *not* carry is the logical-call telemetry handle. A copy propagates
references, not values, so a bare submit would hand all N workers the one mutable
`ProviderCallContextHandle` the caller holds: each writes its `last_call_id` (leaving a
later follow-up call parented on whichever sibling finished last) and each appends to
the single deferred-record list that `finalize()` tuples and clears. So the wrapper
clears it first — **propagate credentials, not the mutable telemetry handle** — which is
what a worker inheriting an empty context saw for this module's var, and what keeps the
"context-local" half of the telemetry contract above true. Nesting fan-out calls under
their parent's logical call is a separate feature needing a per-worker handle and a
join-time merge.

That means clearing **two** vars per worker, not one. `detach_provider_call_context()`
reaches only this module's `_provider_call_metadata`, and a consumer may layer its own
logical-call var *holding the very same handle* — digigraph's
`usage._LOGICAL_CALL_CONTEXT` does. digillm is a leaf library and cannot import into a
consumer to clear it, exactly as it cannot write into a consumer's usage accumulator, so
the consumer registers a callback on the same terms: `set_fan_out_detach_hook(fn)`,
process-wide, no-op until registered, and a raising hook is logged rather than allowed to
fail the tool call. Leave it unregistered and the second var stays shared — the defect
moves one layer up rather than being fixed. The **serial** branch of a tool round runs in
the caller's own context, not a copy of it, so it deliberately clears neither: unbinding
the caller's live handle there would lose its deferred records.

### `structured_completion`

```python
structured_completion(
    model, messages, output_type: type[BaseModel],
    *, temperature=0.2, max_tokens=None, strict=True,
) -> BaseModel  # validated instance of output_type
```

Builds a json_schema `response_format` from `output_type`, calls
`chat_completion`, strips markdown fences, narrows to the outermost `{...}`,
and `model_validate`s. (digigraph's structured path returned a `str`; this
wrapper provides the validated-model contract twelve-x expects.)

When `strict=True` (the default), the schema is normalized via the OpenAI
SDK's own `openai.lib._pydantic.to_strict_json_schema` — plain
`output_type.model_json_schema()` sets `additionalProperties: false` only when
the model has `extra="forbid"`, and never force-lists every property in
`required` (fields with defaults are simply omitted), which OpenAI-family
strict-schema providers reject outright. Falls back to plain
`model_json_schema()` with a warning if that (private, unexported) SDK helper
is ever unavailable.

### `resolve_model`

```python
resolve_model(mode, modes: dict | None = None, *, path=None, default=None) -> str
```

Opt-in test/medium/best resolution. **Deployment-agnostic**: takes an explicit
`{mode: model}` mapping or a caller-supplied YAML `path` (flat mapping or a
`defaults:` sub-mapping, matching digithings' `model_modes.yaml`). It hardcodes
**no** config-directory location. Callers may also just pass a concrete model
string to `chat_completion` and skip this entirely.

## Provider routing

`get_client_for_model(model)` is the single client entry point:

- **House and BYOK path (LiteLLM):** when `OPENAI_API_BASE` is set **and is
  not** `openrouter.ai`, **every** call uses `get_client()`. Registered
  prefixes stay on the wire as LiteLLM `model_name` keys (digiquant pins are
  unprefixed OpenRouter slugs). There is no prefix-skip: BYOK does not open a
  direct vendor HTTP client.
- **BYOK through LiteLLM:** `set_byok(api_key, base_url)` still binds the
  user's token. With a LiteLLM proxy configured, that token is passed as
  LiteLLM clientside credentials (`extra_body.api_key` / `extra_body.api_base`)
  so LiteLLM authenticates to the vendor — or to the user's own OpenAI-compat
  endpoint — while the HTTP client stays on `OPENAI_API_BASE` with the house
  proxy key. Response cache is still skipped while BYOK is active.
  `_with_byok_litellm_pass_through` is a no-op when the base is the leftover
  OpenRouter rewrite (`openrouter.ai`).
- **Default base vs LiteLLM:** any non-empty `OPENAI_API_BASE` is a default
  base (prefix → `get_client()` so house `anthropic/claude-sonnet-5` does not
  hit api.anthropic.com). LiteLLM clientside pass-through is only the
  non-OpenRouter case. After leftover `apply_digiquant_openrouter_env()`
  (`digigraph/src/digigraph/model_config.py`) with no LiteLLM: prefixed BYOK
  uses the user Bearer against the vendor URL; leftover `gemini/` / `xai/`
  stay vendor clients (`GEMINI_API_KEY` / `XAI_API_KEY`).
- **Diagnostics without a proxy:** a `provider/model_id` prefix matching the
  registry routes to a dedicated vendor client (BYOK: uncached user key;
  otherwise cached operator key). Every other model string uses `get_client()`
  (`OPENAI_API_BASE` / `OPENAI_API_KEY`). OpenRouter-backed house slugs
  through LiteLLM (unprefixed `deepseek/…`, house `anthropic/…`) still get
  `_with_openrouter_cost_controls` `extra_body` (`require_parameters` for
  tools / json_schema). Native `gpt-4o-mini` and `ollama/*` do not.

Built-in registry (`xai`, `gemini`, `openrouter`, `anthropic`): prefix parsing
and no-LiteLLM diagnostics — not a skip around LiteLLM. Extend at
runtime via `register_provider(prefix, base_url, api_key_env)`.

A missing required provider key raises `RuntimeError` (no silent fallback), so
misconfiguration surfaces immediately rather than masquerading as a default-model
call.

Every client — cached, provider, and both uncached BYOK paths — is constructed with
an **explicit** `timeout=` (#1734). The value is `httpx.Timeout(600, connect=5.0)`,
byte-identical to the OpenAI SDK default it replaces, so this states the existing
bound rather than changing it: previously the bound lived only in the SDK's
constants module, invisible from this repo and free to move on a dependency bump.
Override with `DIGILLM_REQUEST_TIMEOUT_SECONDS` / `DIGILLM_CONNECT_TIMEOUT_SECONDS`.

Both are read **once at import**, not per call, because `_client_cache` is keyed on
`(api_key, base_url)` only — a call-time env read would hand a cached client its
stale timeout and falsify the cache's "recreated when env changes" contract.

The silence budget for one `completion` is the product of three layers, not this
value alone: the SDK's own `max_retries=2` (3 HTTP attempts) x `_create_with_retry`'s
12 attempts, each attempt bounded by the read timeout. Lowering
`DIGILLM_REQUEST_TIMEOUT_SECONDS` is the only single-knob way to shrink that product.

### Usage observer contract

`set_usage_observer(callback)` installs one process-level, best-effort observer used by
`digigraph.usage`. A terminal model or search operation emits exactly one callback with fixed
metadata: kind, model, success, duration, application-level retry count, usage totals, cost,
and source count. `_create_with_retry` invokes an internal attempt callback immediately before
each SDK call, so `retry_count` is the actual helper-attempt count minus one; empty-response and
xAI 410 ungrounded fallbacks contribute to the same count. Direct Responses API searches report
their wall-clock duration too.

The observer receives no messages, prompts, response bodies, tool arguments/results,
credentials, or reasoning. It is optional and observer exceptions are swallowed so telemetry
cannot change the public completion/search return contract or fail a provider call.

## Per-request override contract (contextvars)

This is the contract **digigraph** will use after migration (follow-up #12). The
header parsing stays in digigraph's FastAPI middleware; digillm exposes only
plain contextvar setters and reads them when building clients.

| Setter | Reads in | Effect |
|--------|----------|--------|
| `set_proxy_key(token)` / `reset_proxy_key(tok)` (or `with proxy_key(token):`) | `get_client()` default path | Per-request LiteLLM proxy / bearer key. Priority: proxy override → `LITELLM_PROXY_API_KEY` → `OPENAI_API_KEY`. |
| `set_byok(api_key, base_url=...)` / `reset_byok(tok)` (or `with byok(api_key, base_url):`) | `get_client()` / `_create_with_retry` | Bring-your-own-key. With a LiteLLM proxy (`OPENAI_API_BASE` set and not `openrouter.ai`), the LiteLLM client is reused and the user's key/base go in `extra_body` (clientside credentials). Without LiteLLM, returns an **uncached** client at the user's endpoint (prefixed BYOK against the vendor URL). Always **bypasses the response cache**. |
| `clear_byok()` | same var, no token | Drops the override token-free — for a thread running inside a `copy_context()` snapshot, which inherits the binding but not the reset token. Use `reset_byok` in the frame that bound it; clearing there would strand that frame's token. |
| `detach_provider_call_context()` | `_provider_call_metadata`, no token | Drops the inherited logical-call metadata — for a fan-out worker running inside a `copy_context()` snapshot, which would otherwise share the caller's *mutable* `ProviderCallContextHandle` with every sibling. Restores what a worker with an empty context saw **for this var only**. |
| `set_fan_out_detach_hook(fn)` | run at the top of every *parallel* tool worker | Lets a consumer clear a logical-call var it layers on top of digillm's — necessarily holding the same mutable handle, so the copy would share it. Process-global, `None` disables, a raising hook is logged and the tool call proceeds. The hook runs inside the worker's copied context, so it must clear token-free and must not touch credentials — carrying those across is the point of the copy. |

digigraph's middleware will translate (today's code shown for reference):

```python
# digigraph FastAPI middleware (NOT in digillm):
tok = set_proxy_key(request.headers.get("x-litellm-proxy-key"))
try:
    ...  # handle request
finally:
    reset_proxy_key(tok)
```

### Precedence notes (decisions)

- **No BYOK skip of LiteLLM.** When `OPENAI_API_BASE` is a LiteLLM proxy (set
  and not `openrouter.ai`), house and BYOK share one HTTP client (the proxy).
  Prefix matching does not open a vendor client. The user's key is LiteLLM
  `extra_body.api_key` / `api_base`. The leftover OpenRouter CLI rewrite is a
  default base, not that proxy. House `anthropic/` stays on that default base
  (not api.anthropic.com); leftover `gemini/` / `xai/` stay vendor clients.
- **BYOK is `(api_key, base_url)` — provider-agnostic.** digigraph carried
  `(key, provider)` with an unfinished Anthropic-passthrough special-case. That
  provider coupling is intentionally **dropped**: a BYOK caller supplies the
  endpoint directly.
- **Response-cache + BYOK.** The SHA-256 response-cache key intentionally omits
  the API key. To prevent a per-user BYOK response from being read from or
  written to the shared in-process cache, `chat_completion` **skips the cache
  entirely while a BYOK override is active**.

## Intentionally NOT carried over from `digigraph.llm`

- `from digigraph.orchestration.registry import list_tool_names` → replaced by
  the `parallel_safe_tools` parameter.
- `from digigraph.project_config import DigiProjectConfig` + `DIGI_CONFIG_PATH`
  defaulting to `"config"` → removed; mode resolution is caller-driven.
- Streaming (`_stream_completion_one_turn` and the streaming tool branches) —
  out of scope for the extracted core; the non-streaming loop is retained.
- Deployment quirks: `OLLAMA_MODEL` / `resolve_effective_model` env substitution,
  direct-Ollama `:11434` detection, and the `ollama-cloud/` prefix stripping. The
  model arg is honored as given; deployments wire model selection via
  `resolve_model` or a concrete model string.
- FastAPI `Request`-parsing override functions (`push_lite_llm_proxy_header`,
  `push_byok_header`, …) → replaced by plain contextvar setters; header parsing
  stays in the consuming service.

## Tracing

`@traceable("chat_completion")` is imported from `digismith.trace` inside a
`try/except ImportError` that falls back to a no-op decorator. digillm therefore
has **no hard dependency** on digismith; install `digillm[trace]` (or have
digismith on the path) plus `LANGSMITH_API_KEY` to enable spans.

## Environment variables

| Var | Used by | Purpose |
|-----|---------|---------|
| `OPENAI_API_KEY` / `OPENAI_API_BASE` | default client | Endpoint + key for non-prefixed models (LiteLLM / Ollama / OpenRouter / OpenAI). |
| `LITELLM_PROXY_API_KEY` | default client | Proxy bearer key (below per-request override, above `OPENAI_API_KEY`). |
| `XAI_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` | provider clients | Keys for the corresponding `provider/` prefixes. |
| `DIGILLM_REQUEST_TIMEOUT_SECONDS` | all clients | Read/write/pool timeout per HTTP attempt (default 600, = the OpenAI SDK default). Read once at import. |
| `DIGILLM_CONNECT_TIMEOUT_SECONDS` | all clients | Connect timeout (default 5, = the OpenAI SDK default). Separate from the above so a wider read timeout cannot silently widen connect. |
| `DIGI_LLM_CACHE_TTL_SECONDS` | response cache | Response-cache TTL (default 3600). |
| `DIGI_TOOL_MESSAGE_MAX_CHARS` | tool loop | Cap on tool-result text injected into the next turn (default 12000). |
| `DIGILLM_EMPTY_RETRY_MAX` / `DIGILLM_EMPTY_RETRY_DELAY` | `completion` | Empty-response self-heal: retry count (default 2) + backoff seconds (default 2.0). |
| `OPENROUTER_FALLBACK_MODELS` | `completion` | Comma-separated cheap models for OpenRouter provider-fallback routing on an empty retry. |

## Tests and CI

```bash
pytest digillm/tests -q          # 57 tests, offline — every provider call is monkeypatched
ruff check digillm/src digillm/tests && ruff format --check digillm/src digillm/tests
```

CI gate: [`.github/workflows/test-digillm.yml`](../.github/workflows/test-digillm.yml),
wired into `ci.yml` behind the `digillm` path filter in `scripts/ci_paths.yaml`.
Added in #1788 — before that this suite ran in **no** lane, and a combined
`pytest` from the repo root could not even collect it: `digillm/tests/__init__.py`
claimed the top-level `tests` package name that the repo-root `tests/` directory
already owns, so collection died with `No module named 'tests.test_digillm'` and
took `make test-unit` down with it. Do not reintroduce that file.

The suite is marked `unit` module-wide (`pytestmark = pytest.mark.unit`, the shape
`digifetch/tests` uses), so it contributes to `make test-unit`. Until #1788 it
carried no marker at all and `pytest digillm/tests -m unit` selected **zero** of
its tests. Mark new tests by leaving that module-level assignment alone rather
than decorating individually.

Two config details that are easy to get wrong here:

- The `unit` marker is registered in **`digillm/pyproject.toml`**, not only in the
  repo-root `pytest.ini`. Because this package's `pyproject.toml` carries a
  `[tool.pytest.ini_options]` section, `pytest digillm/tests` resolves rootdir to
  `digillm/` and reads *that* file as its configfile — the root `pytest.ini`'s
  `markers` never applies, and without the local registration every run prints
  `PytestUnknownMarkWarning`. (`digifetch` needs no equivalent: it has no
  `[tool.pytest.ini_options]`, so it falls through to the root config.)
- The CI lane still runs unfiltered (`pytest digillm/tests`, no `-m unit`), so a
  future test that somehow escapes the marker is still executed rather than
  silently skipped by a green lane.

## Monorepo integration (follow-ups for the integrator)

These are **outside this package** and intentionally **not** done here:

1. **Remove the `digibase` `[llm]` extra** from `digibase/pyproject.toml` — LLM
   code leaves `digibase`. (`digibase/src/digibase/llm.py` is deleted by this
   change.)
2. **Register `digillm` in the monorepo dev-install list** in the root
   `ARCHITECTURE.md` (around line 413), e.g.:

   ```bash
   pip install -e ./digibase -e ./digillm -e "./digismith[langsmith]" \
               -e ./digikey -e "./digigraph[dev]" -e "./digiquant[dev]" \
               -e "./digisearch[dev]"
   ```
3. **Repoint twelve-x** `nodes/llm.py` from `digibase.llm` to
   `digillm.structured_completion` (separate repo).
4. **digigraph migration (#12):** repoint `digigraph/llm.py` to `digillm` and
   move the `X-LiteLLM-Proxy-Key` / `X-BYOK-*` header parsing into digigraph
   middleware that calls `set_proxy_key` / `set_byok`. Not done here;
   `digigraph/llm.py` is untouched by this change.
```
