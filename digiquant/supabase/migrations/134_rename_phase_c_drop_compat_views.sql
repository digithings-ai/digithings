-- 134_rename_phase_c_drop_compat_views.sql
-- Phase C (final) of the `olympus_*` terminology removal (#4295 gap G5).
--
-- Drops every remaining old-name `olympus_*` compatibility VIEW in schema
-- `public`, so the old vocabulary disappears from the database entirely. Base
-- TABLES are never touched, and the ledger is never touched.
--
-- REQUIRED APPLY ORDER: 132 -> 133 -> 134.
--   * 132 (Phase A) added new-name views over the then-still-`olympus_*` base
--     objects.
--   * 133 (Phase B) renamed the base objects to their new names and recreated
--     each old name as a `security_invoker = true` compatibility view.
--   * 134 (this file) drops those old-name compatibility views once `main`
--     runs the new-name code.
-- Applying this file before 133 would target the wrong objects: the old names
-- would still be base objects, not compat views. The guard below makes that
-- failure loud instead of a silent no-op -- if any `olympus_*` TABLE still
-- exists in `public`, this migration RAISEs and the whole file (together with
-- its ledger row) rolls back.
--
-- Safety properties:
--   * Only relkind = 'v' (regular views) are dropped. No base object is
--     altered, renamed, or removed.
--   * No CASCADE: a view with a dependent object fails loudly rather than
--     silently taking the dependent down with it.
--   * `olympus_schema_migrations` is excluded from both the guard and the drop
--     loop by name; renaming/dropping the ledger is a separate, human-gated
--     change and is deliberately out of scope here.
--   * Identifiers are interpolated with quote_ident-safe `%I` in `format()`.
--
-- Replay-safe: unwrapped (the db-migrate loop runs this file plus its ledger
-- INSERT inside one `psql --single-transaction` call). A replay with no
-- `olympus_*` views left is a silent success, so re-running after 133 and 134
-- have both landed is safe.

DO $$
DECLARE
    remaining_tables text;
    target record;
BEGIN
    -- Loud safety guard: Phase B must have renamed every base table before
    -- Phase C can mean anything. `olympus_schema_migrations` is the ledger and
    -- is deliberately exempt.
    SELECT string_agg(format('%I.%I', n.nspname, c.relname), ', ' ORDER BY c.relname)
      INTO remaining_tables
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind = 'r'
       AND c.relname LIKE 'olympus\_%'
       AND c.relname <> 'olympus_schema_migrations';

    IF remaining_tables IS NOT NULL THEN
        RAISE EXCEPTION
            'migration 134 (Phase C) requires Phase B (migration 133) first: '
            'olympus_* base table(s) still present: %. '
            'Apply in order 132 -> 133 -> 134.', remaining_tables;
    END IF;

    -- Drop every remaining old-name olympus_* compatibility view. Dynamic so it
    -- does not depend on Phase B's exact object list.
    FOR target IN
        SELECT n.nspname AS schema_name, c.relname AS view_name
          FROM pg_catalog.pg_class AS c
          JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relkind = 'v'
           AND c.relname LIKE 'olympus\_%'
           AND c.relname <> 'olympus_schema_migrations'
         ORDER BY c.relname
    LOOP
        EXECUTE format('DROP VIEW %I.%I', target.schema_name, target.view_name);
        RAISE NOTICE '134: dropped olympus compat view %.%',
            target.schema_name, target.view_name;
    END LOOP;
END
$$;
