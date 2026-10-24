-- 052_public_price_latest_day_change.sql — add a day-change to the public price
-- fallback view (#1461).
--
-- Run with:  supabase db push   (or apply via MCP against this project).
--
-- The live ticker's daily-close SEED reads public_price_latest. Migration 050
-- exposed only (ticker, date, close), so a seeded equity/ETF row had no prior
-- close and rendered a flat 0.00% change — the markets tape looked dead whenever
-- the intraday broadcast was idle (weekends, pre-open, before the key was set),
-- while the crypto tape (Coinbase open_24h) always showed a real move. This adds
-- the prior session's close and the derived percent change so the seed shows the
-- last real daily move; a live intraday tick still overwrites the seed when the
-- "prices:live" broadcast is flowing.
--
-- ADDITIVE ONLY: CREATE OR REPLACE appends prev_close + change_pct AFTER the
-- existing columns (ticker, date, close) — same leading projection, so it is a
-- valid in-place replace. Base tables untouched; still security-definer with the
-- same anon/authenticated SELECT grant (the privacy allowlist is unchanged —
-- price_history is already public market data).
--
-- Idempotent (CREATE OR REPLACE + re-runnable REVOKE/GRANT).

CREATE OR REPLACE VIEW public.public_price_latest
WITH (security_invoker = false) AS
WITH ranked AS (
  SELECT
    ticker,
    date,
    close,
    lead(close) OVER (PARTITION BY ticker ORDER BY date DESC) AS prev_close,
    row_number() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
  FROM public.price_history
)
SELECT
  ticker,
  date,
  close,
  prev_close,
  CASE
    WHEN prev_close IS NOT NULL AND prev_close > 0
    THEN round(((close - prev_close) / prev_close) * 100, 4)
    ELSE NULL
  END AS change_pct
FROM ranked
WHERE rn = 1;

COMMENT ON VIEW public.public_price_latest IS
  'Public by user ruling 2026-07-10 (issue #1462): latest daily close per ticker from '
  'price_history, plus the prior close and derived day-change % (#1461). The '
  'daily-close fallback the live ticker seeds from when the prices-live broadcast is '
  'idle (weekends / pre-open) or the market is closed.';

REVOKE ALL ON public.public_price_latest FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.public_price_latest TO anon, authenticated;
