---
title: DigiLLM
type: module
status: reviewed
created: 2026-06-15
tags:
  - support
  - llm-routing
  - library
relevance:
  - digigraph
  - digisearch
---
# DigiLLM
> The single home for LLM client code — provider-agnostic routing, structured output, and tool calling, with no service coupling.

## What it is

DigiLLM is the standalone LLM client/wrapper library for the DigiThings stack. It speaks to any OpenAI-compatible endpoint and carries no FastAPI or service coupling and no hard dependency on DigiSmith. It was extracted from the mature `digigraph.llm` implementation so that every component — services and libraries alike — shares one well-tested path to the model layer instead of each reinventing routing, caching, retries, and the tool-calling loop.

It is provider-agnostic by design: a registered `provider/model_id` prefix routes to that provider; a bare model id is sent on the wire unchanged. There is no hidden environment- or YAML-driven model substitution — mode selection (test/medium/best) is an explicit, opt-in call.

## The problem it solves

LLM access code is where subtle production bugs live: inconsistent retry/backoff, accidental response caching of tool calls, BYOK keys leaking into shared caches, structured-output validation drift. When every service rolls its own, those bugs get fixed in one place and not the others. DigiLLM makes the model layer a single, audited dependency: fix it once, every consumer benefits.

## How it fits in the ecosystem

DigiLLM sits beneath every component that calls a model. Consumers: **twelve-x** adopts it today; **DigiGraph** and **DigiSearch** migrate to it next (their current in-tree LLM modules are superseded by this package). It depends only on `openai` and `pydantic`, with optional extras for path-based mode resolution (`[modes]`) and LangSmith tracing (`[trace]`). It imports cleanly with no side effects and no FastAPI in the dependency tree.

## Capabilities — Current

Shipped and in active use:

- Provider registry + routing with a per-model client cache
- `chat_completion` with retry/backoff and a SHA-256 response cache (caching skipped for tool loops and BYOK requests)
- Tool-calling loop with first-class tool-call types
- `structured_completion` — OpenAI `json_schema` → validated Pydantic model
- `resolve_model` — opt-in test/medium/best resolution (no implicit substitution)
- Per-request override contextvars for proxy key and BYOK (bring-your-own-key)
- Optional DigiSmith/LangSmith tracing via the `[trace]` extra

## Capabilities — 12-month roadmap

- DigiGraph and DigiSearch fully migrated off their in-tree LLM modules onto DigiLLM
- Streaming (SSE) response support exposed through the shared client
- Richer cost/usage accounting surfaced to DigiSmith
- Pluggable cache backends (today an in-process cache; Redis-backed shared cache is future DigiBase work)

## Open source vs. proprietary

**Open (MIT/Apache):** the entire DigiLLM library — routing, caching, retries, tool loop, structured output, mode resolution, and the BYOK/proxy override surface. DigiLLM is pure open-core infrastructure; the domain expertise that uses it lives in the proprietary sub-graphs, not here.
