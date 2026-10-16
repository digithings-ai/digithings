-- 005_price_history.sql — Price history table for all watchlist tickers.
-- Single source of truth for OHLCV data; replaces local CSV cache for all computations.
-- Appended daily by scripts/preload-history.py --supabase (or incremental fetch).

CREATE TABLE IF NOT EXISTS price_history (
  date    date    NOT NULL,
  ticker  text    NOT NULL,
  open    numeric,
  high    numeric,
  low     numeric,
  close   numeric NOT NULL,
  volume  bigint,
  PRIMARY KEY (date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date
  ON price_history (ticker, date DESC);

ALTER TABLE price_history ENABLE ROW LEVEL SECURITY;

-- Anon users can read; writes require service_role key.
DROP POLICY IF EXISTS "price_history_anon_select" ON price_history;
CREATE POLICY "price_history_anon_select"
  ON price_history FOR SELECT
  TO anon USING (true);

COMMENT ON TABLE price_history IS
  'Daily OHLCV price data for all watchlist tickers. '
  'Populated by preload-history.py and appended by fetch-quotes.py daily runs.';
