-- 034_drop_daily_snapshots_legacy_columns.sql — remove the legacy flat columns
-- on daily_snapshots that were superseded by the `snapshot` JSONB digest (008).
--
-- Rationale (#714): daily_snapshots carried a dual source of truth — five flat
-- columns (regime, market_data, segment_biases, actionable, risks) AND the
-- `snapshot` JSONB that supersedes them. Migration 029 already made the flat
-- columns nullable after the publish adapter stopped writing them; every recent
-- row has them NULL and the live writer (supabase_io.DailySnapshotUpsertRow)
-- only writes {date, run_type, baseline_date, snapshot, digest_markdown}. The
-- frontend now reads the equivalent data from the snapshot JSONB
-- (market_regime_snapshot / bias / actionable_summary / risk_radar). Drop the
-- dead columns so the table has a single source of truth.
--
-- Safe: no live writer populates these; no data loss (all NULL). Idempotent via
-- IF EXISTS so re-applying is a no-op.

ALTER TABLE daily_snapshots
  DROP COLUMN IF EXISTS regime,
  DROP COLUMN IF EXISTS market_data,
  DROP COLUMN IF EXISTS segment_biases,
  DROP COLUMN IF EXISTS actionable,
  DROP COLUMN IF EXISTS risks;
