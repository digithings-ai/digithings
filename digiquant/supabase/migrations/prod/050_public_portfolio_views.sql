-- 050_public_portfolio_views.sql — Public portfolio read surface (#1461, #1462).
--
-- Run with:  supabase db push   (or apply via MCP against this project).
--
-- User ruling 2026-07-10 (issue #1462): the Olympus/Atlas portfolio becomes publicly
-- readable — performance metrics ONLY, never research notes. These three views are the
-- entire public read surface for digiquant.io's live portfolio page; the SELECT list of
-- each view IS the allowlist (same curation pattern as 041_atlas_run_health_view.sql).
-- They pair with the prices-live edge function (../functions/prices-live/) — see
-- README.md in this directory for the full two-lane live price feed design.
--
-- ADDITIVE ONLY: three new views + their grants. No FKs, no DROP/ALTER/TRUNCATE of any
-- existing object; base tables untouched.
--
-- Security model — intentional security-DEFINER views (security_invoker = false):
--   * Base tables (positions, nav_history, price_history) keep their existing RLS
--     UNTOUCHED. The views run with their owner's (postgres) rights, so what anon can
--     see is decided by the column projection here, not by base-table policy.
--   * Supabase's advisor will flag `security_definer_view`; that is expected and
--     accepted — a curated projection over RLS-protected tables is exactly this pattern.
--   * Explicitly EXCLUDED from public_portfolio_positions: rationale, pm_notes,
--     thesis_id, conviction, stop_loss_pct, target_pct_gain, horizon_days —
--     research IP and risk parameters stay private.
--
-- NOTE (introspected 2026-07-10, follow-up for #1462): the base tables currently carry a
-- permissive `anon_read` SELECT policy, so `positions` (including rationale/pm_notes) is
-- already anon-readable via PostgREST today. This migration deliberately does not touch
-- base-table RLS (out of scope by ruling); tightening/dropping those `anon_read` policies
-- so the views become the ONLY public surface is the recorded follow-up on #1462.
--
-- Idempotent (CREATE OR REPLACE + re-runnable REVOKE/GRANT).

-- 1) Latest-date portfolio positions — performance columns only.
CREATE OR REPLACE VIEW public.public_portfolio_positions
WITH (security_invoker = false) AS
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
WHERE date = (SELECT max(date) FROM public.positions);

COMMENT ON VIEW public.public_portfolio_positions IS
  'Public by user ruling 2026-07-10 (issue #1462): latest-date portfolio rows, performance '
  'metrics only. Deliberately excludes rationale, pm_notes, thesis_id, conviction, '
  'stop_loss_pct, target_pct_gain, and horizon_days — research IP never leaves the base '
  'table. Consumed by digiquant.io''s live portfolio page (#1461).';

-- 2) NAV history — the public-safe performance series. nav_history has no freeform
--    columns (date, nav, cash_pct, invested_pct, updated_at); updated_at is dropped as
--    operator metadata and a derived day return is added for chart convenience.
CREATE OR REPLACE VIEW public.public_nav_history
WITH (security_invoker = false) AS
SELECT
    date,
    nav,
    cash_pct,
    invested_pct,
    round(
        (nav / NULLIF(lag(nav) OVER (ORDER BY date), 0) - 1) * 100,
        4
    ) AS day_return_pct
FROM public.nav_history;

COMMENT ON VIEW public.public_nav_history IS
  'Public by user ruling 2026-07-10 (issue #1462): portfolio NAV series with allocation '
  'percentages and a derived daily return. No freeform/operator columns. Consumed by '
  'digiquant.io''s performance chart (#1461).';

-- 3) Latest daily close per ticker — the valuation fallback the frontend uses before the
--    FINNHUB_API_KEY secret exists (and outside market hours), so the portfolio page can
--    always price positions from the last pipeline close.
CREATE OR REPLACE VIEW public.public_price_latest
WITH (security_invoker = false) AS
SELECT DISTINCT ON (ticker)
    ticker,
    date,
    close
FROM public.price_history
ORDER BY ticker, date DESC;

COMMENT ON VIEW public.public_price_latest IS
  'Public by user ruling 2026-07-10 (issue #1462): latest daily close per ticker from '
  'price_history. Daily-close fallback for live valuation while the prices-live edge '
  'function is dormant or the market is closed (#1461).';

-- Grants: these three views are the ONLY objects this migration exposes.
REVOKE ALL ON public.public_portfolio_positions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.public_nav_history         FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.public_price_latest        FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.public_portfolio_positions TO anon, authenticated;
GRANT SELECT ON public.public_nav_history         TO anon, authenticated;
GRANT SELECT ON public.public_price_latest        TO anon, authenticated;
