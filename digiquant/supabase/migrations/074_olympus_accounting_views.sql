-- 074_olympus_accounting_views.sql
-- Task 3.4 / #2599 — curated public accounting views + labeled legacy fallback.
--
-- Finding: OLY-REV-007 / OLY-REV-008 / OLY-REV-009
-- Defect: public readers cannot distinguish finalized authoritative periods from
--         provisional H9 / legacy nav_history estimates.
--
-- Intent:
--   * Expose only tip periods (rows nobody supersedes).
--   * Finalized NAV / realized attribution are the preferred public series.
--   * Incomplete / non-final tip periods stay explicit (status + quality_reasons).
--   * Days without a final tip fall through to labeled legacy nav_history rows —
--     never blend sources into one unlabeled value for the same date.
--   * Rollback = repoint adapters to public_nav_history (050) or recreate these
--     views as legacy-only projections; do not delete olympus_accounting_* rows.
--
-- Privacy: base accounting tables stay service_role-only (072). These views are
-- security_definer (security_invoker = false) so anon sees only the projected
-- columns — same pattern as 050_public_portfolio_views.sql.
--
-- Public cutover gate: apply schema anytime; point digiquant.io / Olympus readers
-- only after an approved shadow interval (incl. one rebalance) has zero unexplained
-- reconciliation failures. See SCHEMA.md / ARCHITECTURE.md.

-- Tip predicate: a period nobody supersedes (not merely supersedes_id IS NULL).

-- 1) Explicit period status (final + incomplete/estimated/failed tips).
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
        ELSE round((p.net_pnl_total / p.opening_equity) * 100.0, 6)
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
  'Curated tip-period status (#2599 / Task 3.4). Includes final and non-final tips so '
  'incomplete/estimated/failed days stay explicit. Never substitutes lookback. '
  'quality_reasons are engine codes only — no private lineage payloads.';

-- 2) Finalized NAV series only (authoritative closing equity).
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
        ELSE round((p.net_pnl_total / p.opening_equity) * 100.0, 6)
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
  'Authoritative public NAV from finalized accounting tips only (#2599). Empty when no '
  'final tip exists for a date — never invents values from lookback or provisional H9.';

-- 3) Reader series: finalized preferred; labeled legacy for dates without a final tip.
--    Same calendar date never appears twice; sources are never blended into one value.
CREATE OR REPLACE VIEW public.public_accounting_nav_history
WITH (security_invoker = false) AS
SELECT
    f.date,
    f.nav,
    f.cash_pct,
    f.invested_pct,
    f.day_return_pct,
    f.source,
    f.contract
FROM public.public_finalized_nav f
UNION ALL
SELECT
    legacy.date,
    legacy.nav,
    legacy.cash_pct,
    legacy.invested_pct,
    legacy.day_return_pct,
    'legacy_nav_history'::text AS source,
    'legacy_estimate'::text AS contract
FROM (
    -- Lag over the full legacy series first so excluding finalized dates does not
    -- invent a cross-gap day return from non-adjacent provisional rows.
    SELECT
        n.date,
        n.nav,
        n.cash_pct,
        n.invested_pct,
        round(
            (n.nav / NULLIF(lag(n.nav) OVER (ORDER BY n.date), 0) - 1) * 100,
            4
        ) AS day_return_pct
    FROM public.nav_history n
) legacy
WHERE NOT EXISTS (
    SELECT 1
    FROM public.public_finalized_nav f
    WHERE f.date = legacy.date
);

COMMENT ON VIEW public.public_accounting_nav_history IS
  'Public NAV cutover surface (#2599): finalized accounting tips preferred; dates without '
  'a final tip use labeled legacy nav_history (source=legacy_nav_history, '
  'contract=legacy_estimate). Never combines sources for one date. Rollback: repoint '
  'readers to public_nav_history (050) without deleting accounting rows.';

-- 4) Public realized daily attribution (final tip contributions only).
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
  );

COMMENT ON VIEW public.public_daily_realized_attribution IS
  'Public curated realized per-ticker daily contribution (#2599) from finalized '
  'accounting tips. Does not include current_book_lookback / position_attribution. '
  'Empty when no final tip — readers must use an explicitly labeled legacy fallback, '
  'never mix lookback into this series.';

-- Grants: views only — never GRANT base olympus_accounting_* to anon/authenticated.
REVOKE ALL ON public.public_accounting_period_status FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.public_finalized_nav FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.public_accounting_nav_history FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.public_daily_realized_attribution FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.public_accounting_period_status TO anon, authenticated;
GRANT SELECT ON public.public_finalized_nav TO anon, authenticated;
GRANT SELECT ON public.public_accounting_nav_history TO anon, authenticated;
GRANT SELECT ON public.public_daily_realized_attribution TO anon, authenticated;

GRANT SELECT ON public.public_accounting_period_status TO service_role;
GRANT SELECT ON public.public_finalized_nav TO service_role;
GRANT SELECT ON public.public_accounting_nav_history TO service_role;
GRANT SELECT ON public.public_daily_realized_attribution TO service_role;
