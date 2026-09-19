---
type: "Reference"
title: "digichat Quickstart"
openwiki_generated: true
generated: { by: "openwiki/0.5.0", at: "2026-09-19T12:20:11.463Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-19T12:20:11.463Z
---


# digichat Quickstart

digichat is the chat UI (port 3005 in Compose, port 3000 on the host dev
server). The browser never holds upstream credentials — all digigraph and
digikey traffic stays in server Route Handlers — so a working setup always
pairs the UI with reachable backends.

## 1. Start backends and the UI

```bash
make stack-local           # host Python backends (8000–8003, 8005)
make digichat-dev          # http://127.0.0.1:3000 (Next.js hot reload)
```

Alternatively, start the dev server with the npm workspace from the monorepo
root (backends must already be running):

```bash
npm --workspace cloudflare/digichat run dev
```

Copy `cloudflare/digichat/.env.example` to `.env.local` and set at minimum:
`AUTH_SECRET` (+ matching `NEXTAUTH_SECRET`), `AUTH_URL`/
`NEXTAUTH_URL` matching the browser origin (`http://127.0.0.1:3000`),
`DIGIKEY_URL` with the identical `DIGIKEY_BFF_TOKEN`, the four
`*_INTERNAL_URL`s, and `DIGICHAT_DEV_AUTH=1` for password login.

## 2. Verify

Open `http://127.0.0.1:3000`, sign in via dev password (`DIGICHAT_DEV_PASSWORD`,
default `dev`), and send a chat message. `GET /api/health` (the only public
route) reports digigraph and DB state:

```bash
curl -s http://127.0.0.1:3000/api/health | python3 -m json.tool
```

The repo root provides `make digichat-health` as a shorthand for the same
health smoke. Missing BFF token surfaces as `upstream_auth` in chat.

## 3. Gates

From `cloudflare/digichat/`:

```bash
npm run test   # Vitest
npm run lint   # ESLint
npm run build  # type-check + production build
```

Optional Postgres history: `make up-digichat-db`, set
`DIGICHAT_DATABASE_URL=postgresql://digichat:digichat@127.0.0.1:5433/digichat`,
then `npm run db:migrate`.

## Where next

- [digichat Architecture](/openwiki/digichat/architecture.md) — BFF,
  adapters, module map.
- [digichat Auth and Chat](/openwiki/digichat/auth-and-chat.md) — login,
  token exchange, streaming, regen/edit.
- [digichat Operations](/openwiki/digichat/operations.md) — Postgres,
  machine keys, env vars, container.
