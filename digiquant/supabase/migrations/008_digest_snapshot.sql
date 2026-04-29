-- ============================================================================
-- digiquant-atlas: Digest Snapshot (Migration 008)
-- Adds DB-first canonical daily artifact storage to daily_snapshots.
--
-- Rationale:
-- - daily_snapshots already powers the dashboard (latest regime, actionable, risks).
-- - We now store the full structured digest payload (jsonb) as the source of truth,
--   and optionally a rendered Markdown view for library-style reading.
-- ============================================================================

ALTER TABLE IF EXISTS daily_snapshots
  ADD COLUMN IF NOT EXISTS snapshot jsonb,
  ADD COLUMN IF NOT EXISTS digest_markdown text;

-- Helpful index for debugging / analytics queries over snapshot payload.
-- (GIN on jsonb can be expensive; keep it optional and lightweight for now.)
CREATE INDEX IF NOT EXISTS idx_daily_snapshots_snapshot_gin
  ON daily_snapshots
  USING GIN (snapshot);

