# DigiChat — Architecture

> **Scope:** Production Next.js 16 BFF + React 19 chat UI at `digichat/`.
> The legacy zero-dependency demo at `website/digichat/` is out of scope.

---

## 1. Overview

DigiChat is the **user-facing interface** to the DigiThings ecosystem. It is a Next.js
16 App Router application that acts as a **Backend-for-Frontend (BFF)**: the browser
never speaks directly to DigiGraph or any Python service. All LLM calls, auth token
exchanges, and upstream probes are handled in Next.js Route Handlers running on the
server.

### Capability matrix

| Capability | Status |
|---|---|
| React 19 streaming chat (`useChat`, AI SDK v6) | Built |
| Auth.js v5 — generic OIDC provider | Built |
| Auth.js v5 — dev password provider (`DIGICHAT_DEV_AUTH`) | Built |
| DigiKey JWT exchange (`bff_session` + `api_key` grants) | Built |
| Machine API key auth (`digi_live_…`, hashed in Postgres) | Built |
| Conversation persistence — localStorage (always on) | Built |
| Conversation persistence — Postgres (optional) | Built |
| DigiGraph trace stream (`data-digigraphTrace` parts) | Built |
| RAG sources card + Research brief card | Built |
| Quant comparison strip (inline `BacktestResult` parsing) | Built |
| Quant run persistence (`quant_runs` table) | Built |
| Ecosystem side panel (service URLs + health badges) | Built |
| Auto-migration on container boot (`DIGICHAT_AUTO_MIGRATE=1`) | Built |
| Docker Compose profile (`digichat` + `digichat-db`) | Built |
| OpenClaw gateway integration | Not yet (Phase 2) |
| RAG document ingestion UI | Not yet (Phase 2) |
| Fine-grained permission admin UI | Not yet (Phase 2) |
| DigiBase credential brokering | Not yet (roadmap) |

---

## 2. Current Implementation State

### What is built

**React chat shell** (`src/components/chat-shell.tsx`): Client component that owns
thread state. On mount it merges `localStorage` threads with a server `GET
/api/conversations` call, then renders a shadcn Sidebar with conversation list, New
chat button, rename/delete overflow menus, and the main `ChatPanel`.

**AI SDK `useChat`** (`src/components/chat-panel.tsx`): Uses `@ai-sdk/react` with a
`DefaultChatTransport` pointed at `POST /api/chat`. Sends `X-Digichat-Session` header
so upstream DigiGraph can correlate the same conversation across turns. Scroll
stick-to-bottom with a "New messages" chip when scrolled up. Copy and Regenerate
actions on assistant bubbles.

**Conversation persistence** (`src/lib/thread-local.ts`, `src/lib/conversations-repo.ts`):
Dual-path. `localStorage` is always written (versioned blob `{ v: 1, threads: [...] }`
under key `digichat-threads:<userId>`). When `DIGICHAT_DATABASE_URL` is set and the
tenant is provisioned, a 650 ms debounced server-save flushes via `PUT
/api/conversations/[id]`.

**Quant strip** (`src/components/quant-comparison-strip.tsx`): Recursively scans
assistant message parts for objects that look like `BacktestResult`
(`run_id` + `sharpe_ratio` or `num_trades`). Renders a compact metrics table below the
composer. No back-end call needed; parsing is client-side.

**Ecosystem health badges** (`src/components/connections-sheet.tsx`): Side sheet that
calls `GET /api/ecosystem/config` and `GET /api/health`, then renders color-coded
badges (emerald = ok, amber = not ok) for digraph / digiquant / digismith / digisearch
/ database. Endpoint overrides are stored in an httpOnly cookie
(`digichat-endpoints`, 180-day `maxAge`).

**Auth.js OIDC** (`src/auth.ts`): Generic OIDC provider activated when
`AUTH_OIDC_ISSUER` + `AUTH_OIDC_CLIENT_ID` + `AUTH_OIDC_CLIENT_SECRET` are set.
Dev credentials provider (`DIGICHAT_DEV_AUTH=1`). Dev-only local-bootstrap provider
(`DIGICHAT_LOCAL_AUTH_KEY`). Session stored as an encrypted JWT cookie
(`AUTH_SECRET` / `NEXTAUTH_SECRET`).

**DigiKey machine key exchange** (`src/lib/digikey-exchange.ts`): Two exchange paths:
`bff_session` grant (BFF presents `DIGIKEY_BFF_TOKEN` on behalf of an OIDC session)
and `api_key` grant (client presents a `dgk_live_…` Bearer that the BFF exchanges at
DigiKey). Both return a short-lived JWT + optional `litellm_proxy_api_key`.

**Drizzle ORM** (`src/db/schema.ts`, `src/db/index.ts`): Postgres-js driver, `max: 10`
connection pool. Six tables: `tenants`, `user_tenants`, `api_keys`, `conversations`,
`conversation_messages`, `quant_runs`. Managed by three migration files in `drizzle/`.

**Source file reference table**

