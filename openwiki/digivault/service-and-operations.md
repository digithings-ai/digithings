---
type: api-operations-guide
title: digivault Service and Operations
description: digivault HTTP routes, MCP operations, store precedence (D1 → filesystem → Supabase), JWT scope enforcement, tenant binding, rate limiting, tool dispatch model, and container profiles.
tags: [digivault, service, operations, mcp]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-19T12:20:11.463Z
sources:
  - id: openwiki-source-177aa6b06017b843d46bc98a
    resource: repo://digivault/ARCHITECTURE.md
  - id: openwiki-source-0683e4687f56ed72efb06696
    resource: repo://digivault/Dockerfile.mcp
  - id: openwiki-source-928e4ef93d07e66cd31f79b5
    resource: repo://digivault/src/digivault/mcp_server.py
  - id: openwiki-source-ad16574e0f9e829f380e00a8
    resource: repo://digivault/src/digivault/path_scopes.py
  - id: openwiki-source-331e7bc2a90cadb69cd8d283
    resource: repo://digivault/src/digivault/server.py
  - id: openwiki-source-0c9f1e037694094001ae9a5e
    resource: repo://digivault/src/digivault/tenant_scope.py
  - id: openwiki-source-9c6ec740fa4898b68fc6fdd1
    resource: repo://digivault/src/digivault/tool_dispatch.py
generated: { by: "openwiki/0.5.0", at: "2026-09-19T12:20:11.463Z" }
---

# digivault Service and Operations

digivault exposes a FastAPI HTTP API on port 8004 and an MCP server
(streamable HTTP, default `127.0.0.1:8769`) under separate Compose profiles.
The HTTP service reuses `digikey`'s `DigiAuthMiddleware` for JWT scope
enforcement and `digibase` for metrics, CORS, OpenTelemetry, and structured
error responses. The MCP server operates on `DIGIVAULT_ROOT` directly and
carries no JWT enforcement — gateway auth is the outer layer.

## HTTP Routes

| Method | Path | Scope / Auth | Description |
|--------|------|-------------|-------------|
| `GET` | `/healthz` | exempt | Liveness probe: `{"ok": true}` |
| `GET` | `/v1/status` | exempt | Operator diagnostic: reports config presence (service, version, `vault_configured`, `d1_configured`), never secrets |
| `GET` | `/metrics` | exempt | Prometheus metrics from `digibase.metrics.install_metrics` |
| `GET` | `/v1/notes` | `digivault:read` | List all notes in the caller's tenant-scoped vault |
| `GET` | `/v1/notes/{name}` | `digivault:read` | Fetch one note by filename stem |
| `POST` | `/v1/notes` | `digivault:write` | Create a note (or idempotent upsert with `overwrite: true`); accepts optional `frontmatter`, `subdir`, `tags` |
| `PATCH` | `/v1/notes/{name}/frontmatter` | `digivault:write` | Merge frontmatter keys into an existing note |
| `POST` | `/v1/notes/{name}/rename` | `digivault:write` | Rename a note; rewrites every inbound `[[wikilink]]` |
| `GET` | `/v1/notes/{name}/backlinks` | `digivault:read` | Return the list of notes that link to this note |
| `GET` | `/v1/tags/{tag}` | `digivault:read` | List notes carrying a given tag |
| `GET` | `/v1/lint` | `digivault:read` | Validate the vault: unresolved wikilinks, missing frontmatter, orphans, tags |
| `POST` | `/v1/notes/by-path` | `digivault:read` (POST, method-gated) | Load one note whole (`NoteDetail`: body + frontmatter) by exact `vault_path`. D1-only — no filesystem/Supabase fallback. `path_prefix` is a **required** field and an enforced authorization boundary. |
| `POST` | `/v1/notes/batch` | `digivault:write` | Bulk upsert notes and prune stale children through one vault index load |
| `POST` | `/v1/notes/prune-children` | `digivault:write` | Remove stale `{parent_doc}__*` segment notes inside a subdirectory (docs_onboard convergence) |
| `POST` | `/v1/orchestrator_tools` | `digivault:read` | Return OpenAI-style tool manifest for digigraph |
| `POST` | `/v1/orchestrator_invoke` | `digivault:read` | Execute one digivault tool by name (hub dispatch) |

Filesystem note routes (`GET /v1/notes`, `/v1/notes/{name}`, mutations,
backlinks, tags, lint) and vault-local orchestrator tools open the vault
through `_open_scoped_vault`, which narrows the shared `DIGIVAULT_ROOT` to
the caller's authenticated tenant corpus when `DIGI_TENANT_CORPUS_MAP` is
configured — the filesystem analogue of D1's one-database-per-corpus
isolation. A prefix that would escape `DIGIVAULT_ROOT` is refused with 503.

