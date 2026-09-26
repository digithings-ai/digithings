---
type: operations-guide
title: digichat Operations
description: Running digichat 2.0 — local dev with make digichat-dev, Postgres provisioning and Drizzle migrations (auto-migrate), machine API key creation, container build (multi-stage Node 22, standalone output, trusted-proxy-server.mjs), embed host resolution, health endpoint, and key env vars for 2.0.
tags: [digichat, operations, postgres, docker]
sources:
  - id: openwiki-source-97bb67e20dc2eb34fa13391f
    resource: repo://apps/digichat/Dockerfile
  - id: openwiki-source-a3b079ac868406f19c75e166
    resource: repo://apps/digichat/OPERATIONS.md
  - id: openwiki-source-53cb5f509f97fd60c467a6dc
    resource: repo://apps/digichat/scripts/create-api-key.ts
  - id: openwiki-source-a6ef895cabf2c48ed7a1d3b1
    resource: repo://apps/digichat/src/instrumentation.ts
  - id: openwiki-source-f3278b5f2d67ac33416ca013
    resource: repo://apps/digichat/src/lib/api-key.ts
  - id: openwiki-source-243050441e516f20ef05c90a
    resource: repo://apps/digichat/src/lib/migrate.ts
  - id: openwiki-source-28ab975c76b4ebc9e1ba2df4
    resource: repo://apps/digichat/src/lib/request-auth.ts
  - id: openwiki-source-6eac5a0a2f17403dc7be2e4e
    resource: repo://apps/digichat/src/lib/security-headers.ts
  - id: openwiki-source-9905da197df2ad533543ef5a
    resource: repo://apps/digichat/src/proxy.ts
