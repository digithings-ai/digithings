---
type: api-operations-guide
title: digigraph API and Operations
description: digigraph HTTP and MCP surface plus operations — endpoints, digikey path scopes, rate limits, streaming, policy flags, and container.
tags: [digigraph, api, mcp, operations]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-480f9d807ff1b9a39c50e94a
    resource: repo://digigraph/src/digigraph/mcp_server.py
  - id: openwiki-source-78c5cfe6ccb60ca994b9d754
    resource: repo://digigraph/src/digigraph/policy.py
  - id: openwiki-source-3854646407c9bc7a61e346db
    resource: repo://digigraph/src/digigraph/server.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digigraph API and Operations

digigraph (port 8000 HTTP, 8766 MCP streamable-http) fronts the
orchestration hub with an OpenAI-compatible chat endpoint, a workflow
endpoint, opt-in thread APIs, and a FastMCP server. Auth rides on
`DigiAuthMiddleware` with per-path scope tables owned by digikey.

## REST endpoints

- `GET /health` → `{"status": "ok", "service": "digigraph"}` (legacy,
  kept for Docker/digiclaw); `GET /healthz` → `{"ok": true}` (preferred
  liveness, auth- and rate-limit-exempt).
- `POST /workflow` — run the LangGraph workflow (digiclaw skill contract);
  dedicated rate-limit budget shared with chat completions.
- `POST /v1/chat/completions` (mounted `v1` router) — OpenAI-compatible
  chat for Open WebUI / digichat, with SSE streaming via background thread
  + queue.
- `GET /files/{path}` — session workspace file serving.
- `GET /test_llm` — LLM smoke test, debug-gated.
- Thread APIs (`GET /threads/{id}/state|history`,
  `POST /threads/{id}/resume`) — opt-in via `DIGI_ENABLE_THREAD_API`.

## Auth and rate limiting

`DigiAuthMiddleware(service="digigraph",
path_scopes=digigraph_path_scopes)` enforces digikey JWT scopes per route;
any new route must extend the scope table. A per-IP sliding-window limiter
budgets `/workflow` and `/v1/chat/completions` separately from the default
pool. Per-request LiteLLM proxy and BYOK keys arrive via headers
(`X-LiteLLM-Proxy-Key`, `X-BYOK-Key/Provider`) applied as request-scoped
context — never logged.

## MCP server

`python -m digigraph.mcp_server` serves streamable-http on 8766;
`--stdio` targets trusted local clients like Claude Desktop. MCP adds no
API-key layer of its own — bind loopback, firewall, or terminate TLS with
auth at a gateway; set `DIGI_MCP_REQUIRE_AUTH=1` beyond localhost, where
the `workflow` tool refuses unauthenticated calls.

## Policy flags

`policy.py` centralizes `DIGI_HUB_MODE` (`legacy` monolith vs `federated`
vertical delegation), `DIGI_ENABLE_DEBUG_ENDPOINTS`,
`DIGI_ENABLE_THREAD_API`, and `DIGI_ALLOW_CODE_EXEC` (sandboxed code
paths). Model names always resolve via `get_model_for_mode()` — no
hardcoded strings.

## Standard middleware and container

Metrics, CORS, request-ID correlation, error envelopes, and optional OTel
come from digibase like every service. The Compose service binds
`127.0.0.1:8000`, healthchecks `/healthz`, and carries the reserved
`DIGISMITH_URL` for future status polling. `DIGI_CHECKPOINTER`
(`memory|sqlite|postgres`) selects LangGraph checkpoint persistence —
`memory` does not survive restarts.
