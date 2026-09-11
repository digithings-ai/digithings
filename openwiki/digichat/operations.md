---
type: operations-guide
title: digichat Operations
description: Running digichat — dev servers, Postgres and migrations, machine keys, env vars, and the container profile.
tags: [digichat, operations, postgres, docker]
sources:
  - id: openwiki-source-2d4214cece07b9121a74928c
    resource: repo://frontend/digichat/Dockerfile
  - id: openwiki-source-a5dd02cf7bd6166bce9a336e
    resource: repo://frontend/digichat/OPERATIONS.md
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
---

# digichat Operations

digichat runs two ways: host dev server for iteration, container under the
Compose `digichat` profile for production-like deploys. Postgres is
optional in both — without it, threads live in localStorage and
`/api/health` reports `database: skipped`.

## Local dev

Backends on the host (same ports as Compose: 8005 digikey, 8000–8003
services, optional 4000 LiteLLM):

```bash
make stack-local          # host Python stack
make digichat-dev         # Next.js dev server → http://127.0.0.1:3000
```

Minimum `frontend/digichat/.env.local`: `AUTH_SECRET` (+ matching
`NEXTAUTH_SECRET`), `AUTH_URL`/`NEXTAUTH_URL` matching the browser origin,
`DIGIKEY_URL` + identical `DIGIKEY_BFF_TOKEN`, the four
`*_INTERNAL_URL`s, and `DIGICHAT_DEV_AUTH=1` for password login. Without
the BFF token, chat returns `upstream_auth`.

## Postgres and migrations

`make up-digichat-db` starts local Postgres
(`postgresql://digichat:digichat@127.0.0.1:5433/digichat`); then
`npm run db:migrate` applies `drizzle/` (`0001_conversations.sql`,
`0002_quant_runs.sql`). Migrations are additive — new columns nullable or
defaulted, never edits to shipped files. Boot-time auto-migration runs
when `DIGICHAT_AUTO_MIGRATE=1` (Compose sets it; the image ships
`drizzle/` for that reason). Machine `digi_live_…` keys live hashed in
Postgres under owner key `machine:<tenantSlug>` (created via
`npm run db:create-key`); digikey's separate `dgk_live_…` keys feed the
upstream exchange.

## Key env vars

`AUTH_SECRET`, `DIGIKEY_URL`, `DIGIKEY_BFF_TOKEN`,
`DIGIGRAPH_INTERNAL_URL`, `DIGIQUANT_INTERNAL_URL`,
`DIGISEARCH_INTERNAL_URL`, `DIGISMITH_INTERNAL_URL`,
`DIGICHAT_DATABASE_URL`, `DIGICHAT_ENABLED_SERVICES` (federated-hub
capability list, default all four verticals), `DIGICHAT_DEV_AUTH`,
`DIGICHAT_AUTO_MIGRATE=1`. Release installs come from GHCR, not npm.

## Container

Multi-stage Node 22 build from the repo root (workspace lockfile +
`@digithings/design` link required), standalone output run as
non-root `nextjs` via `trusted-proxy-server.mjs` on port 3000. `/embed`
frame-ancestors resolve at request time from `DIGICHAT_EMBED_HOSTS` /
tenant keys — never as build args. `GET /api/health` (the only public
route) checks digigraph + DB.
