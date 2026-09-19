---
type: operations-guide
title: digichat Operations
description: Running digichat — dev servers, Postgres and migrations, machine keys, env vars, container profile, GHCR releases, and Cloudflare Container deploy flow.
tags: [digichat, operations, postgres, docker, cloudflare]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-19T12:20:11.463Z
sources:
  - id: openwiki-source-87a93538e355aacdb4183b20
    resource: repo://.github/workflows/deploy-digichat-cloudflare-container.yml
  - id: openwiki-source-3f1945be9f72047e273c8d0c
    resource: repo://.github/workflows/publish-digichat-image.yml
  - id: openwiki-source-7f3dcdee3d51544bc00f3493
    resource: repo://cloudflare/digichat/.env.example
  - id: openwiki-source-8dca0467e4cf136f3d469654
    resource: repo://cloudflare/digichat/Dockerfile
  - id: openwiki-source-5b3953cf3c102a6e5817ea8d
    resource: repo://cloudflare/digichat/OPERATIONS.md
  - id: openwiki-source-08b0b37b07a09f29d44c5e7d
    resource: repo://cloudflare/digichat/scripts/create-api-key.ts
  - id: openwiki-source-7f01888a127960c25161489b
    resource: repo://cloudflare/digichat/scripts/trusted-proxy-server.mjs
  - id: openwiki-source-a975631680e2fb7a032c05bf
    resource: repo://cloudflare/digichat/src/app/api/health/route.ts
  - id: openwiki-source-3c104db66adbbb05823e0566
    resource: repo://cloudflare/digichat/src/instrumentation.ts
  - id: openwiki-source-3ca04759008a08b280b08d8d
    resource: repo://cloudflare/digichat/src/lib/api-key.ts
  - id: openwiki-source-151685e6f5bfcd5b1616ab71
    resource: repo://cloudflare/digichat/src/lib/migrate.ts
  - id: openwiki-source-7d9696696cdf644d92cc92fd
    resource: repo://Dockerfile.digichat-cloudflare
  - id: openwiki-source-fb5a4d608a92aff8b7143fa1
    resource: repo://infra/digichat-digithings/README.md
generated: { by: "openwiki/0.5.0", at: "2026-09-19T12:20:11.463Z" }
---

# digichat Operations

digichat runs three ways: **host dev server** for fast iteration, **Compose `digichat` profile** for local production-like deploys, and **Cloudflare Containers** for the live digithings.ai `/embed` widget. Postgres is optional in all modes — without it, threads live in `localStorage` and `GET /api/health` reports `database: skipped`.

## Local dev

Backends on the host (same ports as Compose: 8005 digikey, 8000–8003 services, optional 4000 LiteLLM):

```bash
make stack-local    # host Python stack
make digichat-dev   # Next.js dev server → http://127.0.0.1:3000
```

`make digichat-dev` runs `cd cloudflare/digichat && npm run dev`, which starts Next.js with hot reload on port 3000. You can also run it directly:

```bash
cd cloudflare/digichat
npm run dev
```

Or from the repo root:

```bash
npm --workspace cloudflare/digichat run dev
```

Minimum `cloudflare/digichat/.env.local` (copy from `.env.example`): `AUTH_SECRET` (+ matching `NEXTAUTH_SECRET`), `AUTH_URL`/`NEXTAUTH_URL` matching the browser origin (`http://127.0.0.1:3000`), `DIGIKEY_URL=http://127.0.0.1:8005` + identical `DIGIKEY_BFF_TOKEN`, the four `*_INTERNAL_URL`s, and `DIGICHAT_DEV_AUTH=1` for password login. Without the BFF token, chat returns `upstream_auth`.

Smoke-check the running dev server:

```bash
make digichat-health   # curl GET /api/health
```

## Postgres and migrations

Postgres is optional. Without `DIGICHAT_DATABASE_URL`, conversations persist in `localStorage` only and `/api/health` reports `database: skipped`.

```bash
make up-digichat-db    # starts postgres:16 on 127.0.0.1:5433, user/db digichat
```

Then, with `DIGICHAT_DATABASE_URL=postgresql://digichat:digichat@127.0.0.1:5433/digichat` in `.env.local`:

```bash
cd cloudflare/digichat
npm run db:migrate     # applies drizzle/ migrations
npm run db:seed        # creates 'default' tenant
npm run db:create-key -- default my-bot   # issue a machine API key
```

**Migrations** are additive Drizzle SQL files in `cloudflare/digichat/drizzle/`:

| Migration | Contents |
|-----------|----------|
| `0000_init.sql` | `tenants`, `api_keys`, `user_tenants` tables |
| `0001_conversations.sql` | `conversations` + `conversation_messages` tables |
| `0002_quant_runs.sql` | `quant_runs` table for digiclone backtest storage |

