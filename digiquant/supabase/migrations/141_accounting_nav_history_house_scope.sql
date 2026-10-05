-- 141_accounting_nav_history_house_scope.sql
--
-- public_accounting_nav_history (074/123) is security_invoker=false and
-- GRANT SELECT to anon. As a security-definer view it reads nav_history and
-- public_finalized_nav as the owner, so migration 110's house-only anon policy
-- never applies. A private book's later nav_history date, or its finalized
-- accounting period, is published on the public chart.
--
-- public_finalized_nav stays security definer: anon has no SELECT on the
-- accounting bases (072/134), and the public chart still needs those columns.
-- The definer projection is now house-workspace only, so the bypass cannot
-- publish another book. security_barrier=true forces that predicate to run
-- before a caller's WHERE function, so the function cannot observe a private
-- row the predicate drops. The history view stays security_invoker and does
-- not set security_barrier.
--
-- public_accounting_nav_history becomes security_invoker=true (same posture as
-- the 139 public tape) and the legacy nav_history scan is house-scoped inside
-- the window, so day_return_pct is not computed across another book's rows.
-- Anon SELECT stays: digiquant.io reads this view with the anon key. The
-- defect was definer plus an unfiltered base scan, not the public chart.
--
-- House id matches 096/110: 6b753576-ced9-5319-9bfa-c5d0aacd9319.
-- Column lists match 123. Does not touch staged cutover 113.
--
-- Relation names are the post-134 tables. Migration 134 renamed
-- olympus_accounting_periods, olympus_accounting_contributions, and
-- olympus_accounting_holdings. Migration 135 dropped those old-name
-- compatibility views. CREATE OR REPLACE parses this text, so naming a
-- dropped view fails with "relation does not exist" and the single-transaction
-- apply rolls the history replace back with it. The stored 123 view already
-- follows the renamed tables by OID; this file must name them too.

CREATE OR REPLACE VIEW public.public_finalized_nav
WITH (security_invoker = false, security_barrier = true) AS
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
FROM public.accounting_periods p
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

ALTER VIEW public.public_finalized_nav SET (security_invoker = false, security_barrier = true);

COMMENT ON VIEW public.public_finalized_nav IS
  'Authoritative public NAV from house-workspace finalized accounting tips with '
  'complete children (#2599 / #2780 / #3767). SECURITY DEFINER so anon can read '
  'the projection without a grant on the accounting bases. security_barrier=true. '
  'workspace_id is the house book only — a private period must not appear on the '
  'public tape, and a caller WHERE function must not observe one either. '
  'day_return_pct is equity delta (#2779).';

CREATE OR REPLACE VIEW public.public_accounting_nav_history
WITH (security_invoker = true) AS
SELECT
    stitched.date,
    stitched.nav,
    stitched.cash_pct,
    stitched.invested_pct,
    stitched.day_return_pct,
    stitched.source,
    stitched.contract,
    (
        stitched.prev_source IS NOT NULL
        AND stitched.prev_source IS DISTINCT FROM stitched.source
    ) AS series_seam
FROM (
    SELECT
        u.date,
        u.nav,
        u.cash_pct,
        u.invested_pct,
        u.day_return_pct,
        u.source,
        u.contract,
        lag(u.source) OVER (ORDER BY u.date) AS prev_source
    FROM (
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
            WHERE n.workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
        ) legacy
        WHERE NOT EXISTS (
            SELECT 1
            FROM public.public_finalized_nav f
            WHERE f.date = legacy.date
        )
    ) u
) stitched;

ALTER VIEW public.public_accounting_nav_history SET (security_invoker = true);

COMMENT ON VIEW public.public_accounting_nav_history IS
  'Public NAV series (#2599; seam #3767). security_invoker=true. Finalized house '
  'tips preferred; other dates use house nav_history only (source=legacy_nav_history). '
  'A private book cannot extend or replace the series. series_seam marks a source flip. '
  'Anon SELECT remains — the view no longer runs as the owner over every workspace.';

REVOKE ALL ON public.public_finalized_nav FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.public_accounting_nav_history FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.public_finalized_nav TO anon, authenticated;
GRANT SELECT ON public.public_accounting_nav_history TO anon, authenticated;

GRANT SELECT ON public.public_finalized_nav TO service_role;
GRANT SELECT ON public.public_accounting_nav_history TO service_role;
