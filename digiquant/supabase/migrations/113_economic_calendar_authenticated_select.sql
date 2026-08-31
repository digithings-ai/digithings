-- 113_economic_calendar_authenticated_select.sql
--
-- Hotfix (2026-08-31): same class as 109. Auth Pages shipped
-- NEXT_PUBLIC_OLYMPUS_AUTH=1, so the Olympus supabase-js client sends a user JWT
-- (role=authenticated). `economic_calendar` (047) only has
-- economic_calendar_anon_select TO anon. Logged-in FX Hub Events / Today
-- timeline therefore get 0 rows while the table is full (anon still sees them).
--
-- Symptom: Events tab empty-state copy ("No economic releases have been ingested
-- for the next 14 days") after hard refresh; REST as anon returns the window;
-- SET ROLE authenticated returns 0.
--
-- Fix (pre-cutover 900): authenticated SELECT USING (true), matching anon and
-- prices_live_public_read (063). Shared macro calendar — not house book.
-- anon policy is untouched. Idempotent DROP POLICY IF EXISTS before CREATE.

DROP POLICY IF EXISTS economic_calendar_authenticated_select ON public.economic_calendar;
CREATE POLICY economic_calendar_authenticated_select ON public.economic_calendar
    FOR SELECT TO authenticated
    USING (true);

COMMENT ON POLICY economic_calendar_authenticated_select ON public.economic_calendar IS
    'Pre-cutover 900: signed-in users may read the shared macro calendar (047 '
    'anon policy targets anon only; Auth Pages JWT would otherwise empty Events).';
