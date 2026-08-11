---
title: "Architecture overview — guide"
type: reference
status: generated
created: 2026-08-10
tags:
  - api
  - guide
---
# Architecture overview

> Service topology and chat path — digigraph orchestrates, digikey authenticates, LiteLLM routes.

digigraph is the horizontal orchestrator. digisearch and digiquant each own vertical LangGraph pipelines and expose them as HTTP + MCP. digivault is the markdown knowledge vault. digikey issues RS256 JWTs; every protected service verifies JWKS. LiteLLM is the only LLM router. Loopback-only by default.

### Service map

- `digigraph` `:8000` — workflows, OpenAI-compatible chat, federated tools
- `digiquant` `:8001` — NautilusTrader backtest / optimize
- `digisearch` `:8002` — RAG ingest + query
- `digismith` `:8003` — observability helpers + status
- `digivault` `:8004` — vault (opt-in compose profile)
- `digikey` `:8005` — API keys + JWT exchange + JWKS
- `digichat` `:3005` — Next.js BFF + chat UI (profile `digichat`)
- LiteLLM `:4000` — provider proxy; Ollama in Compose on host `:11435` (models optional)

### Chat path (simplified)

Browser → digichat → digikey (session/JWT) → digigraph → LiteLLM; digigraph may call digisearch, digiquant, or digivault tools with the same JWT and `X-Request-ID`.

### Non-negotiables

- Polars only — never pandas
- Pydantic v2 models on the wire
- MCP-first tool design
- NautilusTrader for all backtest / optimize paths
- Never expose live-trading without explicit human approval

Canonical detail: root `ARCHITECTURE.md` and each module's `ARCHITECTURE.md`. This page's module sections below are the operator-facing API reference; machine-readable OpenAPI is at [OpenAPI explorer](https://digithings.ai/docs/api/).

See also [[digigraph]].
