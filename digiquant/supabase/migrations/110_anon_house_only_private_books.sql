-- 110_anon_house_only_private_books.sql
--
-- Pre-cutover privacy patch (2026-08-31): migration 109 expanded *authenticated*
-- SELECT on the house book to house-UUID OR membership, but left classic
-- `anon_read USING (true)` in place. That made anon *wider* than a signed-in
-- member: overlay `positions` / `documents` / NAV rows would leak to the public
-- role the moment `OLYMPUS_OVERLAY_PERSIST=1` wrote them.
--
-- T1-train deferred rewriting anon_read to cutover 900 (DROP house teaser
-- entirely). 900 is still human-gated and must not run on `core` from this
-- work. This file is the missing *narrowing* step so overlay persist can be
-- enabled without waiting for 900 and without leaking private books:
--
--   1. workspace-scoped private book (`positions`, `position_events`,
--      `nav_history`, `portfolio_metrics`): anon SELECT = house workspace only.
--   2. `documents`: anon SELECT = house OR system (same stance as 105
--      authenticated teaser; overlay workspaces stay member-only).
--
-- Policy *names* stay `anon_read` so cutover 900's `DROP POLICY "anon_read"`
-- still matches. House Brief/Portfolio for unsigned visitors is unchanged
-- (those rows are the house UUID). Shared teasers without workspace_id
-- (`daily_snapshots`, `theses`, `instruments`) are untouched — overlay must
-- not upsert `daily_snapshots` (house-only `UNIQUE(date)`; see publish_phase).
--
-- This is NOT cutover 900: anon can still read house weights/NAV. Do not
-- treat 110 as the T5 free-JWT house-book drop.
--
-- House workspace id (096 seed): 6b753576-ced9-5319-9bfa-c5d0aacd9319
-- System workspace id (096 seed): 1105372f-4109-5815-be5a-21091ccfc8ad
--
-- Idempotent DROP POLICY IF EXISTS before CREATE. Unwrapped; replay-safe.

-- ============================================================================
-- Private book tables — anon house teaser only
-- ============================================================================

DROP POLICY IF EXISTS "anon_read" ON public.positions;
CREATE POLICY "anon_read" ON public.positions
    FOR SELECT TO anon
    USING (workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid);

DROP POLICY IF EXISTS "anon_read" ON public.position_events;
CREATE POLICY "anon_read" ON public.position_events
    FOR SELECT TO anon
    USING (workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid);

DROP POLICY IF EXISTS "anon_read" ON public.nav_history;
CREATE POLICY "anon_read" ON public.nav_history
    FOR SELECT TO anon
    USING (workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid);

DROP POLICY IF EXISTS "anon_read" ON public.portfolio_metrics;
CREATE POLICY "anon_read" ON public.portfolio_metrics
    FOR SELECT TO anon
    USING (workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid);

COMMENT ON POLICY "anon_read" ON public.positions IS
    'Pre-cutover 900: anon may read the house book only. Overlay workspace '
    'rows are member-only. Cutover 900 still DROPs this policy.';

-- ============================================================================
-- documents — anon house + system research library; overlay denied
-- ============================================================================

DROP POLICY IF EXISTS "anon_read" ON public.documents;
CREATE POLICY "anon_read" ON public.documents
    FOR SELECT TO anon
    USING (
        workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid
    );

COMMENT ON POLICY "anon_read" ON public.documents IS
    'Pre-cutover 900: anon may read house+system documents. Overlay workspaces '
    'denied. 900 later drops this and recreates a weight-key denylist variant.';
