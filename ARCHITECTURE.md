# digithings Architecture

> **For vision and strategy, see [docs/VISION.md](docs/VISION.md) and [ROADMAP.md](ROADMAP.md). For per-component details, read each service's own `ARCHITECTURE.md` (linked in the topology table below). For release history, see [RELEASES.md](RELEASES.md).**

---

## 1. Ecosystem Purpose

digithings (digithings.ai) is an open-core modular agentic stack for building conversational agents that research, search, analyze, and act. The primary use case is quantitative finance — a "hedge-fund in a box" where a single operator can run strategy research, backtesting, optimization, and execution monitoring through a single chat interface. The same stack supports RAG (retrieval-augmented generation), document search, and general agent workflows without code changes. The design philosophy is **MCP-first** (every capability is a tool with a schema; digigraph discovers and dispatches them dynamically), **federated hub** (digigraph is the horizontal orchestrator; digisearch and digiquant each own their vertical LangGraph pipelines and expose them as HTTP + MCP), and **loopback-only by default** (all services bind `127.0.0.1`; remote access requires Tailscale or Cloudflare Tunnel). The stack targets developer and small-firm deployments on a single machine today with a clear Kubernetes upgrade path.

---

## 2. Service Topology

| Service | Port (host) | Role | Auth Required | Docker Profile | MCP Server | Status |
|---------|------------|------|--------------|----------------|-----------|--------|
| **digigraph** | 8000 | LangGraph orchestration hub; OpenAI-compatible API; delegates to verticals | JWT (digikey) — 503 if not configured | core (always on) | Yes — `python -m digigraph.mcp_server` | Shipped |
| **digiquant** | 8001 | NautilusTrader backtest/optimize; ordered quant pipeline; orchestrator endpoints | JWT (`digiquant:backtest`, `digiquant:optimize`) | core | Yes — `python -m digiquant.mcp_server` | Shipped |
| **digisearch** | 8002 | RAG pipeline; document ingestion; vector search (Chroma/Azure) | JWT (`digisearch:query`, `digisearch:ingest`) | core | Yes — `docker compose --profile digisearch-mcp up` | Shipped |
| **digismith** | 8003 | LangSmith-aligned tracing helpers (library); health + `/v1/status` endpoint | None (public metadata) | core | No | Shipped |
| **digivault** | 8004 | Obsidian-style markdown vault management (frontmatter, wikilinks, backlinks, tags) | JWT (`digivault:read`, `digivault:write`) | digivault | Yes — `python -m digivault.mcp_server` | New |
| **LiteLLM** | 4000 | LLM routing proxy (100+ providers); response cache; rate limiting | `LITELLM_MASTER_KEY` Bearer | core | No | Shipped |
| **digikey** | 8005 | API key issuance; JWT exchange (RS256); JWKS endpoint | Admin token for key issuance | core | No | Shipped |
| **Ollama** | 11435 (host) | Local LLM inference (maps to container port 11434) | None | core | No | Shipped |
| **digichat** | 3005 | Next.js BFF + React chat UI; Auth.js OIDC; machine API keys | OIDC session or Bearer API key | digichat | No | Shipped |
| **digichat-DB** | 5433 | Postgres 16 for digichat conversations and API keys | Postgres credentials | digichat | No | Shipped |
| **digiclaw** (heartbeat) | — | Heartbeat agent; health polling; JSONL audit; ADDM drift trigger | None (internal cron) | heartbeat | No (Phase 2) | Partial (Phase 3) |
| **digibase** (service) | TBD | Data-plane broker: managed Postgres/Redis/object credentials | digikey-scoped tokens | not shipped | No | Roadmap |

**Notes:**
- digigraph, digiquant, and digisearch all depend on digikey being healthy at startup (Compose `condition: service_healthy`).
- digigraph additionally waits for digiquant, digisearch, and LiteLLM.
- digichat waits for digikey, digigraph, and digichat-DB.
- All inter-service URLs inside Docker Compose use internal hostnames (e.g. `http://digigraph:8000`); host-side ports are loopback-bound.

---

## 3. Inter-Service Interaction Flows

### Flow A: User Chat Request — End to End

