-- 073_olympus_lookback_vs_realized.sql
-- Task 3.3 / #2598 (OLY-REV-007) — separate current-book lookback from realized attribution.
--
-- Defect: a 21-day calculation using today's weights was stored as position_attribution
-- and could be mistaken for realized period contribution.
--
-- Intent:
--   * Rename the physical diagnostic table to current_book_lookback and label intervals.
--   * Keep position_attribution as a compatibility VIEW over that table (delete after
--     all readers migrate — Task 3.4 / follow-up).
--   * Expose daily_realized_attribution as a security_invoker VIEW over finalized
--     accounting tip contributions (private base tables; service_role only).
--
-- Replay-safe: rename is guarded; views are CREATE OR REPLACE; columns IF NOT EXISTS.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'position_attribution'
          AND table_type = 'BASE TABLE'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'current_book_lookback'
    ) THEN
        ALTER TABLE public.position_attribution RENAME TO current_book_lookback;
    END IF;
END $$;

-- Indexes follow the table rename in PostgreSQL; normalize names when still legacy.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = 'position_attribution_date_idx'
    ) THEN
        ALTER INDEX public.position_attribution_date_idx
            RENAME TO current_book_lookback_date_idx;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = 'position_attribution_sector_idx'
    ) THEN
        ALTER INDEX public.position_attribution_sector_idx
            RENAME TO current_book_lookback_sector_idx;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = 'position_attribution_ticker_date_idx'
    ) THEN
        ALTER INDEX public.position_attribution_ticker_date_idx
            RENAME TO current_book_lookback_ticker_date_idx;
    END IF;
END $$;

ALTER TABLE public.current_book_lookback
    ADD COLUMN IF NOT EXISTS window_start_date date,
    ADD COLUMN IF NOT EXISTS window_end_date date,
    ADD COLUMN IF NOT EXISTS lookback_days integer,
    ADD COLUMN IF NOT EXISTS contract text NOT NULL DEFAULT 'current_book_lookback';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_current_book_lookback_contract'
    ) THEN
        ALTER TABLE public.current_book_lookback
            ADD CONSTRAINT chk_current_book_lookback_contract
            CHECK (contract = 'current_book_lookback');
    END IF;
END $$;

COMMENT ON TABLE public.current_book_lookback IS
  'Diagnostic only (#2598 / OLY-REV-007): trailing-window Brinson-lite using TODAY''s '
  'book weights over a lookback return window (default 21 calendar days). NOT realized '
  'period contribution. Realized daily contribution lives in daily_realized_attribution '
  '(finalized olympus_accounting_* tip). Do not feed these rows into daily pnl_pct or '
  'training labels as realized P&L.';
COMMENT ON COLUMN public.current_book_lookback.window_start_date IS
  'Inclusive start of the price return window (as_of − lookback_days).';
COMMENT ON COLUMN public.current_book_lookback.window_end_date IS
  'Inclusive end of the price return window (as_of / book date).';
COMMENT ON COLUMN public.current_book_lookback.lookback_days IS
  'Calendar-day span used for trailing returns; default 21.';
COMMENT ON COLUMN public.current_book_lookback.contract IS
  'Always current_book_lookback — explicit contract label so readers cannot confuse '
  'this surface with daily_realized_attribution.';

-- Policy was named for the old table; recreate under the new name.
DROP POLICY IF EXISTS position_attribution_anon_select ON public.current_book_lookback;
DROP POLICY IF EXISTS current_book_lookback_anon_select ON public.current_book_lookback;
CREATE POLICY current_book_lookback_anon_select
    ON public.current_book_lookback
    FOR SELECT TO anon
    USING (true);

CREATE INDEX IF NOT EXISTS current_book_lookback_date_idx
    ON public.current_book_lookback (date DESC);
CREATE INDEX IF NOT EXISTS current_book_lookback_sector_idx
    ON public.current_book_lookback (sector_bucket, date DESC);
CREATE INDEX IF NOT EXISTS current_book_lookback_ticker_date_idx
    ON public.current_book_lookback (ticker, date DESC);

-- Legacy alias: same columns as the diagnostic table. Remove after all readers migrate.
CREATE OR REPLACE VIEW public.position_attribution
WITH (security_invoker = true) AS
SELECT
    id,
    date,
    ticker,
    sector_bucket,
    weight_pct,
    position_return_pct,
    benchmark_return_pct,
    contribution_pct,
    selection_effect_pct,
    allocation_effect_pct,
    total_attribution_pct,
    metrics_as_of,
    created_at,
    window_start_date,
    window_end_date,
    lookback_days,
    contract
FROM public.current_book_lookback;

COMMENT ON VIEW public.position_attribution IS
  'DEPRECATED compatibility alias (#2598) for current_book_lookback. Still a 21-day '
  'static-book lookback diagnostic — never realized period contribution. Prefer '
  'current_book_lookback by name; delete this alias after readers migrate (Task 3.4).';

GRANT SELECT ON public.position_attribution TO anon, authenticated, service_role;

-- Realized daily contribution from finalized accounting tip only.
-- Tip = period that nobody supersedes (not merely supersedes_id IS NULL).
-- contribution is a fraction of opening equity; expose pct points for dashboard parity.
-- Private base tables: grant SELECT on the view to service_role only (Task 3.4 curates public).
CREATE OR REPLACE VIEW public.daily_realized_attribution
WITH (security_invoker = true) AS
SELECT
    c.period_date AS date,
    c.symbol AS ticker,
    c.period_id,
    c.net_pnl,
    c.contribution AS contribution_frac,
    CASE
        WHEN c.contribution IS NULL THEN NULL
        ELSE round(c.contribution * 100.0, 6)
    END AS contribution_pct,
    p.benchmark_symbol,
    p.benchmark_return AS benchmark_return_frac,
    CASE
        WHEN p.benchmark_return IS NULL THEN NULL
        ELSE round(p.benchmark_return * 100.0, 6)
    END AS benchmark_return_pct,
    p.opening_equity,
    p.closing_equity,
    'daily_realized_attribution'::text AS contract,
    'final'::text AS period_status
FROM public.olympus_accounting_contributions c
JOIN public.olympus_accounting_periods p
  ON p.id = c.period_id
 AND p.period_date = c.period_date
WHERE p.status = 'final'
  AND cardinality(p.quality_reasons) = 0
  AND NOT EXISTS (
      SELECT 1
      FROM public.olympus_accounting_periods s
      WHERE s.supersedes_id = p.id
  );

COMMENT ON VIEW public.daily_realized_attribution IS
  'Authoritative realized per-ticker daily contribution (#2598 / OLY-REV-007) from the '
  'current finalized olympus_accounting tip. Never includes current_book_lookback / '
  'legacy position_attribution rows. Missing final accounting ⇒ empty (no lookback '
  'substitution). service_role only until Task 3.4 curated public views.';

REVOKE ALL ON public.daily_realized_attribution FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.daily_realized_attribution TO service_role;
