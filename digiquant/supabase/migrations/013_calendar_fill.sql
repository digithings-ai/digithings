-- 013_calendar_fill.sql — Add is_trading_day flag to price_history
--
-- price_history now stores one row per calendar day per ticker, not just
-- trading days.  Weekend/holiday rows carry the prior close forward (volume=0).
-- TA computations must filter WHERE is_trading_day = true; display/NAV code
-- can read all rows to show a continuous series.

ALTER TABLE price_history
  ADD COLUMN IF NOT EXISTS is_trading_day boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN price_history.is_trading_day IS
  'True when the exchange was open for this asset on this date. '
  'False rows are forward-filled from the prior trading close (volume=0) '
  'so the frontend can render a continuous daily series. '
  'TA indicators must filter to is_trading_day = true.';