**Idempotent upsert:** `POST /v1/notes` accepts `overwrite: true` (and
optional `frontmatter`) so docs_onboard can idempotently write via
`Vault.write_note(..., overwrite=True)`. Default `overwrite: false`.

**Batch ingest:** `POST /v1/notes/batch` opens the vault once, applies all
note writes and stale-child prunes incrementally, then re-reads the
resulting notes — linear bulk ingest without rescanning per note.

## Scopes

`digivault_path_scopes` (defined in `digivault/path_scopes.py`, never in
digikey) maps each `(method, path)` pair to required digikey scopes:

- **Public paths** (`/healthz`, `/health`, `/metrics`, `/docs`, `/redoc`,
  `/openapi.json`, `/v1/status`) are auth-exempt.
- **`digivault:read`** for GET note routes, `POST /v1/orchestrator_tools`,
  `POST /v1/orchestrator_invoke`, and `POST /v1/notes/by-path`.
- **`digivault:write`** for all other POST/PUT/PATCH/DELETE note routes.

**By-path read scope:** `POST /v1/notes/by-path` is scoped `digivault:read`
despite being POST — it carries `vault_path`/`path_prefix` in the body and is
a pure read. The carve-out matches on method as well as path, so a
hypothetical future non-POST verb on the same path is not silently
read-scoped.

**Orchestrator invoke scope:** `/v1/orchestrator_invoke` gates at
`digivault:read` (most tools are reads). The one mutating tool
(`digivault_create_note`) enforces `digivault:write` itself in the handler
(`_require_tool_scope`), keyed on the requested tool name, so a read-only
caller cannot reach it via this shared endpoint.

## Tenant Binding

Two independent enforcement layers cover `path_prefix`, not one:

**Layer 1 (digigraph):** `_handle_digivault_search` and
`_handle_digivault_get_note` overwrite `path_prefix` from
`ToolContext.vault_path_prefix` unconditionally before invoking — a
model-supplied value is always discarded. This protects the model →
digigraph leg.

**Layer 2 (digivault server-side, `tenant_scope.py`):**
`enforce_tenant_path_prefix` binds the caller-supplied `path_prefix` to the
JWT tenant (`request.state.digi_auth.tenant_slug`) via
`DIGI_TENANT_CORPUS_MAP`. This closes the gap where `digivault:read` alone
proves route access but carries no tenant identity — any caller holding it
could name *any* prefix in `D1_DATABASE_MAP`, not just their own corpus's.
An independent fix for callers that talk to digivault directly, bypassing
digigraph entirely.

Behavior by map state:
- **Genuinely unset:** no-op — single-tenant deployments (local dev,
  self-hosted single vault) are unchanged.
- **Set:** fails closed. A `path_prefix` mismatching the map entry for the
  caller's tenant, or a tenant absent from the map, returns 403.
- **Set but unusable** (bad JSON, non-object top level, every entry
  individually malformed, a `vaultPathPrefix` that normalizes to empty):
  `TenantCorpusMapError` → 503, never silently treated as unset.

The check runs once, before the D1/local-vault/Supabase precedence branch,
so all three backends are covered uniformly.

For filesystem note routes there is no caller-supplied `path_prefix` to
bind, so `_open_scoped_vault` resolves the tenant's own mapped prefix from
`mapped_tenant_path_prefix` and opens the vault at that subdirectory.
`mapped_tenant_path_prefix` fails closed: 403 for an unmapped tenant, 503
for a map set but unusable.

**Known residual:** `tenant_slug` is only as trustworthy as
`DigiAuthMiddleware` makes it — the middleware falls back to the unsigned
`X-Digi-Tenant` header when the JWT's `tenant_slug` claim is empty. Tracked
as #2303.

## Search Precedence

`digivault_search_notes` (both the orchestrator invoke branch and the MCP
`search_notes` tool) follows a strict three-tier fallback:

1. **D1** when `_d1_configured()` is true — the shared Cloudflare credential
   pair (`CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN`, falling back to
   legacy `VECTORIZE_*` then `D1_*` names via `_d1_credentials`) plus
   `D1_DATABASE_MAP` are all set. D1 wins even when `DIGIVAULT_ROOT` is
   also set — production sets `DIGIVAULT_ROOT=/data/vault` pointing at
   baked seed stubs, and those must never shadow the real corpus.
   `D1Store.search` uses FTS5 over the Cloudflare D1 REST API. A partial
   config (some but not all three vars set) is `D1StoreError` → 503.

