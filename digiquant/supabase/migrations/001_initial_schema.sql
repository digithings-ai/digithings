-- ============================================================================
-- digiquant-atlas: Supabase Schema (Migration 001)
-- Establishes all 8 core tables, their composite indexes, and RLS policies.
-- Run via Supabase SQL Editor or `supabase db push`.
-- Safe to re-run (all statements use IF NOT EXISTS / DROP POLICY IF EXISTS).
-- ============================================================================

-- 1. daily_snapshots — one row per daily run
-- Stores the top-level digest snapshot: regime, market data, biases, and
-- actionable ideas. Used by the frontend Overview page and ETL scripts.
CREATE TABLE IF NOT EXISTS daily_snapshots (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  date          date NOT NULL UNIQUE,
  run_type      text NOT NULL CHECK (run_type IN ('baseline', 'delta')),
  baseline_date date,
  regime        jsonb NOT NULL,
  market_data   jsonb NOT NULL,
  segment_biases jsonb,
  actionable    text[],
  risks         text[],
  created_at    timestamptz DEFAULT now()
);
-- Descending index: supports "latest N days" queries without full scans
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON daily_snapshots(date DESC);

-- 2. positions — one row per ticker per day
-- Snapshot of each holding as it appears in config/portfolio.json on that date.
-- Updated nightly by update_tearsheet.py; entry_price/entry_date may be null
-- for legacy records predating automated ETL.
CREATE TABLE IF NOT EXISTS positions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  date          date NOT NULL,
  ticker        text NOT NULL,
  name          text,
  category      text,
  weight_pct    numeric NOT NULL,
  action        text,
  thesis_id     text,
  rationale     text,
  current_price numeric,
  entry_price   numeric,
  entry_date    date,
  pm_notes      text,
  UNIQUE(date, ticker)
);
CREATE INDEX IF NOT EXISTS idx_positions_date ON positions(date DESC);
-- Composite index: supports ticker history queries (e.g. "all IAU rows")
CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker, date DESC);

-- 3. theses — one row per thesis per day
-- Each active investment thesis is snapshotted per day. thesis_id is a short
-- slug (e.g. "geo-risk-gold") that links to position_events and documents.
CREATE TABLE IF NOT EXISTS theses (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  date          date NOT NULL,
  thesis_id     text NOT NULL,
  name          text NOT NULL,
  vehicle       text,
  invalidation  text,
  status        text,
  notes         text,
  UNIQUE(date, thesis_id)
);
CREATE INDEX IF NOT EXISTS idx_theses_date ON theses(date DESC);

-- 4. position_events — append-only change ledger
-- Records each discrete portfolio action (OPEN/EXIT/REBALANCE/HOLD) per ticker
-- per day. The UNIQUE(date, ticker) constraint prevents duplicate event rows;
-- if a ticker has multiple actions in one day the last write wins.
CREATE TABLE IF NOT EXISTS position_events (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  date            date NOT NULL,
  ticker          text NOT NULL,
  event           text NOT NULL CHECK (event IN ('OPEN', 'EXIT', 'REBALANCE', 'HOLD')),
  weight_pct      numeric,
  prev_weight_pct numeric,
  price           numeric,
  thesis_id       text,
  reason          text,
  created_at      timestamptz DEFAULT now(),
  UNIQUE(date, ticker)
);
CREATE INDEX IF NOT EXISTS idx_events_date ON position_events(date DESC);
-- Composite index: supports per-ticker event history queries
CREATE INDEX IF NOT EXISTS idx_events_ticker ON position_events(ticker, date DESC);

-- 5. documents — markdown content index (lazy-loaded by frontend)
-- One row per output file per date. Stores the raw markdown in `content`.
-- The frontend Research Library page queries this table filtered by category
-- and date. Full-text search can be layered on top via pg_trgm if needed.
CREATE TABLE IF NOT EXISTS documents (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  date          date NOT NULL,
  title         text NOT NULL,
  doc_type      text,
  phase         int,
  category      text,
  segment       text,
  sector        text,
  run_type      text,
  file_path     text NOT NULL,
  content       text,
  UNIQUE(date, file_path)
);
CREATE INDEX IF NOT EXISTS idx_docs_date ON documents(date DESC);
-- category index: supports filtered document queries (macro, equity, sector, ...)
CREATE INDEX IF NOT EXISTS idx_docs_category ON documents(category);

-- 6. nav_history — portfolio NAV time series
-- Populated by update_tearsheet.py when it detects changes in portfolio weight.
-- Used by the Performance page NAV chart.
CREATE TABLE IF NOT EXISTS nav_history (
  date          date PRIMARY KEY,
  nav           numeric NOT NULL,
  cash_pct      numeric,
  invested_pct  numeric
);

-- 7. benchmark_history — comparison benchmarks (SPY, QQQ, TLT, GLD)
-- Used by the Performance page to plot portfolio vs. benchmark returns.
-- Populated by the yfinance ETL layer in update_tearsheet.py.
CREATE TABLE IF NOT EXISTS benchmark_history (
  date          date NOT NULL,
  ticker        text NOT NULL,
  price         numeric NOT NULL,
  PRIMARY KEY (date, ticker)
);

-- 8. portfolio_metrics — computed rolling metrics (Sharpe, volatility, drawdown)
-- Populated by update_tearsheet.py after each digest run. date is UNIQUE;
-- if a day's metrics are recalculated, the row is upserted via ON CONFLICT.
CREATE TABLE IF NOT EXISTS portfolio_metrics (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  date          date NOT NULL UNIQUE,
  pnl_pct       numeric,
  sharpe        numeric,
  volatility    numeric,
  max_drawdown  numeric,
  alpha         numeric,
  cash_pct      numeric,
  total_invested numeric,
  generated_at  timestamptz DEFAULT now()
);

-- ============================================================================
-- Row Level Security — anon = read-only, service_role = full access
-- The anon role (used by the public Next.js dashboard via the anon key) gets
-- SELECT on all tables. Writes require the service_role key (ETL scripts only).
-- ============================================================================

ALTER TABLE daily_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE theses ENABLE ROW LEVEL SECURITY;
ALTER TABLE position_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE nav_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE benchmark_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_metrics ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_read" ON daily_snapshots;
DROP POLICY IF EXISTS "anon_read" ON positions;
DROP POLICY IF EXISTS "anon_read" ON theses;
DROP POLICY IF EXISTS "anon_read" ON position_events;
DROP POLICY IF EXISTS "anon_read" ON documents;
DROP POLICY IF EXISTS "anon_read" ON nav_history;
DROP POLICY IF EXISTS "anon_read" ON benchmark_history;
DROP POLICY IF EXISTS "anon_read" ON portfolio_metrics;

CREATE POLICY "anon_read" ON daily_snapshots FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read" ON positions FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read" ON theses FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read" ON position_events FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read" ON documents FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read" ON nav_history FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read" ON benchmark_history FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read" ON portfolio_metrics FOR SELECT TO anon USING (true);