```mermaid
sequenceDiagram
    participant Browser
    participant digichat as digichat BFF (3005)
    participant digikey as digikey (8005)
    participant digigraph as digigraph (8000)
    participant LiteLLM as LiteLLM (4000)
    participant digisearch as digisearch (8002)
    participant digiquant as digiquant (8001)

    Browser->>digichat: POST /api/chat (session cookie or Bearer key)
    digichat->>digikey: POST /v1/oauth/token (grant_type=bff_session, Bearer DIGIKEY_BFF_TOKEN)
    digikey-->>digichat: { access_token: JWT, litellm_proxy_api_key }
    digichat->>digigraph: POST /v1/chat/completions (Authorization: Bearer JWT, X-LiteLLM-Proxy-Key, X-Request-ID)
    Note over digigraph: Validates JWT via JWKS; runs LangGraph workflow
    digigraph->>LiteLLM: POST /v1/chat/completions (Bearer litellm_proxy_api_key)
    LiteLLM-->>digigraph: LLM response (streamed)
    digigraph->>digisearch: POST /v1/orchestrator_invoke (tool=digisearch, Bearer JWT, X-Request-ID)
    digisearch-->>digigraph: search results + rag_sources
    digigraph->>digiquant: POST /v1/jobs/backtest (Bearer JWT, X-Request-ID)
    digiquant-->>digigraph: job_id; poll GET /v1/jobs/{id}/status → BacktestResult
    digigraph-->>digichat: SSE stream (OpenAI chunks + digigraph_trace parts)
    digichat-->>Browser: streamed response with trace metadata
```

### Flow B: digigraph Vertical Orchestrator Tool Invocation

```mermaid
sequenceDiagram
    participant digigraph as digigraph (LangGraph node)
    participant Vertical as digisearch or digiquant

    Note over digigraph: On startup (or per-request cache miss)
    digigraph->>Vertical: POST /v1/orchestrator_tools (optional index_config body)
    Vertical-->>digigraph: OpenAI-style tool schemas array (manifest)
    Note over digigraph: LLM selects tool from manifest; node decides to invoke
    digigraph->>Vertical: POST /v1/orchestrator_invoke { tool: "digisearch", args: {...}, request_id }
    Note over Vertical: Validates JWT scope (digisearch:query or digiquant:backtest)
    Vertical-->>digigraph: ToolResult { result, trace, request_id }
    Note over digigraph: LangGraph node continues with result; appends to WorkflowState
```

**Key detail:** digigraph never hard-codes digisearch or digiquant tool schemas. It fetches them at runtime via `/v1/orchestrator_tools`. With `DIGI_HUB_MODE=federated`, additional delegate tool names (`digisearch_research_delegate`, `digiquant_pipeline_delegate`) are also exposed to the LLM surface. With `DIGI_HUB_MODE=legacy` (default), the same vertical invoke path is used but those alias names are not registered.

### Flow C: Authentication Exchange — Machine Key to JWT

```mermaid
sequenceDiagram
    participant Client as Client (digichat BFF or CLI)
    participant digikey as digikey (8005)
    participant Service as Protected Service (digigraph/digisearch/digiquant)

    Client->>digikey: POST /v1/oauth/token { grant_type: api_key, api_key: dgk_live_... }
    Note over digikey: bcrypt-verify key; check scopes; RS256-sign JWT
    digikey-->>Client: { access_token: JWT (RS256), litellm_proxy_api_key, expires_in }
    Client->>Service: GET/POST /v1/... Authorization: Bearer JWT
    Note over Service: DigiAuthMiddleware fetches JWKS from http://digikey:8005/.well-known/jwks.json
    Service->>digikey: GET /.well-known/jwks.json (cached)
    digikey-->>Service: JWKS (public key set)
    Note over Service: Validate: RS256 sig, iss=http://digikey:8005, aud=digi-ecosystem, exp, scopes
    Service-->>Client: 200 response (or 403 insufficient_scope / 503 auth_not_configured)
```

---

## 4. MCP Server Topology

MCP (Model Context Protocol) is the standard for tool discovery and invocation at the edge of the digithings ecosystem. digigraph, digiquant, and digisearch each expose MCP servers. digikey, digismith, and digiclaw do not (digiclaw MCP integration is Phase 2).

