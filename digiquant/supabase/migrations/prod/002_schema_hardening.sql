-- ============================================================================
-- digiquant-atlas: Schema Hardening Migration (002)
-- Adds stricter constraints and valid-range checks to all tables.
-- Safe to re-run (all ALTER TABLE statements are wrapped in DO$$ EXCEPTION blocks).
-- Prerequisite: 001_initial_schema.sql must be applied first.
-- ============================================================================

-- ============================================================================
-- 1. ENUM-LIKE TYPES (implemented as CHECK constraints, not PG ENUM types)
-- Using CHECK instead of native ENUM so columns remain type=text and the
-- Supabase Dashboard can display / filter values without casting.
-- ============================================================================

-- Position categories (matches portfolio.json `.category` field values)
DO $$ BEGIN
  ALTER TABLE positions ADD CONSTRAINT chk_positions_category
    CHECK (category IS NULL OR category IN (
      'commodity_gold', 'commodity_oil', 'commodity_broad',
      'equity_sector', 'equity_broad', 'equity_international',
      'fixed_income_cash', 'fixed_income_short', 'fixed_income_long',
      'crypto', 'forex', 'other'
    ));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Thesis status — normalize any legacy free-form values before constraining
-- (early manual entries used mixed case / different spellings)
UPDATE theses SET status = 'ACTIVE'      WHERE status ILIKE '%confirmed%' OR status ILIKE '%active%';
UPDATE theses SET status = 'MONITORING'  WHERE status ILIKE '%monitoring%';
UPDATE theses SET status = 'CHALLENGED'  WHERE status ILIKE '%challenged%';
UPDATE theses SET status = 'CLOSED'      WHERE status ILIKE '%closed%';
UPDATE theses SET status = 'INVALIDATED' WHERE status ILIKE '%invalidated%';
UPDATE theses SET status = 'PAUSED'      WHERE status ILIKE '%paused%' OR status ILIKE '%hold%';
UPDATE theses SET status = 'NEW'         WHERE status ILIKE '%new%';

DO $$ BEGIN
  ALTER TABLE theses ADD CONSTRAINT chk_theses_status
    CHECK (status IS NULL OR status IN (
      'ACTIVE', 'MONITORING', 'CHALLENGED', 'CLOSED', 'INVALIDATED', 'PAUSED', 'NEW'
    ));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Document types
DO $$ BEGIN
  ALTER TABLE documents ADD CONSTRAINT chk_documents_doc_type
    CHECK (doc_type IS NULL OR doc_type IN (
      'Daily Digest', 'Daily Delta', 'Weekly Rollup', 'Monthly Summary', 'Deep Dive'
    ));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Document categories
DO $$ BEGIN
  ALTER TABLE documents ADD CONSTRAINT chk_documents_category
    CHECK (category IS NULL OR category IN (
      'synthesis', 'macro', 'asset-class', 'equity', 'sector',
      'alt-data', 'institutional', 'portfolio', 'delta', 'output',
      'rollup', 'deep-dive'
    ));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Document run_type
DO $$ BEGIN
  ALTER TABLE documents ADD CONSTRAINT chk_documents_run_type
    CHECK (run_type IS NULL OR run_type IN ('baseline', 'delta'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- 2. NUMERIC RANGE CONSTRAINTS
-- ============================================================================

-- weight_pct: 0–100
DO $$ BEGIN
  ALTER TABLE positions ADD CONSTRAINT chk_positions_weight_range
    CHECK (weight_pct >= 0 AND weight_pct <= 100);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE position_events ADD CONSTRAINT chk_events_weight_range
    CHECK (weight_pct IS NULL OR (weight_pct >= 0 AND weight_pct <= 100));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE position_events ADD CONSTRAINT chk_events_prev_weight_range
    CHECK (prev_weight_pct IS NULL OR (prev_weight_pct >= 0 AND prev_weight_pct <= 100));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- prices must be non-negative
DO $$ BEGIN
  ALTER TABLE positions ADD CONSTRAINT chk_positions_price_nonneg
    CHECK (current_price IS NULL OR current_price >= 0);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE positions ADD CONSTRAINT chk_positions_entry_price_nonneg
    CHECK (entry_price IS NULL OR entry_price >= 0);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE position_events ADD CONSTRAINT chk_events_price_nonneg
    CHECK (price IS NULL OR price >= 0);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE benchmark_history ADD CONSTRAINT chk_bench_price_nonneg
    CHECK (price >= 0);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- NAV must be positive
DO $$ BEGIN
  ALTER TABLE nav_history ADD CONSTRAINT chk_nav_positive
    CHECK (nav > 0);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- cash_pct: 0–100
DO $$ BEGIN
  ALTER TABLE nav_history ADD CONSTRAINT chk_nav_cash_range
    CHECK (cash_pct IS NULL OR (cash_pct >= 0 AND cash_pct <= 100));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE nav_history ADD CONSTRAINT chk_nav_invested_range
    CHECK (invested_pct IS NULL OR (invested_pct >= 0 AND invested_pct <= 100));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE portfolio_metrics ADD CONSTRAINT chk_metrics_cash_range
    CHECK (cash_pct IS NULL OR (cash_pct >= 0 AND cash_pct <= 100));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE portfolio_metrics ADD CONSTRAINT chk_metrics_invested_range
    CHECK (total_invested IS NULL OR (total_invested >= 0 AND total_invested <= 100));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- volatility: 0–10 (1000% annualized would be extreme)
DO $$ BEGIN
  ALTER TABLE portfolio_metrics ADD CONSTRAINT chk_metrics_vol_range
    CHECK (volatility IS NULL OR (volatility >= 0 AND volatility <= 10));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- max_drawdown: -1 to 0 (expressed as fraction)
DO $$ BEGIN
  ALTER TABLE portfolio_metrics ADD CONSTRAINT chk_metrics_dd_range
    CHECK (max_drawdown IS NULL OR (max_drawdown >= -1 AND max_drawdown <= 0));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- phase: 1–9
DO $$ BEGIN
  ALTER TABLE documents ADD CONSTRAINT chk_documents_phase_range
    CHECK (phase IS NULL OR (phase >= 1 AND phase <= 9));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- 3. NOT NULL ENFORCEMENT (on fields that should always be populated)
-- ============================================================================

-- positions: ticker and weight always required (already enforced by schema)
-- theses: name always required (already enforced)
-- documents: file_path always required (already enforced)

-- ticker fields should never be null
ALTER TABLE positions ALTER COLUMN ticker SET NOT NULL;
ALTER TABLE position_events ALTER COLUMN ticker SET NOT NULL;
ALTER TABLE benchmark_history ALTER COLUMN ticker SET NOT NULL;

-- date fields should never be null
ALTER TABLE positions ALTER COLUMN date SET NOT NULL;
ALTER TABLE position_events ALTER COLUMN date SET NOT NULL;
ALTER TABLE documents ALTER COLUMN date SET NOT NULL;

-- ============================================================================
-- 4. ADDITIONAL INDEXES for common query patterns
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_positions_category ON positions(category);
CREATE INDEX IF NOT EXISTS idx_events_event ON position_events(event);
CREATE INDEX IF NOT EXISTS idx_docs_segment ON documents(segment);
CREATE INDEX IF NOT EXISTS idx_theses_status ON theses(status);
CREATE INDEX IF NOT EXISTS idx_theses_thesis_id ON theses(thesis_id);
