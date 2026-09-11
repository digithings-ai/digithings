---
type: library-guide
title: digillm Library
description: digillm provider-agnostic LLM client — routing, tool loop, cache, structured output, and telemetry.
tags: [digillm, llm, openai-compatible, library]
sources:
  - id: openwiki-source-404f95ee629d95d7c5c2422a
    resource: repo://digillm/ARCHITECTURE.md
  - id: openwiki-source-3b0f3d164015c293da5dd7f8
    resource: repo://digillm/src/digillm/client.py
  - id: openwiki-source-662707e0deb8d4a37c70adca
    resource: repo://digillm/src/digillm/telemetry.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
---

# digillm Library

digillm is the single home for LLM client code: a standalone,
provider-agnostic library speaking to any OpenAI-compatible endpoint.
**House default** when `CHEAPERINFERENCE_API_KEY` is set is
[Cheaper Inference](../../docs/providers/cheaperinference.md) (LiteLLM overlay /
CLI rewrite); otherwise OpenRouter. Force OpenRouter with
`DIGI_HOUSE_UPSTREAM=openrouter`. LiteLLM remains the local swap layer via
`OPENAI_API_BASE`. No FastAPI; no hard dependency on digismith.
Hard deps are `openai>=1.0` + `pydantic>=2`; mode resolution, tracing,
and dev tools ride extras. Consumers: twelve-x now; digigraph and
digisearch migrate later.

## Provider routing

`register_provider(prefix, base_url, api_key_env)` maps `provider/`
model prefixes to vendor endpoints; `get_client_for_model()` resolves
per request across the default base, Cheaper Inference (when keyed),
LiteLLM proxy, OpenRouter, and BYOK pass-throughs, with proxy-key and BYOK
contextvars (`proxy_key()`, `byok()`) scoping credentials per request.
Cost-control guards keep house traffic off unintended hosted marketplaces;
see `docs/LLM_PROVIDERS.md`.

## Completion and tool loop

`chat_completion` / `chat_completion_with_tools` wrap the OpenAI client
with retry/backoff, the parallel-safe tool-execution loop, and the
`DIGI_TOOL_MESSAGE_MAX_CHARS` cap on tool text injected into the next
turn. `structured_completion` resolves `json_schema` responses into
validated Pydantic models, with opt-in test/medium/best model resolution.

## Cache and telemetry

`cache.py` keys responses by SHA-256 with TTL/eviction and clearing.
`telemetry.py` separates `NodeRunRecord` (graph work), `ProviderCallRecord`
(logical calls), and `ProviderAttemptRecord` (physical attempts) with
fail-soft observer delivery via `emit_telemetry` — observers never break
the call path. digismith `traceable` wraps entry points when the
`[trace]` extra is installed, degrading to a local no-op otherwise.
