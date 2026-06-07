# DigiLLM – Architecture

`digillm` is the **single home for all LLM client / API-wrapper / tooling code**
in the DigiThings monorepo. It is a standalone, **provider-agnostic** library
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
| `digillm/client.py` | Provider registry + routing, client cache, retry/backoff, SHA-256 response cache, `chat_completion`, the tool-calling loop, tool-call types, and the per-request override contextvars. |
| `digillm/structured.py` | `structured_completion` (json_schema → validated Pydantic model) and `resolve_model` (opt-in test/medium/best resolution). |
| `digillm/__init__.py` | Public API surface (re-exports). |

## Public API

```python
from digillm import (
    chat_completion, chat_completion_with_tools, structured_completion,
    get_client_for_model, get_client, register_provider, resolve_model,
    set_proxy_key, reset_proxy_key, get_proxy_key, proxy_key,   # proxy override
    set_byok, reset_byok, get_byok, byok,                       # BYOK override
    clear_caches,
)
```

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

### `structured_completion`

```python
structured_completion(
    model, messages, output_type: type[BaseModel],
    *, temperature=0.2, max_tokens=None, strict=True,
) -> BaseModel  # validated instance of output_type
```

Builds a json_schema `response_format` from `output_type.model_json_schema()`,
calls `chat_completion`, strips markdown fences, narrows to the outermost
`{...}`, and `model_validate`s. (digigraph's structured path returned a `str`;
this wrapper provides the validated-model contract twelve-x expects.)

### `resolve_model`

```python
resolve_model(mode, modes: dict | None = None, *, path=None, default=None) -> str
```

Opt-in test/medium/best resolution. **Deployment-agnostic**: takes an explicit
`{mode: model}` mapping or a caller-supplied YAML `path` (flat mapping or a
`defaults:` sub-mapping, matching DigiThings' `model_modes.yaml`). It hardcodes
**no** config-directory location. Callers may also just pass a concrete model
string to `chat_completion` and skip this entirely.

## Provider routing

`get_client_for_model(model)` is the single client entry point:

- A `provider/model_id` prefix matching the registry routes to a dedicated,
  **cached** client (`base_url` + key from the provider's env var).
- Every other model string falls back to `get_client()` — the default
  `OPENAI_API_BASE` / `OPENAI_API_KEY` path (LiteLLM proxy, Ollama, OpenRouter,
  or OpenAI direct).

Built-in registry: `xai`, `gemini`, `groq`, `openrouter`. Extend at runtime via
`register_provider(prefix, base_url, api_key_env)` — no code change needed.

A missing required provider key raises `RuntimeError` (no silent fallback), so
misconfiguration surfaces immediately rather than masquerading as a default-model
call.

## Per-request override contract (contextvars)

This is the contract **digigraph** will use after migration (follow-up #12). The
header parsing stays in digigraph's FastAPI middleware; digillm exposes only
plain contextvar setters and reads them when building clients.

| Setter | Reads in | Effect |
|--------|----------|--------|
| `set_proxy_key(token)` / `reset_proxy_key(tok)` (or `with proxy_key(token):`) | `get_client()` default path | Per-request LiteLLM proxy / bearer key. Priority: proxy override → `LITELLM_PROXY_API_KEY` → `OPENAI_API_KEY`. |
| `set_byok(api_key, base_url=...)` / `reset_byok(tok)` (or `with byok(api_key, base_url):`) | `get_client()` default path | Bring-your-own-key. Returns an **uncached** client (user creds must not accumulate in process memory) and **bypasses the response cache**. |

Digigraph's middleware will translate (today's code shown for reference):

```python
# digigraph FastAPI middleware (NOT in digillm):
tok = set_proxy_key(request.headers.get("x-litellm-proxy-key"))
try:
    ...  # handle request
finally:
    reset_proxy_key(tok)
```

### Precedence notes (decisions)

- **Provider prefix wins over BYOK on routing.** `get_client_for_model` checks
  the prefix first; BYOK/proxy overrides only affect the *default* (non-prefixed)
  client path. This mirrors digigraph's behavior.
- **BYOK is `(api_key, base_url)` — provider-agnostic.** Digigraph carried
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
| `DIGI_LLM_CACHE_TTL_SECONDS` | response cache | Response-cache TTL (default 3600). |
| `DIGI_TOOL_MESSAGE_MAX_CHARS` | tool loop | Cap on tool-result text injected into the next turn (default 12000). |

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