| File | Purpose |
|---|---|
| `src/app/page.tsx` | Server component: auth gate → redirect to `/login` or render `ChatShell` |
| `src/app/layout.tsx` | Root layout with `Providers` (session, tooltips) |
| `src/app/login/` | Login page + form |
| `src/app/api/chat/route.ts` | Primary BFF chat endpoint |
| `src/app/api/v1/chat/route.ts` | Machine-client alias — re-exports the chat route |
| `src/app/api/conversations/route.ts` | List + create conversations |
| `src/app/api/conversations/[id]/route.ts` | Get + update + delete a conversation |
| `src/app/api/conversations/[id]/quant-runs/route.ts` | List + insert quant runs |
| `src/app/api/ecosystem/config/route.ts` | Read / write ecosystem endpoint cookie |
| `src/app/api/health/route.ts` | Readiness probe for all services |
| `src/app/api/auth/[...nextauth]/route.ts` | Auth.js handler |
| `src/app/actions/local-bootstrap.ts` | Server action: dev auto-sign-in |
| `src/auth.ts` | Auth.js config (providers, JWT/session callbacks) |
| `src/db/schema.ts` | Drizzle schema — all tables |
| `src/db/index.ts` | Singleton Postgres client + `getDb()` |
| `src/lib/digigraph.ts` | `createDigiGraphClient`, model name helpers |
| `src/lib/digigraph-messages.ts` | Content coercion for DigiGraph OpenAI body |
| `src/lib/digigraph-upstream.ts` | `resolveDigigraphUpstreamAuth` — JWT resolution |
| `src/lib/digikey-exchange.ts` | DigiKey token exchange (both grant types) |
| `src/lib/stream-digigraph-trace.ts` | Trace-aware SSE → UI message stream |
| `src/lib/conversations-repo.ts` | Drizzle query helpers (conversations + quant runs) |
| `src/lib/thread-local.ts` | localStorage read/write/merge |
| `src/lib/ecosystem.ts` | Endpoint resolution + SSRF guard |
| `src/lib/capabilities.ts` | `DIGICHAT_ENABLED_SERVICES` parsing |
| `src/lib/request-auth.ts` | `requireDigiChatAuth` shared auth helper |
| `src/lib/tenant.ts` | OIDC subject → tenant slug lookup |
| `src/lib/api-key.ts` | Machine key validation (env bootstrap + bcrypt Postgres) |
| `src/lib/migrate.ts` | Programmatic Drizzle migration runner |
| `src/instrumentation.ts` | Next.js instrumentation hook: `DIGICHAT_AUTO_MIGRATE=1` |
| `src/components/chat-shell.tsx` | Sidebar + thread state manager |
| `src/components/chat-panel.tsx` | `useChat` + message list + composer |
| `src/components/connections-sheet.tsx` | Ecosystem side sheet |
| `src/components/quant-comparison-strip.tsx` | Backtest metrics table |
| `src/components/digigraph-trace.tsx` | Trace card components |
| `src/components/providers.tsx` | Client providers wrapper |
| `src/components/local-bootstrap-gate.tsx` | Dev auto-sign-in gate |

---

## 3. API Surface

All route handlers live under `src/app/api/`. Authentication is required on every
endpoint except `GET /api/health` (which is unauthenticated to serve as a liveness
probe).

### Chat

