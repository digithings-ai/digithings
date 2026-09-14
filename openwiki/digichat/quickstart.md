---
type: quickstart
title: digichat Quickstart
description: Run the digichat dev server against a local stack, verify chat, and run the frontend test gates.
tags: [digichat, quickstart, nextjs]
sources:
  - id: openwiki-source-e37135cc593e9175f6e913fb
    resource: repo://frontend/digichat/AGENTS.md
  - id: openwiki-source-8e3c7688ec1299cb0d4d2721
    resource: repo://frontend/digichat/ARCHITECTURE.md
  - id: openwiki-source-a5dd02cf7bd6166bce9a336e
    resource: repo://frontend/digichat/OPERATIONS.md
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
---

# digichat Quickstart

digichat is the chat UI (port 3005 in Compose, port 3000 on the host dev
server). The browser never holds upstream credentials — all digigraph and
digikey traffic stays in server Route Handlers — so a working setup always
pairs the UI with reachable backends.

## 1. Start backends and the UI

```bash
make stack-local     # host Python backends (8000–8003, 8005)
make digichat-dev    # http://127.0.0.1:3000
```

Copy `frontend/digichat/.env.example` to `.env.local` and set at minimum:
`AUTH_SECRET` (+ matching `NEXTAUTH_SECRET`), `AUTH_URL`/
`NEXTAUTH_URL` matching the browser origin, `DIGIKEY_URL` with the
identical `DIGIKEY_BFF_TOKEN`, the four `*_INTERNAL_URL`s, and
`DIGICHAT_DEV_AUTH=1` for password login.

## 2. Verify

Open `http://127.0.0.1:3000`, sign in via dev password, and send a chat
message. `GET /api/health` (the only public route) reports digigraph and
DB state. Missing BFF token surfaces as `upstream_auth` in chat.

## 3. Gates

From `frontend/digichat/`:

```bash
npm run test    # Vitest
npm run lint    # ESLint
npm run build   # type-check + production build
```

Optional Postgres history: `make up-digichat-db`, set
`DIGICHAT_DATABASE_URL`, then `npm run db:migrate`.

## Where next

- [digichat Architecture](/openwiki/digichat/architecture.md) — BFF,
  adapters, module map.
- [digichat Auth and Chat](/openwiki/digichat/auth-and-chat.md) — login,
  token exchange, streaming, regen/edit.
- [digichat Operations](/openwiki/digichat/operations.md) — Postgres,
  machine keys, env vars, container.