The Drizzle config (`cloudflare/digichat/drizzle.config.ts`) reads `schema.ts` and outputs to the `drizzle/` folder. Schema source: `src/db/schema.ts` (Drizzle ORM definitions for all five tables).

**Boot-time auto-migration** runs when `DIGICHAT_AUTO_MIGRATE=1`. The Next.js instrumentation hook (`src/instrumentation.ts`) calls `runMigrate()` from `src/lib/migrate.ts` before the server starts serving. Both the Compose profile and Cloudflare Container set this flag. The container image MUST ship the `drizzle/` folder — both Dockerfiles (`cloudflare/digichat/Dockerfile` and `Dockerfile.digichat-cloudflare`) copy it into the runner stage for this reason.

Migrations are additive — new columns are nullable or defaulted, and shipped files are never edited after release.

## Machine API keys

digichat machine keys use the `digi_live_` prefix and are **bcrypt-hashed** in the `api_keys` table (owner key `machine:<tenantSlug>`). They are distinct from digikey's `dgk_live_` keys, which are exchanged for short-lived upstream JWTs.

**Key creation** (`scripts/create-api-key.ts`):
- Generates `digi_live_` + 24 random base64url bytes
- Stores the first 20 chars as `key_prefix` (for lookup) and the full key as a bcrypt hash (cost 12)
- Prints the raw key exactly once — it cannot be recovered

**Key validation** (`src/lib/api-key.ts`):
- First checks `DIGICHAT_BOOTSTRAP_API_KEY` (env, timing-safe compare) — for CI/bootstrap
- Falls back to Postgres: looks up rows by `key_prefix`, then `bcrypt.compare` against each candidate hash
- Returns `{ tenantSlug }` on success, `null` otherwise

Machine clients authenticate with `Authorization: Bearer digi_live_…` on the chat API.

**Seeding and tenant mapping**: `npm run db:seed` creates the `default` tenant slug. Map OIDC users to tenants by inserting into `user_tenants` (`provider_account_id` → `tenant_id`).

## Key env vars

| Variable | Purpose |
|----------|---------|
| `AUTH_SECRET` | Auth.js session encryption (generate: `openssl rand -base64 32`) |
| `AUTH_URL` | Public origin (OAuth callback; must match browser) |
| `DIGIKEY_URL` | digikey base URL (`http://127.0.0.1:8005` for local) |
| `DIGIKEY_BFF_TOKEN` | Shared secret for `bff_session` JWT exchange |
| `DIGIGRAPH_INTERNAL_URL` | digigraph base URL (`http://127.0.0.1:8000`) |
| `DIGIQUANT_INTERNAL_URL` | digiquant base URL (`http://127.0.0.1:8001`) |
| `DIGISEARCH_INTERNAL_URL` | digisearch base URL (`http://127.0.0.1:8002`) |
| `DIGISMITH_INTERNAL_URL` | digismith base URL (`http://127.0.0.1:8003`) |
| `DIGICHAT_ENABLED_SERVICES` | Comma-separated capability list (default: all four verticals) |
| `DIGICHAT_DATABASE_URL` | Postgres connection string (optional; skips DB when unset) |
| `DIGICHAT_AUTO_MIGRATE` | `1` to run Drizzle migrations on boot |
| `DIGICHAT_DEV_AUTH` | `1` for dev password login (never in production) |
| `DIGICHAT_EMBED_HOSTS` | Comma-separated hosts for `/embed` CSP frame-ancestors |
| `DIGICHAT_EMBED_TENANTS` | JSON blob of tenant registry (runtime, never a build arg) |
| `DIGICHAT_TRUSTED_PROXIES` | Comma-separated IPs/CIDRs allowed to supply `X-Forwarded-For` |
| `DIGICHAT_VERSION` | Version string for `/api/health`; falls back to baked `/etc/digichat-version` |

For the full `.env` reference see `cloudflare/digichat/.env.example`.

## Container

### Local Compose profile (`digichat`)

From the repo root:

```bash
make up-digichat
# or: docker compose --profile digichat up -d --build
```

This starts `digichat-db` (Postgres 16 on `127.0.0.1:5433`) and the `digichat` BFF container on `127.0.0.1:3005` (override with `DIGICHAT_PUBLISH_HOST`/`DIGICHAT_PUBLISH_PORT`). Compose sets `DIGICHAT_AUTO_MIGRATE=1`.

### Dockerfile build

Both Dockerfiles — `cloudflare/digichat/Dockerfile` (GHCR self-host release) and `Dockerfile.digichat-cloudflare` (Cloudflare Containers) — share the same build strategy:

