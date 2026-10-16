-- 060_lock_public_write_grants.sql — Strip platform-default write grants from the public
-- roles across schema `public`, and stop handing them to every future relation (#1757).
--
-- Run with:  supabase db push   (or apply via MCP against this project).
--
-- WHAT WAS WRONG
-- Supabase's project bootstrap issues `GRANT ALL ON ALL TABLES IN SCHEMA public TO anon,
-- authenticated` plus a matching `ALTER DEFAULT PRIVILEGES`. Nothing in this repo ever
-- narrowed it: `anon` and `authenticated` each hold INSERT/UPDATE/DELETE/TRUNCATE/
-- REFERENCES/TRIGGER on every relation in `public` (verified 2026-08-01: relacl
-- `anon=arwdDxtm/postgres` on 35 base tables + 2 views). Only migrations 050/051/052
-- ever paired a GRANT with a REVOKE. The anon JWT is a *published* credential — it is
-- inlined in the digiquant.io client bundle — so these grants are reachable by anyone.
--
-- Row-level security is currently the ONLY layer denying those writes, and it is a single
-- layer: `SELECT count(*) FROM pg_policies WHERE schemaname='public' AND cmd <> 'SELECT'`
-- returns 0, so any future `DISABLE ROW LEVEL SECURITY` (or a permissive ALL policy added
-- for a debugging session) makes that table world-writable the instant it lands.
--
-- One instance is already live and does NOT need a future mistake to arm it:
-- `public.atlas_run_health` (migration 041) is a simple single-table projection, so
-- Postgres made it auto-updatable (`information_schema.views.is_updatable = YES`,
-- `is_insertable_into = YES`). It is deliberately `security_invoker = false`, so writes
-- through it are checked as its owner (`postgres`), which bypasses the base table's RLS
-- (`atlas_run_diagnostics` has `relforcerowsecurity = false`). Combined with the standing
-- anon DELETE grant on the view, an unauthenticated `DELETE /rest/v1/atlas_run_health`
-- erases every `atlas_run_diagnostics` row — the entire run-telemetry history that the
-- Olympus System tab is built on. Migration 041 shipped `GRANT SELECT` with no preceding
-- `REVOKE`, which is the whole defect; migration 018 (`price_history_tickers`) has the same
-- omission but is not auto-updatable (it carries DISTINCT), so it is defense-in-depth only.
--
-- WHY AN EXPLICIT PRIVILEGE LIST AND NOT `REVOKE ALL`
-- `REVOKE ALL` would also take SELECT away. On the plain-table statement that would break
-- the dashboard immediately; on the ALTER DEFAULT PRIVILEGES statement it would break the
-- *next* curated view silently and much later — and the frontend's `safeSelect` helper
-- swallows a PostgREST 42501 into an empty state rather than surfacing an error, so the
-- symptom would be a blank panel, not an alert. The six privileges below are exactly the
-- non-SELECT table privileges the public roles were granted. TRIGGER is included
-- deliberately: it is the privilege that lets a non-owner attach a trigger to a table, and
-- the public roles also hold EXECUTE on functions in this schema by default ACL.
--
-- WHY THERE IS NO `FOR ROLE` CLAUSE
-- `pg_default_acl` has TWO grantors for schema `public`: `postgres` and `supabase_admin`.
-- Default privileges are keyed to the role that *creates* the object, and every relation in
-- `public` is owned by `postgres` (38 tables + 5 views, verified) because that is the role
-- this migration chain runs as. So the implicit `FOR ROLE postgres` form below is the one
-- that governs new relations. Do NOT add `FOR ROLE supabase_admin`: `postgres` is not a
-- member of it, so that statement raises `must be a member of role "supabase_admin"` — and
-- because `db-migrate.yml` pipes each file through `psql --single-transaction
-- -v ON_ERROR_STOP=1`, that error would roll back this whole migration.
--
-- BLAST RADIUS: NIL
--   * `service_role` is untouched — it keeps `arwdDxtm`. Every writer uses it: all five
--     production workflows, every Python connector (`data/store/client.py`,
--     `atlas/supabase_io.py`, `cli/prices.py`), and the `prices-live` edge function
--     (`functions/prices-live/index.ts:115-121`).
--   * Zero anon/authenticated writers exist. The only anon-key client in the repo is
--     `scripts/verify_strategy_calibrations_rls.py`, a read-only RLS probe; the Olympus
--     frontend performs no Supabase mutation at all (repo-wide grep, 2026-08-01).
--   * `authenticated` cannot even be assumed by anyone: `SELECT count(*) FROM auth.users`
--     is 0 — there is no sign-up surface on this project.
--   * SELECT is preserved everywhere, so no read path changes. RLS remains the read gate
--     exactly as documented (migration 033's silent-empty-set behaviour is unchanged).
--
-- KNOWN RESIDUALS (deliberately out of scope — see the PR for #1757)
--   * The `supabase_admin` default-ACL entry for `public` cannot be altered from
--     `postgres`. It only applies to relations created BY `supabase_admin`, which no
--     migration in this chain does.
--   * PG17's MAINTAIN privilege is not in the list. There are zero materialized views in
--     `public`, so it grants at most VACUUM/ANALYZE, never a data change.
--   * Sequence (`rwU`) and function (`X`) default grants to the public roles are
--     untouched. With table INSERT gone, `nextval` has no write to enable.
--
-- Idempotent: REVOKE and GRANT are both re-runnable, and re-running is a no-op.

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON ALL TABLES IN SCHEMA public
    FROM PUBLIC, anon, authenticated;

-- `ALL TABLES` includes views and foreign tables (per the GRANT reference), which is what
-- reaches `atlas_run_health` and `price_history_tickers` above.
--
-- Belt and braces, and worth two lines: the whole live exploit lives in a *view*, so naming
-- the two of them explicitly makes this migration independent of that `ALL TABLES` behaviour.
-- Redundant if the statement above already covered them, decisive if it did not.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.atlas_run_health, public.price_history_tickers
    FROM PUBLIC, anon, authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLES FROM anon, authenticated;

-- Re-assert the reads the two under-granted views are supposed to have, so the intent is
-- recorded here rather than inferred from what the REVOKE above happened to leave behind.
-- This matches the `REVOKE` + `GRANT SELECT` pairing migrations 050 and 052 already use.
GRANT SELECT ON public.atlas_run_health      TO anon, authenticated;
GRANT SELECT ON public.price_history_tickers TO anon, authenticated;
