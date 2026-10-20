-- 031_fx_economic_calendar_rls.sql
--
-- Run with:  supabase db push   (or paste into the Supabase SQL editor)
--
-- Security advisor ERROR (rls_disabled_in_public): `fx_economic_calendar` was
-- PostgREST-exposed with RLS disabled. It entered prod via an out-of-repo
-- migration (`001_fx_economic_calendar`, 2026-06). Enable RLS + anon read,
-- mirroring the other public reference tables (price_history / trading_calendar);
-- server-side writers use the service role, which bypasses RLS.
--
-- Also pins the mutable search_path on trigger_set_updated_at (advisor WARN
-- function_search_path_mutable). Idempotent.
--
-- Already applied to prod 2026-06-08 via MCP; this file captures it so a clean
-- `supabase db push` reproduces the schema. Refs #524.

ALTER TABLE public.fx_economic_calendar ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS fx_economic_calendar_anon_select ON public.fx_economic_calendar;
CREATE POLICY fx_economic_calendar_anon_select
  ON public.fx_economic_calendar
  FOR SELECT TO anon
  USING (true);

ALTER FUNCTION public.trigger_set_updated_at() SET search_path = '';
