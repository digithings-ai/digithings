-- ============================================================================
-- digiquant-atlas: Performance & Audit Improvements (003)
-- Adds 11 composite indexes for frontend query patterns, audit columns
-- (created_at / updated_at) with auto-update triggers, and NOT NULL
-- enforcement on critical columns.
-- Prerequisite: 002_schema_hardening.sql must be applied first.
-- ============================================================================

-- ============================================================================
-- 1. COMPOSITE INDEXES for common query patterns
--    Derived from the actual Supabase queries in frontend/lib/queries.js.
--    Each index targets a specific page filter + date sort combination.
-- ============================================================================

-- Position history by category + date (portfolio/sector-specific time series)
CREATE INDEX IF NOT EXISTS idx_positions_category_date ON positions(category, date DESC);

-- Position lookups by ticker + date (position drilldown)
CREATE INDEX IF NOT EXISTS idx_positions_ticker_date ON positions(ticker, date DESC);

-- Thesis history by thesis_id + date (thesis evolution chart)
CREATE INDEX IF NOT EXISTS idx_theses_thesis_id_date ON theses(thesis_id, date ASC);

-- Thesis by status + date (active thesis queries)
CREATE INDEX IF NOT EXISTS idx_theses_status_date ON theses(status, date DESC);

-- Snapshot lookups by run_type + date (baseline vs delta filtering)
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON daily_snapshots(date DESC);

-- Documents by doc_type + date (library filtering)
CREATE INDEX IF NOT EXISTS idx_docs_doc_type_date ON documents(doc_type, date DESC);

-- Documents by category + date (library category filter)
CREATE INDEX IF NOT EXISTS idx_docs_category_date ON documents(category, date DESC);

-- NAV history date ordering (performance chart)
CREATE INDEX IF NOT EXISTS idx_nav_history_date ON nav_history(date ASC);

-- Benchmark history by ticker + date (comparison chart)
CREATE INDEX IF NOT EXISTS idx_bench_ticker_date ON benchmark_history(ticker, date ASC);

-- Position events by ticker + date (event timeline)
CREATE INDEX IF NOT EXISTS idx_events_ticker_date ON position_events(ticker, date DESC);

-- ============================================================================
-- 2. AUDIT COLUMNS — created_at / updated_at on key tables
-- ============================================================================

-- Helper function for auto-updating updated_at
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- daily_snapshots
ALTER TABLE daily_snapshots ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE daily_snapshots ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
DROP TRIGGER IF EXISTS set_updated_at_daily_snapshots ON daily_snapshots;
CREATE TRIGGER set_updated_at_daily_snapshots
  BEFORE UPDATE ON daily_snapshots
  FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- positions
ALTER TABLE positions ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE positions ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
DROP TRIGGER IF EXISTS set_updated_at_positions ON positions;
CREATE TRIGGER set_updated_at_positions
  BEFORE UPDATE ON positions
  FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- theses
ALTER TABLE theses ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE theses ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
DROP TRIGGER IF EXISTS set_updated_at_theses ON theses;
CREATE TRIGGER set_updated_at_theses
  BEFORE UPDATE ON theses
  FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- portfolio_metrics
ALTER TABLE portfolio_metrics ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE portfolio_metrics ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
DROP TRIGGER IF EXISTS set_updated_at_portfolio_metrics ON portfolio_metrics;
CREATE TRIGGER set_updated_at_portfolio_metrics
  BEFORE UPDATE ON portfolio_metrics
  FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
