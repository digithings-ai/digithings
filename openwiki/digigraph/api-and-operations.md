---
type: "Reference"
title: "digigraph API and Operations"
openwiki_generated: true
generated: { by: "openwiki/0.5.0", at: "2026-09-23T13:25:31.068Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-23T13:25:31.068Z
---


# digigraph API and Operations

digigraph (port 8000 HTTP, 8766 MCP streamable-http) fronts the
orchestration hub with an OpenAI-compatible chat endpoint, a workflow
endpoint, product-graph endpoints, opt-in thread APIs, and a FastMCP
server. Auth rides on `DigiAuthMiddleware` with per-path scope tables
owned by digikey.

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
- `GET /v1/models` — returns `digigraph-rag` model for Open WebUI
  discovery.
- `GET /v1/model-info` — current model, mode, and `OPENAI_API_BASE`
  (diagnostic).
- `GET /v1/status` — public project status (name, version, enabled
  agents, `llm_mode`, MCP enabled flag, workflow profile); secret-free.
- `GET /v1/product_graphs` — list digigraph product graphs (digiquant
  research/portfolio scheduled path).
- `POST /v1/product_graphs/{graph_name}/runs` — start a product-graph run
  (dry compile by default); `digigraph` owns the LangGraph entry,
  digiquant owns domain compile/apply.

## Auth and rate limiting

`DigiAuthMiddleware(service="digigraph",
path_scopes=digigraph_path_scopes)` enforces digikey JWT scopes per route;
any new route must extend the scope table. The path scope table (defined
in `digikey.integrations.service_middleware`) maps `/health` and
`/healthz` to public, `/workflow` to `digigraph:workflow`,
`/v1/chat/completions` and `/v1/models` to `digigraph:chat`, and
`/threads/*` and `/files/*` to `digigraph:mcp`; everything else defaults
to `digigraph:workflow`.

A per-IP sliding-window limiter budgets expensive paths separately from
the default pool:

| Path | Budget | Default |
|---|---|---|
| `/workflow` | 10 req / 60 s | — |
| `/v1/chat/completions` | 10 req / 60 s | — |
| `/v1/product_graphs` | 10 req / 60 s | — |
| all other (except health) | — | 30 req / 60 s |

Health paths (`/health`, `/healthz`) are unlimited. The limiter buckets
IPv6 by `/64` to defeat trivial address rotation; IPv4 addresses are
individual. `DIGI_TRUSTED_PROXIES` (comma-separated hosts/CIDRs)
designates proxy hops whose `X-Forwarded-For` should be consulted
(rightmost-walk); unset (the Compose default, since digigraph is directly
exposed on `127.0.0.1:8000`), `X-Forwarded-For` is ignored entirely.

A second, stricter budget meters `require_tool_calls=true` requests
(default 3 req / 60 s, overridable via
`DIGI_REQUIRE_TOOL_CALLS_RATE_LIMIT_MAX`). Forcing
`tool_choice="required"` reliably exhausts all `max_tool_rounds`
completions (~4-5× LLM spend). This budget checks any caller's opt-in
signal per-request, not the deployment-mandated floor; both the
per-path budget and this budget apply independently, and either can 429.

Per-request LiteLLM proxy and BYOK keys arrive via headers
(`X-LiteLLM-Proxy-Key`, `X-BYOK-Key/Provider`) applied as request-scoped
context — never logged. The BYOK middleware rejects unsupported
providers, model-provider mismatches, and omitted models where the
operator default would bill the operator's key instead of the user's
(HTTP 400; no silent substitution).

## MCP server

`python -m digigraph.mcp_server` serves streamable-http on port 8766;
`--stdio` targets trusted local clients like Claude Desktop. The host is
configurable via `DIGIGRAPH_MCP_HOST` (default `127.0.0.1`). Install
prerequisite: `pip install -e "digigraph[mcp]"`.

**Five tools are exposed:**

| Tool | Scope | Description |
|---|---|---|
| `workflow(prompt, thread_id)` | `digigraph:workflow` | Full research + backtest graph |
| `chat(message, thread_id, model)` | `digigraph:chat` | Single-turn OpenAI-compatible chat via in-process TestClient |
| `thread_state(thread_id)` | `digigraph:mcp` | Current LangGraph checkpoint state |
| `list_orchestrator_tools()` | `digigraph:mcp` | Sorted list of registered orchestrator tool names |
| `list_orchestrator_tools_detailed()` | `digigraph:mcp` | Full manifest with name, tags, and `dynamic_schema` flag |

The `chat` and `thread_state` tools call the digigraph FastAPI app
in-process via `TestClient`, forwarding the verified caller bearer as
`Authorization` so `DigiAuthMiddleware` re-verifies it — a pass-through,
not a bypass. `create_mcp_server()` sets `DIGI_ENABLE_THREAD_API=1` in
the process so thread routes are reachable.

**Trust model:** Without `DIGI_MCP_REQUIRE_AUTH`, the server is
unauthenticated — bind loopback, firewall, or terminate TLS with auth at
a gateway. With `DIGI_MCP_REQUIRE_AUTH=1`, every tool calls
`_authorize_mcp_ctx` before doing any work. It reads the
`Authorization: Bearer` header from the FastMCP request context,
verifies the RS256 signature via `DIGIKEY_JWKS_URL` or
`DIGIKEY_PUBLIC_KEY_PEM` (plus issuer, audience, exp), applies the same
fail-closed blocklist revocation policy as `DigiAuthMiddleware`
(`digikey.blocklist.assert_blocklist_ready()` when
`DIGIKEY_REQUIRE_BLOCKLIST=1`, and `is_blocked(jti)` when Redis is
configured), then enforces the tool's scope via
`digikey.scopes.scope_grants_required`. Missing, invalid, expired,
revoked, and wrong-scope tokens are refused (`McpAuthDenied`) and no
work runs. When auth is required but no verifier is configured — or the
transport carries no HTTP headers (stdio) — the gate fails closed and
refuses every call.

The `_headers_from_context` helper returns `None` for stdio transport
(no HTTP headers), keeping the auth gate fail-closed there. Graphiti /
graph memory is not exposed via MCP yet (Phase 2 roadmap).

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
`memory` does not survive restarts; `sqlite` (default when a
`digiproject.yaml` is active) survives restarts but is single-process;
`postgres` is the only shared-store backend for multi-replica
deployments. The Compose config mounts `./config` at `/app/config` (read-only)
for `model_modes.yaml` and `byok-providers.json`; digigraph crash-loops
at startup if `byok-providers.json` is missing, by design.
