-- ============================================================================
-- digiquant-atlas: Unpartition daily_snapshots + documents (Migration 011)
--
-- Replaces RANGE-partitioned tables (004) with ordinary heap tables:
--   - daily_snapshots: PRIMARY KEY (id), UNIQUE (date)
--   - documents: PRIMARY KEY (id), UNIQUE (date, document_key)
--
-- Data: copies all rows; if duplicate dates / (date, document_key) exist,
-- keeps one row deterministically (latest created_at, then id).
--
-- RLS, indexes, and daily_snapshots updated_at trigger are recreated.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1) daily_snapshots
-- ---------------------------------------------------------------------------
CREATE TABLE daily_snapshots_new (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  date date NOT NULL,
  run_type text NOT NULL CHECK (run_type IN ('baseline', 'delta')),
  baseline_date date,
  regime jsonb NOT NULL,
  market_data jsonb NOT NULL,
  segment_biases jsonb,
  actionable text[],
  risks text[],
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  snapshot jsonb,
  digest_markdown text,
  CONSTRAINT daily_snapshots_new_date_key UNIQUE (date)
);

-- Omit updated_at from SELECT: some DBs never got 003’s column on partitioned snapshots.
-- Target table fills updated_at via DEFAULT / trigger on future writes.
INSERT INTO daily_snapshots_new (
  id, date, run_type, baseline_date, regime, market_data, segment_biases,
  actionable, risks, created_at, snapshot, digest_markdown
)
SELECT DISTINCT ON (date)
  id,
  date,
  run_type,
  baseline_date,
  regime,
  market_data,
  segment_biases,
  actionable,
  risks,
  created_at,
  snapshot,
  digest_markdown
FROM daily_snapshots
ORDER BY date, created_at DESC NULLS LAST, id;

DROP TABLE daily_snapshots CASCADE;
ALTER TABLE daily_snapshots_new RENAME TO daily_snapshots;

CREATE INDEX IF NOT EXISTS idx_snapshots_date ON daily_snapshots(date DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_run_type_date ON daily_snapshots(run_type, date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_snapshots_snapshot_gin ON daily_snapshots USING GIN (snapshot);

ALTER TABLE daily_snapshots ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "anon_read" ON daily_snapshots;
CREATE POLICY "anon_read" ON daily_snapshots FOR SELECT TO anon USING (true);

DROP TRIGGER IF EXISTS set_updated_at_daily_snapshots ON daily_snapshots;
CREATE TRIGGER set_updated_at_daily_snapshots
  BEFORE UPDATE ON daily_snapshots
  FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- ---------------------------------------------------------------------------
-- 2) documents (logical key document_key from migration 009)
-- ---------------------------------------------------------------------------
CREATE TABLE documents_new (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  date date NOT NULL,
  title text NOT NULL,
  doc_type text,
  phase int,
  category text,
  segment text,
  sector text,
  run_type text,
  document_key text NOT NULL,
  content text,
  payload jsonb,
  CONSTRAINT documents_new_date_document_key UNIQUE (date, document_key),
  CONSTRAINT chk_documents_doc_type CHECK (doc_type IS NULL OR doc_type IN (
    'Daily Digest', 'Daily Delta', 'Weekly Rollup', 'Monthly Summary', 'Deep Dive'
  )),
  CONSTRAINT chk_documents_category CHECK (category IS NULL OR category IN (
    'synthesis', 'macro', 'asset-class', 'equity', 'sector',
    'alt-data', 'institutional', 'portfolio', 'delta', 'output',
    'rollup', 'deep-dive'
  )),
  CONSTRAINT chk_documents_run_type CHECK (run_type IS NULL OR run_type IN ('baseline', 'delta')),
  CONSTRAINT chk_documents_phase_range CHECK (phase IS NULL OR (phase >= 1 AND phase <= 9))
);

INSERT INTO documents_new (
  id, date, title, doc_type, phase, category, segment, sector, run_type,
  document_key, content, payload
)
SELECT DISTINCT ON (date, document_key)
  id,
  date,
  title,
  doc_type,
  phase,
  category,
  segment,
  sector,
  run_type,
  document_key,
  content,
  payload
FROM documents
ORDER BY date, document_key, id;

DROP TABLE documents CASCADE;
ALTER TABLE documents_new RENAME TO documents;

CREATE INDEX IF NOT EXISTS idx_docs_date ON documents(date DESC);
CREATE INDEX IF NOT EXISTS idx_docs_doc_type_date ON documents(doc_type, date DESC);
CREATE INDEX IF NOT EXISTS idx_docs_category_date ON documents(category, date DESC);
CREATE INDEX IF NOT EXISTS idx_docs_segment ON documents(segment);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "anon_read" ON documents;
CREATE POLICY "anon_read" ON documents FOR SELECT TO anon USING (true);

COMMENT ON TABLE daily_snapshots IS 'One row per trading-day digest run (single table; partitioning removed in 011).';
COMMENT ON TABLE documents IS 'Research library rows per run date + document_key (single table; partitioning removed in 011).';
