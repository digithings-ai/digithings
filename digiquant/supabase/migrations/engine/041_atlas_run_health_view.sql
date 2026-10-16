-- 041_atlas_run_health_view.sql — Curated anon-readable run-health view (Pillar 3D, #726).
--
-- Run with:  supabase db push   (or paste into the Supabase SQL editor / apply via MCP)
--
-- HUMAN GATE: migration 033 deliberately revoked anon SELECT on `atlas_run_diagnostics`
-- (#706/#707) because that table carries operator-internal spend telemetry — `est_cost_usd`,
-- token counts, `error_summary`, and the per-phase `breakdown` JSONB. The Olympus
-- observability dashboard needs *run health* (status, segment success/carry/fail counts,
-- model, timing) but must NEVER see spend. This view is the curation boundary: it projects
-- ONLY the safe columns and is the sole anon-readable surface over the diagnostics table.
--
-- Security model — intentional security-DEFINER view (security_invoker = false):
--   * `atlas_run_diagnostics` has RLS ENABLED with NO anon policy (033) → anon reads of the
--     base table return zero rows. A `security_invoker = true` view would inherit that and
--     also return nothing, so it is explicitly false here: the view runs with its owner's
--     (postgres) rights and bypasses the base-table RLS.
--   * Because the SELECT list omits every sensitive column, anon can read run health through
--     the view yet can never reach cost/tokens/error_summary/breakdown — the projection IS
--     the allowlist. anon still cannot read the base table directly (RLS denies).
--   * Supabase's advisor will flag this as `security_definer_view`; that is expected and
--     accepted here — a curated projection of an RLS-protected table is exactly this pattern.
-- Idempotent (CREATE OR REPLACE).

CREATE OR REPLACE VIEW public.atlas_run_health
WITH (security_invoker = false) AS
SELECT
    run_id,
    run_date,
    run_type,
    model,
    status,
    started_at,
    finished_at,
    duration_s,
    segments_total,
    segments_ok,
    segments_carried,
    segments_failed,
    created_at
FROM public.atlas_run_diagnostics;

COMMENT ON VIEW public.atlas_run_health IS
  'Curated, anon-readable projection of atlas_run_diagnostics for the Olympus observability '
  'dashboard: run status, segment success/carry/fail counts, model, and timing ONLY. '
  'Deliberately excludes est_cost_usd, token counts, error_summary, and the breakdown JSONB '
  '(operator-internal spend telemetry revoked from anon in migration 033). Security-definer by '
  'design so it bypasses the base-table RLS while the column projection enforces the allowlist.';

GRANT SELECT ON public.atlas_run_health TO anon, authenticated;
