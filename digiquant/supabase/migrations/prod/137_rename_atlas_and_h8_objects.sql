-- 137_rename_atlas_and_h8_objects.sql
-- W3 of #4471 — retire the last pre-rebrand names from the run-telemetry and
-- risk-registry objects. Epic #4295 (132/134/135) already renamed the
-- `olympus_*` family (`olympus_run_events` -> `run_events`, ...); these three
-- objects still carry a retired program name (`atlas`) or a phase marker
-- (`h8`):
--
--   * public.atlas_run_diagnostics  -> public.run_diagnostics   (032, 065)
--   * public.atlas_run_health       -> public.run_health        (041, 065)
--   * public.h8_risk_run_refs       -> public.sizing_risk_run_refs (081, 134)
--
-- Pattern is the one 132/134/135 established: rename the base object, rename
-- its indexes / constraints / triggers, then leave a read-compat VIEW under
-- the old name so a reader that has not redeployed yet keeps working. Nothing
-- here drops data.
--
-- Ordering note: the old-name compat views are simple single-table views, so
-- reads keep working for a dashboard build that has not redeployed yet.
-- `atlas_run_diagnostics` additionally grants `UPDATE` to service_role (not
-- just SELECT/INSERT) because a Postgres upsert — `INSERT ... ON CONFLICT
-- (run_id, attempt) DO UPDATE`, which is what `diagnostics.write_row` issues —
-- needs UPDATE on the view, and `security_invoker = true` forwards the check to
-- the base table, where service_role still holds `ALL` from 060. Without that
-- grant the legacy writer's upsert is refused (the same constraint 132
-- documents for view-based upserts); with it a not-yet-redeployed writer keeps
-- persisting across the window. The running writer already targets the base
-- table (this PR renames the call site), so this only protects the deploy
-- window. Reads are unchanged for the same reason.
--
-- Forward-only: migrations 001..136 are never edited. Run via db-migrate
-- (single `psql --single-transaction` with the ledger INSERT), so this file
-- adds no explicit transaction block.
--
-- Idempotent: every statement is catalog-guarded or IF EXISTS, so a replay
-- (which the ledger asymmetry for self-wrapping files would allow) is a no-op.

-- ---------------------------------------------------------------------------
-- Part A: atlas_run_diagnostics -> run_diagnostics
-- ---------------------------------------------------------------------------

-- Phase-A style compat view from an earlier partial run of this migration.
-- Guarded by relkind: `DROP VIEW IF EXISTS` errors when the name is a table.
DO $do$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relname = 'atlas_run_diagnostics'
           AND c.relkind = 'v'
    ) THEN
        DROP VIEW public.atlas_run_diagnostics;
    END IF;
END
$do$;

ALTER TABLE IF EXISTS public.atlas_run_diagnostics RENAME TO run_diagnostics;

ALTER INDEX IF EXISTS public.atlas_run_diagnostics_run_date_idx
    RENAME TO idx_run_diagnostics_run_date;
ALTER INDEX IF EXISTS public.atlas_run_diagnostics_created_at_idx
    RENAME TO idx_run_diagnostics_created_at;

-- Renaming a PRIMARY KEY constraint also renames its backing index, so the
-- pkey is handled here rather than with ALTER INDEX above (134 precedent).
DO $do$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'public.run_diagnostics'::regclass
           AND conname = 'atlas_run_diagnostics_pkey'
    ) THEN
        ALTER TABLE public.run_diagnostics
            RENAME CONSTRAINT atlas_run_diagnostics_pkey TO run_diagnostics_pkey;
    END IF;
END
$do$;

COMMENT ON TABLE public.run_diagnostics IS
    'Per-run telemetry, one row per (run_id, attempt) (#4471 W3; renamed from '
    'atlas_run_diagnostics). Operator-internal: RLS on with no anon policy, and '
    'anon SELECT is revoked (033 / 129) — read it through run_health.';

-- Old-name compat view: keeps historical readers alive, and — because of the
-- UPDATE grant below — a not-yet-redeployed writer's `ON CONFLICT DO UPDATE`
-- upsert still persists (see the ordering note in the header).
CREATE OR REPLACE VIEW public.atlas_run_diagnostics
    WITH (security_invoker = true) AS
SELECT * FROM public.run_diagnostics;
REVOKE ALL ON public.atlas_run_diagnostics
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON public.atlas_run_diagnostics TO service_role;

-- ---------------------------------------------------------------------------
-- Part A2: atlas_run_health -> run_health (curated anon-readable projection)
-- ---------------------------------------------------------------------------

-- The view query references run_diagnostics by relation OID, so the rename
-- alone keeps it correct; the COMMENT and the 041/060/129 grants follow.
-- Guarded (rather than a bare `ALTER VIEW ... RENAME`) so a replay is a no-op:
-- by then `run_health` already exists and `atlas_run_health` is the compat view
-- below, so an unguarded rename would raise "relation run_health already exists".
DO $do$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relname = 'atlas_run_health'
           AND c.relkind = 'v'
    ) AND NOT EXISTS (
        SELECT 1
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relname = 'run_health'
    ) THEN
        ALTER VIEW public.atlas_run_health RENAME TO run_health;
    END IF;
