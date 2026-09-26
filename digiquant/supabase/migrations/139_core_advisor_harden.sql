-- 139_core_advisor_harden.sql
-- #4630 — clear residual core security-advisor ERROR/WARN where SQL can.
--
-- Scope (core project only; twelve-x Hibp / fx_hub_has_access → digithings-ai/twelve-x#211):
--   1. Flip public_portfolio_positions + public_nav_history to security_invoker=true
--      (base tables already grant anon SELECT; view column lists stay the allowlist).
--   2. Keep accounting + run_* views as intentional SECURITY DEFINER projections
--      (base tables lack anon SELECT; 050/041/137 document the pattern). Refresh COMMENTs.
--   3. Drop atlas_run_health rename-compat view (dashboard reads run_health only).
--   4. REVOKE net schema/function EXECUTE from PUBLIC/anon/authenticated.
--      Cron prices-live-* runs as postgres; do not move pg_net (extrelocatable=false).
--   5. Drop duplicate knowledge_notes GIN on tags (keep idx_knowledge_notes_tags from 118).
--
-- Non-goals: Auth Hibp (dashboard toggle), revoke ensure_my_workspace / my_access,
-- reopen #3461/#4115. Forward-only; db-migrate wraps in a single transaction.

-- ---------------------------------------------------------------------------
-- Part A: safe invoker flips (clears 2× security_definer_view ERROR)
-- ---------------------------------------------------------------------------

ALTER VIEW public.public_portfolio_positions SET (security_invoker = true);
COMMENT ON VIEW public.public_portfolio_positions IS
  'Public digiquant tape (#1462 / #4630): latest-date portfolio performance columns only. '
  'security_invoker=true (#4630) — base positions already grants anon SELECT; the SELECT '
  'list remains the allowlist (no rationale/pm_notes/thesis fields).';

ALTER VIEW public.public_nav_history SET (security_invoker = true);
COMMENT ON VIEW public.public_nav_history IS
  'Public digiquant tape (#1462 / #4630): NAV series + derived day return. '
  'security_invoker=true (#4630) — base nav_history already grants anon SELECT; '
  'column projection stays the allowlist.';

-- ---------------------------------------------------------------------------
-- Part B: accepted DEFINER projections (document; do not flip invoker)
-- ---------------------------------------------------------------------------

COMMENT ON VIEW public.public_finalized_nav IS
  'Accepted SECURITY DEFINER projection (#4630); column list is the allowlist. '
  'Base accounting tables have no anon SELECT — invoker would break the public/accounting tape.';

COMMENT ON VIEW public.public_daily_realized_attribution IS
  'Accepted SECURITY DEFINER projection (#4630); column list is the allowlist. '
  'Base accounting tables have no anon SELECT.';

COMMENT ON VIEW public.public_accounting_nav_history IS
  'Accepted SECURITY DEFINER projection (#4630); column list is the allowlist.';

COMMENT ON VIEW public.public_accounting_period_status IS
  'Accepted SECURITY DEFINER projection (#4630); column list is the allowlist. '
  'Base accounting tables have no anon SELECT.';

COMMENT ON VIEW public.run_health IS
  'Curated anon-readable projection of run_diagnostics (041 / #4471 W3 / #4630). '
  'Accepted SECURITY DEFINER projection (#4630); column list is the allowlist. '
  'Deliberately security_invoker=false — base run_diagnostics has no anon policy/grant.';

COMMENT ON VIEW public.run_event_trace IS
  'Accepted SECURITY DEFINER projection (#4630); column list is the allowlist. '
  'Curated pipeline telemetry over run_events (no anon grant on the base table).';

-- Rename-compat from 137; no app consumer on develop (dashboard uses run_health).
DROP VIEW IF EXISTS public.atlas_run_health;

-- ---------------------------------------------------------------------------
-- Part C: pg_net least privilege (advisor residual; REST does not expose net today)
-- ---------------------------------------------------------------------------
-- Extension remains in public (extrelocatable=false). Do not ALTER EXTENSION SET SCHEMA.

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA net FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA net FROM anon;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA net FROM authenticated;
REVOKE USAGE ON SCHEMA net FROM PUBLIC;
REVOKE USAGE ON SCHEMA net FROM anon;
REVOKE USAGE ON SCHEMA net FROM authenticated;

-- ---------------------------------------------------------------------------
-- Part D: duplicate knowledge_notes tags GIN
-- ---------------------------------------------------------------------------
-- 118 created idx_knowledge_notes_tags. Live also had knowledge_notes_tags_idx
-- (same gin(tags)); drop the duplicate not owned by 118.

DROP INDEX IF EXISTS public.knowledge_notes_tags_idx;