| Component | MCP Server Command | Host Port | Exposed Tools (examples) | Typical Clients |
|-----------|-------------------|-----------|--------------------------|-----------------|
| **digigraph** | `python -m digigraph.mcp_server` (install: `pip install -e "digigraph[mcp]"`) | stdio or SSE | `workflow`, `chat`, `thread_state`, `list_orchestrator_tools`, `list_orchestrator_tools_detailed` | digiclaw (Phase 2), IDE plugins, Claude Desktop |
| **digiquant** | `python -m digiquant.mcp_server` | stdio or SSE | `digiquant_run_pipeline`, `digiquant_list_strategies`, `run_backtest`, `run_optimize`, `run_validation` | digigraph (invokes via HTTP orchestrator), power-user IDE |
| **digisearch** | `docker compose --profile digisearch-mcp up` → container port 8765 | 8765 | `digisearch_query`, `digisearch_fetch_all`, `digisearch_research_turn` (with `digisearch[agent]`), `digisearch_research_delegate` | digigraph (invokes via HTTP orchestrator), Langflow, IDE |

**Design notes:**

- For normal chat operation, digigraph does **not** connect to digisearch/digiquant via MCP. It uses HTTP (`POST /v1/orchestrator_tools` + `/v1/orchestrator_invoke`) for vertical dispatch. MCP servers are for external clients (IDEs, digiclaw, Langflow) that want to attach directly to a vertical.
- digigraph's own MCP server exposes the hub workflow surface. Clients that want single-entry-point access should connect here.
- Use **hub-only** (digigraph MCP) when you want one digikey allowlist and unified trace stream. Use **direct vertical MCP** (digisearch or digiquant MCP) when a client should bypass digigraph.
- MCP tool schemas for digisearch and digiquant are also served over HTTP (`GET /v1/orchestrator_tools`) so digigraph can fetch them without running a local MCP process.

---

## 5. Docker Compose Profiles

### Default / Core (no profile flag)

**Includes:** digikey (8005), Ollama (11435), digismith (8003), digigraph (8000), digiquant (8001), digisearch (8002), LiteLLM (4000)

**When to use:** Standard developer stack. All core services. No chat UI, no Redis cache, no heartbeat agent.

```bash
make build
make up
# or: docker compose up -d
```

**Startup order:** digikey → {digiquant, digisearch, LiteLLM} → digismith → digigraph

---

### Profile: `heartbeat`

**Adds:** `heartbeat` container (Python 3.12-slim running `python -m digiclaw` in a loop every 1800 seconds)

**When to use:** Production-style monitoring; ADDM drift detection; periodic health checks logged to JSONL audit.

```bash
make up-heartbeat
# or: docker compose --profile heartbeat up -d
```

**Notes:** Requires digigraph and digiquant to be healthy. Writes audit events to `digiquant/results/audit/events.jsonl`. Reads `HEARTBEAT.md` from workspace root.

---

### Profile: `digichat`

**Adds:** `digichat-db` (Postgres 16 on host port 5433) + `digichat` (Next.js BFF on host port 3005)

**When to use:** Full stack with browser-accessible chat UI. Auth.js OIDC or machine API keys. Persistent conversation storage.

```bash
make up-digichat
# or: docker compose --profile digichat up -d --build
```

**Notes:** Requires `AUTH_SECRET`, `AUTH_URL`, `DIGIKEY_BFF_TOKEN` in `.env`. digichat auto-migrates the database on startup (`DIGICHAT_AUTO_MIGRATE=1`). Default host port is 3005; override with `DIGICHAT_PUBLISH_PORT`. To bind to LAN (not just loopback), set `DIGICHAT_PUBLISH_HOST=0.0.0.0` — see `SECURITY.md`.

---

### Profile: `litellm-cache`

**Adds:** `redis` container (Redis 7 Alpine, internal only — no host port)

**When to use:** Enable Redis-backed LiteLLM response cache to reduce LLM API spend across service restarts.

```bash
docker compose --profile litellm-cache up -d
```

**Notes:** Set `REDIS_URL=redis://redis:6379` in `.env` when this profile is active (compose `env_file` passes it through). Do **not** export an empty `REDIS_URL=` — current LiteLLM `main-stable` treats that as a Redis URL and exits 3. Leave the variable unset when the cache Redis is not running. LiteLLM config (`config/litellm.yaml`) must be updated to use `type: redis` under `cache_params`. See `config/MODELS.md`.

---

### Profile: `digisearch-mcp`

**Adds:** `digisearch-mcp` container (digisearch MCP server on host port 8765)