2. **Local filesystem** when `DIGIVAULT_ROOT` is set — keyword search via
   `local_search.search_local_vault` (Profile A / client volumes, no
   Supabase needed). Optional `path_prefix` isolates client subdirs.

3. **Supabase FTS** via `SupabaseStore.search` (the
   `search_architecture_notes` RPC, anon-key, read-only). Returns 503 only
   if `CORE_SUPABASE_URL`/`CORE_SUPABASE_ANON_KEY` are unset.

`digivault_get_note` and `POST /v1/notes/by-path` are D1-only — no
filesystem/Supabase fallback. Both surface 503 on a non-D1 deployment.

`limit` is clamped to `[1, 50]` regardless of caller input.

## D1Store (`digivault/d1_store.py`)

`D1Store` is a read-only Cloudflare D1 REST-API client for one corpus's
note database. Credentials are constructor args, never read from the
environment inside the class — `server.py` reads env. Each corpus is a
separate D1 database (`D1_DATABASE_MAP` maps vault prefix → database id),
so tenant isolation is structural.

`query()` — the single call site every read/write goes through — retries up
to `MAX_ATTEMPTS` (3) with exponential backoff plus jitter on a transport
error or a status `_is_retryable_status` accepts: 429, 5xx, and 401.
Every other status (400/403/404/422) fails on the first attempt. Backoff is
delivered through an injectable `sleep` constructor arg so tests never
really sleep. Retrying writes is safe only because they are idempotent by
construction (`CREATE ... IF NOT EXISTS`, `ON CONFLICT ... DO UPDATE`, FTS
rebuild fully re-derives).

`D1StoreError` is isolated in `d1_errors.py` so it stays importable even
if `d1_store.py` fails to load.

## Tool Dispatch

`tool_dispatch.py` is the canonical registry — all digivault tool names
live here:

- **`DISPATCH_TOOL_NAMES`**: the full set of six tool names
  (`digivault_search_tag`, `digivault_backlinks`, `digivault_lint`,
  `digivault_create_note`, `digivault_search_notes`,
  `digivault_get_note`).

- **`VAULT_HANDLERS`**: vault-local handlers for the four filesystem-backed
  tools (tag/backlinks/lint/create_note). Both `mcp_server` and
  `server.orchestrator_invoke` route through `dispatch_vault_tool` — no
  duplicate handler tables.

- **Runtime-only tools** (`digivault_search_notes`, `digivault_get_note`):
  claim into the same dispatch table via `register_runtime_handler` from
  `server.py` at import time. `dispatch_tool_names()` equals the full
  canonical set once the HTTP app is loaded.

- **MCP discovery** (`mcp_tool_names()`): advertises the MCP surface name
  of each vault-local handler (`search_tag`, `backlinks`, `lint`,
  `create_note`) plus the MCP-registered `search_notes` runtime tool.
  `get_note` stays orchestrator-only.

