-- 042_onchain_cohort_positioning.sql — On-chain cohort positioning signal (Atlas research, #801).
--
-- One row per (date, market) from Hyperdash's public cohort-summary GraphQL: the long/short
-- notional of the consistently-PROFITABLE ("smart") cohorts vs the consistently-UNPROFITABLE
-- ("crowd") cohorts on each Hyperliquid market (crypto + equity perps), each side's directional
-- bias [0,1], and divergence = smart_bias - crowd_bias in [-1,1] (+1 = smart long / crowd short →
-- smart-money confirm; -1 = smart short / crowd long → distribution / fade). Written best-effort
-- by the Atlas preflight; idempotent upsert on (date, market). Persisted as a time series so the
-- divergence can be backtested as a conviction/risk overlay.

CREATE TABLE IF NOT EXISTS public.onchain_cohort_positioning (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    date                   date NOT NULL,
    market                 text NOT NULL,
    smart_long_notional    numeric,
    smart_short_notional   numeric,
    crowd_long_notional    numeric,
    crowd_short_notional   numeric,
    smart_bias             numeric,
    crowd_bias             numeric,
    divergence             numeric,
    total_traders          integer,
    snapshot_ts            text,
    created_at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (date, market)
);

COMMENT ON TABLE public.onchain_cohort_positioning IS
  'Per-(date,market) Hyperliquid positioning by profitability cohort (Hyperdash scrape): smart '
  '(profitable) vs crowd (rekt) long/short notional + directional bias, and divergence = '
  'smart_bias - crowd_bias. A conviction/risk overlay, never a trade originator (#801).';
COMMENT ON COLUMN public.onchain_cohort_positioning.smart_bias IS
  'smart long / (smart long + smart short), 0..1; null when smart cohorts hold no notional here.';
COMMENT ON COLUMN public.onchain_cohort_positioning.crowd_bias IS
  'crowd long / (crowd long + crowd short), 0..1; null when crowd cohorts hold no notional here.';
COMMENT ON COLUMN public.onchain_cohort_positioning.divergence IS
  'smart_bias - crowd_bias in [-1,1]; +1 smart-money-confirm bullish, -1 distribution/fade.';
COMMENT ON COLUMN public.onchain_cohort_positioning.snapshot_ts IS
  'Hyperdash cohort-summary timestamp for this snapshot (provenance; date is the Atlas run date).';

CREATE INDEX IF NOT EXISTS onchain_cohort_positioning_date_idx
    ON public.onchain_cohort_positioning (date DESC);
CREATE INDEX IF NOT EXISTS onchain_cohort_positioning_market_idx
    ON public.onchain_cohort_positioning (market, date DESC);

-- Anon SELECT only (read-only dashboard surface), mirroring positions / nav_history /
-- position_attribution. Writes go through the service-role key in the Atlas preflight.
ALTER TABLE public.onchain_cohort_positioning ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS onchain_cohort_positioning_anon_select ON public.onchain_cohort_positioning;
CREATE POLICY onchain_cohort_positioning_anon_select
    ON public.onchain_cohort_positioning
    FOR SELECT TO anon
    USING (true);
