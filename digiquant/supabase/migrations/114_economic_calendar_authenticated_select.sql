-- 114_economic_calendar_authenticated_select.sql
--
-- Hotfix (2026-08-31): same class as 109. Auth Pages shipped
-- NEXT_PUBLIC_OLYMPUS_AUTH=1, so the dashboard supabase-js client sends a user JWT
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
--
-- Numbering: 114, not 113. Top-level `113_*.sql` is reserved for the staged
-- cutover `migrations/cutover/113_drop_legacy_book_uniques.sql` (human gate;
-- on develop as tests/dq/olympus/test_cutover_113.py). Do not steal 113.
-- Live `core` already has this policy (applied out-of-band). This file is the
-- `main` ledger so `db-migrate.yml` (push to main) can stamp
-- `olympus_schema_migrations`. Develop already has this as #3338 (`db3745b7e`).
-- Related: Auth Pages #3231; supersedes PR #3321 (which used 113).
-- Do not apply cutover 113 or 900. Do not add 096–112 in this hotfix.

DROP POLICY IF EXISTS economic_calendar_authenticated_select ON public.economic_calendar;
CREATE POLICY economic_calendar_authenticated_select ON public.economic_calendar
    FOR SELECT TO authenticated
    USING (true);

COMMENT ON POLICY economic_calendar_authenticated_select ON public.economic_calendar IS
    'Pre-cutover 900: signed-in users may read the shared macro calendar (047 '
    'anon policy targets anon only; Auth Pages JWT would otherwise empty Events).';
