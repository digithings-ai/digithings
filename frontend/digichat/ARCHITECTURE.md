# digichat — Architecture

> **Scope:** Production Next.js 16 BFF + React 19 chat UI at `frontend/digichat/`.
> Marketing parent is `frontend/digithings-web` `/chat` → iframe `/embed` (not the deleted `frontend/website/`).

---

## 1. Overview

digichat is the **user-facing interface** to the digithings ecosystem. It is a Next.js
16 App Router application that acts as a **Backend-for-Frontend (BFF)**: the browser
never speaks directly to digigraph or any Python service. All LLM calls, auth token
exchanges, and upstream probes are handled in Next.js Route Handlers running on the
server.

**Modular frontend:** one shared UI (`@digithings/digichat-ui`) and activity protocol,
with backends selected per tenant (`digigraph` | `foundry`). digithings tenants use
digigraph (digillm + digivault hub). See
[`docs/architecture/digichat-modular-frontend.md`](../../docs/architecture/digichat-modular-frontend.md)
and [ADR-0018](../../docs/adr/0018-digichat-path-routing.md).

**Turn / thread markdown export (#3465).** Shared serializer lives in `@digithings/digichat-ui` (`serializeAssistantMarkdown` / `serializeThreadMarkdown` / `copyMarkdownWithFallback`). `ChatPanel` and embed session both use it — clipboard first, embed falls back to `.md` download (never a silent no-op).

**Last-turn regen + edit (#3466).** Digigraph surfaces (first-party `ChatPanel` + digigraph embeds) expose **regen** on the last settled assistant and **edit** on the last user turn. Both replay the full digigraph workflow on the same session (tools re-run; digistore may accumulate). Foundry embeds omit `regenerate` / `editLastUser` on `DigiChatController` (client config projects `backendType` only — no endpoints). Edit that shortens a persisted thread must set `allowTruncate: true` on the next PUT. Foundry execution API is #3475.

### Capability matrix

| Capability | Status |
|---|---|
| React 19 streaming chat (`useChat`, AI SDK v6) | Built |
| Auth.js v5 — generic OIDC provider | Built |
| Auth.js v5 — dev password provider (`DIGICHAT_DEV_AUTH`) | Built |
| digikey JWT exchange (`bff_session` + `api_key` grants) | Built |
| Machine API key auth (`digi_live_…`, hashed in Postgres) | Built |
| Conversation persistence — localStorage (always on) | Built |
| Conversation persistence — Postgres (optional) | Built |
| digigraph activity stream (`data-digichatActivity` parts) | Built |
| Shared activity UI (rich vault hits + research brief) | Built |
| digigraph digithings adapter (`adapters/digithings/`) | Built |
| Foundry client adapter (`adapters/foundry/`) | Built |
| Quant comparison strip (inline `BacktestResult` parsing) | Built |
| Quant run persistence (`quant_runs` table) | Built |
| Ecosystem side panel (service URLs + health badges) | Built |
| Auto-migration on container boot (`DIGICHAT_AUTO_MIGRATE=1`) | Built |
| Docker Compose profile (`digichat` + `digichat-db`) | Built |
| OpenClaw gateway integration | Not yet (Phase 2) |
| RAG document ingestion UI | Not yet (Phase 2) |
| Fine-grained permission admin UI | Not yet (Phase 2) |
| digibase credential brokering | Not yet (roadmap) |

---

## 2. Current Implementation State

### What is built

**React chat shell** (`src/components/chat-shell.tsx`): Client component that owns
thread state. On mount it merges `localStorage` threads with a server `GET
/api/conversations` call, **hydrates the auto-selected remote thread** via
`GET /api/conversations/[id]` before mounting the composer (when local cache is
missing or older than the server summary `updatedAt`), then renders a shadcn
Sidebar with conversation list, New chat button, rename/delete overflow menus, and
the main `ChatPanel`. Sidebar clicks reuse the same hydrate-before-activate path
(`openThread`). Server PUT is a full message replace — `canFlushServerMessages`
refuses to flush a remote thread that is still `hydrated: false`, and the API
returns **409 `would_truncate`** if a PUT would drop existing rows unless
`allowTruncate: true` (used by `/clear` and by last-user edit — #3466).

**AI SDK `useChat`** (`src/components/chat-panel.tsx`): Uses `@ai-sdk/react` with a
`DefaultChatTransport` pointed at `POST /api/chat`. Sends `X-Digichat-Session` header
so upstream digigraph can correlate the same conversation across turns. Scroll
stick-to-bottom with a "New messages" chip when scrolled up. Copy, Regenerate,
and Edit-last-user actions on bubbles (first-party is always digigraph).

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

**digikey machine key exchange** (`src/lib/digikey-exchange.ts`): Two exchange paths:
`bff_session` grant (BFF presents `DIGIKEY_BFF_TOKEN` on behalf of an OIDC session)
and `api_key` grant (client presents a `dgk_live_…` Bearer that the BFF exchanges at
digikey). Both return a short-lived JWT + optional `litellm_proxy_api_key`.

**Drizzle ORM** (`src/db/schema.ts`, `src/db/index.ts`): Postgres-js driver, `max: 10`
connection pool. Six tables: `tenants`, `user_tenants`, `api_keys`, `conversations`,
`conversation_messages`, `quant_runs`. Managed by three migration files in `drizzle/`.

**Design-canon theming** (`src/app/globals.css`, `src/app/layout.tsx`,
`src/components/providers.tsx` — #1403, Phase 3 utilitarian-terminal v0.1):
the app runs on the shared digithings token canon. `@digithings/design/tokens.css`
defines `[data-theme="dark"|"light"]` semantic tokens; `@digithings/web/styles/web-theme.css`
is the single Tailwind `@theme inline` bridge for token-named utilities;
digichat's `globals.css` derives the shadcn variable set from those tokens under
`:root[data-theme]` scopes (`--background: var(--bg)`, `--border: var(--hair)`,
`--destructive: var(--danger)`, …). **Loud CTA fill** is ink/paper
(`--primary: var(--ink)` / `--primary-foreground: var(--bg)`); rose livery
(`.accent-digichat` / `--accent-digichat`) is **accent only** — `--ring`,
`--chart-1`, `--sidebar-primary`, live dots, transcript markers — never the
default button fill. Local `@theme` `--radius-*` pins to `0` (true circles
keep `rounded-full`). Type is Geist Mono for claim, body, and chrome
(`--font-sans`/`--font-display`/`--font-family` remap to `--font-geist-mono`).
`<html>` ships `data-theme="dark"` + `.dark` as SSR defaults; the shared
`themeInitScript` re-points both pre-paint (`dt-theme` localStorage key, shared
with the marketing sites) and a `MutationObserver` (`ThemeClassSync` in
`providers.tsx`) mirrors every later `[data-theme]` flip onto the `.dark`/`.light`
classes for the Tailwind `dark:` variant. The old `@digithings/digichat-ui`
`tokens-shadcn-bridge.css` (shadcn vars → token names, the reverse direction) is
no longer imported; `/embed` sets `[data-theme]` on the root from the effective
theme (URL `?theme=`, parent `digichat:theme` postMessage, or tenant `theme` —
its own iframe document) and per-tenant accent hexes still override at the
wrapper. Because the shared `ThemeProvider` (in `providers.tsx`, which wraps
`/embed` too via the root layout) keeps a `prefers-color-scheme` listener that
rewrites `[data-theme]` to the OS scheme whenever there is no `dt-theme` key —
always true for an anonymous embed visitor — `/embed` re-asserts the effective
theme with a `MutationObserver` on `html[data-theme]` (guarded write, so the
observer never loops), so a mid-session OS light↔dark flip can't silently
override a parent- or tenant-forced theme (#1434). Composer send (imported
`.dc-send` plus the authenticated ↵ kbd) is overridden locally to an ink/paper
rect because `@digithings/digichat-ui` session.css still ships an 8px
accent-tinted pill.

**Shared controls layer** (`src/components/ui/*` — #1419): ten of the fifteen
shadcn-derived wrappers are now thin re-exports of the `@digithings/web`
controls family (`button`, `badge`, `card`, `input`, `label` pin
`dress="chat"`; `avatar`, `collapsible`, `dropdown-menu`, `sheet`, `tooltip`
re-export bare — the shared default skin is digichat's dress). Import sites
are unchanged (`@/components/ui/<x>`). `globals.css` imports
`@digithings/web/styles/controls-core.css` + `controls-overlay.css` before
the digichat-ui sheets and `@source`s the shared controls directory
(load-bearing — the behavioral controls carry token-backed utilities).
`scroll-area`, `separator`, `sidebar`, `skeleton`, `textarea` stay local (no
shared counterpart yet). Full swap/kept ledger, cascade contract, and
browser-QA deltas: [`CONTROLS.md`](CONTROLS.md).

**Source file reference table**

| File | Purpose |
|---|---|
| `src/app/page.tsx` | Server component: Option A default redirects `/` → `/embed`; `DIGICHAT_REQUIRE_ROOT_AUTH=1` keeps Auth.js gate → `ChatShell` (no session redirects to `/embed` too — no standalone login page ships) |
| `src/lib/root-auth.ts` | `isRootAuthRequired()` — root `/` Auth.js wall (default OFF) |
| `src/app/layout.tsx` | Root layout with `Providers` (session, tooltips) |
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
| `src/lib/digigraph.ts` | `createdigigraphClient`, model name helpers |
| `src/lib/digigraph-messages.ts` | Content coercion for digigraph OpenAI body |
| `src/lib/digigraph-upstream.ts` | `resolvedigigraphUpstreamAuth` — JWT resolution |
| `src/lib/digikey-exchange.ts` | digikey token exchange (both grant types) |
| `src/lib/adapters/digithings/stream.ts` | digigraph SSE → `data-digichatActivity` |
| `src/lib/adapters/digithings/activity/` | digivault / digisearch activity mappers (digigraph tools) |
| `src/lib/adapters/foundry/stream.ts` | Azure Foundry → AI SDK UI message stream |
| `src/lib/adapters/shared/messages.ts` | Shared helpers (e.g. `lastUserMessageText`) |
| `src/lib/digigraph-activity-map.ts` | Re-export of digithings activity mappers |
| `src/lib/embed-gate-provider.ts` | Consume per-tenant embed chat access tokens |
| `src/lib/chat-activity.ts` | Activity allowlist, detail gate, projector |
| `src/lib/conversations-repo.ts` | Drizzle query helpers (conversations + quant runs) |
| `src/lib/thread-local.ts` | localStorage read/write/merge |
| `src/lib/ecosystem.ts` | Endpoint resolution + SSRF guard |
| `src/lib/capabilities.ts` | `DIGICHAT_ENABLED_SERVICES` parsing |
| `src/lib/request-auth.ts` | `requiredigichatAuth` shared auth helper |
| `src/lib/tenant.ts` | OIDC subject → tenant slug lookup |
| `src/lib/api-key.ts` | Machine key validation (env bootstrap + bcrypt Postgres) |
| `src/lib/migrate.ts` | Programmatic Drizzle migration runner |
| `src/instrumentation.ts` | Next.js instrumentation hook: `DIGICHAT_AUTO_MIGRATE=1` |
| `src/components/chat-shell.tsx` | Sidebar + thread state manager |
| `src/components/chat-panel.tsx` | `useChat` + message list + composer |
| `src/components/connections-sheet.tsx` | Ecosystem side sheet |
| `src/components/quant-comparison-strip.tsx` | Backtest metrics table |
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
- Request body: `{ messages: UIMessage[] }` (AI SDK UI message format). **Full conversation history** — every prior user+assistant turn — must be posted on each request; the BFF forwards the entire array to digigraph (trace stream and `streamText` paths). Foundry backends intentionally send only the latest user text because Azure holds server-side conversation state.
- Notable request headers: `X-Digichat-Session` / `X-Session-Id` (stable UUID for upstream tracing), `X-Request-ID` (propagated to digigraph), `X-Digichat-Trace: 0` (opt out of trace stream), `X-Embed-Chat-Token` (optional per-tenant trial-gate token).
- Response: Server-Sent Events (AI SDK UI message stream) — text deltas plus optional `data-digichatActivity` parts.
- The route resolves upstream auth, builds a `createdigigraphClient`, then either (a) calls `createdigigraphTraceStreamResponse` for the trace path or (b) calls `streamText` with `smoothStream` for the legacy path.
- `maxDuration = 120` (Vercel/Next.js edge timeout).
- **Rate limiting (two layers):** every request hits a shared per-`{tenantSlug}:{ownerUserSub}` sliding-window check (`checkBffRateLimit`, `DIGICHAT_CHAT_RATE_LIMIT_MAX`/`_WINDOW_MS`, default 30/min). Unauthenticated `/embed` requests all resolve to the *same* `ownerUserSub` (`embed:anonymous`, see below), so they'd share one bucket — a per-IP check (`checkEmbedIpRateLimit`, `DIGICHAT_EMBED_IP_RATE_LIMIT_MAX`/`_WINDOW_MS`, default 10/min) runs first for that case, so one visitor can't exhaust the shared quota for everyone (#1251). **Invariant:** the per-IP default must stay below the shared default, or the shared bucket's ceiling binds first and the per-IP layer becomes a no-op (caught in review on the first cut of #1251, which shipped 60 against a shared default of 30 — see the regression test in `embed-ip-rate-limit.test.ts`). When `DIGICHAT_TRUSTED_PROXIES` is unset, IP selection keeps the historical order: `cf-connecting-ip`, the leftmost `X-Forwarded-For` hop, then `unknown`. When configured with comma-separated IPs/CIDRs, only a TCP peer in that allowlist may supply a forwarded client-IP header; `x-digichat-peer-ip` is captured from the socket by the production entrypoint, which strips a caller-provided value before forwarding to the loopback-only Next server. Then `cf-connecting-ip` is preferred, or the XFF chain is walked from right to left past trusted proxy hops to the first valid non-trusted address. An untrusted or malformed boundary falls back to the captured peer. This mirrors digigraph's allowlist policy while accounting for Next.js Route Handlers' lack of socket access; rate-limit IPs remain non-identity signals.
- **Per-tenant trial gate:** a `trial_form` tenant may set `gate.consumeUrl` to an operator-controlled HTTPS endpoint. When `X-Embed-Chat-Token` is present, the BFF sends `{ "token": "..." }` to that endpoint before applying the fallback per-IP turn quota. A 2xx response consumes the turn, any 4xx response denies it, and 5xx, timeout, or transport failures allow it so a quota-provider outage does not disable chat. The token is never logged or forwarded to a chat backend.
- **Anonymous `/embed` requests** (`resolveEmbedChatTenant` in `embed-chat-tenant.ts`) resolve to `{ tenantSlug: "embed", ownerUserSub: "embed:anonymous" }` when `DIGICHAT_LEGACY_EMBED_ENABLED=1` (or deprecated `DIGICHAT_EMBED_ENABLED=1`) or a valid legacy `X-Embed-Token` matches `DIGICHAT_EMBED_TOKEN`; registered tenants resolve via `DIGICHAT_EMBED_TENANTS` (token or first-party bypass). Otherwise 503. This path never touches `conversations-repo` — no server-side persistence call exists in this route for any caller (persistence, when it happens, is client-initiated via the separate `/api/conversations` endpoints below, which require a real session).

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
digigraph sends OpenAI-compatible SSE (`data: {...}`). The BFF either pipes through AI
SDK's `streamText` (legacy path) or manually iterates the SSE stream in
`iterateOpenAiSse` and re-emits as AI SDK UI message stream parts (trace path). There
is no back-pressure mechanism on the BFF-to-digigraph leg beyond the native Node.js
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
and the custom `data-digichatActivity` part emitted by digigraph / digivault /
foundry streams. Messages are stored verbatim as JSONB in
`conversation_messages.payload`.

### BacktestResult parsing

The quant strip client-scans assistant message parts recursively for objects containing
`run_id` plus at least one of `sharpe_ratio` or `num_trades`. Fields read:
`run_id`, `strategy_name`, `sharpe_ratio`, `total_return_pct`, `max_drawdown_pct`,
`num_trades`. This scan is opportunistic and schema-free, which makes it resilient to
digiquant payload evolution but also silently ignores malformed results.

### digikey exchange response

`POST /v1/oauth/token` at digikey returns `{ access_token, litellm_proxy_api_key? }`.
The `litellm_proxy_api_key` is forwarded to digigraph as `X-LiteLLM-Proxy-Key` when
present, allowing LiteLLM to route models per-tenant.

---

## 5. Internal Architecture

### Next.js App Router structure

```
src/app/
  layout.tsx            # Root layout (Providers, Geist Mono)
  page.tsx              # Server component: default → /embed; optional root auth → ChatShell
  login/                # Login page (only when DIGICHAT_REQUIRE_ROOT_AUTH=1)
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

The root `page.tsx` is a **React Server Component**. By default
(`DIGICHAT_REQUIRE_ROOT_AUTH` unset/`0` — Option A) it redirects to `/embed`. When
`DIGICHAT_REQUIRE_ROOT_AUTH=1` (Option B — no shipped deployment uses this today),
it calls `auth()` and, with no session, also redirects to `/embed` — there is no
standalone `/login` page; a session must come from an OIDC callback, a machine
key, or the dev-only local-bootstrap credentials provider. `ChatShell` is a
`"use client"` component that owns all thread state as React state; the server
renders nothing but the initial HTML shell for it.

### BFF pattern (route handlers)

Route handlers run on the Node.js runtime (not Edge). They are the sole callers of
digigraph, digikey, and digisearch. The browser has no direct path to the Python
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
  ├─ Upstream auth: digikey bff_session | api_key exchange | static key
  │
  ├─ Trace path (default, DIGICHAT_TRACE_UI != "0")
  │   ├─ POST {base}/v1/chat/completions  (raw fetch, no AI SDK client)
  │   ├─ iterateOpenAiSse: parse SSE frames
  │   │   ├─ delta.content  → text-delta parts
  │   │   └─ delta.digigraph_trace → data-digichatActivity parts (typed mapper)
  │   └─ createUIMessageStreamResponse → SSE to browser
  │
  └─ Legacy path (DIGICHAT_TRACE_UI=0 or X-Digichat-Trace: 0)
      ├─ createdigigraphClient → AI SDK OpenAI provider
      ├─ streamText + smoothStream(chunking: "word")
      └─ toUIMessageStreamResponse → SSE to browser
```

### Auth.js session flow

1. User visits `/`. If `DIGICHAT_REQUIRE_ROOT_AUTH` is not enabled (default), redirect
   to `/embed` (tenant `gateMode` applies there — digithings dogfood uses `ungated`).
2. When root auth is required, the server component calls `auth()` — reads and decrypts
   the session JWT from the httpOnly `__Secure-authjs.session-token` cookie.
3. No session → `redirect("/embed")` (no standalone `/login` page ships).
4. A session is established via `POST /api/auth/callback/credentials` (dev-only
   providers) or an OIDC redirect (production), not through a digichat-hosted page.
5. Auth.js writes an encrypted session JWT cookie. `jwt` callback copies `user.id` →
   `token.sub`. `session` callback copies `token.sub` → `session.user.id`.
5. On subsequent requests, `auth()` decrypts the cookie and returns the session. No
   database session store — stateless JWT only.

### digikey JWT exchange flow

On every `/api/chat` call:
1. If the incoming request carries `Authorization: Bearer dgk_live_…`, the BFF calls
   `POST {DIGIKEY_URL}/v1/oauth/token` with `grant_type=api_key` and the raw key.
   digikey validates and returns a short-lived JWT.
2. Otherwise, if `DIGIKEY_URL` and `DIGIKEY_BFF_TOKEN` are set, the BFF calls
   `POST {DIGIKEY_URL}/v1/oauth/token` with `grant_type=bff_session`, the BFF token,
   tenant slug, and OIDC subject. digikey returns a short-lived JWT scoped to that
   tenant+subject.
3. Fallback: `DIGIGRAPH_UPSTREAM_API_KEY` static bearer (bootstrap only).
4. The resulting JWT is forwarded as `Authorization: Bearer <JWT>` to digigraph,
   along with `X-digichat-Tenant`, `X-Digi-Caller: digichat`, `X-Session-Id`,
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
`/api/conversations*` route calls `requiredigichatAuth()` first, which 401s a bare
anonymous request before any read/write — so no Postgres row can be created for
`ownerUserSub: "embed:anonymous"` (verified by inspection for #1251, not assumed).

### Embed tenant registry & backends

`DIGICHAT_EMBED_TENANTS` (JSON, keyed by hostname) declares embed tenants:
per-host `slug`, `backend` (`digigraph` | `foundry` + https `projectEndpoint` +
`agentName`; digigraph may optionally set `digisearchIndex` / `vaultPathPrefix`
for per-tenant corpus isolation — forwarded as `X-Digi-Corpus-Index` /
`X-Digi-Vault-Prefix` on `/api/chat`), `gateMode` (`turn_limited` | `ungated` |
`trial_form`), `theme`
(`dark` | `light`), optional `accent` hex pair, `activityDetail`
(`off` | `labels` | `full`), optional UI flags `showByok` / `showStatusBar` /
`layout` (`page` | `embed`) — independent of `gateMode` (never derive
`showByok = !ungated`), optional `llmAccess`
(`free_then_byok` | `byok_only` | `backend_only` | `operator`) for LLM spend
policy (digithings.ai = `free_then_byok` + `showByok: true`; foundry/DataTap =
`backend_only` + BYOK off), `attribution` flag, `aliases`, and a required `token`.

On structured `free_quota_exceeded` / clear rate-limit errors, embed tenants with
`llmAccess: free_then_byok` stop the turn and open the in-chat BYOK sequence
(even when `gateMode` is `ungated` — see `shouldSuggestByokOnEmbedError`). After
the visitor activates a validated key, the failed turn is retried with existing
`X-BYOK-*` headers. BYOK providers listed in the UI: OpenAI, OpenRouter,
Anthropic, Gemini, x.ai (model required for all non-OpenAI providers).
Provider list is defined by `config/byok-providers.json`.

A non-2xx digigraph reply is **not** relayed to an embed visitor: the body is
logged server-side and the stream carries a generic "unavailable right now",
because a 500 body can hold stack traces, internal hostnames and prompt echoes.
The one exception is a refusal the visitor can act on — `relayableUpstreamCode`
in `lib/adapters/digithings/stream.ts` passes through the *code* alone, and only
for codes in `BYOK_MODEL_REMEDIABLE_CODES`, so the BYOK sequence opens instead
of the turn dead-ending. The upstream `message` is never relayed on that path:
digigraph's text for `byok_default_model_provider_mismatch` reflects the
caller's own `X-BYOK-Provider` header back at them.

### BYOK (bring-your-own-key) — session-only, inline terminal flow

Visitor API keys are **session memory only** (`useBYOKKey` React state). The
key itself is never written to `localStorage`, `sessionStorage`, cookies, or
Postgres — the only thing that persists across sessions is the non-secret
`digichat_byok_pref` cookie (`readByokPrefCookie`/`writeByokPrefCookie` in
`use-byok-key.ts`), which holds just `{provider, model}` so a returning
visitor's picker opens pre-selected instead of always defaulting to
OpenRouter. `useBYOKKey()` restores that pair into its `provider`/`model`
state on mount, always with `isSet: false` (no key ever ships with it), and
`clearKey()` deletes the cookie outright rather than rewriting it — clearing
a key does not silently reset the remembered provider to OpenRouter. This
cookie is a known no-op on `/embed`'s cross-site iframe surface when the
visitor's browser blocks or partitions third-party cookies (Safari/Firefox by
default, Chrome without CHIPS) — the picker just falls back to its default
there, nothing breaks. Legacy durable keys (`byok_api_key` / `byok_provider` /
`byok_model`) are purged on hook mount. A page refresh always clears the live
key.

`ByokCliFlow` (`src/components/byok-cli-flow.tsx`) takes `active` (a
currently-live, validated key — gates the "done" step and "BYOK active" text)
and, separately, optional `initialProvider`/`initialModel` (just seeds the
picker's starting selection, e.g. from the cookie above, without implying a
live key). All three call sites (`chat-panel.tsx`, `embed/embed-client.tsx`,
`byok-settings-panel.tsx`) wire `useBYOKKey()`'s `provider`/`model` into the
latter pair independently of `active`/`isSet`.

UX is a stepwise terminal sequence rendered **inline in the chat transcript**
(DigiChatSession `settingsPanel` slot inside `.dc-thread`, and the app shell
`ChatPanel` when `/key` opens BYOK mode):

1. Select provider (arrow keys + Enter, or click) — pre-selected from
   `initialProvider` above when set
2. Paste API key. For OpenAI, Anthropic, and Gemini this immediately fires
   `POST /api/byok/test` in the background, before any model is chosen —
   see "Key-step live model ping" below.
3. Select model from presets (or custom slug) — for OpenRouter, from a live
   catalog with tier tabs instead (see below); for OpenAI/Anthropic/Gemini,
   from the key-step ping's live `models` list once it resolves, falling
   back to presets while pending, on failure, or on an empty list.
4. `POST /api/byok/test` ping — activation is refused until `ok: true`. For
   OpenAI/Anthropic/Gemini this step is skipped: the key-step ping from
   step 2 is reused directly, so exactly one validation call happens
   across the whole flow for these three providers.
5. On success, key is held in-memory for this tab session and sent as
   `X-BYOK-Key` / `X-BYOK-Provider` / `X-BYOK-Model` on subsequent `/api/chat`
   requests only. `X-BYOK-Model` is sent whenever the user chose a model —
   every send path (`chat-panel.tsx`, `use-embed-digi-chat.ts`,
   `api/chat/route.ts`'s upstream forward, and `byok-ping.ts`) forwards a
   non-blank model unconditionally, for every provider. It used to be gated
   on `byokRequiresModel(provider)`, which dropped the model an OpenAI user
   had explicitly picked; digigraph then answered on its own tier default,
   an `openrouter/…` slug billed to the operator (#2490). `byokRequiresModel`
   governs whether a model is **mandatory**, never whether a chosen one is
   forwarded, and it is still what `api/chat/route.ts` asks before returning
   400 `byok_model_required`. It is defined once in the framework-neutral
   `src/lib/byok-providers.ts` (no `"use client"` directive, so both React
   client code and Next.js server Route Handlers can import it) and
   re-exported by `use-byok-key.ts` for its own callers. Every call site that
   asks the *mandatory* question defers to that one predicate (never a
   hand-maintained per-provider list): `byok-cli-flow.tsx` (which offers a
   blank "" model option and refuses a blank custom slug accordingly, and is
   the single flow component that `chat-panel.tsx`, `embed/embed-client.tsx`
   and `byok-settings-panel.tsx` all host), `use-byok-key.ts`'s
   `validateBYOKModel`, and `api/chat/route.ts`'s `byokNeedsModel` gate,
   which calls `byokRequiresModel(byokProvider)` directly in place of its old
   5-provider OR-chain, so a 6th `requiresModel` provider can't silently skip
   its 400 there the way `xai` once did (#2351). `api/byok/test/route.ts` also imports this module —
   `readByokProvider` replaces its old `readProvider` (which fell through to
   `"openai"` for any unrecognized value) and `byokKeyPrefixError` replaces
   its five hand-written prefix `if`-blocks. That route's own `needsModel`
   gate (which providers require `X-BYOK-Model` before the test ping runs at
   all) is deliberately its own hand-written check — `provider === "xai"`
   only (#2347) — and is **not** derived from `byokRequiresModel`. The two
   guard different things: `byokRequiresModel(provider)` governs whether a
   model is required before the real `/api/chat` request is accepted;
   `needsModel` here governs only whether the *validation ping* needs a
   model before it can run at all. They diverge on purpose — none of
   `testOpenAIKey`, `testAnthropicKey`, `testGeminiKey`, or
   `testOpenRouterKey` read their own `model` parameter, so requiring one
   before the ping just delayed a call that would have worked without it;
   only `testXaiKey` has no live-list call, so x.ai is the one provider that
   still needs a model up front. Deriving `needsModel` from
   `byokRequiresModel` instead would reintroduce the exact bug #2347 fixed —
   the two must stay independent.

For OpenRouter, `byok-cli-flow.tsx` prefetches `GET /api/byok/models?provider=openrouter`
(no key required) as soon as `openrouter` becomes the selected provider, usually
before the model step even renders. Once that catalog lands, the model step
replaces the flat preset list with tier tabs (free / opensource / flagship /
all / a user-starred "custom" set held only in component state) plus a
per-entry star toggle. Any fetch failure or non-OpenRouter provider falls back
to the original flat preset list unchanged — the tiered UI is strictly additive
and never blocks the flow on network.

For OpenAI, Anthropic, and Gemini, `byok-cli-flow.tsx` fires
`pingByokKey(key, provider, "", { requireModel: false })` as soon as the
key step is submitted (`submitKey`), before a model is chosen.
`requireModel: false` (an option `pingByokKey` gained for this) skips its
own client-side `validateBYOKModel` pre-check, which would otherwise
refuse to call the server at all for a model-required provider with no
model chosen yet — exactly the state at the key step for Anthropic and
Gemini. The result is cached in `keyPing` state; its `models` array
(already returned by `testOpenAIKey`/`testAnthropicKey`/`testGeminiKey`,
unused before #2347) populates the model-step picker in place of
`byokModelPresets(provider)`, falling back to the presets with no visible
error whenever the ping hasn't resolved yet, failed, or came back with an
empty list. When the visitor then picks a model, `runValidateAndActivate`
reuses `keyPing` directly instead of issuing a second
`POST /api/byok/test` — exactly one validation call happens across the
whole flow for these three providers, same as it always was for the
other providers, just moved earlier. OpenRouter's own prefetch and x.ai's
fallback-preset-only behavior are unchanged.

The BFF forwards BYOK headers to digigraph for the request lifetime and never
logs or returns the raw key. `byokActivationGate` + Vitest cover the
session-only / validation-before-activate contract. `POST /api/byok/test` is
rate-limited on both the embed-IP path and the authenticated/session path
(`checkBffRateLimit`, same unconditional-on-both-paths shape as
`GET /api/byok/models`) — each call makes an outbound credentialed request to
the provider using digichat's own egress, so the authenticated path needs a
ceiling too, not just the anonymous-embed one.

`config/byok-providers.json`'s `keyPrefix` field is read by no runtime code, and
`fallbackModels` is read only by `digigraph/src/digigraph/llm_auth.py` (whose loader
takes `id`/`baseUrl`/`requiresModel` plus the first `fallbackModels` entry, used as
the remediation example in `byok_default_model_refusal`). Each is pinned to a
different in-app copy: `keyPrefix` against `src/lib/byok-providers.ts`'s own catalog
(`BYOK_PROVIDER_LIST`, `byokRequiresModel`, `byokKeyPrefixError`, `readByokProvider`)
by two test files — `use-byok-key.catalog-parity.test.ts` (the client hook's re-exports,
plus its own `byokModelPresets`) and its sibling
`hooks/byok-providers.catalog-parity.test.ts`
(the shared module itself, which is what `api/chat/route.ts` and
`api/byok/test/route.ts` import directly) — so either copy drifting from the
catalog fails a test instead of drifting silently. `fallbackModels` has no
counterpart in `byok-providers.ts`, which carries no model list; its in-app copy is
`use-byok-key.ts`'s `byokModelPresets`, pinned by the first of those two files. That
is what keeps digigraph's refusal naming a model this UI actually offers. **One
surface of that drift class is still unguarded:** the same file's
`byokModelPlaceholder` is a second hardcoded switch that reproduces every
provider's `fallbackModels[0]` and renders it in its own `(e.g. …)` sentence
(`use-byok-key.ts:237`) — the same shape digigraph's refusal produces. All five
values agree with the catalog today, but nothing pins them: its only assertion is
`expect(byokModelPlaceholder("xai")).toBeTruthy()`. Pin it to the catalog the way
`byokModelPresets` is pinned rather than adding a third copy. `api/byok/test/route.ts`
also calls `readByokProvider` from that same module: an `X-BYOK-Provider`
value naming no known provider gets an explicit
`400 Unknown BYOK provider: "…"` response instead of being silently treated
as `openai`, the pre-#2351 behavior of that route's old `readProvider`.

**digithings rule:** digithings tenants use `backend.type: digigraph` only.
digivault and digisearch are digigraph tools (activity mappers under
`src/lib/adapters/digithings/activity/`), not digichat HTTP backends. Client
Azure tenants use `foundry`. Removed: `external-relay` and digichat-Node
`digivault` backends.

Parsed fail-fast in `src/lib/embed-tenants.ts`; the same registry feeds
`/api/chat` tenant resolution (`src/lib/embed-chat-tenant.ts`) and the
client-safe `GET /api/embed/tenant-config` endpoint — both runtime-only,
reading `process.env.DIGICHAT_EMBED_TENANTS` fresh per request. Adapter
layout and contract:
[`docs/architecture/digichat-modular-frontend.md`](../../docs/architecture/digichat-modular-frontend.md).

**Tenant presentation is resolved server-side, before first paint.** `/embed`
is a server component (`src/app/embed/page.tsx`, `dynamic = "force-dynamic"`)
that reads the iframe URL's own `?token=`/`?host=` and resolves the tenant via
`resolveEmbedClientConfigFromParams` (`src/lib/embed-client-config.ts`), then
pins `<html data-theme>` with a pre-paint inline script and seeds the client
hook through `initialTenantCfg`. This exists because the root layout hardcodes
`data-theme="dark"` as its no-JS default (`src/app/layout.tsx`) and
`useEmbedTenantConfig` could previously only learn the tenant by fetching
`/api/embed/tenant-config` after mount — so every light-themed tenant painted
dark for a full round-trip and then flipped, a visible dark→light flash baked
into the SSR HTML itself. Measured after the change: FCP at 44 ms with
`data-theme="light"` already applied, while the config fetch only settled at
47.9 ms.

Two invariants keep it honest. The authorization rule is **identical** to the
header path (`resolveVerifiedEmbedTenant`) — a registered host alone never
unlocks a customer tenant's config, only its matching token does (#1339) — so
the earlier render discloses nothing the endpoint would not. And both paths
project through the *same* `toEmbedClientConfig`, because the client re-fetches
the endpoint after mount: any field drift between the two would repaint, which
is the flash this whole indirection removes. `token` and `backend` have no
branch in that projection and so can never reach the browser.

The `/embed` CSP frame-ancestors (`src/lib/security-headers.ts` + `src/proxy.ts`)
is set at **request time**. `next.config.ts` bakes only fail-closed
`frame-ancestors 'none'` on `/embed` so a missing proxy cannot open framing;
the Proxy overwrites `Content-Security-Policy` with the runtime allowlist from
`embedFrameAncestors()` / `embedFrameAncestorsCsp()`. That helper never reads
anything but hostnames — never the token — so it's driven by a separate,
non-secret `DIGICHAT_EMBED_HOSTS` env var (plain comma-separated hostnames),
preferred over deriving hosts from the full `DIGICHAT_EMBED_TENANTS` registry
when both are set (#1360). Wildcard tokens (`*`, `*.example.com`) are rejected;
digichat never emits `frame-ancestors *`. Loopback hostnames listed in
`DIGICHAT_EMBED_HOSTS` / the registry (`localhost`, `127.0.0.1`, `[::1]`) emit
`http://host:*` (and https equivalents) even when `NODE_ENV=production`, so a
prod-like Docker digichat can be framed by local digithings-web at
`http://127.0.0.1:3010` (#2093). `DIGICHAT_ALLOW_LOCAL_EMBED_PARENTS=1` also
adds those http wildcards when DIGICHAT_EMBED_HOSTS omits loopback. Non-loopback
customer hosts stay `https://` only.

`DIGICHAT_EMBED_TENANTS` itself stays runtime-only (a container env var, never
a build-arg) because a Docker build-arg persists in image layer history and
cloud-build logs (e.g. `az acr build`) — passing the full token-bearing
registry there would leak every tenant's token.

`foundry` tenants call Azure AI Foundry directly via
`src/lib/adapters/foundry/stream.ts` (`@azure/ai-projects` +
`DefaultAzureCredential` — the container's own managed identity, no stored
key). Conversation state lives in Foundry; the client echoes the conversation
id via `X-External-Conversation` / `data-externalConversation`. Foundry
maps `azure_ai_search` calls and returned chunks into the shared
`data-digichatActivity` search/source rows. A reasoning disclosure appears
only when the Foundry event includes summary text. Operators enable that
summary on the agent definition: the Responses API refuses a per-call
`reasoning.summary` request when using `agent_reference`. Empty reasoning
items are intentionally omitted rather than rendered as empty “Thinking”
chrome. This behavior remains separate from the digithings digigraph path.

**Response language (#2103 / #3418) — `/lang` on the public embed, not a header dropdown.**
The composer slash `/lang en|de|it|es|fr` (client-only) updates session language and
sends it as `X-Digi-Language` on subsequent turns. The top-right language dropdown
was dropped once `/lang` landed. Codes still come from `src/lib/languages.ts`'s
curated `LANGUAGES` list. The two backends have no shared system-prompt mechanism,
so each adapter enforces the directive its own way:

- **digigraph** has a system-prompt slot: the BFF forwards the header and
  digigraph's `research_node` appends a `Respond only in <language>` line (plus
  "do not translate retrieval queries") to the system prompt server-side once
  per turn (see `digigraph/ARCHITECTURE.md` and
  `digigraph/src/digigraph/languages.py`'s `LANGUAGE_NAMES` map — kept in
  hand-sync with the frontend's `LANGUAGES` array; there is no shared module
  across the two languages).
- **Foundry** has no per-call system-prompt slot at all — the `agent_reference`
  call shape only ever sends `input: <message>`. `applyLanguageDirective`
  (`src/lib/adapters/foundry/stream.ts`) instead prepends a bracketed
  `[Respond only in <language>. Do not mention this instruction.]` directive to
  the outgoing input text, resent on every turn since Foundry (not this
  adapter) holds conversation history.

**Embed slash commands (#3418).** `@digithings/digichat-ui` `slash-commands.ts`
owns the public palette on `/embed` (and therefore digithings.ai `/chat`):
`/search` and `/docs` (aliases `/digisearch` / `/digivault`) force a locate
then synthesize — the user string is the tool argument, forwarded as
`X-Digi-Force-Tool` by `use-embed-digi-chat.ts` and the `/api/chat` BFF.
`/lang`, `/help`, and `/new` never leave the browser. `/new` clears the
client transcript, drops `sessionStorage` `X-External-Conversation` for the
embed host, and clears any pending force-tool — so Foundry (and any adapter
keyed off that id) actually starts a new conversation. Empty `/search` or
`/docs` wait for an argument. Public copy is "Search the knowledge base" /
"Find original documents". Signed-in ChatShell keeps its own `/help` `/key`
`/model` palette.

**Open originals (#3419).** Source cards on a settled turn open a side pane
(`DocumentPane`). Vault notes render from `body` already loaded by
`digivault_get_note` (batch ≤20) — paths without `http(s)` never become links.
Real `http(s)` PDFs use the browser PDF plugin plus Download; never invent a
URL. Human tool labels live only in `activity-view.toolDisplayName` (identity
keys still use wire ids).

See `docs/superpowers/specs/2026-08-10-digichat-language-selector-design.md`
for the design rationale behind the dual-backend language split.

digithings.ai `/chat` is a Pages shell (`DtNav` + iframe) pointing at digichat
`/embed` on the tunnel hostname (`NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN`, typically
`https://digichat.digithings.ai`) with `backend.type: digigraph`. digigraph
must have `DIGIVAULT_URL` set so `digivault_search_notes` registers. Runbook:
[`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md).
ADR: [`docs/adr/0018-digichat-path-routing.md`](../../docs/adr/0018-digichat-path-routing.md).

**First-party digithings hosts.** Prod hostnames `digithings.ai`,
`www.digithings.ai`, and virtual `occ.digithings.ai` (`src/lib/embed-first-party.ts`)
may use digichat `/embed` without presenting `X-Embed-Token` when registered in
`DIGICHAT_EMBED_TENANTS`. In `NODE_ENV=development` only, registered `localhost` /
`127.0.0.1` / `[::1]` hosts get the same bypass for local dogfood. Customer embeds
(e.g. DataTap) still require a matching token. Preview `*.pages.dev` hosts are
**not** allowlisted. `/chat/occ` iframes `?host=occ.digithings.ai` (no DNS) for
OCC corpus isolation.

**postMessage seed.** Embed emits `{ type: "digichat:ready" }` to the **actual
parent browsing-context origin** (`location.ancestorOrigins[0]` or
`document.referrer` via `resolveReadyTargetOrigin` in
`src/lib/embed-seed-messages.ts`) — never the virtual `?host=` tenant key
(e.g. `occ.digithings.ai`). digithings.ai posts
`{ type: "digichat:seed", messages, pending, ts }` after checking
`event.origin` against the digichat embed origin (`ChatEmbedShell`). Validators
and caps live in `src/lib/embed-seed-messages.ts`. DataTap's `datatap:gated` /
`datatap:unlocked` channel is unchanged.

**postMessage theme.** digithings.ai `/chat` and `/chat/occ` (`ChatEmbedShell`)
read the parent site's canon `html[data-theme]` (shared `ThemeProvider` /
`dt-theme` localStorage), pin first paint with `?theme=light|dark` on the iframe
URL, then post `{ type: "digichat:theme", theme, ts }` on `digichat:ready` and
whenever the parent theme toggles — no iframe reload. The embed accepts theme
messages from the same first-party allowlist as seed (`parseThemeMessage` in
`src/lib/embed-theme-messages.ts`) and applies them via the existing
`[data-theme]` + `.dark`/`.light` path (MutationObserver still defends against
OS/`ThemeProvider` overrides). Priority: parent postMessage > URL `?theme=` >
tenant registry theme.

**postMessage parent-error.** After `READY_TIMEOUT_MS` (30s) without
`digichat:ready`, `ChatEmbedShell` posts
`{ type: "digichat:parent-error", code: "ready_timeout"|"embed_unloadable", ts }`
into the iframe (same first-party allowlist as seed/theme). The embed formats a
CLI-style DigiChatSession transcript line (`error: …` via
`formatParentErrorLine` in `src/lib/embed-parent-error-messages.ts`) — no
parent-page banner. If the iframe never loads, the shell shows the same line in
the iframe slot. Copy references `DIGICHAT_EMBED_ORIGIN` / Containers (not the
legacy tunnel / `DIGICHAT_EMBED_HOSTS` wording). When
`resolveReadyTargetOrigin` returns null the embed self-reports
`ready_target_missing`.

**`X-Embed-Host` alone is not sufficient authorization (#1339).** A tenant's
host string is its own public domain, so `resolveEmbedTenantByHost` never
grants embed access by itself — `resolveVerifiedEmbedTenant`
(`src/lib/embed-chat-tenant.ts`) additionally requires the request's
`X-Embed-Token` header to match that tenant's own registry-configured
`token` **unless** the host is on the first-party allowlist (above). Both `/api/chat` and `GET /api/embed/tenant-config` resolve
through this verified path; without a matching token a non-first-party request is treated
exactly like an unregistered host (generic gated defaults, or the legacy
`DIGICHAT_LEGACY_EMBED_ENABLED`/`DIGICHAT_EMBED_TOKEN` path), never the specific
tenant's config or relay. The token is not secret from that tenant's own
site visitors — it's provisioned out-of-band and baked into the tenant's
embed snippet as a query param (`<iframe src=".../embed?token=...">`),
read client-side in `src/app/embed/page.tsx` and forwarded as
`X-Embed-Token` — the same trust model as a Stripe publishable key or
reCAPTCHA site key: not guessable by an unrelated caller, but not a bearer
secret a real visitor needs to protect either.

**Where `X-Embed-Host` actually comes from client-side (#1372).** The embed
snippet should pass the embedding page's own origin explicitly via `?host=`
on the iframe `src` (`resolveEmbedHost()` in `src/lib/embed-gate.ts` prefers
this over anything else) — the embedding site always knows its own origin
reliably, and passing it explicitly avoids relying on the iframe trying to
detect its parent. If `?host=` is absent, `resolveEmbedHost()` falls back to
`document.referrer`'s origin, then (same-origin dev embeds only)
`window.parent.location.origin`. **Never** fall back further to
`window.location.origin` — that's this app's own origin, not a signal about
who is embedding it, and `window.parent.location.origin` throwing is the
*expected*, *normal* case for every real cross-origin production embed (that
throw is the whole point of the browser's same-origin policy). A prior
version of this fallback did exactly that and shipped for a while — meaning
`X-Embed-Host` was silently wrong (always this app's own origin) for every
real production embed, so `resolveVerifiedEmbedTenant` could never match a
real tenant host; every embed silently degraded to the generic gated
config regardless of token. Confirmed via a live deployment before this fix.

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
- **`/embed`**: `next.config` bakes fail-closed `frame-ancestors 'none'`; `src/proxy.ts`
  overwrites CSP at request time with `embedFrameAncestorsCsp()` (first-party origins
  + runtime `DIGICHAT_EMBED_HOSTS` and/or `DIGICHAT_EMBED_TENANTS` host keys). Never
  emits `frame-ancestors *`.

Vitest: `src/lib/security-headers.test.ts`, `src/proxy.test.ts`.

### Machine API key prefixes (REM-079 glossary)

| Prefix | Issuer | Validated by | Purpose |
|--------|--------|--------------|---------|
| `digi_live_` | digichat (`npm run db:create-key`) | `validateMachineApiKey()` → Postgres bcrypt | BFF route auth (`requiredigichatAuth`) |
| `dgk_live_` | digikey (`POST /v1/admin/keys`) | `exchangedigikeyApiKey()` → short-lived JWT | Upstream digigraph/digiquant calls via BFF exchange |

Do not conflate the two: digichat DB keys gate the BFF; digikey keys gate the agent stack.

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
session cookie. Route handlers hold no in-memory state. digichat can be horizontally
scaled without sticky sessions, provided all replicas share the same `AUTH_SECRET`
and `DIGICHAT_DATABASE_URL`.

### Postgres connection pool (Drizzle)

`src/db/index.ts` initializes a `postgres-js` pool with `max: 10, idle_timeout: 20,
connect_timeout: 10`. In a multi-replica deployment, each replica holds up to 10
connections, so N replicas require up to 10N connections. For a single Postgres
instance the default `max_connections=100` supports up to 10 replicas before
exhaustion. **Recommendation:** use PgBouncer in front of Postgres in production, or
reduce `max` per replica.

### AI SDK streaming via digigraph SSE (back-pressure)

The trace stream path opens a `fetch` to digigraph and iterates the response body with
a `ReadableStreamDefaultReader`. Node.js buffers the upstream chunks in memory. If the
client (browser) is slow to consume the outgoing stream (e.g., tab is backgrounded,
the connection is slow), the BFF buffers in Node.js without explicit back-pressure
signaling to digigraph. For typical chat payloads (text responses) this is not
concerning. For large tool outputs or long reasoning traces, large in-flight buffers
are possible. **Recommendation:** implement a streaming cancellation path so that when
the client disconnects, the BFF aborts the upstream digigraph request (see Section 12).

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
Browser → BFF (auth cookie read + session decrypt) → digikey (JWT exchange, 1 HTTP
round-trip) → digigraph (processing starts) → first SSE chunk → BFF → browser.

The digikey round-trip adds latency on every message send. For low-latency targets,
consider caching the digikey JWT for its declared `exp` minus a grace period (e.g.,
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

### digigraph (primary)

digigraph exposes an OpenAI-compatible API at `{DIGIGRAPH_INTERNAL_URL}/v1`. digichat
calls `POST /v1/chat/completions` with `stream: true`. In the trace path, the BFF
constructs the request body manually via `coreMessagesTodigigraphOpenAi` (which
coerces AI SDK `ModelMessage` content to plain strings to avoid digigraph's strict
`422` validation). In the legacy path, the AI SDK OpenAI provider constructs the body.

digigraph SSE frames carry an optional `digigraph_trace` field on each
`choices[0].delta`. The trace path maps typed payloads (`rag_sources`,
`graph_update`, and opaque labels) through `mapdigigraphTraceToSpans` and emits
only `data-digichatActivity` parts (legacy `data-digigraphTrace` dual-emit was
removed in Phase 2). Auth `chat-panel` and embed both render via
`@digithings/digichat-ui` `ChatActivities` (rich hits + `brief`).

Session correlation: `X-Session-Id` (conversation UUID), `X-Request-ID` (per-request
UUID), `X-digichat-Tenant`, `X-Digi-Caller: digichat` are forwarded to digigraph and
flow through to digismith tracing spans.

### digikey (token exchange)

digikey at `{DIGIKEY_URL}` accepts `POST /v1/oauth/token`. Two grant types are used:
`bff_session` (BFF-to-digikey server-to-server, authenticated by `DIGIKEY_BFF_TOKEN`)
and `api_key` (client machine key exchange). digikey returns a short-lived JWT and
optionally a `litellm_proxy_api_key`. digichat never sees the raw digikey signing
secret; only `DIGIKEY_BFF_TOKEN` is needed (a long-lived BFF credential).

### digisearch health badge

`GET /api/health` probes `{DIGISEARCH_INTERNAL_URL}/health` when `digisearch` is in
`DIGICHAT_ENABLED_SERVICES`. digisearch is not called directly by the chat BFF;
digigraph calls digisearch internally during workflow execution. The health badge
in the Ecosystem sheet reflects connectivity only.

digigraph and digiquant get the same `DIGICHAT_ENABLED_SERVICES` treatment (#1346):
unlike `digisearchUrl`, `digigraphUrl`/`digiquantUrl`/`digismithUrl` in
`EcosystemEndpoints` always have a default value (`ecosystem.ts`'s `DEFAULTS`), so
the health route checks `isServiceCapabilityEnabled(...)` directly rather than URL
presence — a deployment serving only `external-relay` embed tenants (no digigraph
stack running at all) can omit them from `DIGICHAT_ENABLED_SERVICES` without
`/api/health` reporting itself unhealthy. Note the `DIGICHAT_ENABLED_SERVICES=""`
gotcha in `capabilities.ts`: an empty string falls back to the all-enabled default,
so disabling every service requires a non-matching placeholder value instead.

### digiquant backtest result parsing

digichat does not call digiquant directly. `BacktestResult`-shaped JSON appears in
assistant message parts because digigraph includes digiquant tool outputs in the
message stream. The quant strip parses these client-side. With Postgres enabled,
the client can persist runs by calling `POST /api/conversations/[id]/quant-runs`
using the extracted `run_id` and metrics.

### digismith status endpoint

`GET /api/health` probes `{DIGISMITH_INTERNAL_URL}/health` when `digismith` is in
`DIGICHAT_ENABLED_SERVICES`. digismith is not called from the chat flow; tracing is
handled by digigraph emitting `span` trace events in the SSE stream. The health
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
| `AUTH_URL` | Public origin of digichat (OAuth redirect base) | Yes in production |
| `AUTH_TRUST_HOST` | Allow `X-Forwarded-Host` from reverse proxy | Yes in Docker |
| `AUTH_OIDC_ISSUER` | OIDC provider issuer URL | If using OIDC |
| `AUTH_OIDC_CLIENT_ID` | OIDC client ID | If using OIDC |
| `AUTH_OIDC_CLIENT_SECRET` | OIDC client secret | If using OIDC |
| `DIGICHAT_DEV_AUTH` | Enable dev password login (`1` = on) | Dev only |
| `DIGICHAT_DEV_PASSWORD` | Dev password (default: `dev`) | Dev only |
| `DIGICHAT_LOCAL_AUTH_KEY` | Dev auto-sign-in key (non-production only) | Dev only |
| `DIGICHAT_REQUIRE_ROOT_AUTH` | Require Auth.js session on `/` (`1` = on). Default unset/`0` redirects `/` → `/embed` (Option A) | Optional |
| `DIGIGRAPH_INTERNAL_URL` | digigraph base URL (default: `http://127.0.0.1:8000`) | Yes |
| `DIGIGRAPH_UPSTREAM_API_KEY` | Static Bearer to digigraph (fallback auth) | If not using digikey |
| `DIGIKEY_URL` | digikey base URL | If using digikey |
| `DIGIKEY_BFF_TOKEN` | BFF credential for digikey `bff_session` grant | If using digikey |
| `DIGIQUANT_INTERNAL_URL` | digiquant base URL (health probe) | Recommended |
| `DIGISMITH_INTERNAL_URL` | digismith base URL (health probe) | Recommended |
| `DIGISEARCH_INTERNAL_URL` | digisearch base URL (health probe) | Optional |
| `DIGICHAT_ENABLED_SERVICES` | Comma-separated active service IDs; unset defaults to all four (`digigraph,digisearch,digiquant,digismith`), explicitly set to `""` to enable none | Optional |
| `DIGICHAT_DATABASE_URL` | PostgreSQL connection URL | For server persistence |
| `DIGICHAT_AUTO_MIGRATE` | Run Drizzle migrations on startup (`1` = on) | Docker recommended |
| `DIGICHAT_BOOTSTRAP_API_KEY` | Static machine API key (env bootstrap) | For machine clients |
| `DIGICHAT_BOOTSTRAP_TENANT_SLUG` | Tenant for bootstrap key (default: `default`) | If using bootstrap key |
| `DIGICHAT_DEFAULT_TENANT_SLUG` | Default tenant slug when DB unavailable | Production fallback |
| `DIGICHAT_TRACE_UI` | Disable trace stream (`0` = off, default on) | Optional |
| `DIGICHAT_MODEL` | digigraph model name (default: `digigraph-rag`) | Optional |
| `DIGICHAT_OPENWEBUI_FORMAT` | Opt-in Open WebUI format (`1` only). Default off; digichat sends `X-Response-Format: plain` | Optional |
| `DIGICHAT_ENDPOINT_HOST_ALLOWLIST` | Comma-separated hosts for SSRF guard | Security hardening |
| `DIGICHAT_LEGACY_EMBED_ENABLED` | Enable legacy generic embed for **unregistered** hosts (`1` = on). Does not default on when `DIGICHAT_EMBED_TENANTS` is set. Deprecated alias: `DIGICHAT_EMBED_ENABLED` | Optional |
| `DIGICHAT_EMBED_TOKEN` | Alternative to legacy flag: gate unregistered `/embed` on `X-Embed-Token` | Optional |
| `DIGICHAT_EMBED_TENANTS` | Optional JSON registry of embed tenants (see "Embed tenant registry & external backends"). Unset = no external embed tenants; first-party embeds behave exactly as before. Runtime-only — never pass as a Docker build-arg, it carries every tenant's secret `token` and build-args persist in image layer history / cloud-build logs (#1360). Each entry requires a `token` — the embed snippet passes it back as `?token=` / `X-Embed-Token`; a registered host alone is not sufficient authorization (#1339). | Optional |
| `DIGICHAT_EMBED_HOSTS` | Plain comma-separated embed-tenant hostnames, no secrets. Feeds `/embed` CSP `frame-ancestors` at **runtime** via `src/proxy.ts` (preferred over deriving hosts from `DIGICHAT_EMBED_TENANTS` when both are set — #1360). Optional seed list: `embed-hosts.txt` (not baked into the GHCR image). Never emits `frame-ancestors *`; fail-closed to first-party origins when unset/invalid. | Optional |
| `DIGICHAT_CHAT_RATE_LIMIT_MAX` / `_WINDOW_MS` | Shared per-`{tenantSlug}:{ownerUserSub}` chat rate limit (default 30/60000ms) | Optional |
| `DIGICHAT_EMBED_IP_RATE_LIMIT_MAX` / `_WINDOW_MS` | Per-IP chat rate limit for anonymous `/embed` requests, in front of the shared bucket above (default 10/60000ms — must stay below `DIGICHAT_CHAT_RATE_LIMIT_MAX`) | Optional |
| `DIGICHAT_TRUSTED_PROXIES` | Comma-separated IP addresses/CIDRs whose socket peers may supply `cf-connecting-ip` or `X-Forwarded-For` for anonymous-embed rate limiting. Unset preserves historical header behavior. The bundled production entrypoint captures the direct socket peer and isolates Next on loopback; do not set this unless that entrypoint remains in the request path. In a Cloudflare Container, trust the container ingress/overlay peer, not Cloudflare's published edge ranges. | Optional |
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

digiclaw (`digiclaw/`) provides heartbeat, audit, and gateway functionality. digichat
currently has no integration with digiclaw. Planned work includes routing all chat
requests through an OpenClaw gateway for rate limiting, audit logging, and policy
enforcement at the BFF boundary.

### RAG document ingestion UI

There is no UI for uploading or managing documents for digisearch. Users can exercise
digisearch only indirectly via digigraph tool calls. A document ingestion panel (drag-
and-drop PDF/text → `POST /v1/ingest` on digisearch) would complete the end-to-end
RAG workflow from the browser.

### Fine-grained permission UI

The current multi-tenant model requires manual SQL to map OIDC subjects to tenants
(`INSERT INTO user_tenants`). An admin UI for tenant management, user provisioning,
and API key lifecycle (list, revoke, rotate) would be needed before digichat is
suitable for use by multiple distinct organizations.

### digibase credential brokering

`DIGICHAT_DATABASE_URL` is currently a raw PostgreSQL URL stored in an environment
variable. The ARCHITECTURE.md for the root project notes that the strategic direction
is to route chat DB credentials, checkpoints, and cache credentials through a
**digibase data-plane service** so that secrets live in one brokered place rather than
as raw URLs in every service. The `digibase/` directory currently ships only the
Python library. When digibase ships the HTTP credential broker, digichat should
replace direct `DIGICHAT_DATABASE_URL` with a digibase-issued short-lived credential.

---

## 12. Redesign Recommendations

The following are specific, actionable improvements ordered by estimated impact.

### (a) Replace direct `DIGICHAT_DATABASE_URL` with digibase credential broker

When digibase ships its credential broker, digichat should request a Postgres credential
from digibase using its digikey JWT rather than holding a permanent connection string.
This eliminates long-lived database credentials from the digichat environment entirely
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
in-process (`BoundedTTLMap`), so — like digigraph's and digisearch's own limiters —
multiple digichat replicas would each enforce independently, multiplying the effective
limit by replica count. Moving to Redis-backed counters remains open if digichat scales
to multiple instances behind a load balancer.

The new `embed_ip:*` keys share the same 10,000-entry bounded map (`MAX_RATE_LIMIT_KEYS`
in `bff-rate-limit.ts`) as every other rate-limit key, including authenticated
`chat:*` buckets, and eviction is FIFO by insertion order (not LRU). An attacker who
can mint many distinct client IPs (only realistic when not actually behind Cloudflare —
see the trust-boundary note above) could cycle through enough of them to evict
legitimate entries, resetting their windows early. Impact is limiter degradation, not
an auth bypass; segmenting the two key spaces into separate bounded maps would close
this if it becomes a real concern.

### (e) Add streaming cancellation (AbortController from client to digigraph SSE disconnect)

The AI SDK `stop()` function terminates the browser-side SSE consumer, but the BFF
continues receiving and discarding chunks from digigraph until digigraph finishes or
times out. This wastes digigraph compute and BFF memory.

The fix: in `createdigigraphTraceStreamResponse`, create an `AbortController` before
the upstream `fetch`. Register a cleanup handler on the writable side of the UI message
stream (or use the `execute` writer's `onClose`/`onAbort` if exposed by AI SDK) to
call `controller.abort()`. digigraph will then receive a connection reset and can
cancel its LangGraph execution.

### (f) Add `X-Request-ID` propagation from BFF to digigraph for full trace correlation

The BFF already generates and forwards `X-Request-ID` to digigraph and includes it in
the response headers (`X-Request-Id`). The browser-side `ChatPanel` should read this
response header and attach it to subsequent `PUT /api/conversations/[id]` calls so
that the stored conversation has a trace of every `X-Request-ID` that produced each
assistant turn. This would enable linking a stored conversation message to a specific
digismith trace span for post-hoc debugging.

Additionally, the BFF should log `X-Request-ID` at the start of every Route Handler
invocation (a one-line addition to each route file) so that structured server logs can
be correlated with digismith spans without relying on the client to preserve the ID.
