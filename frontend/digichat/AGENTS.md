# Agent Guide: DigiChat

## Purpose

DigiChat is the user-facing interface to the DigiThings ecosystem. It is a Next.js 16 App Router application acting as a **Backend-for-Frontend (BFF)**: the browser never calls DigiGraph or any Python service directly. All LLM calls, auth token exchanges, and upstream probes run in Next.js Route Handlers on the server.

---

## Read First

In this order, before writing any code:

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — full capability matrix, module map, API surface (all route handlers), auth flow, DB schema, streaming behavior
2. `node_modules/next/dist/docs/` — **required** before writing any Next.js code; this version has breaking changes from prior releases (path inside installed dependencies, not a committed file)
3. [`../../AGENTS.md`](../../AGENTS.md) — non-negotiable stack-wide rules
4. `../../ROADMAP.md` — OpenClaw integration and RAG ingestion UI are Phase 2; do not build them now (see `docs/VISION.md` for the current plan)
5. `../../docs/agent-backlog/` — current task queue lives on GitHub Project #1; see `docs/agents/AGENT_WORKFLOW.md`

---

## Pre-Flight Checklist

Before making any change to `frontend/digichat/`:

- [ ] Read `ARCHITECTURE.md` sections for the area you're touching (auth, chat route, conversations, ecosystem, DB schema)
- [ ] Run `npm run test` from `frontend/digichat/` — passes before and after
- [ ] Run `npm run lint` from `frontend/digichat/` — zero errors
- [ ] Confirm browser **never** holds a DigiGraph JWT or `DIGIKEY_BFF_TOKEN` — all upstream auth is server-side only
- [ ] Confirm `isAllowedServiceUrl()` is called on any user-supplied endpoint URL before fetching it (SSRF guard)
- [ ] Confirm `AUTH_SECRET` / `NEXTAUTH_SECRET` never appears in client bundle or API responses
- [ ] Confirm any new API route requires `requireDigiChatAuth()` unless it is explicitly a public endpoint (only `GET /api/health` is public)
- [ ] Confirm `DIGICHAT_AUTO_MIGRATE=1` behavior in `src/instrumentation.ts` is not bypassed for production

---

## Non-Negotiable Rules

Beyond root `AGENTS.md`:

- **BFF pattern is non-negotiable**: No DigiGraph URL, DigiKey token, or upstream service credential may ever reach the browser. All upstream calls go through Next.js Route Handlers.
- **Auth on every route except health**: Every `src/app/api/` route handler must call `requireDigiChatAuth()`. `GET /api/health` is the only exception.
- **SSRF guard on ecosystem endpoints**: Any user-supplied service URL must pass `isAllowedServiceUrl()` before being fetched. Never construct a fetch URL from raw user input.
- **No raw Next.js version assumptions**: Next.js 16 App Router has breaking changes. Read `node_modules/next/dist/docs/` before writing route handlers, server actions, or middleware.
- **Machine keys are bcrypt-hashed in Postgres**: `digi_live_…` API keys are stored hashed. Never store or log raw machine key material.
- **Session token never in responses**: `AUTH_SECRET` encrypted session cookie must not be re-surfaced in API responses or logged. `X-Digichat-Session` header carries only a stable opaque UUID — not the session token itself.
- **`DIGICHAT_ALLOW_DEV_GLOBAL=1` is dev-only**: Dev password provider and local bootstrap gate must never activate in production builds. They are guarded by env var checks — do not weaken them.
- **Drizzle migrations are additive**: New columns must be nullable or have a default. Never drop a column from an existing migration file — write a new one.
- **OpenClaw and RAG ingestion UI are Phase 2**: Do not scaffold, stub, or add routing for channel integrations or document upload UI without explicit phase scope.

---

## Test Commands

```bash
# From digichat/ directory
npm run test          # Vitest unit tests
npm run lint          # ESLint
npm run build         # Type-check + production build (catches type errors)

# Database operations (requires DIGICHAT_DATABASE_URL)
npm run db:migrate    # Run pending Drizzle migrations
npm run db:seed       # Seed dev data
npm run db:create-key -- <tenant_slug> <key_name>  # Create machine API key

# Dev server
make digichat-dev     # Start Next.js dev server (from repo root)

# Full unit suite (from repo root)
make test-unit
```

---


---

## More

Extension patterns, anti-patterns, and integration boundaries live in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that doc when changing interfaces or behavior.
