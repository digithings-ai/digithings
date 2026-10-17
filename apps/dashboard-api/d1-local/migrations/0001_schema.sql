-- DIG-2901 placeholder migration (schema-only).
--
-- Real DDL lands via DIG-2890 (twelve-x, 26 tables) and DIG-2891 (core,
-- 106 tables). This file exists only to prove the local apply path:
-- `wrangler dev --local` applies everything under d1-local/migrations/
-- to the persisted local D1 on every boot of ./scripts/run_stack_local.sh.
--
-- No seed data here and none until ticket 0 (DIG-2888 snapshot) exists.
-- Supabase stays live and untouched as the rollback throughout.

CREATE TABLE IF NOT EXISTS d1_local_schema_version (
  version     INTEGER PRIMARY KEY,
  applied_at  TEXT NOT NULL DEFAULT '',
  note        TEXT NOT NULL DEFAULT ''
);

INSERT INTO d1_local_schema_version (version, applied_at, note)
  SELECT 1, datetime('now'), 'DIG-2901 schema-only placeholder'
  WHERE NOT EXISTS (SELECT 1 FROM d1_local_schema_version WHERE version = 1);
