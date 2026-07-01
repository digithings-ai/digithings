-- 025_trading_calendar.sql — Venue-aware trading calendar table (epic #335)
--
-- A separate trading_calendar table keyed by (date, venue) replaces the
-- is_trading_day flag on price_history (migration 013).  Separating the
-- calendar from price rows eliminates forward-filled weekend/holiday rows,
-- prevents TA indicators from running on synthetic zero-volume data, and
-- correctly handles multi-venue schedules (NYSE vs. CRYPTO vs. FX).
--
-- Populated by the backfill job (issue #337) using the exchange_calendars
-- library.  Venue values: 'NYSE' | 'NASDAQ' | 'CRYPTO' | 'FX'.
-- The is_trading_day column on price_history is deprecated; see ADR-0013.

CREATE TABLE IF NOT EXISTS trading_calendar (
  date           date          NOT NULL,
  venue          text          NOT NULL,   -- 'NYSE' | 'NASDAQ' | 'CRYPTO' | 'FX'
  is_trading_day boolean       NOT NULL,
  reason         text          NULL,       -- 'weekend' | 'holiday:<name>' | 'early_close' | NULL
  created_at     timestamptz   NOT NULL DEFAULT now(),
  PRIMARY KEY (date, venue)
);

-- Partial on trading days only.  venue+date covers both the equality join
-- (ON tc.date=ph.date AND tc.venue='NYSE') and the date-range backfill scan
-- (WHERE venue='NYSE' AND date BETWEEN A AND B).  is_trading_day is redundant
-- as a key column inside a WHERE is_trading_day=true partial index.
CREATE INDEX IF NOT EXISTS trading_calendar_venue_date_idx
  ON trading_calendar (venue, date) WHERE is_trading_day = true;

ALTER TABLE trading_calendar ENABLE ROW LEVEL SECURITY;

-- Anon users can read; writes require service_role key.
DROP POLICY IF EXISTS "trading_calendar_anon_select" ON trading_calendar;
CREATE POLICY "trading_calendar_anon_select"
  ON trading_calendar FOR SELECT
  TO anon USING (true);

COMMENT ON TABLE trading_calendar IS
  'Venue-keyed trading calendar.  One row per (date, venue) covering NYSE, '
  'NASDAQ, CRYPTO (always open), and FX sessions.  Populated by the backfill '
  'job (issue #337) using the exchange_calendars library.  '
  'Join to price_history on date + venue to filter real trading days without '
  'forward-filled rows in the price table.  See ADR-0013.';

COMMENT ON COLUMN trading_calendar.venue IS
  'Exchange / session identifier.  Allowed values: NYSE, NASDAQ, CRYPTO, FX.  '
  'All core-universe US equity ETFs use NYSE regardless of primary listing.';

COMMENT ON COLUMN trading_calendar.reason IS
  'Non-NULL when is_trading_day = false.  Allowed values: weekend, '
  'holiday:<name> (e.g. holiday:Christmas), early_close.  NULL on open days.';
