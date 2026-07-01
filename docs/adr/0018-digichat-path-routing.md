# ADR 0018 — DigiChat served at `digithings.ai/chat` (path), not a separate `chat.` deploy

Status: Accepted · Supersedes the `chat.digithings.ai` subdomain decision in [ADR-0002](0002-domain-unification.md)

## Context

ADR-0002 planned DigiChat as `chat.digithings.ai` — a separate production deployment target. In practice this reads as "DigiChat has its own pipeline / its own site," which is not desired: DigiChat should be part of the digithings.ai surface, reachable at **`digithings.ai/chat`**, with a single web presence.

DigiChat is, however, a **stateful Next.js standalone server** (`output: "standalone"`, a Dockerfile running `node server.js`): NextAuth sessions, a Postgres/Drizzle database, streaming LLM responses through its BFF, and an `/embed` route. It therefore **cannot** be a static page under the Cloudflare-Pages static digithings.ai — it needs a server runtime.

## Decision

Serve DigiChat under the path **`digithings.ai/chat`** via a Cloudflare route to the DigiChat container, rather than a `chat.` subdomain:

- digithings.ai stays a static Cloudflare Pages site (`frontend/digithings-web`); a Cloudflare route forwards `digithings.ai/chat/*` to the DigiChat container origin.
- DigiChat runs as the existing container/service in the monorepo stack (`make up-digichat`) — **not** a separate website pipeline or domain.
- DigiChat gains an **env-gated `basePath`** so it serves correctly under the subpath:
  - `next.config.ts` → `basePath: process.env.DIGICHAT_BASE_PATH || undefined`.
  - `src/lib/base-path.ts` exposes `BASE_PATH`/`p()`; raw `fetch("/api/...")`, NextAuth `SessionProvider basePath`, and `signIn`/`signOut`/`window.location` callbacks are prefixed (Next `<Link>`/router and server `redirect()` apply basePath automatically — verified).
  - Unset env → root (self-host, local dev, and the legacy deploy are unchanged: zero regression).

## Production configuration (Cloudflare + env)

- Cloudflare route: `digithings.ai/chat/*` → DigiChat container origin.
- DigiChat build/runtime env for that deploy: `DIGICHAT_BASE_PATH=/chat`, `NEXT_PUBLIC_DIGICHAT_BASE_PATH=/chat`, `AUTH_URL=https://digithings.ai/chat`.
- The marketing site's "Try Chat" link points at `/chat`.

## Consequences

- One domain, one website pipeline; DigiChat is a service behind a path, not a second site.
- DigiChat still requires a server host for its container (inherent to an auth + DB + streaming app) — this is a stack service, not a separate product deploy.
- Verified: with `basePath=/chat`, `GET /chat` → 307 `/chat/login`, `/chat/login` → 200, `/login` → 404; default build stays at root.