**When to use:** Expose digisearch MCP tools to external clients (Langflow, Claude Desktop, IDE plugins) without going through digigraph.

```bash
docker compose --profile digisearch-mcp up -d
# MCP endpoint: http://127.0.0.1:8765/mcp
```

---

## 6. Authentication and Authorization

### Key Types

| Type | Prefix | Purpose | Requires |
|------|--------|---------|---------|
| Live API key | `dgk_live_` | Machine clients, digichat machine users, CI | `DIGIKEY_ALLOW_DEV_GLOBAL=0` (default) |
| Dev global key | `dev_global` kind | Local development only, all scopes | `DIGIKEY_ALLOW_DEV_GLOBAL=1` in env |
| BFF session | — | digichat exchanges OIDC session for JWT | `DIGIKEY_BFF_TOKEN` on digikey + digichat |
| Ephemeral signing key | — | Local Docker dev JWKS (rotates on restart) | `DIGIKEY_ALLOW_EPHEMERAL_KEY=1` |

### JWT Claims Structure

digikey issues RS256 JWTs. Relevant claims:

| Claim | Value | Notes |
|-------|-------|-------|
| `iss` | `http://digikey:8005` (or `DIGIKEY_ISSUER`) | Must match consumer `DIGIKEY_ISSUER` |
| `aud` | `digi-ecosystem` (or `DIGIKEY_AUDIENCE`) | Validated by all protected services |
| `sub` | key prefix or OIDC subject | Tenant/user identifier |
| `scopes` | array of strings | e.g. `["digigraph:workflow", "digisearch:query"]` |
| `exp` | Unix timestamp | Short-lived; no revocation today (see Known Gaps) |
| `jti` | UUID | Included in audit events; not checked against blocklist today |
| `litellm_proxy_api_key` | string | Injected by digikey when `DIGIKEY_LITELLM_PROXY_KEY` is set; forwarded as `X-LiteLLM-Proxy-Key` |

### Scope Naming Convention

Scopes follow the pattern `service:action`:

```
digigraph:workflow       digigraph:chat          digigraph:mcp
digiquant:backtest       digiquant:optimize
digisearch:query         digisearch:ingest
*                        # matches all (dev_global only)
```

### DigiAuthMiddleware (service-side validation)

All three protected services (digigraph, digiquant, digisearch) use `digikey.integrations.service_middleware`. On every protected request:

1. Read `Authorization: Bearer <token>` header.
2. Fetch JWKS from `DIGIKEY_JWKS_URL` (cached; falls back to `DIGIKEY_PUBLIC_KEY_PEM` if set).
3. Validate RS256 signature, `iss`, `aud`, `exp`.
4. Check required scope for the route (e.g. `digiquant:backtest` for `POST /backtest/start`).
5. Attach `request.state.tenant`, `request.state.key_prefix`, `request.state.jti` for audit events.

**Fail-closed behavior:** If neither `DIGIKEY_JWKS_URL` nor `DIGIKEY_PUBLIC_KEY_PEM` is configured, protected routes return `503 auth_not_configured`. There is no anonymous access to protected routes.

### Header Propagation

| Header | Direction | Purpose |
|--------|-----------|---------|
| `Authorization: Bearer <JWT>` | Client → all services | Identity and scope |
| `X-Request-ID` | Propagated hub→vertical | Correlation across audit logs and traces |
| `X-LiteLLM-Proxy-Key` | digichat → digigraph → LiteLLM | Per-session LLM proxy authorization |
| `X-Session-Id` / `X-Digichat-Session` | digichat → digigraph | LangGraph `thread_id` for checkpoint continuity |
| `X-Digi-Tenant` | Optional; operator-set | Multi-tenant routing (Phase 2) |

### digichat Auth Exchange Flow

```
Browser (OIDC session)
  └─► digichat BFF
        ├─► digikey POST /v1/oauth/token (grant_type=bff_session)
        │     └─► JWT + litellm_proxy_api_key
        └─► digigraph POST /v1/chat/completions
              Authorization: Bearer JWT
              X-LiteLLM-Proxy-Key: <litellm key>
```

Machine clients use `grant_type=api_key` with a `dgk_live_` key for the same exchange.

### Known Gaps

