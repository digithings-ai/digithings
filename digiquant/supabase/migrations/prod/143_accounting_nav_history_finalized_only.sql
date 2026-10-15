-- 143_accounting_nav_history_finalized_only.sql
--
-- public_accounting_nav_history must be ONE NAV scale.
--
-- The view installed by migration 141 (141_accounting_nav_history_house_scope.sql)
-- stitched the house legacy estimate table under the finalized accounting series
-- with a per-date fallback: any date the finalized series did not carry was filled
-- from the legacy estimate. That produced a sawtooth no account ever produced --
-- 30 Sep 121.8 -> 3 Oct 100.19 -> 5 Oct 122.5 -- because the two series are on
-- different scales (~122 finalized vs ~100 legacy estimate). A consumer that
-- plotted the raw nav column drew a ~22% collapse and recovery that never happened.
--
-- It also admitted the first finalized row as an opening-balance period: 26 Aug,
-- NAV 15.13, cash 100%, invested 0, day_return 0. That row is the seed of the
-- accounting series, not a trading day, and it drew a phantom +577.3% move on 27 Aug.
--
-- This migration:
--   * drops the legacy scale and the per-date fallback entirely -- a date the
--     finalized series does not carry is simply absent, never filled;
--   * excludes the seed row, and only the first row of the series, so a later
--     genuine 100%-cash flat day is a real observation and stays;
--   * keeps the column list byte-for-byte so every existing consumer keeps
--     compiling. series_seam stays and is now constant false: one series cannot seam.
--
-- public_finalized_nav is NOT redefined here. It is the security-definer,
-- house-scoped, complete-children projection installed by 141 and it stays the
-- single authority for what counts as a finalized tip. This view reads it.
--
-- The seed row itself is still in accounting_periods. Removing stored production
-- data is Chris's call, not this migration's; this migration stops the view from
-- publishing it.

CREATE OR REPLACE VIEW public.public_accounting_nav_history
WITH (security_invoker = true) AS
SELECT
    seeded.date AS date,
    seeded.nav AS nav,
    seeded.cash_pct AS cash_pct,
    seeded.invested_pct AS invested_pct,
    seeded.day_return_pct AS day_return_pct,
    seeded.source AS source,
    seeded.contract AS contract,
    false::boolean AS series_seam
FROM (
    SELECT
        f.date,
        f.nav,
        f.cash_pct,
        f.invested_pct,
        f.day_return_pct,
        f.source,
        f.contract,
        row_number() OVER (ORDER BY f.date) AS series_position
    FROM public.public_finalized_nav f
) seeded
WHERE NOT (
    seeded.series_position = 1
    AND seeded.cash_pct = 100
    AND seeded.invested_pct = 0
    AND seeded.day_return_pct = 0
);

ALTER VIEW public.public_accounting_nav_history SET (security_invoker = true);

COMMENT ON VIEW public.public_accounting_nav_history IS
  'Public NAV series on the finalized accounting scale only (#2599; seam #3767). '
  'security_invoker=true. One scale: a date the finalized series does not carry is '
  'absent, never filled from the legacy estimate, so the column is safe to plot once '
  'the whole window is finalized; until then plot the base-100 continuity index that '
  'GET /nav-series serves alongside it. The first series row is excluded when it is '
  'the opening balance (cash 100%, invested 0, day_return 0); a later flat cash day is '
  'a real observation and stays. series_seam is now constant false -- one series '
  'cannot seam -- and the column stays so consumers keep compiling. '
  'Anon SELECT remains -- the view does not run as the owner over every workspace.';

REVOKE ALL ON public.public_accounting_nav_history FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.public_accounting_nav_history TO anon, authenticated;

GRANT SELECT ON public.public_accounting_nav_history TO service_role;
