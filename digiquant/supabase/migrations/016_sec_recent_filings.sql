-- Recent SEC EDGAR filings (legacy). Dropped in 017_drop_sec_recent_filings.sql; batch ingest removed from repo.

CREATE TABLE IF NOT EXISTS sec_recent_filings (
  cik              text        NOT NULL,
  ticker           text,
  accession        text        NOT NULL,
  form             text        NOT NULL,
  filing_date      date        NOT NULL,
  report_date      date,
  primary_document text,
  filing_url       text,
  ingested_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (cik, accession)
);

CREATE INDEX IF NOT EXISTS idx_sec_recent_filings_filing_date
  ON sec_recent_filings (filing_date DESC);

CREATE INDEX IF NOT EXISTS idx_sec_recent_filings_ticker_date
  ON sec_recent_filings (ticker, filing_date DESC);

ALTER TABLE sec_recent_filings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "sec_recent_filings_anon_select" ON sec_recent_filings;
CREATE POLICY "sec_recent_filings_anon_select"
  ON sec_recent_filings FOR SELECT
  TO anon USING (true);

COMMENT ON TABLE sec_recent_filings IS
  'Latest EDGAR filings for watchlist tickers (8-K, 4, 13D/G, 10-Q/K, etc.). '
  'Populated by ingest_sec_recent_filings.py; requires SEC_EDGAR_USER_AGENT.';
