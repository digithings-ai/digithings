---
type: api-operations-guide
title: digigraph API and Operations
description: digigraph HTTP and MCP surface plus operations — endpoints, digikey path scopes, rate limits, streaming, policy flags, and container.
tags: [digigraph, api, mcp, operations]
sources:
- id: openwiki-source-480f9d807ff1b9a39c50e94a
  resource: repo://digigraph/src/digigraph/mcp_server.py
- id: openwiki-source-78c5cfe6ccb60ca994b9d754
  resource: repo://digigraph/src/digigraph/policy.py
- id: openwiki-source-3854646407c9bc7a61e346db
  resource: repo://digigraph/src/digigraph/server.py
verified:
  - by: openwiki/0.5.0
    at: 2026-09-19T12:20:11.463Z
generated: { by: "openwiki/0.5.0", at: "2026-09-19T12:20:11.463Z" }
---

# digigraph API and Operations

digigraph (port 8000 HTTP, 8766 MCP streamable-http) fronts the
orchestration hub with an OpenAI-compatible chat endpoint, a workflow
endpoint, opt-in thread and file APIs, product-graph run endpoints, a
`v1` sub-router for model discovery and status, and a FastMCP server.
Auth rides on `DigiAuthMiddleware` with per-path scope tables owned by
digikey. BYOK and LiteLLM proxy keys arrive per-request via dedicated
middleware on `X-BYOK-Key/Provider/Model` and `X-LiteLLM-Proxy-Key`.

## REST endpoints

### Health

- `GET /health` → `{"status": "ok", "service": "digigraph"}` (legacy,
  kept for Docker/digiclaw).
- `GET /healthz` → `{"ok": true}` — preferred liveness probe, auth- and
  rate-limit-exempt.

Both are in `_UNLIMITED_PATHS` and bypass the per-IP rate limiter.

### Core endpoints

- `POST /workflow` — runs the LangGraph workflow (`run_digigraph_workflow`);
  digiclaw skill contract. Dedicated 10 req/min budget, same pool as
  chat completions.
- `POST /v1/chat/completions` (mounted `v1` router) — OpenAI-compatible
  chat for Open WebUI / digichat. Supports SSE streaming via
  `_stream_completions_progressive` (background thread + queue) and
  non-streaming inline execution. 10 req/min shared with `/workflow`.
- `GET /test_llm` — LLM smoke test hitting the same `completion_text`
  path as the research node. Debug-gated (`DIGI_ENABLE_DEBUG_ENDPOINTS`).

### Opt-in thread and file routes

Gated behind `DIGI_ENABLE_THREAD_API=1`:

- `GET /threads/{thread_id}/state` — current LangGraph checkpoint state,
  exposing `stored_datasets`, `research_response`, `backtest_result`,
  `symbols`, etc.
- `GET /threads/{thread_id}/history` — checkpoint history (most recent
  first).
- `POST /threads/{thread_id}/resume` — resume an interrupted thread
  (e.g. after `DIGI_INTERRUPT_AFTER_RESEARCH`).
- `GET /files/{path}` — serve exported files (CSV, JSON, Parquet) from
  `run_data_dir` with path-traversal protection via
  `assert_safe_path`.

### v1 sub-router and product graphs

The `APIRouter(prefix="/v1")` mounts these endpoints:

- `GET /v1/models` — OpenAI-compatible model list returning
  `digigraph-rag` for Open WebUI discovery.
- `GET /v1/status` — public, secret-free project status (name, version,
  enabled agents, llm_mode, mcp_enabled, workflow_profile). Fresh
  `DigiProjectConfig.load()` on every request.
- `GET /v1/model-info` — effective LLM model and mode for debugging.
- `GET /v1/debug/input_messages` — last N chat request summaries
  (debug-gated).
- `GET /v1/product_graphs` — list registered product graphs.
- `POST /v1/product_graphs/{name}/runs` — run one product graph (dry
  compile by default). digigraph owns the LangGraph entry; digiquant
  owns domain compile/apply via `POST /v1/orchestrator_invoke`. Rate
  limited at 10 req/min alongside `/workflow` and chat.

## Auth and rate limiting

### JWT auth middleware

`DigiAuthMiddleware(service="digigraph", path_scopes=digigraph_path_scopes)`
enforces digikey JWT scopes per route. Any new route must extend the
scope table. When `DIGIKEY_JWKS_URL` or `DIGIKEY_PUBLIC_KEY_PEM` is
unset the middleware operates in passthrough mode.

Required scopes per route family:

| Scope | Routes |
|---|---|
| `digigraph:workflow` | `POST /workflow`, `/v1/debug/*` |
| `digigraph:chat` | `POST /v1/chat/completions`, `GET /v1/models` |
| `digigraph:mcp` | `/threads/*`, `/files/*` |

### Rate limiting

A per-IP sliding-window limiter (`RateLimiter` from
`digigraph/rate_limit.py`) buckets IPv6 by /64 and IPv4 individually,
respecting `DIGI_TRUSTED_PROXIES` for reverse-proxy deployments. Budgets:

| Path | Budget |
|---|---|
| `/workflow` | 10 req / 60 s |
| `/v1/chat/completions` | 10 req / 60 s |
| `/v1/product_graphs` | 10 req / 60 s |
| everything else | 30 req / 60 s |
| `/health`, `/healthz` | unlimited |

A **second, stricter** budget targets `require_tool_calls=true` requests:
default 3 req / 60 s, overridable via
`DIGI_REQUIRE_TOOL_CALLS_RATE_LIMIT_MAX`. Forcing `tool_choice="required"`
exhausts all `max_tool_rounds` completions (~4–5× LLM spend), so the
secondary budget is checked independently; either limiter can 429 the
request. A deployment that itself mandates `require_tool_calls` via
project config is not further constrained — this budget only meters a
request's own opt-in signal.

