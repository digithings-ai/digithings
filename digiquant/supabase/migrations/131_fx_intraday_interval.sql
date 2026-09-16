-- 131_fx_intraday_interval.sql — add the candle-length discriminator to
-- public.fx_intraday_observations and swap the primary key to include it.
--
-- WHY: migration 130 created the table keyed (source, series_id, ts), which was
-- correct while the writer only emitted 1h bars. A 5m ingest reuses the SAME ts
-- grid — every 5m bar opens at :00/:05/:10 and the 1h bars open at :00 — so a 5m
-- upsert on the old key would overwrite the 1h row at each shared :00 open.
-- `interval` (the yfinance bar length: '1h', '5m', …) separates the two, and the
-- twelve-x grader can then prefer the finest interval that covers a grading
-- window (5m depth is <=60 days, 1h is ~730 days).
--
-- Backfill: every row extant at migration time was written by the 1h-only
-- writer, so `interval` defaults to '1h'. PG 11+ applies the default as
-- metadata only — no table rewrite, no separate UPDATE.
--
-- Writers updated in the same commit (upsert key + interval column):
--   1. digiquant/src/digiquant/data/prices/supabase_writer.py
--      (upsert_fx_intraday_observations, on_conflict)
--   2. digiquant/src/digiquant/cli/prices.py (fetch-fx-intraday rows)
--   3. digiquant/src/digiquant/data/prices/macro_ingest.py (CandleObservation)
--
-- Unwrapped on purpose, matching 130: db-migrate.yml runs the file and its
-- ledger INSERT in one psql --single-transaction call, so the version is
-- recorded iff the DDL commits. Do NOT add an explicit transaction block.
--
-- Idempotent / replay-safe: ADD COLUMN IF NOT EXISTS, and the primary-key swap
-- is guarded on catalog state so a replay neither errors on the missing old key
-- nor on the already-present new one (same shape as 065).

ALTER TABLE public.fx_intraday_observations
    ADD COLUMN IF NOT EXISTS interval text NOT NULL DEFAULT '1h';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.fx_intraday_observations'::regclass
          AND conname = 'fx_intraday_observations_pkey'
          AND pg_get_constraintdef(oid) = 'PRIMARY KEY (source, series_id, ts)'
    ) THEN
        ALTER TABLE public.fx_intraday_observations
            DROP CONSTRAINT fx_intraday_observations_pkey;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.fx_intraday_observations'::regclass
          AND contype = 'p'
    ) THEN
        ALTER TABLE public.fx_intraday_observations
            ADD CONSTRAINT fx_intraday_observations_pkey
            PRIMARY KEY (source, series_id, interval, ts);
    END IF;
END $$;

COMMENT ON TABLE public.fx_intraday_observations IS
  'Intraday FX OHLC candles (source=''yahoo'', interval ''1h'' and ''5m'') used by '
  'twelve-x trade grading to order stop-vs-target touches inside a single day, '
  'which a daily close cannot express. Written by `digiquant prices '
  'fetch-fx-intraday` and read with the core service key; no anon/authenticated '
  'consumer, so RLS is enabled with zero policies and all client grants are '
  'revoked. `ts` is the bar OPEN and `interval` is the bar length, so the same '
  'ts can exist at multiple intervals (a 5m and a 1h bar both open at :00). '
  'Upsert key is (source, series_id, interval, ts); series_id matches the daily '
  'macro convention (FX/EUR, ...).';

COMMENT ON COLUMN public.fx_intraday_observations.interval IS
  'yfinance bar length: ''1h'', ''5m'', … Part of the primary key together with '
  '(source, series_id, ts) so coarser and finer candles coexist on the same ts '
  'grid instead of overwriting each other — 5m bars share their :00 opens with '
  '1h bars. Set from the writer''s --interval flag (single source of truth) and '
  'stored per row so consumers (the twelve-x grader) can prefer the finest '
  'interval that covers a window without trusting the ingest configuration.';

COMMENT ON COLUMN public.fx_intraday_observations.ts IS
  'Candle OPEN instant, UTC (yfinance indexes intraday bars by their start). '
  'Part of the primary key; the writer normalizes any yfinance timezone to UTC '
  'before upserting. The same ts can carry bars of several lengths — see '
  '`interval` for the bar span — so consumers must filter on it.';

COMMENT ON COLUMN public.fx_intraday_observations.close IS
  'Candle close, same quote direction as `open`. The trailing candle is a moving '
  'value until the bar closes; the (source, series_id, interval, ts) upsert '
  'replaces it with the settled candle on the next refresh.';