- **MCP `search_tag`** projects a slim JSON array of
  `{name, title, rel_path}` (pre-#3041 contract); orchestrator invoke
  keeps the shared handler's `{"notes": [...]}` envelope.

- Vault-local handlers honour an optional `path_prefix`: reads are
  filtered beneath that subdirectory and `create_note` writes beneath it,
  with `../`/leading-dot components refused. Duplicate-stem handling is
  scope-aware: `lint` scopes inside `Vault.lint(scope=…)` and
  `create_note` passes the prefix as `scope`, so a stem living only outside
  the prefix neither blocks the write nor leaks its existence.

```
digigraph / MCP client
│
├─ MCP tools/list ──────────► mcp_server ──register_mcp_tools──► VAULT_HANDLERS
│                              │
├─ MCP tools/call ─────────────────────┴──► dispatch_vault_tool
│
├─ POST /v1/orchestrator_tools ──► orchestrator_tools (names from tool_dispatch)
│
└─ POST /v1/orchestrator_invoke
   ├─ search_notes / get_note ──► server.py (D1 / tenant) + register_runtime_handler
   └─ tag / backlinks / lint / create_note ──► dispatch_vault_tool
```

## MCP Server

`python -m digivault.mcp_server` is a thin transport wrapper over
FastMCP. Tool registration goes exclusively through
`tool_dispatch.register_mcp_tools` — no `@mcp.tool` handlers are defined
in `mcp_server.py`.

- **Default transport:** streamable HTTP on `127.0.0.1:8769`.
- **Override host:** `--host` flag or `DIGIVAULT_MCP_HOST` env var.
- **Override port:** `--port` flag (default 8769).
- **Stdio transport:** `--stdio` flag for trusted local clients (Claude
  Desktop).
- **Vault:** opened from `DIGIVAULT_ROOT`; raises `VaultError` if unset.

**MCP-exposed tools:** `search_notes` (required `path_prefix`; D1 → local
→ Supabase), `search_tag`, `backlinks`, `lint`, and `create_note`.
`create_note` registers but refuses calls unless `DIGIVAULT_MCP_WRITE=1`.
`digivault_get_note` stays orchestrator-only.

**No JWT check:** the MCP sidecar carries no `DIGIKEY_*` env vars — treat a
wider bind as a network API with gateway auth.

## Container Profiles

### Profile: `digivault` (HTTP API)

- **Build:** `digivault/Dockerfile`, repo-root context, `digivault[service]`
  extra (never `[supabase]`).
- **Port:** `127.0.0.1:8004:8004`, loopback-bound.
- **Env:** inherits `.env`; sets `DIGIVAULT_ROOT=/data/vault` (volume
  `digivault_data`), `DIGIKEY_JWKS_URL`/`DIGIKEY_ISSUER`/
  `DIGIKEY_AUDIENCE` for JWT verification.
- **Depends on:** digikey (service_healthy).
- **Healthcheck:** `curl -f http://127.0.0.1:8004/healthz` every 15s.
- **Start:** `docker compose --profile digivault up -d`.

### Profile: `digivault-mcp` (MCP Server)

- **Build:** `digivault/Dockerfile.mcp`, repo-root context,
  `digivault[service]` extra. Workspace deps (digibase, digikey) are
  installed editable first.
- **Image:** `digi-digivault-mcp:latest`.
- **Port:** `127.0.0.1:8769:8769`.
- **Env:** `DIGIVAULT_ROOT=/data/vault` (same volume).
- **Start:** `docker compose --profile digivault-mcp up -d`.

In the Cloudflare stack (`digithings-stack-cloudflare`), the MCP server
runs inside the Container under supervisord as
`[program:digivault-mcp]` (`python -m digivault.mcp_server --port 8769
--host 0.0.0.0`), reachable only through the key-gated
`/_stack/mcp/digivault/*` edge route (`MCP_EDGE_KEY`).

## Rate Limiting

Per-IP sliding window (in-process `deque` + lock), mirroring
`digisearch/server.py`:

| Path | Limit |
|------|-------|
| `/v1/orchestrator_invoke` | 10 requests / 60s |
| `/v1/orchestrator_tools` | 30 requests / 60s |
| `/healthz` | exempt |
| everything else | 30 requests / 60s (default) |

Reads the IP from `X-Forwarded-For` (first hop) or `request.client.host`.
`DIGI_DISABLE_RATE_LIMIT=1` disables it (tests). TestClient traffic
(`client.host == "testclient"`) is exempt. Exceeding the limit returns 429
with `code: rate_limit_exceeded` and a `Retry-After` header.

## Environment Variables

| Var | Purpose |
|-----|---------|
| `DIGIVAULT_ROOT` | Path to the managed vault directory (required for filesystem note routes; 503 when unset) |
| `DIGIVAULT_MCP_HOST` | MCP bind host (default `127.0.0.1`) |
| `DIGIKEY_JWKS_URL` / `DIGIKEY_ISSUER` / `DIGIKEY_AUDIENCE` / `DIGIKEY_PUBLIC_KEY_PEM` | digikey JWT verification |
| `DIGI_DISABLE_RATE_LIMIT` | `1`/`true`/`yes` disables the per-IP rate limiter |
| `CORE_SUPABASE_URL` + `CORE_SUPABASE_ANON_KEY` | Supabase FTS fallback credentials (only when neither D1 nor `DIGIVAULT_ROOT` is configured) |
| `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` + `D1_DATABASE_MAP` | D1 credentials. Canonical names first, legacy `VECTORIZE_*` then `D1_*` fallback. All three must be set for D1 to be authoritative. `D1_DATABASE_MAP` is a JSON object `{"<vault-prefix>": "<database id>"}` and must not contain a `""` key. |
| `DIGI_TENANT_CORPUS_MAP` | Optional. JSON object keyed by tenant slug → `{vaultPathPrefix, ...}`. No-op when unset; fails closed (403/503) when set. Parsed independently in `tenant_scope.py` so digivault stays installable standalone. |
| `DIGIVAULT_MCP_WRITE` | Set to `1` to enable `create_note` on the MCP surface |
