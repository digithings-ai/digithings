---
type: quickstart
title: digichat Quickstart
description: Run the digichat 2.0 dev server against a local stack, verify chat, run the Vitest/ESLint/type-check gates, and optionally persist history to Postgres.
tags: [digichat, quickstart, nextjs, dev-server]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-23T13:25:31.068Z
sources:
  - id: openwiki-source-94be7dc18ad64ed2d1bb5a18
    resource: repo://apps/digichat/AGENTS.md
  - id: openwiki-source-a78895b22779966e9333b39a
    resource: repo://apps/digichat/ARCHITECTURE.md
  - id: openwiki-source-a3b079ac868406f19c75e166
    resource: repo://apps/digichat/OPERATIONS.md
  - id: openwiki-source-bdb8729d14409eb59142ae39
    resource: repo://apps/digichat/package.json
  - id: openwiki-source-c446e66cf357ccbb766d508c
    resource: repo://apps/digichat/scripts/check-config.ts
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
generated: { by: "openwiki/0.5.0", at: "2026-09-23T13:25:31.068Z" }
---

# digichat Quickstart

digichat is the user-facing chat UI for the digithings ecosystem: a Next.js 16
App Router application acting as a **Backend-for-Frontend (BFF)**. The browser
never holds upstream credentials — all LLM calls, auth token exchanges, and
upstream probes run in server Route Handlers — so a working setup always pairs
the UI with reachable backends.

## 1. Start backends and the UI

Run the host Python backends and the Next.js dev server from the repo root:

```bash
make stack-local   # host Python backends: digikey 8005, services 8000–8003
make digichat-dev  # Next.js dev server → http://127.0.0.1:3000
```

`make stack-local` runs digikey (8005) plus digigraph, digiquant, digisearch,
and digismith (8000–8003) directly on the host, no Docker. `make digichat-dev`
runs `npm run dev` from `apps/digichat/` with hot reload on port 3000.

## 2. Configure `.env.local`

Copy `apps/digichat/.env.example` to `.env.local` and set at minimum:

- `AUTH_SECRET` — set `NEXTAUTH_SECRET` to the same value to avoid decrypt
  errors.
- `AUTH_URL` / `NEXTAUTH_URL` — must match the origin you open in the browser
  (`http://127.0.0.1:3000`; don't mix `localhost` and `127.0.0.1` for cookies).
- `DIGIKEY_URL=http://127.0.0.1:8005` and `DIGIKEY_BFF_TOKEN` — identical to the
  token on the running digikey process. Without this, chat returns
  `upstream_auth`.
- `DIGIGRAPH_INTERNAL_URL=http://127.0.0.1:8000`,
  `DIGIQUANT_INTERNAL_URL=http://127.0.0.1:8001`,
  `DIGISMITH_INTERNAL_URL=http://127.0.0.1:8003`,
  `DIGISEARCH_INTERNAL_URL=http://127.0.0.1:8002`.
- `DIGICHAT_DEV_AUTH=1` and `DIGICHAT_DEV_PASSWORD` (e.g. `dev`) for password
  login at `/login`.

## 3. Check the deployment config

Validate the deployment config and print what it resolves to. This fails loudly
on a missing file, invalid YAML/JSON, or a schema violation (the container would
otherwise silently fall back to the built-in dev default):

```bash
cd apps/digichat
npm run config:check          # tsx scripts/check-config.ts
# or from the repo root:
make digichat-config-check CONFIG=infra/digichat-release/config/digichat.yaml
```

## 4. Verify

Open `http://127.0.0.1:3000`, sign in via the dev password, and send a chat
message. `GET /api/health` (the only public route) reports digigraph and DB
state. A missing BFF token surfaces as `upstream_auth` in chat.

## 5. Gates

From `apps/digichat/`:

```bash
npm run test  # Vitest unit tests
npm run lint  # ESLint
npm run build # type-check + production build
```

## 6. Optional Postgres history

Without `DIGICHAT_DATABASE_URL`, `/api/health` reports `database: skipped` and
threads live in `localStorage` only. To persist chat history to Postgres:

```bash
make up-digichat-db   # Postgres 16 on host port 5433
```

Then set `DIGICHAT_DATABASE_URL=postgresql://digichat:digichat@127.0.0.1:5433/digichat`
in `.env.local`, run `cd apps/digichat && npm run db:migrate`, and restart
digichat.

## Where next

- [digichat Architecture](/openwiki/digichat/architecture.md) — BFF, adapters,
  module map.
- [digichat Auth and Chat](/openwiki/digichat/auth-and-chat.md) — login, token
  exchange, streaming, regen/edit.
- [digichat Operations](/openwiki/digichat/operations.md) — Postgres, machine
  keys, env vars, container.