- **No JWT revocation:** Revoked keys remain valid until `exp`. A `jti` blocklist is on the roadmap ([ROADMAP.md](ROADMAP.md), digikey section in [digikey/ARCHITECTURE.md](digikey/ARCHITECTURE.md)).
- **Multi-tenant incomplete:** `X-Digi-Tenant` is propagated but tenant isolation within digisearch and digiquant is not enforced at the data layer today.
- **digibase credential broker not shipped:** Each service holds its own raw `DATABASE_URL` / `REDIS_URL`. Central credential rotation is Phase 1 of the digibase service roadmap.

---

## 7. Observability Stack

Observability in digithings operates across three layers. None of them are fully integrated into a single dashboard today.

### Layer 1: Distributed Tracing

**LangSmith (conditional):** digigraph wraps LLM calls with `digismith.trace.traceable`. When `LANGSMITH_API_KEY` is set and the `langsmith` package is installed, traces are sent directly from digigraph to LangSmith (or a custom `LANGSMITH_ENDPOINT`). The `digismith` library is a thin no-op wrapper when LangSmith is not configured — no crash, no implicit data leakage.

Required span attributes: `workflow_id`, `request_id` (mirrors `X-Request-ID`), `session_id`. Optional: `job_id` (digiquant backtest job), `tool` name, `run_name`.

Prohibited in spans: raw prompts, API keys, bearer tokens, file paths outside approved workspace roots, full document bodies.

**OpenTelemetry (optional per service):** Install `digibase[otel]` on any service and set `OTEL_EXPORTER_OTLP_ENDPOINT` to export infra-level traces. This complements LangSmith; it does not replace it. Same PII rules apply on span attributes.

**digismith status endpoint:** `GET /v1/status` (port 8003) returns version flags and sanitized LangSmith host only. It is intentionally public — never add secrets or keys to this payload.

### Layer 2: Audit Logs

**JSONL append-only audit:** digiclaw (`digiclaw/audit.py`) and digiquant (`digiquant/audit.py`) write structured JSONL to `AUDIT_LOG_PATH` (default: `digiquant/results/audit/events.jsonl`). digigraph writes `workflow_start`, `workflow_end`, and `tool_denied` events to the same path.

**Event fields (standard):** `event_type`, `agent_id`, `request_id`, `workflow_id`, `timestamp`, `payload` (redacted). Secret keys are stripped by `audit_log()` before writing.

**Optional remote sink:** Set `AUDIT_SINK_URL` to forward events to an external collector. Not currently wired in all services — check per-component docs.

### Layer 3: Health and Status

Every service exposes `GET /health` returning `{"status": "ok"}` (used by Docker Compose healthchecks and digiclaw heartbeat). digichat exposes `GET /api/health` which also checks the digigraph upstream and Postgres connection.

digichat's ecosystem side panel displays health badges for digigraph, digiquant, digismith, and digisearch (configurable via `DIGICHAT_ENABLED_SERVICES`).

### Gap Analysis

| Gap | Impact | Roadmap |
|-----|--------|---------|
| No Prometheus endpoints | Cannot scrape service metrics into Grafana without custom instrumentation | Phase 2 |
| No centralized metrics dashboard | Must use LangSmith UI + log files separately | Phase 2 (digibase + Prometheus) |
| Span PII not enforced | Operators must configure LangSmith data masking manually | Policy gap; no automated check today |
| Audit sink not wired in digisearch | digisearch audit events may be missed by remote collectors | Phase 2 |
| No distributed trace correlation across services | `X-Request-ID` propagates but is not auto-injected into OTel spans | Requires digibase[otel] instrumentation per service |

---

## 8. Security Perimeter

### Network Boundary

All services in Docker Compose bind `127.0.0.1` (loopback) on the host. Services communicate over the internal Docker network using container hostnames (e.g. `http://digigraph:8000`). No service is exposed to `0.0.0.0` by default.

For remote access, use:
- **Tailscale**: preferred for teams; machine-to-machine encrypted mesh.
- **Cloudflare Tunnel**: for public endpoints behind Cloudflare WAF.

Do not expose raw ports to the internet. There is no TLS between internal services (terminate at the ingress layer — Tailscale funnel or CF Tunnel).

### Secret Management

Secrets are passed via environment variables defined in root `.env` (not committed to git; `.env.example` is the template). The only current secret store is env vars in Docker Compose. Future: digibase credential broker (Phase 1) would centralize rotation without requiring every service to hold raw URLs.

