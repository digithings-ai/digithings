-- 136_rename_schema_migrations_ledger.sql
-- Retire the old-name `olympus_schema_migrations` migration ledger (#4295).
--
-- `.github/workflows/db-migrate.yml` renamed its ledger to
-- `public.digithings_schema_migrations` and now runs a copy-forward bootstrap
-- BEFORE its skip gate: on every apply it creates the new table if missing and,
-- while the old table still exists, copies every `(version, applied_at)` row
-- into it (`ON CONFLICT (version) DO NOTHING`, in one transaction). Only once
-- that has happened is it safe to drop the old table, which is what this file
-- does.
--
-- LOUD and fail-closed on purpose. It refuses to drop the old ledger unless the
-- new one exists and holds at least as many rows, so a run that races the
-- bootstrap — or a fresh environment where the workflow has never been allowed
-- to run — aborts instead of deleting prod's only record of what it has applied.
-- If the old table is already gone (a fresh environment, or a re-run after an
-- earlier apply), the whole migration is a no-op.
--
-- REQUIRED ORDER: 132 -> 133 -> 134 -> 136, and the db-migrate copy-forward
-- bootstrap must have run at least once before this file executes. db-migrate
-- applies files in filename order, but its bootstrap step always runs ahead of
-- the whole loop, so one approved run does both: copy the rows, then drop the
-- old table. Merging this file to `main` does NOT by itself drop anything — the
-- `production`-environment approval on that db-migrate run is what executes it.
--
-- Unwrapped on purpose: db-migrate pipes this file and its ledger INSERT through
-- one `psql --single-transaction`, so it must not carry its own `BEGIN;`/`COMMIT;`.
--
-- Never touches any object owned by migrations 132/133/134/135, and never drops
-- any table other than the old ledger.

DO $$
DECLARE
  old_rows bigint;
  new_rows bigint;
BEGIN
  IF to_regclass('public.olympus_schema_migrations') IS NULL THEN
    RAISE NOTICE '136: public.olympus_schema_migrations is already gone; nothing to do';
    RETURN;
  END IF;

  IF to_regclass('public.digithings_schema_migrations') IS NULL THEN
    RAISE EXCEPTION
      '136: refusing to drop public.olympus_schema_migrations -- public.digithings_schema_migrations does not exist. Apply 132 -> 133 -> 134 -> 136 in order and let the db-migrate copy-forward bootstrap run first.';
  END IF;

  SELECT count(*) INTO old_rows FROM public.olympus_schema_migrations;
  SELECT count(*) INTO new_rows FROM public.digithings_schema_migrations;

  IF new_rows < old_rows THEN
    RAISE EXCEPTION
      '136: refusing to drop public.olympus_schema_migrations -- the new ledger has % row(s) but the old one has %. The db-migrate copy-forward bootstrap has not completed; do not drop the old ledger.',
      new_rows, old_rows;
  END IF;

  RAISE NOTICE '136: dropping public.olympus_schema_migrations (old_rows=%, new_rows=%)',
    old_rows, new_rows;
  DROP TABLE public.olympus_schema_migrations;
END $$;
