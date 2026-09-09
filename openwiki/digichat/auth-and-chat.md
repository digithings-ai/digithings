---
type: behavior-guide
title: digichat Auth and Chat
description: digichat login, digikey token exchange, streaming chat route with regen/edit, and conversation persistence.
tags: [digichat, auth, chat, bff]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-89092abbe1894e77dc33d695
    resource: repo://digikey/ARCHITECTURE.md
  - id: openwiki-source-8e3c7688ec1299cb0d4d2721
    resource: repo://frontend/digichat/ARCHITECTURE.md
  - id: openwiki-source-7c075b60bdd1f2699392afa6
    resource: repo://frontend/digichat/src/app/api/chat/route.ts
  - id: openwiki-source-bd578238e83e5e4c284f525e
    resource: repo://frontend/digichat/src/auth.ts
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digichat Auth and Chat

Every digichat interaction is a server-side flow: the browser holds an
Auth.js session cookie, the BFF exchanges it for short-lived upstream
credentials, and the chat route streams model output back. Upstream JWTs
never cross into the browser.

## Login

`src/auth.ts` configures Auth.js v5 with three providers, each gated by
environment:

- **OIDC** (`AUTH_OIDC_ISSUER/CLIENT_ID/CLIENT_SECRET`) — enterprise SSO
  with `openid email profile` scope.
- **Dev password** (`DIGICHAT_DEV_AUTH=1`, password in
  `DIGICHAT_DEV_PASSWORD` defaulting to `dev`) — local development only.
- **Local bootstrap** (`DIGICHAT_LOCAL_AUTH_KEY`) — dev-only, disabled when
  `NODE_ENV=production`.

The session cookie secret comes from `AUTH_SECRET` / `NEXTAUTH_SECRET` and
must stay stable or users clear cookies.

## Upstream exchange

The BFF presents `DIGIKEY_BFF_TOKEN` to digikey's `bff_session` grant and
receives a short-lived JWT (`principal_kind=bff_session`,
`sub=bff:<subject>`, with `profile_id`/`profile_version` when a profile
pointer exists). Per-request upstream auth resolves server-side
(`resolveDigigraphUpstreamAuth`); BYOK keys travel in `extra_body`/headers
the browser never sees. `POST /api/chat` also enforces a BFF rate limit
(`429 rate_limit_exceeded` with `retry-after`) and a per-session run lock.

## Chat route

`POST /api/chat` (`maxDuration = 120`) streams via the AI SDK (`streamText`
+ `smoothStream`), fanning out to the digigraph or Foundry streaming
adapter by tenant. Turn modes arrive in `X-Digi-Turn-Mode`
(`send | regenerate | edit_last_user`, optional `X-Digi-Run-Id`):
regeneration replays the workflow from the truncated transcript, concurrent
runs on one session return `409 run_in_progress`, and duplicate run IDs
return `409 run_id_replay`. Embed surfaces add IP rate limiting and trial
turn quotas.

## Persistence

Threads persist to localStorage always-on, merged on mount with server
`GET /api/conversations`; Postgres persistence (Drizzle `src/db/schema.ts`)
is optional, including the `quant_runs` table for backtest comparisons
parsed inline from `BacktestResult` payloads. Turn/thread markdown export
goes through the shared serializer with clipboard-first, download fallback.
