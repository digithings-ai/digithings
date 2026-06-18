-- 040_position_attribution.sql — Per-position performance attribution (Pillar 3B, #726).
--
-- One row per (date, ticker) decomposing the paper book's active return vs the benchmark:
-- contribution (wᵢ·rᵢ), selection (wᵢ·(rᵢ−r_b)), and a synthetic CASH row carrying the
-- cash-drag allocation effect. A single-benchmark model (SPY) — full multi-sector Brinson
-- needs benchmark sector weights we don't have. The dashboard reads this (anon SELECT,
-- mirroring positions/nav_history) for the Attribution/Exposure tab. Computed by
-- scripts/atlas/refresh_attribution.py; idempotent upsert on (date, ticker).

CREATE TABLE IF NOT EXISTS public.position_attribution (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    date                   date NOT NULL,
    ticker                 text NOT NULL,
    sector_bucket          text,
    weight_pct             numeric,
    position_return_pct    numeric,
    benchmark_return_pct   numeric,
    contribution_pct       numeric,
    selection_effect_pct   numeric,
    allocation_effect_pct  numeric,
    total_attribution_pct  numeric,
    metrics_as_of          date,
    created_at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (date, ticker)
);

COMMENT ON TABLE public.position_attribution IS
  'Per-(date,ticker) single-benchmark attribution: contribution wi*ri, selection wi*(ri-rb), '
  'plus a CASH row for cash drag. Sum(total_attribution_pct) reconciles to portfolio_return '
  '- benchmark_return when every holding is priced (Pillar 3B, #726).';
COMMENT ON COLUMN public.position_attribution.contribution_pct IS 'weight × position return (pct points).';
COMMENT ON COLUMN public.position_attribution.selection_effect_pct IS 'weight × (position − benchmark) return.';
COMMENT ON COLUMN public.position_attribution.allocation_effect_pct IS 'Cash-drag effect on the CASH row; 0 for holdings.';
COMMENT ON COLUMN public.position_attribution.total_attribution_pct IS 'selection + allocation; sums to active return.';

CREATE INDEX IF NOT EXISTS position_attribution_date_idx
    ON public.position_attribution (date DESC);
CREATE INDEX IF NOT EXISTS position_attribution_sector_idx
    ON public.position_attribution (sector_bucket, date DESC);

-- Anon SELECT only (read-only dashboard surface), mirroring positions / nav_history.
ALTER TABLE public.position_attribution ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS position_attribution_anon_select ON public.position_attribution;
CREATE POLICY position_attribution_anon_select
    ON public.position_attribution
    FOR SELECT TO anon
    USING (true);