- **Build context**: repo root (needed for workspace lockfile + `@digithings/design` link)
- **Base**: `node:22-alpine`, multi-stage: `deps` → `builder` → `runner`
- **Runner**: non-root `nextjs` user (uid 1001), Next.js standalone output
- **CMD**: `node cloudflare/digichat/scripts/trusted-proxy-server.mjs`
- **Port**: 3000 (public), with internal Next.js on 3001

The `trusted-proxy-server.mjs` entrypoint:
1. Spawns Next.js standalone `server.js` on `127.0.0.1:3001`
2. Waits up to 30 s for Next.js to become ready
3. Listens on the public port (3000), forwarding requests to Next with `x-digichat-peer-ip` set to the TCP peer address
4. When `DIGICHAT_TRUSTED_PROXIES` is set, it acts as a proxy that captures the real peer IP; when unset, it lets Next.js listen directly on the public port

The container ships `drizzle/`, `config/`, and `public/` in the runner stage. Version is baked from `package.json` into `/etc/digichat-version`.

`/embed` frame-ancestors are resolved at **request time** from `DIGICHAT_EMBED_HOSTS` and `DIGICHAT_EMBED_TENANTS` host keys — never passed as Docker build args (tokens would leak into layer history).

### Cloudflare Containers deployment

The `Dockerfile.digichat-cloudflare` variant adds `DIGICHAT_ASSET_PREFIX="/_dtchat"` to avoid clashing with Cloudflare Pages `/_next` paths on digithings.ai. The deploy workflow (`.github/workflows/deploy-digichat-cloudflare-container.yml`) triggers on pushes to `main` that change `cloudflare/digichat/package.json` or the Container wrapper, plus manual `workflow_dispatch`. Secrets (`AUTH_SECRET`, `DIGICHAT_EMBED_TENANTS`, `DIGIGRAPH_INTERNAL_URL`, `DIGIKEY_URL`, `DIGIKEY_BFF_TOKEN`) are set via `wrangler secret put`.

## GHCR releases

digichat is installed from GHCR, not npm. The canonical image is `ghcr.io/digithings-ai/digichat:vX.Y.Z`.

**Versioning**: `release-please-config.json` tracks `cloudflare/digichat` with release-please watching the `develop` branch (not `main` — promotion squash commits lose Conventional Commit subjects). When `cloudflare/digichat/package.json` version bumps on `develop`, release-please proposes a version PR.

**Publish** (`.github/workflows/publish-digichat-image.yml`): on push to `main` when `cloudflare/digichat/**` changes, the workflow reads the current `package.json` version, checks if that tag already exists on GHCR (idempotent), and pushes `ghcr.io/digithings-ai/digichat:vX.Y.Z` + `:latest`.

**Release install**:

```bash
make digichat-release-up VERSION=2.2.0
# pulls ghcr.io/digithings-ai/digichat:v2.2.0 via infra/digichat-release/compose.digichat-release.yml
```

**Post-publish smoke**: see `docs/digichat/RELEASE-SMOKE.md`. Client install docs: `docs/digichat/INSTALL.md`. Profile A (GHCR pull) and Profile A bundle (one supervisord image matching CF Containers) workflows are documented in `infra/digichat-release/`.

## Health endpoint

`GET /api/health` (public, no auth) checks:
- Each enabled ecosystem service (`DIGICHAT_ENABLED_SERVICES`) with a 4-second timeout per probe
- Postgres `SELECT 1` (or `skipped` when `DIGICHAT_DATABASE_URL` is unset)
- Returns version from `DIGICHAT_VERSION` env, `/etc/digichat-version`, or `package.json`

Response shape: `{ ok: boolean, checks: { service, digraph, digiquant, digismith, digisearch?, database }, version }`. HTTP 200 when all enabled checks pass; 503 otherwise.

## Troubleshooting

- **`upstream_auth` / missing JWT**: `DIGIKEY_BFF_TOKEN` must match the running digikey process. Restart digichat after changing env.
- **`JWTSessionError` / decrypt mismatch**: browser holds a session cookie from an old `AUTH_SECRET`. Clear site cookies or use a private window. Set `NEXTAUTH_SECRET` to the same value as `AUTH_SECRET`.
- **Auth**: in Docker you must sign in at `/login` (or use machine `Authorization: Bearer …`). `DIGICHAT_DEV_AUTH=1` enables password login; never enable in production.
- **digigraph 422**: the BFF normalizes AI SDK `ModelMessage` payloads to plain `{ role, content }` for `POST /v1/chat/completions`. If a call still fails, the assistant bubble shows the upstream response body.
