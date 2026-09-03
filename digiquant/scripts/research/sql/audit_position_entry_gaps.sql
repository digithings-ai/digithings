-- Find tickers where the latest positions row has no entry_price but an OPEN/ADD event carries a mark.
-- Run in Supabase SQL editor or psql after setting search_path if needed.
--
-- Repair in-app: `python3 scripts/backfill_positions_entry_from_events.py --date YYYY-MM-DD`
-- (uses position_events first, then price_history vs entry_date when set).
--
-- 1) Latest snapshot date per ticker from positions
WITH latest_pos AS (
  SELECT DISTINCT ON (ticker)
    ticker,
    date AS pos_date,
    entry_price,
    entry_date
  FROM positions
  ORDER BY ticker, date DESC
),
priced_events AS (
  SELECT DISTINCT ON (ticker)
    ticker,
    date AS ev_date,
    event,
    price AS event_price
  FROM position_events
  WHERE event IN ('OPEN', 'ADD')
    AND price IS NOT NULL
  ORDER BY ticker, date ASC
)
SELECT
  lp.ticker,
  lp.pos_date,
  lp.entry_price AS positions_entry_price,
  lp.entry_date,
  pe.ev_date AS first_priced_open_add_date,
  pe.event,
  pe.event_price
FROM latest_pos lp
LEFT JOIN priced_events pe ON upper(pe.ticker) = upper(lp.ticker)
WHERE (lp.entry_price IS NULL OR lp.entry_price = 0)
  AND pe.event_price IS NOT NULL
ORDER BY lp.ticker;
