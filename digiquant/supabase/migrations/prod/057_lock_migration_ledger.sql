-- 057_lock_migration_ledger.sql — Lock the migration ledger against the public anon key (#1755).
--
-- Run with:  supabase db push   (or apply via MCP against this project).
--
-- Live-pipeline review 2026-07-31 (issue #1755) found `public.olympus_schema_migrations`
-- with RLS DISABLED, zero policies, and INSERT/UPDATE/DELETE/TRUNCATE granted to `anon`
-- and `authenticated`. It was the ONLY table in `public` with `relrowsecurity = false` —
-- every other table already relied on RLS to gate the same broad grants. Anon SELECT was
-- confirmed live over PostgREST using the anon JWT that ships in the public digiquant.io
-- bundle, and the repo is public.
--
-- Why this matters more than a normal table: db-migrate.yml trusts this ledger to decide
-- which migrations to skip.
--   * Forge a row (`057_...sql`) and the `exists` gate at db-migrate.yml:68 fires
--     `continue` — the migration is never executed and the workflow exits 0 reporting
--     success. Prod schema silently diverges from main. That is the 044/045 incident
--     class (#1016) this very gate was built to end.
--   * Delete rows and prior migrations re-run. 056_thesis_topic_identity.sql is now
--     DDL-idempotent, so its merge/dedupe DML (DELETE FROM theses, UPDATE topic_key, ...)
--     would re-execute against current data and COMMIT.
--
-- Root cause: the table is created ad hoc by the workflow itself
-- (`CREATE TABLE IF NOT EXISTS ...` inline at db-migrate.yml:52) rather than by a
-- checked-in migration, so it never traversed the path that applies this repo's
-- RLS + REVOKE convention. This file puts it under that convention.
--
-- Writer-safe — verified against the live catalog before applying:
--   * Table owner is `postgres`, and `relforcerowsecurity = false`, so the owner bypasses RLS.
--   * `postgres` and `service_role` both have `rolbypassrls = true`; `service_role` cannot
--     log in, so db-migrate's DIGI_CHECKPOINTER_POSTGRES_URI necessarily connects as an
--     owner-class role.
--   * The pre-fix ACL granted `anon`/`authenticated` DIRECTLY (no PUBLIC entry), so
--     revoking them cannot affect `postgres` or `service_role`.
--
-- Belt and braces, same shape as 051_lock_strategy_store.sql: RLS with no policy removes
-- row access, and the REVOKE removes the PostgREST table grant, so neither anon nor
-- authenticated can touch this table even if a future migration re-grants schema-wide
-- privileges.
--
-- Idempotent: ENABLE ROW LEVEL SECURITY is a no-op when already enabled, and REVOKE of an
-- absent privilege is a no-op. Safe to re-run — which matters, because this migration is
-- applied by the very workflow whose ledger it locks.
--
-- NOTE: already applied to the live project on 2026-08-01 as the immediate remediation for
-- #1755. This file exists so a rebuild from the repo reproduces the locked state rather
-- than recreating the hole; re-application is a harmless no-op.

ALTER TABLE public.olympus_schema_migrations ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_schema_migrations FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.olympus_schema_migrations IS
  'Migration ledger for db-migrate.yml (#1016): one row per applied migration file. '
  'Locked down 2026-08-01 (issue #1755) — RLS enabled with no policies and all grants '
  'revoked from anon/authenticated, because a forged or truncated row makes db-migrate '
  'silently skip or re-run migrations. Owner/service_role access only (both bypass RLS).';
