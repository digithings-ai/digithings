-- 084_olympus_accounting_day_return_pct.sql
-- Gate-1 residual #2779 (WP3 review on #2603): curated day_return_pct must match
-- the engine equity identity (E1 − E0) / E0, which includes cash_pnl.
--
-- Defect: migration 074 used net_pnl_total / opening_equity, omitting cash_pnl
-- (dividends / corporate-action cash). Python metrics already use
-- period_day_return_pct = (closing_equity − opening_equity) / opening_equity.
--
-- Replay-safe: CREATE OR REPLACE VIEW only — no base-row rewrites, no new grants
-- on olympus_accounting_* tables.

-- Tip period status: equity-delta day return (includes cash_pnl via E1 − E0).
CREATE OR REPLACE VIEW public.public_accounting_period_status
WITH (security_invoker = false) AS
SELECT
    p.period_date AS date,
    p.status,
    p.quality_reasons,
    p.opening_equity,
    p.closing_equity,
    CASE
        WHEN p.opening_equity = 0 THEN NULL
        ELSE round(
            ((p.closing_equity - p.opening_equity) / p.opening_equity) * 100.0,
            6
        )
    END AS day_return_pct,
    p.benchmark_symbol,
    CASE
        WHEN p.benchmark_return IS NULL THEN NULL
        ELSE round(p.benchmark_return * 100.0, 6)
    END AS benchmark_return_pct,
    'accounting_period_status'::text AS contract
FROM public.olympus_accounting_periods p
WHERE NOT EXISTS (
    SELECT 1
    FROM public.olympus_accounting_periods s
    WHERE s.supersedes_id = p.id
);

COMMENT ON VIEW public.public_accounting_period_status IS
  'Curated tip-period status (#2599 / Task 3.4; day_return equity delta #2779). '
  'Includes final and non-final tips so incomplete/estimated/failed days stay '
  'explicit. day_return_pct = (closing_equity − opening_equity) / opening_equity '
  '(includes cash_pnl). Never substitutes lookback. quality_reasons are engine '
  'codes only — no private lineage payloads.';

-- Finalized NAV: same equity-delta day return.
CREATE OR REPLACE VIEW public.public_finalized_nav
WITH (security_invoker = false) AS
SELECT
    p.period_date AS date,
    p.closing_equity AS nav,
    CASE
        WHEN p.closing_equity = 0 THEN NULL
        ELSE round((p.closing_cash / p.closing_equity) * 100.0, 4)
    END AS cash_pct,
    CASE
        WHEN p.closing_equity = 0 THEN NULL
        ELSE round((1.0 - (p.closing_cash / p.closing_equity)) * 100.0, 4)
    END AS invested_pct,
    CASE
        WHEN p.opening_equity = 0 THEN NULL
        ELSE round(
            ((p.closing_equity - p.opening_equity) / p.opening_equity) * 100.0,
            6
        )
    END AS day_return_pct,
    'finalized_accounting'::text AS source,
    'finalized_accounting'::text AS contract
FROM public.olympus_accounting_periods p
WHERE p.status = 'final'
  AND cardinality(p.quality_reasons) = 0
  AND NOT EXISTS (
      SELECT 1
      FROM public.olympus_accounting_periods s
      WHERE s.supersedes_id = p.id
  );

COMMENT ON VIEW public.public_finalized_nav IS
  'Authoritative public NAV from finalized accounting tips only (#2599; day_return '
  'equity delta #2779). day_return_pct matches (E1 − E0) / E0 including cash_pnl. '
  'Empty when no final tip exists for a date — never invents values from lookback '
  'or provisional H9.';

-- Grants unchanged from 074 (replay-safe re-assert).
REVOKE ALL ON public.public_accounting_period_status FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.public_finalized_nav FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.public_accounting_period_status TO anon, authenticated;
GRANT SELECT ON public.public_finalized_nav TO anon, authenticated;

GRANT SELECT ON public.public_accounting_period_status TO service_role;
GRANT SELECT ON public.public_finalized_nav TO service_role;