**Never commit to git:** `DIGIKEY_PRIVATE_KEY_PEM`, `DIGIKEY_ADMIN_TOKEN`, `DIGIKEY_BFF_TOKEN`, `LITELLM_MASTER_KEY`, `OPENAI_API_KEY`, `OLLAMA_API_KEY`, `LANGSMITH_API_KEY`, `AUTH_SECRET`.

### Code Execution

digigraph supports sandboxed Python execution (via the `data_engineer_agent` tool using Polars). This is gated by `DIGI_ALLOW_CODE_EXEC=true`. When enabled, the executor runs code in-process — it is **not sandboxed in a container or VM** today. Operators must set this explicitly; it is off by default.

Human-in-the-loop interrupt before code execution is supported via `DIGI_INTERRUPT_AFTER_RESEARCH=1` + the thread resume endpoint.

### Critical Risks

| Risk | Severity | Mitigation Today | Roadmap Fix |
|------|----------|-----------------|-------------|
| No JWT revocation | High | Short-lived tokens; network isolation | `jti` blocklist in digikey |
| Unsandboxed code execution | High | Off by default (`DIGI_ALLOW_CODE_EXEC`); loopback-only network | gVisor or subprocess sandboxing |
| Multi-tenant incomplete | Medium | Network isolation; per-key scopes | digibase + per-tenant index isolation |
| Ephemeral JWKS rotates on restart | Medium | Dev-only (`DIGIKEY_ALLOW_EPHEMERAL_KEY=1`); use PEM or stable key in production | Vault/KMS-backed signing keys |
| digichat `DIGICHAT_PUBLISH_HOST=0.0.0.0` | High if set | Warning in `SECURITY.md`; not the default | Always use Tailscale/CF Tunnel for remote |

See [SECURITY.md](SECURITY.md) for the full hardening spec.

---

## 9. Setup Guide

### Quick Start (Docker — recommended)

```bash
cp .env.example .env
# Edit .env: set OLLAMA_API_KEY (Ollama Cloud free tier) or OPENAI_API_KEY
# Set DIGIKEY_ADMIN_TOKEN and DIGIKEY_BFF_TOKEN to random secrets
make build
make up
```

Services available after `make up`:
- digigraph API: `http://localhost:8000`
- LiteLLM proxy: `http://localhost:4000`
- digikey: `http://localhost:8005`
- digisearch: `http://localhost:8002`

Issue a dev API key after startup:
```bash
python -m digikey.cli issue-key --tenant default --label dev --scopes '*' --kind dev_global
# Requires: DIGIKEY_ALLOW_DEV_GLOBAL=1 in .env and pip install -e ./digikey
```

### With digichat BFF

```bash
# Add to .env: AUTH_SECRET, AUTH_URL=http://127.0.0.1:3005, DIGICHAT_POSTGRES_PASSWORD
make up-digichat
# or: docker compose --profile digichat up -d --build
# digichat: http://127.0.0.1:3005
```

### With Heartbeat Monitoring

```bash
make up-heartbeat
# or: docker compose --profile heartbeat up -d
# Heartbeat polls /health every 30 min and appends to digiquant/results/audit/events.jsonl
```

### Local Dev (no Docker)

```bash
# Start all Python backends on host (digikey 8005, services 8000–8003, LiteLLM 4000)
make stack-local          # runs scripts/run_stack_local.sh

# Start digichat UI with hot reload (separate terminal)
make digichat-dev         # cd frontend/digichat && npm run dev → http://127.0.0.1:3000
```

Requires Python 3.12+ virtual environment with all packages installed editable:
```bash
pip install -e ./digibase -e ./digillm -e ./digifetch -e "./digismith[langsmith]" -e ./digikey \
            -e "./digigraph[dev]" -e "./digiquant[dev]" \
            -e "./digisearch[dev]"
```

### Seeding digisearch (local)

```bash
# After make up or make stack-local:
export DIGISEARCH_SEED_API_KEY=dgk_live_...   # key with digisearch:ingest scope
make seed-digisearch-local

# Optional EDGAR dev corpus:
make export-edgar-digisearch-dev              # downloads ~25 SEC filings
make seed-digisearch-edgar-dev                # ingest into edgar_dev index
```

### Critical Environment Variables

