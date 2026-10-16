-- 128_db_cleanup_dead_tables.sql
-- Drop seven tables with no runtime consumer and zero rows in prod. The best
-- security is a tight database: every anon-readable surface that nothing reads
-- is attack surface for free.
--
--   portfolio_lots / portfolio_trades / portfolio_holdings_daily
--       Retired with the portfolio ledger cutover (#2065-era). Only references
--       left on develop are tests/dq/research/test_migration_116.py.
--   deep_dive_triggers / deliberation_rounds / deliberation_sessions
--       Retired Hermes deliberation store; only test_migration_024.py /
--       test_migration_116.py reference them.
--   fx_economic_calendar (core)
--       Vestigial: core's economic_calendar is the single source and the
--       twelve-x twin was retired (apps/dashboard/lib/twelve-x/types.ts:130).
--
-- Reads on the market-data drop (127) are unaffected; audit_log and the
-- kairos-tenancy set (job_runs, workspaces, ...) are deliberately NOT here —
-- they belong to that epic's RLS work.
--
-- Supersedes the KEEP rows in cutover/900_drop_anon_read_cutover.sql for
-- deliberation_sessions_anon_select, deliberation_rounds_anon_select,
-- deep_dive_triggers_anon_select and fx_economic_calendar_anon_select. The
-- cutover/ tree is never executed by the db-migrate loop (maxdepth 1), so this
-- header is the record.
--
-- Rollback = restore-from-snapshot; no code path writes these tables.
DROP TABLE IF EXISTS public.deliberation_rounds;
DROP TABLE IF EXISTS public.deep_dive_triggers;
DROP TABLE IF EXISTS public.deliberation_sessions;
DROP TABLE IF EXISTS public.portfolio_lots;
DROP TABLE IF EXISTS public.portfolio_trades;
DROP TABLE IF EXISTS public.portfolio_holdings_daily;
DROP TABLE IF EXISTS public.fx_economic_calendar;
