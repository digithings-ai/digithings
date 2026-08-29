-- 085_olympus_accounting_tip_children_complete.sql
-- Gate-1 residual #2780 (WP3 review on #2603): public tip/final views must refuse
-- incomplete child sets, matching Python select_final_period /
-- period_children_complete.
--
-- Defect: migration 074 tip filters used status=final + tip predicate only. A
-- mid-chain crash can leave a FINAL period row with zero contributions while
-- metrics correctly skip it via period_children_complete — public NAV would not.
--
-- Predicate (parity with digiquant.olympus.accounting.io.period_children_complete
-- for persisted period_row selection):
--   * If the period implies invested/PnL activity, at least one contribution row
--     must exist.
--   * Every contribution with closing_quantity > 0 must have a matching holding
--     row (upper(symbol)).
--
-- Replay-safe: CREATE OR REPLACE VIEW only — no base-row rewrites, no new grants
-- on olympus_accounting_* tables. Incorporates 084 day_return equity-delta formula.

-- Shared tip child-completeness fragment (inlined in each view WHERE).

-- 1) Period status tips — still expose non-final tips, but only when children
--    are complete (incomplete child sets are not publishable tip status either).
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
)
  AND (
      -- Idle / zero-activity periods may have empty children.
      NOT (
          (p.opening_equity - p.opening_cash) <> 0
          OR (p.closing_equity - p.closing_cash) <> 0
          OR p.net_pnl_total <> 0
          OR p.gross_pnl_total <> 0
      )
      OR EXISTS (
          SELECT 1
          FROM public.olympus_accounting_contributions c
          WHERE c.period_id = p.id
      )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM public.olympus_accounting_contributions c
      WHERE c.period_id = p.id
        AND c.closing_quantity > 0
        AND NOT EXISTS (
            SELECT 1
            FROM public.olympus_accounting_holdings h
            WHERE h.period_id = p.id
              AND upper(h.symbol) = upper(c.symbol)
        )
  );

COMMENT ON VIEW public.public_accounting_period_status IS
  'Curated tip-period status (#2599; day_return #2779; children-complete #2780). '
  'Includes final and non-final tips when child sets match period_children_complete. '
  'Incomplete child sets are withheld so mid-chain crashes cannot publish a tip. '
  'day_return_pct = (closing_equity − opening_equity) / opening_equity. '
  'Never substitutes lookback.';

-- 2) Finalized NAV — final + clean quality + tip + children complete.
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
          FROM public.olympus_accounting_contributions c
          WHERE c.period_id = p.id
      )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM public.olympus_accounting_contributions c
      WHERE c.period_id = p.id
        AND c.closing_quantity > 0
        AND NOT EXISTS (
            SELECT 1
            FROM public.olympus_accounting_holdings h
            WHERE h.period_id = p.id
              AND upper(h.symbol) = upper(c.symbol)
        )
  );

COMMENT ON VIEW public.public_finalized_nav IS
  'Authoritative public NAV from finalized accounting tips with complete children '
  '(#2599 / #2780). Matches select_final_period / period_children_complete. '
  'day_return_pct is equity delta (#2779). Empty when no complete final tip — '
  'never invents values from lookback or provisional H9.';

-- 3) Realized attribution — same children gate on the joined final tip.
CREATE OR REPLACE VIEW public.public_daily_realized_attribution
WITH (security_invoker = false) AS
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
          FROM public.olympus_accounting_contributions c2
          WHERE c2.period_id = p.id
      )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM public.olympus_accounting_contributions c3
      WHERE c3.period_id = p.id
        AND c3.closing_quantity > 0
        AND NOT EXISTS (
            SELECT 1
            FROM public.olympus_accounting_holdings h
            WHERE h.period_id = p.id
              AND upper(h.symbol) = upper(c3.symbol)
        )
  );

COMMENT ON VIEW public.public_daily_realized_attribution IS
  'Public curated realized per-ticker daily contribution (#2599 / #2780) from '
  'finalized accounting tips with complete children (period_children_complete). '
  'Does not include current_book_lookback / position_attribution. Empty when no '
  'complete final tip — never mix lookback into this series.';

-- public_accounting_nav_history references public_finalized_nav — no rewrite needed
-- once finalized_nav gates on children; recreate for comment clarity only if desired.
-- Grants: re-assert curated SELECT only.
REVOKE ALL ON public.public_accounting_period_status FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.public_finalized_nav FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.public_daily_realized_attribution FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.public_accounting_period_status TO anon, authenticated;
GRANT SELECT ON public.public_finalized_nav TO anon, authenticated;
GRANT SELECT ON public.public_daily_realized_attribution TO anon, authenticated;

GRANT SELECT ON public.public_accounting_period_status TO service_role;
GRANT SELECT ON public.public_finalized_nav TO service_role;
GRANT SELECT ON public.public_daily_realized_attribution TO service_role;
