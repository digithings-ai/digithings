-- 033_revoke_anon_run_diagnostics.sql
--
-- Run with:  supabase db push   (or paste into the Supabase SQL editor / apply via MCP)
--
-- Privacy hardening ahead of sharing the Olympus dashboard (#706). The
-- `atlas_run_diagnostics` table (migration 032) carries operator-internal
-- telemetry — LLM spend (`est_cost_usd`), token counts, and the per-phase
-- `breakdown` JSONB — and was granted anon SELECT `USING (true)` "so an Olympus
-- dashboard can query it". The dashboard never does: a repo-wide search shows
-- no frontend read of `atlas_run_diagnostics` (the observability panel reads the
-- `documents`/`daily_snapshots` payloads, not this table). Today that telemetry
-- is therefore world-readable to anyone replaying the bundled anon key while
-- adding zero value to a portfolio viewer.
--
-- Drop the anon SELECT policy so the table is service-role-only (the chain's
-- fail-soft `diagnostics.write_row` uses the service role, which bypasses RLS —
-- writes are unaffected). This is the most-restrictive direction and is
-- frontend-safe. The edge gate (Cloudflare Access) remains the primary control;
-- this is defense-in-depth so cost/token internals never leave the DB even to
-- allow-listed viewers. Idempotent.

DROP POLICY IF EXISTS atlas_run_diagnostics_anon_select ON public.atlas_run_diagnostics;

-- Note: RLS stays ENABLED on the table (migration 032). This drops the anon
-- SELECT *policy* (not a SQL GRANT/REVOKE) — with RLS on and no SELECT policy,
-- anon reads return an empty result set (RLS denies all rows), not a permission
-- error. The service role still has full access (RLS bypass), so the pipeline's
-- diagnostics writes are unaffected.
