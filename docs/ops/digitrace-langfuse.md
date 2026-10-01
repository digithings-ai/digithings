# digitrace Langfuse (Phase 1) — operator runbook

Stand-up self-hosted **Langfuse** for digitrace on Cloudflare Containers
([#4930](https://github.com/digithings-ai/digithings/issues/4930)).

App package: [`apps/digitrace-langfuse/`](../../apps/digitrace-langfuse/).  
Lab memo: [`docs/plans/digitrace-langfuse-swap-2026-10-01.md`](../plans/digitrace-langfuse-swap-2026-10-01.md).

**Status:** code/config landed in-repo. Live deploy, secret values, R2 create,
ClickHouse/Redis provision, custom domain, and UI+OTLP smoke are **human /
Platform** follow-ups.

## Architecture (Phase 1)

| Piece | Where | Notes |
|-------|--------|------|
| Langfuse Web | CF Container (`LangfuseWebContainer`) | UI + API + OTLP `:3000`; image `langfuse/langfuse:4.49.0` |
| Langfuse Worker | CF Container (`LangfuseWorkerContainer`) | Queues `:3030`; image `langfuse/langfuse-worker:4.49.0` |
| Edge Worker | `digitrace-langfuse` | Proxies to Web; `/_langfuse/healthz`, `/_langfuse/worker-wake` |
| Postgres | House Postgres, **dedicated database** (e.g. `langfuse`) | `DATABASE_URL` via `wrangler secret put` |
| Event blobs | R2 bucket `digitrace-langfuse-events` | `LANGFUSE_S3_EVENT_UPLOAD_*` (S3 API). Binding `LANGFUSE_EVENTS` is reserved; uploads do not use the Worker R2 API |
| ClickHouse | **External** managed or VM | **Not** a lite CF Container. Floor ≈ **2 CPU / 8 GiB** |
| Redis | **External** managed or VM | Queues + cache |

Phase 0 digitrace still uses the LangSmith SDK until Phase 2 dual-export. Do not
claim dual-export works yet. Do **not** set `LANGSMITH_ENDPOINT` to Langfuse.

## Recommended managed providers (guidance)

Pick any managed offering that meets the floor; document the choice in the
deploy ticket (do not invent credentials here).

| Service | Guidance |
|---------|----------|
| ClickHouse | ClickHouse Cloud, Altinity, or a VM ≥ 2 vCPU / 8 GiB RAM. Set `CLICKHOUSE_CLUSTER_ENABLED=false` for single-node. |
| Redis | Upstash, Redis Cloud, or a small managed Redis 7. Prefer `REDIS_CONNECTION_STRING`. |

Local laptop only: [`apps/digitrace-langfuse/docker-compose.local.yml`](../../apps/digitrace-langfuse/docker-compose.local.yml)
(CH + Redis). Labelled **local-dev**, not production.

## Hostname (HUMAN GATE)

Preferred: **`trace.digithings.ai`**. Alternate: `langfuse.digithings.ai`.

1. Platform creates DNS / custom domain.
2. Uncomment the `[[routes]]` block in `apps/digitrace-langfuse/wrangler.toml`.
3. Set secret `NEXTAUTH_URL` to `https://trace.digithings.ai` (exact public origin).

## Postgres

**Choice:** reuse **house Postgres** with a **dedicated database** (recommended
name `langfuse`). Do not share tables with digikey / checkpointer DBs.

```sql
-- Run as a Postgres admin (value never committed):
CREATE DATABASE langfuse;
```

Point `DATABASE_URL` at that database (role with DDL for first-boot migrations).

### Schema / migrations

Langfuse Web applies Postgres migrations on startup by default. Prefer first-boot
auto-migrate on a fresh DB. To disable later: `LANGFUSE_AUTO_POSTGRES_MIGRATION_DISABLED=true`
(only after migrations are known-applied). ClickHouse migrations use
`CLICKHOUSE_MIGRATION_URL` (TCP) on first boot; keep
`LANGFUSE_AUTO_CLICKHOUSE_MIGRATION_DISABLED` unset until stable.

## R2 event bucket

1. Create bucket **`digitrace-langfuse-events`** in the digithings Cloudflare account.
2. Create an R2 S3 API token with Object Read/Write on that bucket.
3. Endpoint shape (account id is not a secret class, but do not commit tokens):

   `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`

4. Secret-put the `LANGFUSE_S3_EVENT_UPLOAD_*` keys listed below.
5. `[vars]` already set bucket name, `auto` region, path-style `true`, prefix `events/`.

## Secret put checklist

From `apps/digitrace-langfuse/` (values never echoed / never committed):

```bash
cd apps/digitrace-langfuse

# Core
npx wrangler secret put DATABASE_URL
npx wrangler secret put NEXTAUTH_SECRET          # openssl rand -base64 32
npx wrangler secret put NEXTAUTH_URL             # https://trace.digithings.ai
npx wrangler secret put SALT                     # openssl rand -base64 32
npx wrangler secret put ENCRYPTION_KEY           # openssl rand -hex 32

# ClickHouse (external)
npx wrangler secret put CLICKHOUSE_URL           # https://…:8443 or http://…:8123
npx wrangler secret put CLICKHOUSE_MIGRATION_URL # clickhouse://…:9440 or :9000
npx wrangler secret put CLICKHOUSE_USER
npx wrangler secret put CLICKHOUSE_PASSWORD
# optional: CLICKHOUSE_DB

# Redis (external)
npx wrangler secret put REDIS_CONNECTION_STRING
# or: REDIS_HOST / REDIS_PORT / REDIS_AUTH

# R2 S3 event upload
npx wrangler secret put LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT
npx wrangler secret put LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID
npx wrangler secret put LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY
```

Plain `[vars]` (non-secret) live in `wrangler.toml`:
`CLICKHOUSE_CLUSTER_ENABLED`, `LANGFUSE_S3_EVENT_UPLOAD_BUCKET`,
`LANGFUSE_S3_EVENT_UPLOAD_REGION`, `LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE`,
`LANGFUSE_S3_EVENT_UPLOAD_PREFIX`.

Confirm names only:

```bash
npx wrangler secret list
```

## Deploy

```bash
cd apps/digitrace-langfuse
npm install
npx wrangler deploy
curl -sS "https://trace.digithings.ai/_langfuse/healthz"
curl -sS "https://trace.digithings.ai/_langfuse/worker-wake"
```

## UI login smoke (manual)

1. Open the public origin.
2. Complete Langfuse first-user / organization setup.
3. Create a project; note **public key** + **secret key** (OTLP Basic auth).
4. Confirm project UI loads without 5xx.

## OTLP smoke

Langfuse OTLP ingest: `POST /api/public/otel` (or `/api/public/otel/v1/traces`
depending on SDK path — the script targets `/api/public/otel`).

Auth: HTTP Basic with Langfuse public:secret, exposed to digibase via
`DIGI_OTEL_HEADERS` or `OTEL_EXPORTER_OTLP_HEADERS` (#4927). Example shape
(do not commit real values):

```bash
# Authorization=Basic $(printf '%s:%s' "$PK" "$SK" | base64 -w0)
export DIGITRACE_LANGFUSE_OTLP_ENDPOINT="https://trace.digithings.ai/api/public/otel"
export DIGI_OTEL_HEADERS="Authorization=Basic <redacted>"
bash scripts/smoke_digitrace_langfuse_otlp.sh
```

The script **fails closed** if endpoint or auth headers are missing and never
prints secret values.

## Deferred to human / Platform

- [ ] Create R2 bucket `digitrace-langfuse-events` + S3 API token
- [ ] Create Postgres database `langfuse` on house Postgres; store `DATABASE_URL`
- [ ] Provision ClickHouse (≥ 2 CPU / 8 GiB) and Redis; store connection secrets
- [ ] Generate `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY`
- [ ] HUMAN GATE: DNS + uncomment `trace.digithings.ai` route; set `NEXTAUTH_URL`
- [ ] `wrangler secret put` checklist above; `wrangler deploy`
- [ ] Wake Worker; UI first-user; OTLP smoke script green
- [ ] Optional: media upload bucket/prefix if needed beyond events

## Out of scope

- DigiQuant clocks / house-run cadence
- Dual-export / cut LangSmith / Task 7 secret remap (Phases 2–4)
- DigiVoice / #4947
