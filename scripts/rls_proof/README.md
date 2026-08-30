# RLS isolation proof harness (vanilla PostgreSQL)

Program-level acceptance for the Kairos + tenancy epic:

- user A cannot read user B's private rows on any tenant table
- anon reads zero private rows post-cutover
- tier gates hold at the policy layer (baseline+ can read house weight docs; free cannot)

This harness reproduces the **post-cutover** schema on stock Postgres 16 when Docker /
Supabase CLI are unavailable. It is **not** a substitute for applying migrations on the
real `core` Supabase project.

## Layout

| Path | Role |
|------|------|
| `00_supabase_shim.sql` | Roles, `auth.*`, extensions, realtime publication, checkpointer stubs |
| `01_seed.sql` | Two tenants + free observer + representative private rows |
| `02_proof.sql` | `SET ROLE` + JWT claims matrix; fails the process on any assertion miss |
| `run.sh` | Recreate DB → shim → migrations → cutover → seed → proof |

## Migration apply order

1. **Shim** (`00_supabase_shim.sql`)
2. **develop** top-level `digiquant/supabase/migrations/*.sql` (001…109, lexicographic `sort` — same as `db-migrate.yml`). Includes `109_authenticated_house_teaser_read` (pre-cutover Auth Pages JWT hotfix).
3. **Kairos/T4 migrations** `099`, `102`–`105` — now canonical in `digiquant/supabase/migrations/`, applied by the same glob (vendor step dropped after the K3–T4 merges)
4. **Cutover** `digiquant/supabase/migrations/cutover/900_drop_anon_read_cutover.sql` (staged; not auto-applied in CI). Section A2 restores 098 membership-only SELECT on the house book tables so 109's teaser does not leak weights to free JWTs after `anon_read` is dropped.

## Run

```bash
# Prerequisites: postgresql-16, postgresql-contrib, postgresql-16-cron (optional but preferred)
sudo apt-get install -y postgresql postgresql-contrib postgresql-16-cron
# shared_preload_libraries = 'pg_cron' ; cron.database_name = 'rls_proof' ; restart cluster

sudo -u postgres psql -c "CREATE DATABASE rls_proof;"   # run.sh recreates it
LOG=/opt/cursor/artifacts/rls_isolation_proof.log ./scripts/rls_proof/run.sh
```

## Shim inventory vs production

| Shim | Production (Supabase `core`) | Notes |
|------|------------------------------|-------|
| Roles `anon` / `authenticated` / `service_role` | Platform roles | `service_role` created with `BYPASSRLS` |
| `authenticator` login role | PostgREST `authenticator` (login) | `NOINHERIT LOGIN`; password `rls_proof_local` is a **local stand-in only** — not production |
| `auth.users(id)` | Full Auth schema | Minimal PK-only stub for membership FKs / proof inserts |
| `auth.uid()` / `auth.jwt()` | Auth helpers | Read `request.jwt.claims` JSON (`sub`, `app_metadata`, …) |
| `pgcrypto` / `moddatetime` | Usually pre-enabled | Enabled explicitly here |
| `pg_cron` | Enabled on `core` | Real `postgresql-16-cron` when preload configured; 061 skips schedule if absent |
| `public.set_updated_at()` | Not in develop chain (003 has `trigger_set_updated_at`) | Alias for unmerged `103_notification_prefs.sql` |
| LangGraph `checkpoint*` tables | Created by checkpointer library | Empty stubs so 036/061 can ALTER |
| `PUBLICATION supabase_realtime` | Realtime platform publication | Empty stub; 063 ADDs `prices_live` |
| Stub `fx_economic_calendar` | Out-of-repo prod table (031) | Minimal columns so 031 can ENABLE RLS |
| Stub `olympus_schema_migrations` | Created by `db-migrate.yml` | 057 locks it |
| Default privileges ALL → client roles | Supabase bootstrap ACL | Migration 060 then revokes writes from anon/authenticated |
| `session_replication_role=replica` wrap on **097 only** | Not automatic | 075 append-only trigger rejects 097's `UPDATE olympus_profile_config SET workspace_id…`. Harness wraps that one file; do the same on cutover if applying as superuser. |

## What this does *not* prove

- PostgREST / JWT signature verification (claims are injected via `set_config`)
- Edge Functions, Storage, Realtime fan-out
- Cloudflare Access / digiquant.io frontend cutover switches
- Live Stripe claim sync into Auth `app_metadata` (JWT `plan_tier` is seeded in claims)

## Re-run at real cutover

After 096–109 are on `core` and cutover `900` is promoted:

1. Prefer proving against a Supabase branch / preview DB with the same SQL identity switches, **or**
2. Vendor step dropped 2026-08-30 after K3/K4/K5/T4 merged — the harness now proves the canonical migration chain directly.
