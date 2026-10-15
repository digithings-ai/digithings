-- 140_house_public_portfolio_positions.sql
--
-- public_portfolio_positions (050) takes the latest date with
-- `date = (SELECT max(date) FROM public.positions)` and no workspace predicate.
-- Migration 139 flipped the view to security_invoker, which does not add that
-- predicate. service_role bypasses RLS (prices-live reads this view with the
-- service key), and an authenticated member's policy is house OR own book
-- (109/117). A later private book therefore becomes the only date the view
-- returns, and the public ticker set is that private book.
--
-- Pin both the outer scan and the max(date) subquery to the house workspace.
-- House id matches 096/110: 6b753576-ced9-5319-9bfa-c5d0aacd9319.
-- Column list is unchanged (050 allowlist). security_invoker stays true.
-- Does not touch staged cutover 113.

CREATE OR REPLACE VIEW public.public_portfolio_positions
WITH (security_invoker = true) AS
SELECT
    date,
    ticker,
    name,
    category,
    sector_bucket,
    weight_pct,
    entry_price,
    entry_date,
    current_price,
    day_change_pct,
    unrealized_pnl_pct,
    since_entry_return_pct,
    metrics_as_of
FROM public.positions
WHERE workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
  AND date = (
      SELECT max(date)
      FROM public.positions
      WHERE workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
  );

ALTER VIEW public.public_portfolio_positions SET (security_invoker = true);

COMMENT ON VIEW public.public_portfolio_positions IS
  'Public digiquant tape (#1462 / #4630): latest house-book performance columns only. '
  'security_invoker=true. workspace_id is pinned to the house workspace on both the '
  'row filter and the max(date) subquery so a later private book cannot replace the '
  'public ticker set (service_role bypasses RLS; authenticated may also see own rows). '
  'SELECT list remains the allowlist (no rationale/pm_notes/thesis fields).';