generated: { by: "openwiki/0.5.0", at: "2026-09-23T13:25:31.068Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-26T12:43:34.078Z
---

# digichat Operations

digichat runs two ways: the host Next.js dev server for fast iteration, and the
Compose `digichat` profile for production-like deploys. Postgres is optional in
both — without it, threads live in localStorage and `/api/health` reports
`database: skipped`.

## Container startup flow

```mermaid
sequenceDiagram
    participant Compose as Docker Compose
    participant Proxy as trusted-proxy-server.mjs
    participant Next as Next.js server.js (standalone, :3001)
    participant Instr as instrumentation.ts
    participant DB as Postgres (optional)
    participant Health as /api/health

    Compose->>Proxy: start node apps/digichat/scripts/trusted-proxy-server.mjs
    Proxy->>Proxy: resolveDigichatVersion() from env or /etc/digichat-version
    opt DIGICHAT_TRUSTED_PROXIES set
        Proxy->>Next: spawn on 127.0.0.1:3001, forward with x-digichat-peer-ip
    end
    Proxy->>Next: spawn (or listen directly if no trusted proxies)
    Proxy->>Next: waitForNext() — TCP connect retry up to 30 s
    Next->>Instr: register() — NEXT_RUNTIME=nodejs
    Instr->>Instr: initDigichatConfigAtStartup() — validates digichat.yaml / DIGICHAT_EMBED_TENANTS
    opt DIGICHAT_AUTO_MIGRATE=1
        Instr->>DB: runMigrate() — applies drizzle/ migrations
    end
    Proxy->>Proxy: listen on PORT (default 3000)
    Health->>Next: GET /api/health probes digigraph + DB
```

The CMD is `node apps/digichat/scripts/trusted-proxy-server.mjs`. When
`DIGICHAT_TRUSTED_PROXIES` is set, the proxy spawns Next.js on an internal port
(3001) and forwards requests with a synthetic `x-digichat-peer-ip` header
derived from `socket.remoteAddress`; without it, Next.js listens directly on the
public port. In either mode the proxy waits up to 30 seconds for the Next server
to become ready.

## Local dev

Backends on the host (same ports as Compose: 8005 digikey, 8000–8003 services,
optional 4000 LiteLLM):

```bash
make stack-local # host Python stack
make digichat-dev # Next.js dev server → http://127.0.0.1:3000
```

Minimum `apps/digichat/.env.local`: `AUTH_SECRET` (+ matching `NEXTAUTH_SECRET`),
`AUTH_URL`/`NEXTAUTH_URL` matching the browser origin, `DIGIKEY_URL` +
identical `DIGIKEY_BFF_TOKEN`, the four `*_INTERNAL_URL`s, and
`DIGICHAT_DEV_AUTH=1` for password login. Without the BFF token, chat returns
`upstream_auth`.

`DIGICHAT_LOCAL_AUTH_KEY` (any random secret) performs a real Auth.js credentials
sign-in on first visit via `src/app/actions/local-bootstrap.ts`, producing a
normal encrypted session cookie so you skip `/login` entirely. The provider is
not registered when `NODE_ENV=production`.

## Postgres and migrations

`make up-digichat-db` starts local Postgres
(`postgresql://digichat:digichat@127.0.0.1:5433/digichat`); then
`npm run db:migrate` applies the `drizzle/` folder:

| Migration | Contents |
|---|---|
| `0000_init.sql` | `tenants`, `api_keys`, `user_tenants` (core schema) |
| `0001_conversations.sql` | `conversations`, `conversation_messages` |
| `0002_quant_runs.sql` | `quant_runs` (persisted backtest comparisons) |

Migrations are additive — new columns nullable or defaulted, never edits to
shipped files. `drizzle.config.ts` reads the schema from
`src/db/schema.ts` and outputs SQL to `./drizzle`.

Boot-time auto-migration runs when `DIGICHAT_AUTO_MIGRATE=1` (Compose sets it).
`src/instrumentation.ts` calls `runMigrate()` from `src/lib/migrate.ts`, which
resolves `process.cwd()/drizzle` and applies pending migrations via
`drizzle-orm/postgres-js/migrator`. The image ships the `drizzle/` folder for
this reason (Dockerfile line 51: `COPY … drizzle ./apps/digichat/drizzle`).

After first boot with Postgres:

```bash
cd apps/digichat && DIGICHAT_DATABASE_URL=postgresql://digichat:digichat@127.0.0.1:5433/digichat npm run db:seed
npm run db:create-key -- default automation
```

Seed creates the `default` tenant slug. Map OIDC users to tenants by inserting
into `user_tenants` (`provider_account_id`, `tenant_id`).

## Machine API keys

Machine `digi_live_…` keys are bcrypt-hashed (cost 12) in the `api_keys` table
(`src/lib/api-key.ts`). The key prefix (first 20 characters) is stored in
`key_prefix` for lookup; the full key is hashed in `key_hash`. Validation
compares with `timingSafeEqual` to avoid timing attacks.

These are distinct from digikey's `dgk_live_…` keys, which authenticate against
digikey's `POST /v1/oauth/token` for upstream JWT exchange. digichat machine
keys authenticate directly at the BFF layer. After authentication, conversations
are owned under `machine:<tenantSlug>` (`src/lib/request-auth.ts`).

Create keys after seeding:

```bash
DIGICHAT_DATABASE_URL=… npx tsx scripts/create-api-key.ts [tenantSlug] [label]
```

A bootstrap key can also be set via `DIGICHAT_BOOTSTRAP_API_KEY` (plaintext,
checked with constant-time comparison) for CI/local without Postgres.

## Key env vars

### Core

| Variable | Purpose |
|---|---|
| `AUTH_SECRET` | Auth.js session encryption |
| `AUTH_URL` | Public origin of digichat (OAuth callback) |
| `DIGIKEY_URL` | digikey base URL for JWT exchange |
| `DIGIKEY_BFF_TOKEN` | Shared secret for `grant_type=bff_session` |
| `DIGIGRAPH_INTERNAL_URL` | digigraph base URL |
| `DIGIQUANT_INTERNAL_URL` | digiquant base URL |
| `DIGISMITH_INTERNAL_URL` | digismith base URL |
| `DIGISEARCH_INTERNAL_URL` | digisearch base URL |
| `DIGICHAT_DATABASE_URL` | Postgres connection (optional) |
| `DIGICHAT_AUTO_MIGRATE` | Auto-apply Drizzle migrations on boot (`=1`) |

### Federated hub

| Variable | Purpose |
|---|---|
| `DIGICHAT_ENABLED_SERVICES` | Comma-separated capability list (default: all four: `digigraph,digisearch,digiquant,digismith`) |

### Embed / tenant

| Variable | Purpose |
|---|---|
| `DIGICHAT_EMBED_HOSTS` | Comma-separated hostnames for `/embed` CSP `frame-ancestors` (runtime, no rebuild needed) |
| `DIGICHAT_EMBED_TENANTS` | JSON map of hostname → tenant config (backend, gate, skin, token); feeds CSP + tenant registry |
| `DIGICHAT_CONFIG_PATH` | Path to `digichat.yaml` deployment config (default: `/app/config/digichat.yaml`) |
| `DIGICHAT_LEGACY_EMBED_ENABLED` | Legacy generic embed for unregistered hosts only |

### Dashboard plan proof (#3662)

| Variable | Purpose |
|---|---|
| `DIGICHAT_PLAN_PROOF_SECRET` | HMAC secret for signing `X-Embed-Plan-Proof` tokens (server-only) |
| `DIGICHAT_DASHBOARD_SUPABASE_URL` | digiquant Supabase project URL for `/auth/v1/user` verification |
| `DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY` | Supabase anon key for dashboard access token verification |

The plan proof flow: the dashboard iframe posts a Supabase `access_token` to
digichat's `POST /api/plan-proof`. Digichat verifies the embed tenant (must be
`digiquant-dashboard`), calls Supabase `/auth/v1/user` to read
`app_metadata.plan_tier`, falls back to the effective tier via the `my_access`
RPC, and mints an HMAC-signed token (5-minute TTL) only for Desk+ tiers. Free
and brief plans receive `403 plan_tier_required`. The chat route verifies the
signature server-side — client-asserted tier headers are never trusted.

