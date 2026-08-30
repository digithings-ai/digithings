-- 109_authenticated_house_teaser_read.sql
--
-- Hotfix (2026-08-30): Auth Pages (#3231) shipped NEXT_PUBLIC_OLYMPUS_AUTH=1 on
-- Cloudflare Pages. The Olympus supabase-js client then sends a user JWT
-- (role=authenticated). Pre-cutover, house Brief/Portfolio still depend on the
-- classic anon_read surfaces — but those policies are TO anon only.
--
-- Symptom: logged-in users see empty Brief ("Nothing material…") + Portfolio
-- ("No active positions") while house rows still exist (daily_snapshots through
-- 2026-08-28; 323 house positions). PostgREST returns PGRST116/406 on
-- daily_snapshots?.single() because authenticated gets 0 RLS rows.
--
-- Fix (pre-cutover 900 — do NOT run cutover here):
--   1. authenticated SELECT on shared teaser tables that have no workspace_id
--      (daily_snapshots, theses, instruments) — USING (true), matching anon.
--   2. Expand authenticated policies on workspace-scoped house book tables
--      (positions, position_events, nav_history, portfolio_metrics) to also
--      allow the house workspace UUID, mirroring documents (105). Own-workspace
--      membership remains. System workspace is deliberately NOT added on the
--      private book (same stance as 098).
--
-- anon_read policies are untouched. Cutover 900 still owns dropping/narrowing
-- them later. Idempotent DROP POLICY IF EXISTS before CREATE.

-- House workspace id (seeded in 096; same literal as 105 documents policy).
-- 6b753576-ced9-5319-9bfa-c5d0aacd9319

-- ============================================================================
-- Shared teaser tables (no workspace_id column)
-- ============================================================================

DROP POLICY IF EXISTS "authenticated_read_house_teaser" ON public.daily_snapshots;
CREATE POLICY "authenticated_read_house_teaser" ON public.daily_snapshots
    FOR SELECT TO authenticated
    USING (true);

COMMENT ON POLICY "authenticated_read_house_teaser" ON public.daily_snapshots IS
    'Pre-cutover 900: signed-in users may read house daily digests (anon_read '
    'targets the anon role only; Auth Pages JWT would otherwise empty Brief).';

DROP POLICY IF EXISTS "authenticated_read_house_teaser" ON public.theses;
CREATE POLICY "authenticated_read_house_teaser" ON public.theses
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_house_teaser" ON public.instruments;
CREATE POLICY "authenticated_read_house_teaser" ON public.instruments
    FOR SELECT TO authenticated
    USING (true);

-- ============================================================================
-- House book tables (workspace_id) — own membership OR house teaser
-- ============================================================================

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.positions;
CREATE POLICY "authenticated_select_own_workspace" ON public.positions
    FOR SELECT TO authenticated
    USING (
        workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
        OR workspace_id IN (
            SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.position_events;
CREATE POLICY "authenticated_select_own_workspace" ON public.position_events
    FOR SELECT TO authenticated
    USING (
        workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
        OR workspace_id IN (
            SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.nav_history;
CREATE POLICY "authenticated_select_own_workspace" ON public.nav_history
    FOR SELECT TO authenticated
    USING (
        workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
        OR workspace_id IN (
            SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.portfolio_metrics;
CREATE POLICY "authenticated_select_own_workspace" ON public.portfolio_metrics
    FOR SELECT TO authenticated
    USING (
        workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
        OR workspace_id IN (
            SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
        )
    );
