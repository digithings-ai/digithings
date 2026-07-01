-- ============================================================================
-- digiquant-atlas: Partition Strategy (004)
-- Implements table partitioning for the two highest-volume tables:
--   - daily_snapshots  (~250-365 rows/year, jsonb columns several KB each)
--   - documents        (~8,000-10,000 rows/year including sector files)
--
-- Strategy: RANGE partitioning by calendar year (PARTITION BY RANGE (date)).
-- Each year gets its own partition. The default partition absorbs any data
-- outside the explicit year ranges until a new year partition is added.
--
-- IMPORTANT: This migration is advisory / non-destructive. It:
--   1. Creates new partitioned shadow tables (*_partitioned)
--   2. Copies existing data into the partitioned tables
--   3. Renames old tables to *_legacy, new tables to the canonical names
--
-- Rollback: rename *_legacy back to the original name.
-- Prerequisite: 003_performance_audit.sql must be applied first.
-- ============================================================================

-- ============================================================================
-- 1. PARTITION daily_snapshots BY RANGE (date)
-- ============================================================================

-- Step 1a: create the new partitioned parent (no rows, just structure)
CREATE TABLE IF NOT EXISTS daily_snapshots_partitioned (
  id            uuid NOT NULL DEFAULT gen_random_uuid(),
  date          date NOT NULL,
  run_type      text NOT NULL CHECK (run_type IN ('baseline', 'delta')),
  baseline_date date,
  regime        jsonb NOT NULL,
  market_data   jsonb NOT NULL,
  segment_biases jsonb,
  actionable    text[],
  risks         text[],
  created_at    timestamptz DEFAULT now(),
  PRIMARY KEY (id, date)           -- partition key must be in PK
) PARTITION BY RANGE (date);

-- Step 1b: create year partitions (2025, 2026, 2027 + default)
-- Add new years here each January (or automate via cron in database functions)
CREATE TABLE IF NOT EXISTS daily_snapshots_y2025
  PARTITION OF daily_snapshots_partitioned
  FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');

CREATE TABLE IF NOT EXISTS daily_snapshots_y2026
  PARTITION OF daily_snapshots_partitioned
  FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE IF NOT EXISTS daily_snapshots_y2027
  PARTITION OF daily_snapshots_partitioned
  FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');

-- Default partition: catches any rows outside the explicit year ranges
CREATE TABLE IF NOT EXISTS daily_snapshots_default
  PARTITION OF daily_snapshots_partitioned DEFAULT;

-- Step 1c: indexes on the partitioned parent (inherited by all child partitions)
CREATE INDEX IF NOT EXISTS idx_snap_part_date
  ON daily_snapshots_partitioned(date DESC);

CREATE INDEX IF NOT EXISTS idx_snap_part_run_type
  ON daily_snapshots_partitioned(run_type, date DESC);

-- ============================================================================
-- 2. PARTITION documents BY RANGE (date)
-- ============================================================================

-- Step 2a: create the new partitioned parent
CREATE TABLE IF NOT EXISTS documents_partitioned (
  id        uuid NOT NULL DEFAULT gen_random_uuid(),
  date      date NOT NULL,
  title     text NOT NULL,
  doc_type  text,
  phase     int,
  category  text,
  segment   text,
  sector    text,
  run_type  text,
  file_path text NOT NULL,
  content   text,
  PRIMARY KEY (id, date)           -- partition key must be in PK
) PARTITION BY RANGE (date);

-- Step 2b: year partitions for documents
CREATE TABLE IF NOT EXISTS documents_y2025
  PARTITION OF documents_partitioned
  FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');

CREATE TABLE IF NOT EXISTS documents_y2026
  PARTITION OF documents_partitioned
  FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE IF NOT EXISTS documents_y2027
  PARTITION OF documents_partitioned
  FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');

-- Default partition for documents outside explicit year ranges
CREATE TABLE IF NOT EXISTS documents_default
  PARTITION OF documents_partitioned DEFAULT;

-- Step 2c: indexes on the partitioned parent
CREATE INDEX IF NOT EXISTS idx_docs_part_date
  ON documents_partitioned(date DESC);

CREATE INDEX IF NOT EXISTS idx_docs_part_category_date
  ON documents_partitioned(category, date DESC);

CREATE INDEX IF NOT EXISTS idx_docs_part_doc_type_date
  ON documents_partitioned(doc_type, date DESC);

-- ============================================================================
-- 3. DATA MIGRATION — copy existing rows into partitioned tables
-- ============================================================================

-- Copy snapshots (preserves all columns including created_at)
INSERT INTO daily_snapshots_partitioned
  SELECT id, date, run_type, baseline_date, regime, market_data,
         segment_biases, actionable, risks, created_at
  FROM daily_snapshots
  ON CONFLICT DO NOTHING;

-- Copy documents
INSERT INTO documents_partitioned
  SELECT id, date, title, doc_type, phase, category,
         segment, sector, run_type, file_path, content
  FROM documents
  ON CONFLICT DO NOTHING;

-- ============================================================================
-- 4. TABLE SWAP — rename old → legacy, new → canonical
-- ============================================================================

-- Rename old tables aside (data preserved for rollback)
ALTER TABLE IF EXISTS daily_snapshots  RENAME TO daily_snapshots_legacy;
ALTER TABLE IF EXISTS documents        RENAME TO documents_legacy;

-- Promote partitioned tables to canonical names
ALTER TABLE daily_snapshots_partitioned RENAME TO daily_snapshots;
ALTER TABLE documents_partitioned       RENAME TO documents;

-- ============================================================================
-- 5. MAINTENANCE NOTE
-- ============================================================================
-- To add a new year partition in future (run on Jan 1 of that year):
--
--   CREATE TABLE IF NOT EXISTS daily_snapshots_y2028
--     PARTITION OF daily_snapshots
--     FOR VALUES FROM ('2028-01-01') TO ('2029-01-01');
--
--   CREATE TABLE IF NOT EXISTS documents_y2028
--     PARTITION OF documents
--     FOR VALUES FROM ('2028-01-01') TO ('2029-01-01');
--
-- The _default partitions will continue absorbing new-year rows until the
-- explicit partition is created.
-- ============================================================================