**`POST /api/chat`** (also aliased at `POST /api/v1/chat`):
- Auth: Auth.js session cookie or `Authorization: Bearer <machine-key>`.
- Request body: `{ messages: UIMessage[] }` (AI SDK UI message format).
- Notable request headers: `X-Digichat-Session` / `X-Session-Id` (stable UUID for upstream tracing), `X-Request-ID` (propagated to DigiGraph), `X-Digichat-Trace: 0` (opt out of trace stream).
- Response: Server-Sent Events (AI SDK UI message stream) — text deltas plus optional `data-digigraphTrace` parts.
- The route resolves upstream auth, builds a `createDigiGraphClient`, then either (a) calls `createDigigraphTraceStreamResponse` for the trace path or (b) calls `streamText` with `smoothStream` for the legacy path.
- `maxDuration = 120` (Vercel/Next.js edge timeout).
- **Rate limiting (two layers):** every request hits a shared per-`{tenantSlug}:{ownerUserSub}` sliding-window check (`checkBffRateLimit`, `DIGICHAT_CHAT_RATE_LIMIT_MAX`/`_WINDOW_MS`, default 30/min). Unauthenticated `/embed` requests all resolve to the *same* `ownerUserSub` (`embed:anonymous`, see below), so they'd share one bucket — a per-IP check (`checkEmbedIpRateLimit`, `DIGICHAT_EMBED_IP_RATE_LIMIT_MAX`/`_WINDOW_MS`, default 10/min) runs first for that case, so one visitor can't exhaust the shared quota for everyone (#1251). **Invariant:** the per-IP default must stay below the shared default, or the shared bucket's ceiling binds first and the per-IP layer becomes a no-op (caught in review on the first cut of #1251, which shipped 60 against a shared default of 30 — see the regression test in `embed-ip-rate-limit.test.ts`). IP is read from `cf-connecting-ip`, falling back to the first `X-Forwarded-For` hop — both are spoofable by the client unless a proxy in front strips/overwrites them (true of Cloudflare in the ADR-0018 production deployment, not guaranteed elsewhere). DigiGraph closed the equivalent gap with a `DIGI_TRUSTED_PROXIES` allowlist (`digigraph/ARCHITECTURE.md` §12.8, REM-027); DigiChat has no equivalent yet — acceptable for now since this is a rate-limiting decision, not an authorization one, but tracked as a follow-up.
- **Anonymous `/embed` requests** (`resolveEmbedChatTenant` in `embed-chat-tenant.ts`) resolve to `{ tenantSlug: "embed", ownerUserSub: "embed:anonymous" }` when `DIGICHAT_EMBED_ENABLED=1` or a valid `X-Embed-Token` is presented; otherwise 503. This path never touches `conversations-repo` — no server-side persistence call exists in this route for any caller (persistence, when it happens, is client-initiated via the separate `/api/conversations` endpoints below, which require a real session).

### Conversations

**`GET /api/conversations`** — returns `{ serverPersistence: boolean, conversations: [{ id, title, updatedAt }] }`. When no DB is configured, returns `serverPersistence: false` with an empty list.

**`POST /api/conversations`** — body `{ id?: string, title?: string }`. Returns `{ id }` with 201. The optional client `id` allows the UI to pre-mint a UUID so it matches the `threadId` used in `useChat`.

**`GET /api/conversations/[id]`** — returns `{ id, title, messages: UIMessage[] }`.

**`PUT /api/conversations/[id]`** — body `{ title?: string, messages: UIMessage[] }`. Full replace of stored messages (delete + re-insert). Returns 204.

**`DELETE /api/conversations/[id]`** — returns 204.

**`GET /api/conversations/[id]/quant-runs`** — returns `{ runs: QuantRunRow[] }`.

**`POST /api/conversations/[id]/quant-runs`** — body `{ label?, strategyName, symbols, strategyParams?, backtestResult }`. Returns `{ id }` with 201.

### Ecosystem

**`GET /api/ecosystem/config`** — Auth.js session required. Returns `{ effective, defaults, hasCustomEndpoints, persistence: { serverDatabaseConfigured } }`.

**`POST /api/ecosystem/config`** — body: endpoint URLs object or `{ reset: true }`. Validates URLs through `isAllowedServiceUrl`, writes an httpOnly cookie, returns `{ ok, effective }`.

### Health

**`GET /api/health`** — unauthenticated. Probes `{base}/health` for all enabled services (4 s AbortController timeout per service). Probes Postgres with `SELECT 1`. Returns `{ ok, checks, version }`. HTTP 200 when healthy, 503 when any required service is unreachable.

### Auth

**`GET /api/auth/[...nextauth]`** and **`POST /api/auth/[...nextauth]`** — standard Auth.js handlers. OIDC callback, credentials sign-in, session refresh, sign-out.

### Streaming behavior

The `/api/chat` route does not use WebSockets. All streaming is HTTP/1.1
`Transfer-Encoding: chunked` SSE (Server-Sent Events) surfaced as a ReadableStream.
DigiGraph sends OpenAI-compatible SSE (`data: {...}`). The BFF either pipes through AI
SDK's `streamText` (legacy path) or manually iterates the SSE stream in
`iterateOpenAiSse` and re-emits as AI SDK UI message stream parts (trace path). There
is no back-pressure mechanism on the BFF-to-DigiGraph leg beyond the native Node.js
stream backpressure; see Section 7.

---

## 4. Data Model

### Drizzle schema (`src/db/schema.ts`)

**`tenants`** — `id` (UUID PK), `slug` (unique text), `name`, `created_at`. Root
multi-tenancy unit. Provisioned manually or via `npm run db:seed`.

**`user_tenants`** — `id`, `provider_account_id` (OIDC `sub`), `tenant_id` (FK →
`tenants`), `created_at`. Unique index on `(provider_account_id, tenant_id)`.
Maps OIDC subjects to tenants. Currently requires manual SQL insert or a future admin
UI.

**`api_keys`** — `id`, `tenant_id` (FK), `key_hash` (bcrypt), `key_prefix` (first 20
chars, used for cheap prefix lookup), `label`, `created_at`. Machine API keys.
Created via `npm run db:create-key -- <slug> <label>`.

**`conversations`** — `id` (UUID, client-mintable), `tenant_id` (FK), `owner_user_sub`
(OIDC sub or `machine:<slug>`), `title`, `created_at`, `updated_at`. Index on
`(tenant_id, owner_user_sub, updated_at)` for paginated listing.

**`conversation_messages`** — `id`, `conversation_id` (FK, CASCADE delete), `sequence`
(int, 0-based), `payload` (JSONB, full AI SDK `UIMessage`), `created_at`. Unique index
on `(conversation_id, sequence)`. The full `PUT /api/conversations/[id]` replaces the
entire message set (delete all + re-insert by sequence index). No incremental append.

**`quant_runs`** — `id`, `conversation_id` (FK, CASCADE delete), `label`, `strategy_name`,
`symbols` (JSONB `string[]`), `strategy_params` (JSONB, nullable),
`backtest_result` (JSONB), `created_at`. Index on `(conversation_id, created_at)`.

### AI SDK message format

Messages conform to AI SDK v6 `UIMessage`: `{ id: string, role: "user"|"assistant",
parts: UIPart[] }`. Parts include `TextUIPart`, `ReasoningUIPart`, `ToolInvocationUIPart`,
and the custom `data-digigraphTrace` part emitted by the trace stream. Messages are
stored verbatim as JSONB in `conversation_messages.payload`.

### BacktestResult parsing

The quant strip client-scans assistant message parts recursively for objects containing
`run_id` plus at least one of `sharpe_ratio` or `num_trades`. Fields read:
`run_id`, `strategy_name`, `sharpe_ratio`, `total_return_pct`, `max_drawdown_pct`,
`num_trades`. This scan is opportunistic and schema-free, which makes it resilient to
DigiQuant payload evolution but also silently ignores malformed results.

### DigiKey exchange response

`POST /v1/oauth/token` at DigiKey returns `{ access_token, litellm_proxy_api_key? }`.
The `litellm_proxy_api_key` is forwarded to DigiGraph as `X-LiteLLM-Proxy-Key` when
present, allowing LiteLLM to route models per-tenant.

---

## 5. Internal Architecture

### Next.js App Router structure

```
src/app/
  layout.tsx            # Root layout (Providers, Inter font)
  page.tsx              # Server component: auth gate → ChatShell
  login/                # Login page
  api/
    auth/[...nextauth]/ # Auth.js handlers
    chat/               # BFF chat endpoint
    v1/chat/            # Machine-client alias
    conversations/      # CRUD + quant-runs
    ecosystem/config/   # Endpoint cookie management
    health/             # Readiness probe
src/components/         # Client and server components
src/lib/                # Server-side utility modules
src/db/                 # Drizzle client + schema
src/auth.ts             # Auth.js configuration
src/instrumentation.ts  # Auto-migrate hook
```

The root `page.tsx` is a **React Server Component** that calls `auth()` synchronously
and redirects to `/login` when no session exists. `ChatShell` is a `"use client"`
component that owns all thread state as React state; the server renders nothing but
the initial HTML shell for it.

### BFF pattern (route handlers)

Route handlers run on the Node.js runtime (not Edge). They are the sole callers of
DigiGraph, DigiKey, and DigiSearch. The browser has no direct path to the Python
services. This is enforced by network topology (Python services bind to container-
internal names or loopback) and by the BFF design itself: the upstream bearer token is
never sent to the client.

### AI SDK streaming pipeline

```
Browser (useChat)
  │  POST /api/chat  {messages, X-Digichat-Session}
  ▼
BFF route handler
  ├─ Auth: session cookie OR machine key bcrypt check
  ├─ Tenant resolution (user_tenants lookup or env fallback)
  ├─ Upstream auth: DigiKey bff_session | api_key exchange | static key
  │
  ├─ Trace path (default, DIGICHAT_TRACE_UI != "0")
  │   ├─ POST {base}/v1/chat/completions  (raw fetch, no AI SDK client)
  │   ├─ iterateOpenAiSse: parse SSE frames
  │   │   ├─ delta.content  → text-delta parts
  │   │   └─ delta.digigraph_trace → data-digigraphTrace parts
  │   └─ createUIMessageStreamResponse → SSE to browser
  │
  └─ Legacy path (DIGICHAT_TRACE_UI=0 or X-Digichat-Trace: 0)
      ├─ createDigiGraphClient → AI SDK OpenAI provider
      ├─ streamText + smoothStream(chunking: "word")
      └─ toUIMessageStreamResponse → SSE to browser
```

### Auth.js session flow

1. User visits `/`. Server component calls `auth()` — reads and decrypts the session
   JWT from the httpOnly `__Secure-authjs.session-token` cookie.
2. No session → `redirect("/login")`.
3. Login page submits credentials to `POST /api/auth/callback/credentials` (dev) or
   initiates OIDC redirect (production).
4. Auth.js writes an encrypted session JWT cookie. `jwt` callback copies `user.id` →
   `token.sub`. `session` callback copies `token.sub` → `session.user.id`.
5. On subsequent requests, `auth()` decrypts the cookie and returns the session. No
   database session store — stateless JWT only.

### DigiKey JWT exchange flow

On every `/api/chat` call:
1. If the incoming request carries `Authorization: Bearer dgk_live_…`, the BFF calls
   `POST {DIGIKEY_URL}/v1/oauth/token` with `grant_type=api_key` and the raw key.
   DigiKey validates and returns a short-lived JWT.
2. Otherwise, if `DIGIKEY_URL` and `DIGIKEY_BFF_TOKEN` are set, the BFF calls
   `POST {DIGIKEY_URL}/v1/oauth/token` with `grant_type=bff_session`, the BFF token,
   tenant slug, and OIDC subject. DigiKey returns a short-lived JWT scoped to that
   tenant+subject.
3. Fallback: `DIGIGRAPH_UPSTREAM_API_KEY` static bearer (bootstrap only).
4. The resulting JWT is forwarded as `Authorization: Bearer <JWT>` to DigiGraph,
   along with `X-Digichat-Tenant`, `X-Digi-Caller: digichat`, `X-Session-Id`,
   `X-Request-ID`, and optionally `X-LiteLLM-Proxy-Key`.

A new JWT is exchanged on **every** chat request. There is no client-side caching of
the upstream JWT; this is safe but adds one HTTP round-trip latency to every message
send (see Section 8).

### Drizzle migration approach

Three SQL migration files in `drizzle/`:
- `0000_init.sql` — `tenants`, `user_tenants`, `api_keys`
- `0001_conversations.sql` — `conversations`, `conversation_messages`
- `0002_quant_runs.sql` — `quant_runs`

`runMigrate()` in `src/lib/migrate.ts` opens a single-connection Postgres client,
calls `drizzle-orm migrate()`, then closes. It is called from
`src/instrumentation.ts` when `DIGICHAT_AUTO_MIGRATE=1` and `NEXT_RUNTIME=nodejs`
(i.e., on the first server startup, not on edge routes).

### localStorage vs Postgres persistence dual-path

`saveLocalThreads` is called on every state mutation (new thread, message commit, rename,
delete). It is synchronous and writes the full thread list to `localStorage` on every
call, which becomes a concern for large conversation histories (see Section 8).

When Postgres is available, `flushServerSave` is debounced at 650 ms after the last
mutation. It first creates the conversation row if `remote: false`, then issues a `PUT`
with the full message array. This is a full-replace strategy — not an append — so it
re-sends the entire conversation on every flush. For long threads this may be
non-trivial in payload size.

This entire dual-path is inapplicable to the anonymous `/embed` surface: `src/app/embed/page.tsx`
calls only `useChat` against `POST /api/chat` — it never imports `saveLocalThreads`,
`flushServerSave`, or anything from `conversations-repo`. Even if it did, every
`/api/conversations*` route calls `requireDigiChatAuth()` first, which 401s a bare
anonymous request before any read/write — so no Postgres row can be created for
`ownerUserSub: "embed:anonymous"` (verified by inspection for #1251, not assumed).

### Embed tenant registry & external backends

`DIGICHAT_EMBED_TENANTS` (JSON, keyed by hostname) declares embed tenants:
per-host `slug`, `backend` (`digigraph` | `external-relay` + https URL),
`gateMode` (`turn_limited` | `ungated`), `theme` (`dark` | `light`),
optional `accent` hex pair, `attribution` flag, `aliases`, and a required
`token`. Parsed fail-fast in `src/lib/embed-tenants.ts`; the same registry
feeds `/api/chat` tenant resolution (`src/lib/embed-chat-tenant.ts`), the
client-safe `GET /api/embed/tenant-config` endpoint, and the `/embed`
CSP frame-ancestors (`src/lib/security-headers.ts` — which means the env
var must be present at build time, not just runtime).

`external-relay` tenants bypass DigiGraph entirely: `/api/chat` proxies to
the configured relay via `src/lib/external-relay-stream.ts`, translating
the relay's SSE contract (`conversation`, `text-delta`, `trace`, `done`,
`error`) into AI SDK UI message stream parts. Conversation state lives on
the relay's side (e.g. Azure Foundry conversations); the client echoes the
relay's conversation id via `X-External-Conversation` (sessionStorage,
`digichat_embed_conversation:<host>`). Both rate limiters (per-IP embed +
shared BFF bucket, now keyed by the tenant's real slug) run before the
backend branch. Relay URLs come from config, never the request, so there
is no open-proxy/SSRF surface. First consumer: DataTapStream (datatap-web)
via its Azure Function relay.

**`X-Embed-Host` alone is not sufficient authorization (#1339).** A tenant's
host string is its own public domain, so `resolveEmbedTenantByHost` never
grants embed access by itself — `resolveVerifiedEmbedTenant`
(`src/lib/embed-chat-tenant.ts`) additionally requires the request's
`X-Embed-Token` header to match that tenant's own registry-configured
`token`. Both `/api/chat` and `GET /api/embed/tenant-config` resolve
through this verified path; without a matching token a request is treated
exactly like an unregistered host (generic gated defaults, or the legacy
`DIGICHAT_EMBED_ENABLED`/`DIGICHAT_EMBED_TOKEN` path), never the specific
tenant's config or relay. The token is not secret from that tenant's own
site visitors — it's provisioned out-of-band and baked into the tenant's
embed snippet as a query param (`<iframe src=".../embed?token=...">`),
read client-side in `src/app/embed/page.tsx` and forwarded as
`X-Embed-Token` — the same trust model as a Stripe publishable key or
reCAPTCHA site key: not guessable by an unrelated caller, but not a bearer
secret a real visitor needs to protect either.

An Origin/Referer check was considered and rejected: on `/api/chat` and
`/api/embed/tenant-config` themselves, Origin/Referer always reflect this
app's own origin (that's how cross-origin iframes work — a script fetch
from inside the iframe reports the iframe's own origin, never the parent
page's), so it can't distinguish tenants. A signed session cookie set at
`/embed` load time (using the real Referer on that top-level navigation)
was also considered, but rejected because it's a third-party cookie from
the browser's perspective and would be blocked by Safari ITP / Chrome's
third-party-cookie phase-out for a meaningful share of real visitors,
silently degrading them to the generic embed experience.

**Deploy-order dependency:** any tenant already present in a deployed
`DIGICHAT_EMBED_TENANTS` (e.g. DataTapStream) must have a `token` added to
its registry entry, and the corresponding site's embed snippet must be
updated to pass `?token=` on the iframe `src`, in the same deploy that
picks up this change — otherwise `parseEmbedTenants` throws (registry
entries without a token are invalid) and that tenant's build/boot fails.

---

## 6. Security Analysis

### Auth.js OIDC

The generic OIDC provider follows the Authorization Code flow. Auth.js v5 handles PKCE
(`code_challenge_method=S256`) and the `state` parameter automatically. The session is
stored as an encrypted JWT in an httpOnly cookie, which is the correct mitigation
against XSS-based session theft.

The `trustHost: true` setting in `src/auth.ts` bypasses host header validation. This is
necessary inside Docker Compose (reverse proxy) but means a misconfigured or absent
reverse proxy could allow host header injection to redirect OIDC callbacks.
**Recommendation:** set `AUTH_URL` explicitly in production rather than relying on
`trustHost`.

### Machine API key handling

Machine keys prefixed `digi_live_…` are validated via a two-step process: prefix lookup
(first 20 chars) then bcrypt comparison. `timingSafeEqual` is used for the env
bootstrap key, but the Postgres path uses `bcrypt.compare` which is inherently
timing-safe. The bootstrap key (`DIGICHAT_BOOTSTRAP_API_KEY`) is compared in constant
time. No machine key material is ever returned to the client.

The prefix column (`key_prefix`) leaks the first 20 characters of the key. For a 32-byte
random key this is acceptable (remaining entropy is adequate), but it is worth noting.

### httpOnly session cookies

Auth.js session cookies and the `digichat-endpoints` cookie are both `httpOnly`, which
prevents JavaScript access. The endpoint cookie is also `sameSite: "lax"` and
`secure: true` in production. CSRF risk is low for the endpoint cookie (no money or
sensitive mutation), but the absence of explicit CSRF tokens on mutation routes
(`POST /api/ecosystem/config`, `PUT /api/conversations/[id]`) is a gap if `sameSite`
protection alone is considered insufficient.

### DIGICHAT_DEV_AUTH=1 risk in production

The dev credentials provider checks `process.env.DIGICHAT_DEV_AUTH !== "1"` at module
initialization time, not at request time. If `DIGICHAT_DEV_AUTH=1` is set in a
production container (e.g., accidentally committed to a `.env` file or an
orchestrator secret), password login with the default password `"dev"` is fully
functional. The `DIGICHAT.md` explicitly forbids this but there is no runtime guard.
**Recommendation:** add a startup assertion that throws when `NODE_ENV=production` and
`DIGICHAT_DEV_AUTH=1`.

### DIGICHAT_LOCAL_AUTH_KEY

The `local-bootstrap` provider is guarded by `process.env.NODE_ENV !== "production"`
at provider registration time, so it cannot be triggered in a production build. The
`local-bootstrap.ts` server action also checks `NODE_ENV`. This is correctly secured.

### Postgres credentials in env

`DIGICHAT_DATABASE_URL` is a raw PostgreSQL connection URL containing credentials. It
is read on the server only (`getDb()`) and never returned to the client. However, it
is passed as a plain environment variable in `docker-compose.yml`:
`DIGICHAT_DATABASE_URL=postgresql://digichat:${DIGICHAT_POSTGRES_PASSWORD:-digichat}@...`.
The default password `digichat` is the same as the username and database name.
**Recommendation:** override `DIGICHAT_POSTGRES_PASSWORD` in every deployment and do
not use the default.

### CORS configuration

There is no explicit CORS configuration in `next.config.ts`. Next.js defaults restrict
cross-origin requests to the same origin for Route Handlers. This is correct for a BFF
pattern — CORS should not be opened since the browser should only talk to the same
origin that served the page.

### CSP headers

`next.config.ts` applies security headers via `src/lib/security-headers.ts`:

- **Authenticated routes** (`/((?!embed$|embed/).*)`): full CSP (`default-src 'self'`, …),
  `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`.
- **`/embed`**: relaxed `frame-ancestors` for `digithings.ai` and `digiquant.io` only
  (see `EMBED_FRAME_ANCESTORS`); no global CSP downgrade on the main app shell.

Vitest: `src/lib/security-headers.test.ts`.

### Machine API key prefixes (REM-079 glossary)

| Prefix | Issuer | Validated by | Purpose |
|--------|--------|--------------|---------|
| `digi_live_` | DigiChat (`npm run db:create-key`) | `validateMachineApiKey()` → Postgres bcrypt | BFF route auth (`requireDigiChatAuth`) |
| `dgk_live_` | DigiKey (`POST /v1/admin/keys`) | `exchangeDigikeyApiKey()` → short-lived JWT | Upstream DigiGraph/DigiQuant calls via BFF exchange |

Do not conflate the two: DigiChat DB keys gate the BFF; DigiKey keys gate the agent stack.

### SSRF guard

`isAllowedServiceUrl` in `src/lib/ecosystem.ts` restricts endpoint URLs to `http/https`
without credentials, and allows only loopback, `*.local`, single-label Docker service
names, and private RFC1918 ranges. This is a reasonable SSRF guard for the ecosystem
endpoint cookie. The allowlist can be further tightened via
`DIGICHAT_ENDPOINT_HOST_ALLOWLIST`.

---

## 7. Scalability Analysis

### Next.js stateless (horizontal scale friendly)

All per-request state lives in the database, localStorage (client), or the encrypted
session cookie. Route handlers hold no in-memory state. DigiChat can be horizontally
scaled without sticky sessions, provided all replicas share the same `AUTH_SECRET`
and `DIGICHAT_DATABASE_URL`.

### Postgres connection pool (Drizzle)

`src/db/index.ts` initializes a `postgres-js` pool with `max: 10, idle_timeout: 20,
connect_timeout: 10`. In a multi-replica deployment, each replica holds up to 10
connections, so N replicas require up to 10N connections. For a single Postgres
instance the default `max_connections=100` supports up to 10 replicas before
exhaustion. **Recommendation:** use PgBouncer in front of Postgres in production, or
reduce `max` per replica.

### AI SDK streaming via DigiGraph SSE (back-pressure)

The trace stream path opens a `fetch` to DigiGraph and iterates the response body with
a `ReadableStreamDefaultReader`. Node.js buffers the upstream chunks in memory. If the
client (browser) is slow to consume the outgoing stream (e.g., tab is backgrounded,
the connection is slow), the BFF buffers in Node.js without explicit back-pressure
signaling to DigiGraph. For typical chat payloads (text responses) this is not
concerning. For large tool outputs or long reasoning traces, large in-flight buffers
are possible. **Recommendation:** implement a streaming cancellation path so that when
the client disconnects, the BFF aborts the upstream DigiGraph request (see Section 12).

### localStorage sync overhead for large conversation histories

`saveLocalThreads` serializes **all threads** on every mutation and writes to
`localStorage`. With many long conversations, each containing hundreds of AI SDK
`UIMessage` objects (which include full trace payloads), the JSON blob can grow to
several megabytes. `localStorage` has a 5–10 MB limit per origin. Full-replace writes
on every message are O(total conversation size).
**Recommendation:** cap the number of threads kept in localStorage, store only
metadata (id, title, updatedAt) in the main list, and hydrate message bodies on
demand from the server when Postgres is available.

### Postgres migration on startup risk

`runMigrate()` is called in the Next.js instrumentation hook on every server start when
`DIGICHAT_AUTO_MIGRATE=1`. In a rolling deployment with multiple replicas starting
simultaneously, migrations can conflict. Drizzle's `migrate()` function uses a
migration journal table (`__drizzle_migrations`) as a distributed lock, which
serializes migrations but may cause startup latency for replicas waiting on the lock.
For a small number of replicas (1–3) this is acceptable. **Recommendation:** for
larger deployments, run migrations as a separate init container / job before scaling
the application.

---

## 8. Performance Analysis

### AI SDK streaming UX (time-to-first-token)

The critical path for the first token visible in the browser is:
Browser → BFF (auth cookie read + session decrypt) → DigiKey (JWT exchange, 1 HTTP
round-trip) → DigiGraph (processing starts) → first SSE chunk → BFF → browser.

The DigiKey round-trip adds latency on every message send. For low-latency targets,
consider caching the DigiKey JWT for its declared `exp` minus a grace period (e.g.,
30 seconds) in the BFF process memory or a Redis sidecar. The current implementation
re-exchanges on every request.

### React Server Components opportunity (currently client-heavy)

The root `page.tsx` is a server component that immediately renders a client shell
(`ChatShell`). The sidebar, conversation list, and message list are all client
components. There is an opportunity to render the initial conversation list as a React
Server Component (using the Postgres repo directly), which would eliminate the client-
side `GET /api/conversations` waterfall on initial load and reduce time-to-interactive.
This would require converting `ChatShell` to a hybrid RSC+client architecture.

### Drizzle query optimization

`listConversationSummaries` is limited to 200 rows and uses a composite index on
`(tenant_id, owner_user_sub, updated_at)` for efficient descending-sort lookup. This
is appropriate for the current scale.

`getConversationMessages` does two sequential queries (conversation lookup then
messages). For large conversations with hundreds of messages, the `payload` JSONB
column can be large. There is no projection to strip trace data from stored messages
before sending to the client.

`replaceConversationMessages` wraps delete, bulk insert, and conversation metadata update in a
single Drizzle `db.transaction()` (REM-034). A failure mid-replace rolls back the whole batch.
For a 200-message conversation this is still 201 write operations inside one transaction.
PostgreSQL handles this efficiently, but it is worth monitoring for long conversations.

### Conversation list pagination

`listConversationSummaries` hardcodes `.limit(200)`. There is no pagination cursor for
users with more than 200 conversations. **Recommendation:** add `cursor` / `before`
parameter to `GET /api/conversations` before this becomes a user-facing constraint.

### Quant strip rendering overhead

`extractQuantMetricRows` runs a recursive deep scan of all assistant message parts on
every render where `messages` changes (via `useMemo`). For very long conversations
with large tool payloads, this can be a non-trivial computation. The `useMemo`
dependency on `messages` (array reference) means it re-runs on every streaming
text delta because `useChat` produces a new messages array reference per chunk.
**Recommendation:** debounce the scan or run it only when `status === "ready"`.

---

## 9. Integration Points

### DigiGraph (primary)

DigiGraph exposes an OpenAI-compatible API at `{DIGIGRAPH_INTERNAL_URL}/v1`. DigiChat
calls `POST /v1/chat/completions` with `stream: true`. In the trace path, the BFF
constructs the request body manually via `coreMessagesToDigigraphOpenAi` (which
coerces AI SDK `ModelMessage` content to plain strings to avoid DigiGraph's strict
`422` validation). In the legacy path, the AI SDK OpenAI provider constructs the body.

DigiGraph SSE frames carry an optional `digigraph_trace` field on each
`choices[0].delta`. The trace path extracts this field and emits
`data-digigraphTrace` parts with type `rag_sources`, `graph_update`, `code_block`,
`span`, etc.

Session correlation: `X-Session-Id` (conversation UUID), `X-Request-ID` (per-request
UUID), `X-Digichat-Tenant`, `X-Digi-Caller: digichat` are forwarded to DigiGraph and
flow through to DigiSmith tracing spans.

### DigiKey (token exchange)

DigiKey at `{DIGIKEY_URL}` accepts `POST /v1/oauth/token`. Two grant types are used:
`bff_session` (BFF-to-DigiKey server-to-server, authenticated by `DIGIKEY_BFF_TOKEN`)
and `api_key` (client machine key exchange). DigiKey returns a short-lived JWT and
optionally a `litellm_proxy_api_key`. DigiChat never sees the raw DigiKey signing
secret; only `DIGIKEY_BFF_TOKEN` is needed (a long-lived BFF credential).

### DigiSearch health badge

`GET /api/health` probes `{DIGISEARCH_INTERNAL_URL}/health` when `digisearch` is in
`DIGICHAT_ENABLED_SERVICES`. DigiSearch is not called directly by the chat BFF;
DigiGraph calls DigiSearch internally during workflow execution. The health badge
in the Ecosystem sheet reflects connectivity only.

DigiGraph and DigiQuant get the same `DIGICHAT_ENABLED_SERVICES` treatment (#1346):
unlike `digisearchUrl`, `digigraphUrl`/`digiquantUrl`/`digismithUrl` in
`EcosystemEndpoints` always have a default value (`ecosystem.ts`'s `DEFAULTS`), so
the health route checks `isServiceCapabilityEnabled(...)` directly rather than URL
presence — a deployment serving only `external-relay` embed tenants (no DigiGraph
stack running at all) can omit them from `DIGICHAT_ENABLED_SERVICES` without
`/api/health` reporting itself unhealthy. Note the `DIGICHAT_ENABLED_SERVICES=""`
gotcha in `capabilities.ts`: an empty string falls back to the all-enabled default,
so disabling every service requires a non-matching placeholder value instead.

### DigiQuant backtest result parsing

DigiChat does not call DigiQuant directly. `BacktestResult`-shaped JSON appears in
assistant message parts because DigiGraph includes DigiQuant tool outputs in the
message stream. The quant strip parses these client-side. With Postgres enabled,
the client can persist runs by calling `POST /api/conversations/[id]/quant-runs`
using the extracted `run_id` and metrics.

### DigiSmith status endpoint

`GET /api/health` probes `{DIGISMITH_INTERNAL_URL}/health` when `digismith` is in
`DIGICHAT_ENABLED_SERVICES`. DigiSmith is not called from the chat flow; tracing is
handled by DigiGraph emitting `span` trace events in the SSE stream. The health
badge confirms the tracing service is reachable.

---

## 10. Docker & MCP Composition

### Docker Compose digichat profile

Activated with `--profile digichat` (or `make up-digichat` from repo root).

**`digichat-db`** service: `postgres:16-alpine`, container `digi-digichat-db`, binds
to `127.0.0.1:5433:5432` by default. Healthcheck: `pg_isready -U digichat -d digichat`.

**`digichat`** service: built from `digichat/Dockerfile` (Node.js 22 Alpine, three-stage
standalone build). Binds to `${DIGICHAT_PUBLISH_HOST:-127.0.0.1}:${DIGICHAT_PUBLISH_PORT:-3005}:3000`.
`depends_on` with healthcheck conditions for `digichat-db`, `digikey`, and `digigraph`.
Healthcheck: `curl -sf http://127.0.0.1:3000/api/health`.

### Environment variables

| Variable | Purpose | Required |
|---|---|---|
| `AUTH_SECRET` | Auth.js session JWT signing/encryption key | Yes |
| `AUTH_URL` | Public origin of DigiChat (OAuth redirect base) | Yes in production |
| `AUTH_TRUST_HOST` | Allow `X-Forwarded-Host` from reverse proxy | Yes in Docker |
| `AUTH_OIDC_ISSUER` | OIDC provider issuer URL | If using OIDC |
| `AUTH_OIDC_CLIENT_ID` | OIDC client ID | If using OIDC |
| `AUTH_OIDC_CLIENT_SECRET` | OIDC client secret | If using OIDC |
| `DIGICHAT_DEV_AUTH` | Enable dev password login (`1` = on) | Dev only |
| `DIGICHAT_DEV_PASSWORD` | Dev password (default: `dev`) | Dev only |
| `DIGICHAT_LOCAL_AUTH_KEY` | Dev auto-sign-in key (non-production only) | Dev only |
| `DIGIGRAPH_INTERNAL_URL` | DigiGraph base URL (default: `http://127.0.0.1:8000`) | Yes |
| `DIGIGRAPH_UPSTREAM_API_KEY` | Static Bearer to DigiGraph (fallback auth) | If not using DigiKey |
| `DIGIKEY_URL` | DigiKey base URL | If using DigiKey |
| `DIGIKEY_BFF_TOKEN` | BFF credential for DigiKey `bff_session` grant | If using DigiKey |
| `DIGIQUANT_INTERNAL_URL` | DigiQuant base URL (health probe) | Recommended |
| `DIGISMITH_INTERNAL_URL` | DigiSmith base URL (health probe) | Recommended |
| `DIGISEARCH_INTERNAL_URL` | DigiSearch base URL (health probe) | Optional |
| `DIGICHAT_ENABLED_SERVICES` | Comma-separated active service IDs | Optional |
| `DIGICHAT_DATABASE_URL` | PostgreSQL connection URL | For server persistence |
| `DIGICHAT_AUTO_MIGRATE` | Run Drizzle migrations on startup (`1` = on) | Docker recommended |
| `DIGICHAT_BOOTSTRAP_API_KEY` | Static machine API key (env bootstrap) | For machine clients |
| `DIGICHAT_BOOTSTRAP_TENANT_SLUG` | Tenant for bootstrap key (default: `default`) | If using bootstrap key |
| `DIGICHAT_DEFAULT_TENANT_SLUG` | Default tenant slug when DB unavailable | Production fallback |
| `DIGICHAT_TRACE_UI` | Disable trace stream (`0` = off, default on) | Optional |
| `DIGICHAT_MODEL` | DigiGraph model name (default: `sitaas-rag`) | Optional |
| `DIGICHAT_OPENWEBUI_FORMAT` | Enable OpenWebUI format flag (default: `1`) | Optional |
| `DIGICHAT_ENDPOINT_HOST_ALLOWLIST` | Comma-separated hosts for SSRF guard | Security hardening |
| `DIGICHAT_EMBED_ENABLED` | Enable the unauthenticated `/embed` chat surface (`1` = on) | For public embed |
| `DIGICHAT_EMBED_TOKEN` | Alternative to `DIGICHAT_EMBED_ENABLED`: gate `/embed` on `X-Embed-Token` instead | Optional |
| `DIGICHAT_EMBED_TENANTS` | Optional JSON registry of embed tenants (see "Embed tenant registry & external backends"). Unset = no external embed tenants; first-party embeds behave exactly as before. Must be present at build time for CSP frame-ancestors derivation. Each entry requires a `token` — the embed snippet passes it back as `?token=` / `X-Embed-Token`; a registered host alone is not sufficient authorization (#1339). | Optional |
| `DIGICHAT_CHAT_RATE_LIMIT_MAX` / `_WINDOW_MS` | Shared per-`{tenantSlug}:{ownerUserSub}` chat rate limit (default 30/60000ms) | Optional |
| `DIGICHAT_EMBED_IP_RATE_LIMIT_MAX` / `_WINDOW_MS` | Per-IP chat rate limit for anonymous `/embed` requests, in front of the shared bucket above (default 10/60000ms — must stay below `DIGICHAT_CHAT_RATE_LIMIT_MAX`) | Optional |
| `DIGICHAT_POSTGRES_PASSWORD` | Postgres password (Compose default: `digichat`) | Change in production |
| `DIGICHAT_VERSION` | Version string returned in health response | Optional |
| `NEXTAUTH_SECRET` | Legacy Auth.js secret alias (same value as `AUTH_SECRET`) | If using legacy env |
| `NEXTAUTH_URL` | Legacy Auth.js URL alias (same value as `AUTH_URL`) | If using legacy env |

### Dockerfile stages

Three-stage build:
1. `deps` (node:22-alpine): `npm ci` to populate `node_modules`.
2. `builder` (node:22-alpine): copies deps, copies source, runs `next build`. `NEXT_TELEMETRY_DISABLED=1`.
3. `runner` (node:22-alpine): copies only `public/`, `.next/standalone/`, `.next/static/`. Adds `curl` for the Compose healthcheck. Runs as non-root `nextjs` user (uid 1001). `next.config.ts` sets `output: "standalone"` to enable this.

The standalone output is a self-contained Node.js server (`server.js`) with only production
dependencies. Image size is significantly smaller than a non-standalone build.

### Auto-migration

`src/instrumentation.ts` is a Next.js instrumentation module. When `NEXT_RUNTIME=nodejs`
(Node.js runtime, not edge) and `DIGICHAT_AUTO_MIGRATE=1`, it calls `runMigrate()`
which opens a single dedicated connection, runs all pending Drizzle migrations, and
closes. This runs once per process start, before the server accepts requests.

---

## 11. Phase 2+ Gaps & Roadmap

### OpenClaw gateway integration

DigiClaw (`digiclaw/`) provides heartbeat, audit, and gateway functionality. DigiChat
currently has no integration with DigiClaw. Planned work includes routing all chat
requests through an OpenClaw gateway for rate limiting, audit logging, and policy
enforcement at the BFF boundary.

### RAG document ingestion UI

There is no UI for uploading or managing documents for DigiSearch. Users can exercise
DigiSearch only indirectly via DigiGraph tool calls. A document ingestion panel (drag-
and-drop PDF/text → `POST /v1/ingest` on DigiSearch) would complete the end-to-end
RAG workflow from the browser.

### Fine-grained permission UI

The current multi-tenant model requires manual SQL to map OIDC subjects to tenants
(`INSERT INTO user_tenants`). An admin UI for tenant management, user provisioning,
and API key lifecycle (list, revoke, rotate) would be needed before DigiChat is
suitable for use by multiple distinct organizations.

### DigiBase credential brokering

`DIGICHAT_DATABASE_URL` is currently a raw PostgreSQL URL stored in an environment
variable. The ARCHITECTURE.md for the root project notes that the strategic direction
is to route chat DB credentials, checkpoints, and cache credentials through a
**DigiBase data-plane service** so that secrets live in one brokered place rather than
as raw URLs in every service. The `digibase/` directory currently ships only the
Python library. When DigiBase ships the HTTP credential broker, DigiChat should
replace direct `DIGICHAT_DATABASE_URL` with a DigiBase-issued short-lived credential.

---

## 12. Redesign Recommendations

The following are specific, actionable improvements ordered by estimated impact.

### (a) Replace direct `DIGICHAT_DATABASE_URL` with DigiBase credential broker

When DigiBase ships its credential broker, DigiChat should request a Postgres credential
from DigiBase using its DigiKey JWT rather than holding a permanent connection string.
This eliminates long-lived database credentials from the DigiChat environment entirely
and aligns with the platform-wide secret management direction. Until then, ensure
`DIGICHAT_POSTGRES_PASSWORD` is not the default `digichat` in any deployment.

### (b) Add conversation export (JSON/PDF) for audit trails

The quant copilot use case produces regulated outputs (backtest results, research
briefs). Users and compliance teams need exportable records of conversations. A
`GET /api/conversations/[id]/export?format=json|pdf` endpoint, combined with a
download button in the UI, would satisfy this requirement. JSON export is trivial
given the existing `GET /api/conversations/[id]` route; PDF requires a server-side
rendering step (e.g., `@react-pdf/renderer` or a headless browser).

### (c) Implement optimistic UI updates for message sending

Currently, the user message is appended to the UI only after `sendMessage` resolves
and `useChat` returns the updated messages array. For connections with any latency, the
UI is momentarily empty between submit and first response. Optimistically appending the
user message to the local display before the server confirms improves perceived
responsiveness significantly.

### (d) ~~Add rate limiting on `POST /api/chat` at BFF layer~~ — done; extend to distributed storage

Per-user/per-tenant rate limiting at the BFF (`checkBffRateLimit`, in-memory sliding
window) shipped, and #1251 added a per-IP layer in front of it specifically for the
shared anonymous `embed:anonymous` bucket (`checkEmbedIpRateLimit`). Both are
in-process (`BoundedTTLMap`), so — like DigiGraph's and DigiSearch's own limiters —
multiple DigiChat replicas would each enforce independently, multiplying the effective
limit by replica count. Moving to Redis-backed counters remains open if DigiChat scales
to multiple instances behind a load balancer.

The new `embed_ip:*` keys share the same 10,000-entry bounded map (`MAX_RATE_LIMIT_KEYS`
in `bff-rate-limit.ts`) as every other rate-limit key, including authenticated
`chat:*` buckets, and eviction is FIFO by insertion order (not LRU). An attacker who
can mint many distinct client IPs (only realistic when not actually behind Cloudflare —
see the trust-boundary note above) could cycle through enough of them to evict
legitimate entries, resetting their windows early. Impact is limiter degradation, not
an auth bypass; segmenting the two key spaces into separate bounded maps would close
this if it becomes a real concern.

### (e) Add streaming cancellation (AbortController from client to DigiGraph SSE disconnect)

The AI SDK `stop()` function terminates the browser-side SSE consumer, but the BFF
continues receiving and discarding chunks from DigiGraph until DigiGraph finishes or
times out. This wastes DigiGraph compute and BFF memory.

The fix: in `createDigigraphTraceStreamResponse`, create an `AbortController` before
the upstream `fetch`. Register a cleanup handler on the writable side of the UI message
stream (or use the `execute` writer's `onClose`/`onAbort` if exposed by AI SDK) to
call `controller.abort()`. DigiGraph will then receive a connection reset and can
cancel its LangGraph execution.

### (f) Add `X-Request-ID` propagation from BFF to DigiGraph for full trace correlation

The BFF already generates and forwards `X-Request-ID` to DigiGraph and includes it in
the response headers (`X-Request-Id`). The browser-side `ChatPanel` should read this
response header and attach it to subsequent `PUT /api/conversations/[id]` calls so
that the stored conversation has a trace of every `X-Request-ID` that produced each
assistant turn. This would enable linking a stored conversation message to a specific
DigiSmith trace span for post-hoc debugging.

Additionally, the BFF should log `X-Request-ID` at the start of every Route Handler
invocation (a one-line addition to each route file) so that structured server logs can
be correlated with DigiSmith spans without relying on the client to preserve the ID.
