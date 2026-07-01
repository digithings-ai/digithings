-- Retire sec_recent_filings: watchlist is ETF-heavy (filings low-signal); issuer EDGAR checks are ad hoc during research/deep dives (see skills), not daily batch ingest.

DROP POLICY IF EXISTS "sec_recent_filings_anon_select" ON sec_recent_filings;
DROP TABLE IF EXISTS sec_recent_filings;
