-- 142_house_accounting_status_attribution.sql
--
-- public_accounting_period_status and public_daily_realized_attribution (123)
-- stay security_invoker=false and GRANT SELECT to anon. Anon has no SELECT on
-- the accounting bases, so these projections stay security definer. 123 had no
-- workspace predicate, so a private book's tip period and its realized
-- contribution are published beside the house book.
--
-- Same close as 141's public_finalized_nav: read the post-134 tables
-- (accounting_periods, accounting_contributions, accounting_holdings).
-- Migration 135 dropped the olympus_* compatibility views, so naming those
-- views fails and rolls the file back. Keep security_invoker=false and set
-- security_barrier=true, so a caller WHERE function does not observe a row the
-- house predicate drops. Restrict the published period to the house workspace.
--
-- House id matches 096/110: 6b753576-ced9-5319-9bfa-c5d0aacd9319.
-- Column lists and the credible-tip / children-complete predicates match 123.
-- Does not touch staged cutover 113. Does not replace public_accounting_nav_history
-- (141 already installs that view as security_invoker=true).

CREATE OR REPLACE VIEW public.public_accounting_period_status
WITH (security_invoker = false, security_barrier = true) AS
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
FROM public.accounting_periods p
WHERE p.workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
  AND NOT EXISTS (
      SELECT 1
      FROM public.accounting_periods s
      WHERE s.supersedes_id = p.id
        AND NOT (
            s.status IN ('incomplete', 'failed')
            AND s.opening_equity = 0
            AND s.closing_equity = 0
        )
  )
  AND (
      NOT (
          (p.opening_equity - p.opening_cash) <> 0
          OR (p.closing_equity - p.closing_cash) <> 0
          OR p.net_pnl_total <> 0
          OR p.gross_pnl_total <> 0
      )
      OR EXISTS (
          SELECT 1
          FROM public.accounting_contributions c
          WHERE c.period_id = p.id
      )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM public.accounting_contributions c
      WHERE c.period_id = p.id
        AND c.closing_quantity > 0
        AND NOT EXISTS (
            SELECT 1
            FROM public.accounting_holdings h
            WHERE h.period_id = p.id
              AND upper(h.symbol) = upper(c.symbol)
        )
  );

ALTER VIEW public.public_accounting_period_status SET (security_invoker = false, security_barrier = true);

COMMENT ON VIEW public.public_accounting_period_status IS
  'House-workspace tip-period status (#2599; day_return #2779; children-complete '
  '#2780; credible-tip gate #3767). SECURITY DEFINER, security_barrier=true, so '
  'anon can read the projection without a grant on accounting_periods and a '
  'caller WHERE function cannot observe a dropped row. workspace_id is the house '
  'book only. A superseder voids a tip unless it is an incomplete/failed '
  'zero-equity tombstone. Incomplete child sets are withheld.';

CREATE OR REPLACE VIEW public.public_daily_realized_attribution
WITH (security_invoker = false, security_barrier = true) AS
SELECT
    c.period_date AS date,
    c.symbol AS ticker,
    CASE
        WHEN c.contribution IS NULL THEN NULL
        ELSE round(c.contribution * 100.0, 6)
    END AS contribution_pct,
    CASE
        WHEN p.benchmark_return IS NULL THEN NULL
        ELSE round(p.benchmark_return * 100.0, 6)
    END AS benchmark_return_pct,
    p.opening_equity,
    p.closing_equity,
    'daily_realized_attribution'::text AS contract,
    'final'::text AS period_status
FROM public.accounting_contributions c
JOIN public.accounting_periods p
  ON p.id = c.period_id
 AND p.period_date = c.period_date
WHERE p.workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
  AND p.status = 'final'
  AND cardinality(p.quality_reasons) = 0
  AND NOT EXISTS (
      SELECT 1
      FROM public.accounting_periods s
      WHERE s.supersedes_id = p.id
        AND NOT (
            s.status IN ('incomplete', 'failed')
            AND s.opening_equity = 0
            AND s.closing_equity = 0
        )
  )
  AND (
      NOT (
          (p.opening_equity - p.opening_cash) <> 0
          OR (p.closing_equity - p.closing_cash) <> 0
          OR p.net_pnl_total <> 0
          OR p.gross_pnl_total <> 0
      )
      OR EXISTS (
          SELECT 1
          FROM public.accounting_contributions c2
          WHERE c2.period_id = p.id
      )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM public.accounting_contributions c3
      WHERE c3.period_id = p.id
        AND c3.closing_quantity > 0
        AND NOT EXISTS (
            SELECT 1
            FROM public.accounting_holdings h
            WHERE h.period_id = p.id
              AND upper(h.symbol) = upper(c3.symbol)
        )
  );

ALTER VIEW public.public_daily_realized_attribution SET (security_invoker = false, security_barrier = true);

COMMENT ON VIEW public.public_daily_realized_attribution IS
  'House-workspace realized per-ticker daily contribution (#2599 / #2780) from '
  'finalized accounting tips with complete children under the credible-tip gate '
  '(#3767). SECURITY DEFINER, security_barrier=true. Reads accounting_contributions and '
  'accounting_periods; the published period is the house workspace only. Does '
  'not include current_book_lookback / position_attribution.';

REVOKE ALL ON public.public_accounting_period_status FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.public_daily_realized_attribution FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.public_accounting_period_status TO anon, authenticated;
GRANT SELECT ON public.public_daily_realized_attribution TO anon, authenticated;

GRANT SELECT ON public.public_accounting_period_status TO service_role;
GRANT SELECT ON public.public_daily_realized_attribution TO service_role;
