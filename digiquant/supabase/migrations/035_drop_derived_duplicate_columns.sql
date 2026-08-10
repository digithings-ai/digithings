-- 035_drop_derived_duplicate_columns.sql — remove derived / duplicate columns (#714)
--
-- Second consolidation pass after 034 (daily_snapshots). Each column here is
-- either a stored value that is trivially derivable at read time, or a literal
-- duplicate of a column on another table. All writers are updated in the same
-- change (see PR) — notably the active digiquant-prices.yml cron, which runs
-- `prices compute-technicals` (bb_middle) and `execute_at_open.py`
-- (weight_change_pct). IF EXISTS guards keep this idempotent.
--
--   price_technicals.bb_middle    == sma_20 (Bollinger middle band == 20-day SMA)
--   price_history.is_trading_day  — deprecated by trading_calendar (ADR-0013 / migration 025);
--                                   never written to price_history, computed via the calendar join
--   position_events.weight_change_pct == weight_pct - prev_weight_pct (computed at read time)
--   positions.contribution_pct    == weight_pct * since_entry_return_pct/100 (computed at read time)
--   portfolio_metrics.cash_pct    duplicates nav_history.cash_pct
--   portfolio_metrics.total_invested -> invested_pct (renamed to match nav_history.invested_pct)

ALTER TABLE price_technicals DROP COLUMN IF EXISTS bb_middle;

ALTER TABLE price_history DROP COLUMN IF EXISTS is_trading_day;

ALTER TABLE position_events DROP COLUMN IF EXISTS weight_change_pct;

ALTER TABLE positions DROP COLUMN IF EXISTS contribution_pct;

-- portfolio_metrics: drop the duplicate cash_pct (auto-drops chk_metrics_cash_range),
-- then rename total_invested -> invested_pct. The invested-range CHECK references the
-- old column name, so drop it first and recreate it against the new name (a plain
-- RENAME would leave a constraint whose stored definition cannot be relied on).
ALTER TABLE portfolio_metrics DROP CONSTRAINT IF EXISTS chk_metrics_invested_range;
ALTER TABLE portfolio_metrics DROP COLUMN IF EXISTS cash_pct;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'portfolio_metrics' AND column_name = 'total_invested'
  ) THEN
    ALTER TABLE portfolio_metrics RENAME COLUMN total_invested TO invested_pct;
  END IF;
END $$;

ALTER TABLE portfolio_metrics ADD CONSTRAINT chk_metrics_invested_range
  CHECK (invested_pct IS NULL OR (invested_pct >= 0 AND invested_pct <= 100));
