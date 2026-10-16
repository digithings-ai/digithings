-- 129_tighten_anon_read.sql
-- Tighten the anon read surface (#4115, security-review follow-up). The anon
-- key ships inside the static-export dashboard, so every anon-readable
-- relation is a public surface. The policies and grants revoked below have no
-- consumer in apps/dashboard or apps/digiquant-web (verified by
-- grep against origin/develop), and nothing else in the repo reads them with
-- the anon key — every remaining writer/reader runs service_role.
--
-- Removed for anon (the 116 authenticated_read_public_reference policies stay,
-- so signed-in dashboard users keep their reads):
--   * architecture_notes          — 048 shared docs corpus; digivault + sync
--                                   scripts use service_role
--   * onchain_cohort_positioning  — 042 shared research; research writers use
--                                   service_role
--   * trading_calendar            — 025 venue calendar; the Python calendar
--                                   readers use service_role, and the
--                                   dashboard has no reference (pinned by
--                                   market-data.test.ts)
--   * olympus_position_events + olympus_position_events_authoritative — views
--                                   with an anon grant and no reader
--   * atlas_run_diagnostics, checkpoints, checkpoint_blobs,
--     checkpoint_writes, checkpoint_migrations, strategy_calibrations —
--     grant-only hygiene: RLS has no anon policy on these, so anon could
--     never read them; drop the stale SELECT grants
--   * knowledge_notes.knowledge_notes_read — a PUBLIC-role policy with no
--     anon/authenticated grant underneath (only postgres + service_role hold
--     privileges); inert, removed to clear the lint
--
-- Deliberately KEPT (do not revoke here):
--   * current_book_lookback — position_attribution is security_invoker=true,
--     so the dashboard reads the attribution view as anon and needs the
--     base-table grant
--   * every public_* view + atlas_run_health + olympus_run_event_trace — the
--     curated anon interface the dashboard reads
--   * analyst_coverage, daily_snapshots, decision_log, documents,
--     economic_calendar, instruments, macro_series_observations, nav_history,
--     portfolio_metrics, position_events, positions, prices_live,
--     strategy_tearsheets, theses, thesis_vehicles — browser-read surfaces
--
-- Supersedes the KEEP rows in cutover/900_drop_anon_read_cutover.sql
-- (architecture_notes_anon_select, onchain_cohort_positioning_anon_select,
-- trading_calendar_anon_select): that file is staged behind the auth cutover
-- and is never executed by the db-migrate loop (maxdepth 1).
-- Rollback: recreate the policies and grants from git history
-- (024 / 025 / 042 / 048 / 073).

DROP POLICY IF EXISTS architecture_notes_anon_select ON public.architecture_notes;
REVOKE SELECT ON public.architecture_notes FROM anon;

DROP POLICY IF EXISTS onchain_cohort_positioning_anon_select ON public.onchain_cohort_positioning;
REVOKE SELECT ON public.onchain_cohort_positioning FROM anon;

DROP POLICY IF EXISTS trading_calendar_anon_select ON public.trading_calendar;
REVOKE SELECT ON public.trading_calendar FROM anon;

REVOKE SELECT ON public.olympus_position_events FROM anon;
REVOKE SELECT ON public.olympus_position_events_authoritative FROM anon;

REVOKE SELECT ON public.atlas_run_diagnostics FROM anon;
REVOKE SELECT ON public.checkpoints FROM anon;
REVOKE SELECT ON public.checkpoint_blobs FROM anon;
REVOKE SELECT ON public.checkpoint_writes FROM anon;
REVOKE SELECT ON public.checkpoint_migrations FROM anon;
REVOKE SELECT ON public.strategy_calibrations FROM anon;

DROP POLICY IF EXISTS knowledge_notes_read ON public.knowledge_notes;