### Dev-only

| Variable | Purpose |
|---|---|
| `DIGICHAT_DEV_AUTH` | Enable password login (never in production) |
| `DIGICHAT_DEV_PASSWORD` | Dev password (default: `dev`) |
| `DIGICHAT_LOCAL_AUTH_KEY` | Auto-sign-in with real Auth.js session on first visit |

## Container

Multi-stage Node 22 build from the repo root (workspace lockfile +
`@digithings/design` link required for the `deps` stage `npm ci`), standalone
output run as non-root `nextjs` via `trusted-proxy-server.mjs` on port 3000.

Three build stages:

1. **deps** — copies workspace `package.json` files, runs `npm ci --workspace apps/digichat --include-workspace-root`
2. **builder** — copies full source, runs `npm run build --workspace apps/digichat`, bakes `DIGICHAT_VERSION` into `/tmp/digichat-version`
3. **runner** — copies standalone output, static assets, `drizzle/`, `trusted-proxy-server.mjs`, and `config/`; runs as `nextjs` (uid 1001)

`/embed` frame-ancestors resolve at request time from `DIGICHAT_EMBED_HOSTS` /
`DIGICHAT_EMBED_TENANTS` host keys — never as build args. The Next 16 proxy
(`src/proxy.ts`) overwrites the fail-closed CSP baked by `next.config.ts` on
every `/embed` request, re-reading `process.env` each call so stock GHCR images
admit new parents without rebuild.

### Embed host resolution

`embedFrameAncestorsCsp()` in `src/lib/security-headers.ts`:
- Prefers `DIGICHAT_EMBED_HOSTS` when set (even empty)
- Falls back to `DIGICHAT_EMBED_TENANTS` registry keys when unset
- Always includes first-party origins (`digithings.ai`, `www.digithings.ai`, `digiquant.io`)
- Adds `http://localhost:*` / `http://127.0.0.1:*` in non-production or when `DIGICHAT_ALLOW_LOCAL_EMBED_PARENTS=1`
- Never emits bare `*` or wildcard host tokens

## Health endpoint

`GET /api/health` is the only public route. It probes:

- **digigraph** — `GET {digigraphUrl}/health` (4 s timeout), gated by `DIGICHAT_ENABLED_SERVICES`
- **digiquant** — same pattern
- **digismith** — same pattern
- **digisearch** — probed only when `digisearchUrl` is set
- **database** — `SELECT 1` when `DIGICHAT_DATABASE_URL` is configured; `skipped` otherwise

Returns `200` with `{"ok": true, …}` when all enabled services respond and the
database is ok or skipped. Returns `503` if any enabled service is unreachable
or the database errors. The `version` field reads `DIGICHAT_VERSION` env, then
`/etc/digichat-version` (baked at build), then `package.json`.

## Release artifacts

Releases install from GHCR (`ghcr.io/digithings-ai/digichat:vX.Y.Z`), not npm.
Tags are cut by release-please on `develop`; a human-pushed `digichat-vX.Y.Z`
tag publishes the image via `publish-digichat-image.yml`.

Local Compose builds from the monorepo (`make up-digichat`). To pull a pinned
GHCR release:

```bash
make digichat-release-up VERSION=2.3.2
```

## Troubleshooting

- **`upstream_auth` / missing JWT:** `DIGIKEY_BFF_TOKEN` must match the secret
  on the digikey process. Restart digichat after changing env. Alternatives:
  `Authorization: Bearer dgk_live_…`, or `DIGIGRAPH_UPSTREAM_API_KEY`.
- **Auth.js `JWTSessionError`:** Browser has a session cookie from an older
  `AUTH_SECRET`. Clear site cookies or use a private window. Set
  `NEXTAUTH_SECRET` to the same value as `AUTH_SECRET`.
- **`make digichat-dev` fails:** Ensure `apps/digichat/.env.local` exists and
  `npm install` has been run in `apps/digichat/`.
- Never enable `DIGICHAT_DEV_AUTH` in production.
- Do not expose digigraph to the public internet; route users through digichat.
