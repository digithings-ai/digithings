---
type: frontend-architecture
title: digichat Architecture
description: BFF design of the digichat chat UI — Next.js route handlers, backend adapters, shared UI package, and the never-in-browser credential invariant.
tags: [digichat, bff, nextjs, frontend]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-8e3c7688ec1299cb0d4d2721
    resource: repo://frontend/digichat/ARCHITECTURE.md
  - id: openwiki-source-8bc18f959241fc17599de8c5
    resource: repo://frontend/digichat/package.json
  - id: openwiki-source-64650938c858fae1d37aa390
    resource: repo://frontend/digichat/src/lib/ecosystem.test.ts
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digichat Architecture

digichat (`frontend/digichat`, package `digichat`, port 3005) is the
user-facing chat interface to the digithings ecosystem. It is a Next.js 16
App Router application acting strictly as a **Backend-for-Frontend (BFF)**:
the browser never speaks to digigraph or any Python service. All LLM calls,
auth token exchanges, and upstream probes run in server-side Route
Handlers.

## BFF invariant

No digigraph URL, digikey token, or upstream credential may ever reach the
browser. Route handlers under `src/app/api/` (`auth`, `byok`, `chat`,
`conversations`, `ecosystem`, `embed`, `health`, `v1`) do the upstream
work; every handler except `GET /api/health` requires
`requireDigiChatAuth()`. User-supplied service URLs pass
`isAllowedServiceUrl()` (SSRF guard) before any fetch. The
`X-Digichat-Session` header carries only an opaque UUID, never the session
token.

## Modular frontend

One shared UI (`@digithings/digichat-ui` workspace dependency) and activity
protocol serve multiple backends selected per tenant: `src/lib/adapters/`
holds `digithings` (digigraph via digillm + digivault hub), `foundry`, and
`shared` adapters. Turn/thread markdown export and last-turn regen/edit
semantics are implemented per adapter (digigraph replays the full workflow;
unsupported Foundry operations return `501 not_supported`; concurrent runs
conflict with `409`).

## Module map

| Area | Role |
|------|------|
| `src/app/api/` | Route handlers: auth, chat, conversations, ecosystem, embed, health |
| `src/lib/adapters/` | Backend adapters (`digithings`, `foundry`, `shared`) |
| `src/components/` | Chat shell, thread state, activity UI |
| `src/db/` | Drizzle schema + index (Postgres persistence, migrations) |
| `src/auth.ts`, `src/proxy.ts` | Auth.js config, edge proxy |
| `src/instrumentation.ts` | Boot-time auto-migration (`DIGICHAT_AUTO_MIGRATE=1`) |

Conversation persistence is localStorage always-on with optional Postgres;
quant runs persist to a `quant_runs` table; machine `digi_live_…` API keys
are bcrypt-hashed in Postgres. OpenClaw integration and RAG ingestion UI
are Phase 2 — not scaffolded.

## Representative tests

Vitest from `frontend/digichat/`: `route.test.ts` for the chat handler,
`ecosystem.test.ts` for the SSRF allowlist, plus adapter, persistence, and
markdown-export suites; `npm run lint` (ESLint) and `npm run build`
(type-check + production build) gate changes.