Set `DIGI_DISABLE_RATE_LIMIT=true` to disable (tests/dev).

### Per-request LLM credentials

Two dedicated middlewares bind request-scoped credentials:

1. **`lite_llm_proxy_header_context`** — picks up
   `X-LiteLLM-Proxy-Key` (digikey funnel via digichat) and binds it as
   a `ContextVar` for the request duration. Its `finally` pops it.

2. **`byok_header_context`** — picks up `X-BYOK-Key`,
   `X-BYOK-Provider`, and `X-BYOK-Model`. Validates that a supported
   provider is named, that a model is supplied when the provider
   requires it, and that the operator's default model won't be billed
   when the user's key is active. Refuses with 400 on mismatch — a
   pasted key must never be silently bypassed. The key is bound for the
   request duration only and never logged.

For streaming, the worker thread copies the BYOK context at spawn, then
clears its own copy in its own `finally`.

## MCP server

`python -m digigraph.mcp_server` serves streamable-http on port 8766
(binds `127.0.0.1` by default; override with `DIGIGRAPH_MCP_HOST`).
`--stdio` targets trusted local clients like Claude Desktop.

### Tools and scopes

| Tool | Scope |
|---|---|
| `workflow(prompt, thread_id)` | `digigraph:workflow` |
| `chat(message, thread_id, model)` | `digigraph:chat` |
| `thread_state(thread_id)` | `digigraph:mcp` |
| `list_orchestrator_tools()` | `digigraph:mcp` |
| `list_orchestrator_tools_detailed()` | `digigraph:mcp` |

The `chat` and `thread_state` tools call the digigraph FastAPI app
in-process via `TestClient`, forwarding the caller's verified bearer
token through `DigiAuthMiddleware` — the token is re-verified, not
bypassed.

### Auth model (`DIGI_MCP_REQUIRE_AUTH`)

Without `DIGI_MCP_REQUIRE_AUTH` the server is unauthenticated — bind
loopback or firewall accordingly.

With `DIGI_MCP_REQUIRE_AUTH=1`, **every** tool calls
`_authorize_mcp_ctx` before doing any work:

1. Extract `Authorization: Bearer` from the FastMCP request context
   headers (returns `None` for stdio — fails closed).
2. Verify the RS256 signature via `DIGIKEY_JWKS_URL` or
   `DIGIKEY_PUBLIC_KEY_PEM`, plus issuer, audience, and expiry
   (`digikey.jwt_verify.decode_token`).
3. Apply fail-closed blocklist revocation
   (`digikey.blocklist.assert_blocklist_ready`, `is_blocked(jti)`).
4. Enforce the tool's scope via
   `digikey.scopes.scope_grants_required`.

Missing, invalid, expired, revoked, and wrong-scope tokens are refused
(`McpAuthDenied`). When auth is required but no verifier is configured
the server fails closed — every call is refused.

### MCP singleton

`get_mcp_server()` returns a module-level singleton (lazy init via
`create_mcp_server()`). On creation it force-sets
`DIGI_ENABLE_THREAD_API=1` so the `thread_state` tool can reach the
in-process `/threads/{id}/state` route.

## Policy flags

`policy.py` centralizes four operational flags:

| Function | Env var | Effect |
|---|---|---|
| `debug_endpoints_enabled()` | `DIGI_ENABLE_DEBUG_ENDPOINTS` | gates `/test_llm` and `/v1/debug/*` |
| `thread_api_enabled()` | `DIGI_ENABLE_THREAD_API` | gates `/threads/*` and `/files/*` |
| `hub_mode()` | `DIGI_HUB_MODE` | `legacy` (default) monolith vs `federated` vertical delegation |
| `code_execution_allowed()` | `DIGI_ALLOW_CODE_EXEC` | gates sandboxed Python (Polars) paths |

`federated_hub_enabled()` is a convenience: `hub_mode() == "federated"`.

Model names always resolve via `get_model_for_mode()` in
`model_config.py` — no hardcoded strings.

## Checkpointer configuration

`DIGI_CHECKPOINTER` selects LangGraph checkpoint persistence:

| Value | Backend | Persistence |
|---|---|---|
| `memory` (default) | `MemorySaver` | in-process dict; does not survive restarts |
| `sqlite` | `SqliteSaver` | file on disk; `DIGI_CHECKPOINTER_SQLITE_URI` (default `~/.digigraph/checkpoints.sqlite`) |
| `postgres` | `PostgresSaver` | shared across replicas; config via standard `PG*` env vars |

`get_checkpointer()` in `graph/graph.py` returns a process-wide
singleton (thread-safe lazy init). The returned checkpointer is wrapped
in `McpTokenRedactingCheckpointer` so bearer tokens are never written to
persistent state.

Only the Postgres backend supports horizontal scaling. Retention is
enforced in the database via `pg_cron`, not in digigraph.

## Standard middleware and container

Metrics (`/metrics`), CORS, request-ID correlation
(`X-Request-ID` / `request_id`), structured error envelopes
(`json_error_response`), and optional OTel (`setup_otel_fastapi`)
come from digibase like every service.

The Compose service binds `127.0.0.1:8000`, healthchecks `/healthz`,
depends on healthy digikey, digiquant, digisearch, and LiteLLM,
mounts `./config:/app/config:ro` (must contain `byok-providers.json`
or digigraph crash-loops; missing `model_modes.yaml` silently falls
back to a hardcoded default), and mounts `./digiquant/results/audit`
for the shared audit log.

`DIGISMITH_URL` is reserved for future status polling — digigraph's
LangSmith traces go directly from the in-process SDK to LangSmith.