| Variable | Description | Required? |
|----------|-------------|-----------|
| `OPENAI_API_KEY` | OpenAI API key (LiteLLM container) | One of OpenAI or Ollama Cloud |
| `OLLAMA_API_KEY` | Ollama Cloud API key (free tier; LiteLLM container) | One of OpenAI or Ollama Cloud |
| `LITELLM_MASTER_KEY` | LiteLLM proxy admission secret | Recommended for production |
| `LITELLM_PROXY_API_KEY` | digigraph Bearer for LiteLLM proxy | Set to same as LITELLM_MASTER_KEY |
| `DIGIKEY_ADMIN_TOKEN` | Secret for issuing API keys via admin API | Required |
| `DIGIKEY_BFF_TOKEN` | digichat BFF session exchange token | Required for digichat |
| `DIGIKEY_ALLOW_EPHEMERAL_KEY` | `1` permits ephemeral JWKS (local dev only) | Set to `1` for local; use stable key in prod |
| `DIGIKEY_PRIVATE_KEY_PEM` | RS256 private key for stable JWT signing | Required for production (not ephemeral) |
| `DIGIKEY_LITELLM_PROXY_KEY` | Injected into token exchange response | Set to same as LITELLM_MASTER_KEY for funnel |
| `AUTH_SECRET` | Next-Auth signing secret for digichat | Required for digichat |
| `AUTH_URL` | Full public URL of digichat (must match browser origin) | Required for digichat |
| `DIGICHAT_POSTGRES_PASSWORD` | Postgres password for digichat-DB | Required for `digichat` profile |
| `LANGSMITH_API_KEY` | Enables LangSmith trace export from digigraph | Optional |
| `DIGI_LLM_MODE` | `test` / `medium` / `best` — model selection tier | Optional (default: `test`) |
| `DIGI_HUB_MODE` | `legacy` / `federated` — vertical delegate tool exposure | Optional (default: `legacy`) |
| `DIGI_ALLOW_CODE_EXEC` | `true` enables sandboxed Python in digigraph | Optional (default: off) |
| `DIGI_CHECKPOINTER` | `memory` / `sqlite` / `postgres` — LangGraph checkpoint backend | Optional (default: `memory`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTel collector endpoint for infra traces | Optional |
| `AUDIT_SINK_URL` | Remote audit event collector | Optional |
| `AUDIT_LOG_PATH` | Local JSONL audit file path | Optional (default in digiquant/results/audit/) |

---

## 10. Scalability and Kubernetes Path

### Current Limits

The default Docker Compose deployment is designed for a single machine (developer or small firm). Known scaling limits:

| Limit | Root Cause | Impact |
|-------|-----------|--------|
| Single-instance per service | Docker Compose; no replica support | No horizontal scaling; single point of failure |
| In-memory rate limiting | Per-process rate limiter in digigraph policy | Not distributed; resets on restart; ineffective with multiple replicas |
| LangGraph `MemorySaver` (default) | In-process Python dict | Thread state lost on restart; no cross-instance sharing |
| Chroma local volume | `digisearch_chroma` Docker volume on single host | Cannot be shared across digisearch replicas |
| LiteLLM local cache | `type: local` in `litellm.yaml` | Per-process disk cache; not shared with other LiteLLM instances |
| digikey SQLite (default) | `sqlite:////data/digikey.db` in container | Not suitable for multiple digikey replicas; switch to Postgres |

### Kubernetes Target Architecture

When scaling beyond a single machine, each service becomes a `Deployment`. Below is the target namespace layout:

```mermaid
graph TD
    subgraph ns-ingress [Namespace: digi-ingress]
        Ingress[NGINX / Tailscale Ingress]
    end
    subgraph ns-core [Namespace: digi-core]
        DG[digigraph Deployment\nreplicas: 2+\nPostgres checkpointer\nRedis rate limiter]
        DQ[digiquant Deployment\nreplicas: 1–2\nStateless backtest workers]
        DS[digisearch Deployment\nreplicas: 2+\nAzure AI Search or Qdrant backend]
        SM[digismith Deployment\nreplicas: 1]
        LM[LiteLLM Deployment\nreplicas: 2+\nRedis cache]
    end
    subgraph ns-auth [Namespace: digi-auth]
        DK[digikey Deployment\nreplicas: 2+\nShared Postgres required]
    end
    subgraph ns-chat [Namespace: digi-chat]
        DC[digichat Deployment\nreplicas: 2+]
        DCDB[Postgres StatefulSet\nor managed RDS/Cloud SQL]
    end
    subgraph ns-data [Namespace: digi-data]
        Redis[Redis StatefulSet\nor managed ElastiCache]
        PG[Postgres StatefulSet\nor managed RDS]
    end
    Ingress --> DG
    Ingress --> DC
    DG --> DK
    DG --> DS
    DG --> DQ
    DG --> LM
    DG --> PG
    DG --> Redis
    DK --> PG
    DS --> PG
    DC --> DCDB
    LM --> Redis
```

### Migration Steps: Compose → Kubernetes

| Concern | Compose Today | K8s Target | Action Required |
|---------|--------------|------------|-----------------|
| LangGraph checkpointer | `MemorySaver` (in-process) | Postgres (`DIGI_CHECKPOINTER=postgres`) | Set `DIGI_CHECKPOINTER_POSTGRES_URI`; install `langgraph-checkpoint-postgres` |
| digigraph rate limiting | Per-process dict | Redis-backed (`digibase` rate limiter) | Wire `REDIS_URL` to digigraph; implement distributed rate limiter (Phase 2) |
| digisearch vector store | Chroma local volume | Azure AI Search or Qdrant Cloud | Set `AZURE_SEARCH_*` env vars; Chroma is dev/test only |
| digikey storage | SQLite default | Postgres (required for multi-replica) | Set `DIGIKEY_DATABASE_URL=postgresql://...` |
| LiteLLM cache | Local disk | Redis (`type: redis` in litellm.yaml) | Set `REDIS_URL`; use `litellm-cache` profile → K8s Redis StatefulSet |
| Secrets | `.env` file | K8s Secrets → env injection | Migrate all `*_KEY`, `*_TOKEN`, `*_PASSWORD` vars to K8s Secrets |
| digibase credential broker | Not shipped | Central K8s service | Phase 1 digibase service: manages Postgres/Redis connection grants per tenant |
| Ollama inference | Local container | Separate GPU node pool | Ollama on GPU nodes; or use Ollama Cloud (`OLLAMA_API_KEY`) to skip self-hosting |

### Performance Targets (unchanged by scale)

- 10M-row NautilusTrader backtest: < 2 seconds
- 100k-parameter sweep: < 30 seconds
- Token reduction vs naive prompts: ≥ 70% (LiteLLM caching + mode-based model selection)

---

## Cross-Reference: Per-Component Architecture Docs

Each service maintains its own detailed architecture document. The root `ARCHITECTURE.md` (this file) covers inter-service topology. For component internals, read:

| Component | Doc |
|-----------|-----|
| digigraph | [digigraph/ARCHITECTURE.md](digigraph/ARCHITECTURE.md) |
| digiquant | [digiquant/ARCHITECTURE.md](digiquant/ARCHITECTURE.md) |
| digisearch | [digisearch/ARCHITECTURE.md](digisearch/ARCHITECTURE.md) |
| digismith | [digismith/ARCHITECTURE.md](digismith/ARCHITECTURE.md) |
| digibase | [digibase/ARCHITECTURE.md](digibase/ARCHITECTURE.md) |
| digiclaw | [digiclaw/ARCHITECTURE.md](digiclaw/ARCHITECTURE.md) |
| digikey | [digikey/ARCHITECTURE.md](digikey/ARCHITECTURE.md) |
| digichat | [frontend/digichat/ARCHITECTURE.md](frontend/digichat/ARCHITECTURE.md) |
| Frontend umbrella (ADR-0009) | [docs/adr/0009-frontend-umbrella.md](docs/adr/0009-frontend-umbrella.md) |
| Local full stack setup | [docs/LOCAL_STACK.md](docs/LOCAL_STACK.md) |
| LLM model configuration | [config/MODELS.md](config/MODELS.md) |
| Security hardening | [SECURITY.md](SECURITY.md) |

**API versioning:** HTTP APIs use a shared error envelope from `digibase`: `{"error": {"code", "message", "request_id", "service"}}`. Services echo and honor `X-Request-ID`. digiquant v1 job endpoints: `POST /v1/jobs/backtest`, `GET /v1/jobs/{job_id}/status`. Compatibility: prefer the same git SHA across all services in production.
