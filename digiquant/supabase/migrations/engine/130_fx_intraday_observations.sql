-- 130_fx_intraday_observations.sql — Intraday FX OHLC candles for twelve-x trade
-- grading. Both a stop and a target can be touched inside one day, and the daily
-- `macro_series_observations` close cannot order those touches; the twelve-x grader
-- reads this table with the core service key and walks the candles instead.
--
-- Writer: `digiquant prices fetch-fx-intraday` (source='yahoo', one batched
-- yfinance download for the YAHOO_FX_DEFAULT pairs at interval=1h / period=730d,
-- gated in pipeline-digiquant-prices.yml behind `run_writers: true` exactly like
-- the paused fx-refresh fetch-macro step). No browser or anon consumer exists.
--
-- `series_id` values match the daily convention stored in core exactly — verified
-- 2026-09-16 against `macro_series_observations WHERE source='yahoo'`: FX/EUR,
-- FX/GBP, FX/JPY, FX/CAD, FX/AUD, FX/CHF, FX/NZD — so consumers join daily and
-- intraday rows on `(source, series_id)` with no mapping table.
--
-- Upsert key (source, series_id, ts): Yahoo re-serves the trailing partial candle
-- on every refresh, so the writer re-upserts the same (series, ts) row with the
-- settled values. `source` keeps room for a second vendor without a key change.
--
-- RLS POSTURE — READ BEFORE "COMPLETING" THE POLICY SET
-- -----------------------------------------------------
-- RLS is enabled with ZERO policies on purpose, and the omission is the control.
-- Under RLS, absent policy = deny, so only `rolbypassrls` holders (postgres, which
-- owns the table, and service_role) can reach a row. This is STRICTER than
-- `prices_live` (063), which keeps a public read policy because the digiquant.io
-- dashboard renders those quotes; intraday FX candles have no client-facing
-- consumer at all — the only reader is the twelve-x grader on the core service
-- key — so the `prices_live_lease` shape (064: RLS on, no policies, service_role
-- only) is the correct precedent. Do NOT add an anon/authenticated policy.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS, ENABLE ROW LEVEL SECURITY is a no-op
-- when already enabled, and REVOKE/GRANT are re-runnable.

CREATE TABLE IF NOT EXISTS public.fx_intraday_observations (
  source    text NOT NULL,
  series_id text NOT NULL,
  ts        timestamptz NOT NULL,
  open      double precision,
  high      double precision,
  low       double precision,
  close     double precision,
  PRIMARY KEY (source, series_id, ts)
);

ALTER TABLE public.fx_intraday_observations ENABLE ROW LEVEL SECURITY;

-- Belt and braces behind RLS, the convention migrations 050, 052, 057, 060, 063
-- and 064 established: the REVOKE removes the PostgREST table grant so no client
-- role reaches the rows even if a future migration re-widens schema-level
-- privileges. There is no paired GRANT SELECT — see the RLS posture above.
REVOKE ALL ON public.fx_intraday_observations FROM PUBLIC, anon, authenticated;

-- The single writer and the single reader (twelve-x reads with the core service
-- key), stated rather than inherited — same argument as 063's prices_live writer
-- grant. No DELETE: the writer only upserts, and a grader feed that cannot delete
-- rows cannot be silently emptied.
GRANT SELECT, INSERT, UPDATE ON public.fx_intraday_observations TO service_role;

COMMENT ON TABLE public.fx_intraday_observations IS
  'Intraday FX OHLC candles (source=''yahoo'', currently 1h bars) used by twelve-x '
  'trade grading to order stop-vs-target touches inside a single day, which a daily '
  'close cannot express. Written by `digiquant prices fetch-fx-intraday` and read '
  'with the core service key; no anon/authenticated consumer, so RLS is enabled '
  'with zero policies and all client grants are revoked. Upsert key is '
  '(source, series_id, ts); series_id matches the daily macro convention (FX/EUR, ...).';

COMMENT ON COLUMN public.fx_intraday_observations.source IS
  'Data vendor discriminator and part of the primary key. Always ''yahoo'' today; '
  'kept so a second provider''s candles can coexist on the same (series_id, ts) '
  'grid without a schema or key change.';

COMMENT ON COLUMN public.fx_intraday_observations.series_id IS
  'Pair identifier, matching macro_series_observations exactly (FX/EUR, FX/GBP, '
  'FX/JPY, FX/CAD, FX/AUD, FX/CHF, FX/NZD) so daily and intraday rows join on '
  '(source, series_id) with no mapping table. Quote direction is Yahoo''s native '
  'convention per pair (see YAHOO_FX_DEFAULT: FX/JPY is JPY per USD, FX/EUR is '
  'USD per EUR), NOT a single base currency across all rows.';

COMMENT ON COLUMN public.fx_intraday_observations.ts IS
  'Candle OPEN instant, UTC (yfinance indexes intraday bars by their start). '
  'Part of the primary key; the writer normalizes any yfinance timezone to UTC '
  'before upserting. The bar length is not stored — the writer currently emits 1h '
  'bars — so a consumer that needs the candle span must take it from the ingest '
  'configuration.';

COMMENT ON COLUMN public.fx_intraday_observations.open IS
  'Candle open in the pair''s Yahoo-native quote direction (see series_id). '
  'Nullable only defensively: the fetcher drops rows with any missing/non-finite '
  'OHLC value, so writers should never insert a partial candle.';

COMMENT ON COLUMN public.fx_intraday_observations.high IS
  'Candle high, same quote direction as `open`. Carries the stop/target-touch '
  'test when the grader walks a day''s candles.';

COMMENT ON COLUMN public.fx_intraday_observations.low IS
  'Candle low, same quote direction as `open`. Carries the stop/target-touch '
  'test when the grader walks a day''s candles.';

COMMENT ON COLUMN public.fx_intraday_observations.close IS
  'Candle close, same quote direction as `open`. The trailing candle is a moving '
  'value until the bar closes; the (source, series_id, ts) upsert replaces it with '
  'the settled candle on the next refresh.';