END
$do$;

COMMENT ON VIEW public.run_health IS
    'Curated, anon-readable projection of run_diagnostics (#4471 W3; renamed '
    'from atlas_run_health, migration 041). Deliberately security_invoker = '
    'false: the SELECT column projection is the allowlist, and spend telemetry '
    'stays out.';
GRANT SELECT ON public.run_health TO anon, authenticated;

-- Old-name compat view for a dashboard build that has not redeployed yet.
-- SELECT-only: never re-grant write privileges that 060 revoked.
DROP VIEW IF EXISTS public.atlas_run_health;
CREATE VIEW public.atlas_run_health
    WITH (security_invoker = false) AS
SELECT * FROM public.run_health;
COMMENT ON VIEW public.atlas_run_health IS
    'Read-compat alias for run_health (#4471 W3). Prefer run_health.';
REVOKE ALL ON public.atlas_run_health
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.atlas_run_health TO anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Part B: h8_risk_run_refs -> sizing_risk_run_refs
-- ---------------------------------------------------------------------------

-- Phase-A style compat view from an earlier partial run of this migration.
-- Guarded by relkind: `DROP VIEW IF EXISTS` errors when the name is a table.
DO $do$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relname = 'h8_risk_run_refs'
           AND c.relkind = 'v'
    ) THEN
        DROP VIEW public.h8_risk_run_refs;
    END IF;
END
$do$;

ALTER TABLE IF EXISTS public.h8_risk_run_refs RENAME TO sizing_risk_run_refs;

ALTER INDEX IF EXISTS public.idx_h8_risk_run_refs_run_date
    RENAME TO idx_sizing_risk_run_refs_run_date;

-- Constraint names arrive in three flavours: the original `olympus_*` ones
-- (134 renamed the FKs but left the pkey and the CHECK under their 081 names)
-- and the `h8_*` ones a fresh apply of 132/134 would have produced. Handle all
-- of them, oldest first, so the rename resolves regardless of the history the
-- target database carries.
DO $do$
DECLARE
    pair record;
BEGIN
    FOR pair IN
        SELECT * FROM (VALUES
            ('olympus_h8_risk_run_refs_pkey', 'sizing_risk_run_refs_pkey'),
            ('h8_risk_run_refs_pkey', 'sizing_risk_run_refs_pkey'),
            ('olympus_h8_risk_run_refs_source_run_id_check',
             'sizing_risk_run_refs_source_run_id_check'),
            ('h8_risk_run_refs_source_run_id_check',
             'sizing_risk_run_refs_source_run_id_check'),
            ('fk_h8_risk_run_refs_policy', 'fk_sizing_risk_run_refs_policy'),
            ('fk_h8_risk_run_refs_snapshot', 'fk_sizing_risk_run_refs_snapshot')
        ) AS t(old_name, new_name)
    LOOP
        IF EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conrelid = 'public.sizing_risk_run_refs'::regclass
               AND conname = pair.old_name
        ) THEN
            EXECUTE format(
                'ALTER TABLE public.sizing_risk_run_refs RENAME CONSTRAINT %I TO %I',
                pair.old_name,
                pair.new_name
            );
        END IF;
    END LOOP;
END
$do$;

-- Triggers hold the function OID, so they keep firing across the table
-- rename; only their names move (134 precedent). Again accept both the
-- `olympus_*` (081) and `h8_*` (134) spellings.
DO $do$
DECLARE
    pair record;
BEGIN
    FOR pair IN
        SELECT * FROM (VALUES
            ('reject_olympus_h8_risk_run_refs_mutation',
             'reject_sizing_risk_run_refs_mutation'),
            ('reject_h8_risk_run_refs_mutation',
             'reject_sizing_risk_run_refs_mutation'),
            ('reject_olympus_h8_risk_run_refs_truncate',
             'reject_sizing_risk_run_refs_truncate'),
            ('reject_h8_risk_run_refs_truncate',
             'reject_sizing_risk_run_refs_truncate')
        ) AS t(old_name, new_name)
    LOOP
        IF EXISTS (
            SELECT 1 FROM pg_trigger WHERE tgname = pair.old_name
        ) THEN
            EXECUTE format(
                'ALTER TRIGGER %I ON public.sizing_risk_run_refs RENAME TO %I',
                pair.old_name,
                pair.new_name
            );
        END IF;
    END LOOP;
END
$do$;

COMMENT ON TABLE public.sizing_risk_run_refs IS
    'One sizing-run ref per run: run_date, policy_id FK, snapshot_id FK, '
    'effective_at (#2698 / WP6.3; renamed from h8_risk_run_refs, #4471 W3). '
    'RLS on with zero policies; append-only via the reject_* triggers.';

-- Old-name compat view. A simple single-table view is auto-updatable, and the
-- registry writes with a plain INSERT (no ON CONFLICT), so a not-yet-redeployed
-- writer keeps persisting through this alias.
CREATE OR REPLACE VIEW public.h8_risk_run_refs
    WITH (security_invoker = true) AS
SELECT * FROM public.sizing_risk_run_refs;
REVOKE ALL ON public.h8_risk_run_refs
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.h8_risk_run_refs TO service_role;
