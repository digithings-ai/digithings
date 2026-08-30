-- ============================================================================
-- STAGED — CUTOVER-GATED — NOT AUTO-APPLIED
-- ============================================================================
-- Filename (when promoted): NNN_drop_anon_read_cutover.sql
--   where NNN = the then-next free prefix under digiquant/supabase/migrations/
--   (after 096–105 have landed on the deploy target; check olympus_schema_migrations).
--
-- WHY THIS PATH IS INERT TODAY
--   .github/workflows/db-migrate.yml applies with:
--     find digiquant/supabase/migrations -maxdepth 1 -name '*.sql' | sort
--   digiquant/scripts/atlas/verify-supabase-migrations.sh uses the same
--   -maxdepth 1 glob. Subdirectories are never listed, never ledger-keyed, and
--   never EXECUTED. This file lives under migrations/cutover/ so a merge to
--   main that only adds it may *trigger* the workflow (paths filter is
--   migrations/**) but the apply loop finds zero new top-level files → no DDL.
--   Do NOT move this file to the migrations/ root until cutover.
--
-- HOW TO APPLY (human, at cutover — never auto)
--   1. Confirm preconditions below.
--   2. cp this file to digiquant/supabase/migrations/<next>_drop_anon_read_cutover.sql
--      on a short-lived cutover branch; open PR → merge → promote to main
--      (db-migrate.yml + production environment approval) OR run manually via
--      psql against core (see docs/agent-backlog/kairos-tenancy/DEPLOYMENT.md).
--   3. Record the basename in olympus_schema_migrations (db-migrate does this).
--
-- CUTOVER PRECONDITIONS (all required before rename/apply)
--   * T1 flag flipped on digiquant.io Cloudflare Pages:
--       NEXT_PUBLIC_OLYMPUS_AUTH=1  (rebuild + deploy Olympus static export)
--   * Supabase Auth providers enabled on core (Google + GitHub) and redirect
--     URLs include https://digiquant.io/olympus/auth/callback/
--   * Cloudflare Access decision executed (D7): remove Access from production
--     /olympus/*; keep Access on staging only
--   * Migrations 096–105 applied on core (workspaces + RLS, vault, Stripe,
--     broker mirror, notification_prefs, BYOK, documents.workspace_id)
--   * Authenticated own-workspace policies from 098 (+ T4 documents policy)
--     already live — this file only removes/narrows anon, it does not replace
--     authenticated access
--
-- SPEC BINDING
--   Privacy boundary: docs/superpowers/specs/2026-08-29-kairos-tenancy-implementation-spec.md §2
--     Private / workspace-scoped → DROP anon SELECT (or narrow documents)
--     Shared market / research corpus → KEEP anon SELECT (justify per table)
--   T0 deferred this drop to "T1's release train"; T1 shipped flag-gated UI only.
--   This is that missing migration — preparation artifact only until cutover.
--
-- INVENTORY (every CREATE POLICY … TO anon in migration history)
--   Status: LIVE = still present on a current table; DROPPED = prior migration
--   already removed it; TABLE_GONE = relation dropped (IF EXISTS no-op here).
--
--   | Policy | Table | Origin | Cutover action |
--   |--------|-------|--------|----------------|
--   | anon_read | daily_snapshots | 001/006/011 | KEEP — house research digest (shared corpus) |
--   | anon_read | positions | 001 | DROP — private book |
--   | anon_read | theses | 001 | KEEP — research theses (shared) |
--   | anon_read | position_events | 001 | DROP — private book |
--   | anon_read | documents | 001/006/011 | NARROW — drop blanket; house+system only (105) |
--   | anon_read | nav_history | 001 | DROP — private NAV |
--   | anon_read | benchmark_history | 001 | TABLE_GONE (010 dropped table) — IF EXISTS no-op |
--   | anon_read | portfolio_metrics | 001 | DROP — private metrics |
--   | price_history_anon_select | price_history | 005 | KEEP — shared market OHLCV |
--   | price_technicals_anon_select | price_technicals | 007 | KEEP — shared technicals |
--   | macro_series_observations_anon_select | macro_series_observations | 015 | KEEP — shared macro |
--   | sec_recent_filings_anon_select | sec_recent_filings | 016 | DROPPED in 017 |
--   | thesis_vehicles_anon_select | thesis_vehicles | 024 | KEEP — research |
--   | deliberation_sessions_anon_select | deliberation_sessions | 024 | KEEP — research |
--   | deliberation_rounds_anon_select | deliberation_rounds | 024 | KEEP — research |
--   | analyst_coverage_anon_select | analyst_coverage | 024 | KEEP — research |
--   | deep_dive_triggers_anon_select | deep_dive_triggers | 024 | KEEP — research audit |
--   | trading_calendar_anon_select | trading_calendar | 025 | KEEP — venue calendar |
--   | decision_log_anon_select | decision_log | 026 | KEEP — analyst decision narrative (shared) |
--   | fx_economic_calendar_anon_select | fx_economic_calendar | 031 | KEEP — macro calendar |
--   | atlas_run_diagnostics_anon_select | atlas_run_diagnostics | 032 | DROPPED in 033 |
--   | position_attribution_anon_select | position_attribution | 040 | renamed → current_book_lookback (073) |
--   | current_book_lookback_anon_select | current_book_lookback | 073 | DROP — book-weight diagnostic (private) |
--   | onchain_cohort_positioning_anon_select | onchain_cohort_positioning | 042 | KEEP — shared research |
--   | strategies_anon_select | strategies | 046 | DROPPED in 051 |
--   | strategy_signals_anon_select | strategy_signals | 046 | DROPPED in 051 |
--   | strategy_trades_anon_select | strategy_trades | 046 | DROPPED in 051 |
--   | strategy_tearsheets_anon_select | strategy_tearsheets | 046 | KEEP — public strategy tearsheets |
--   | economic_calendar_anon_select | economic_calendar | 047 | KEEP — shared calendar |
--   | architecture_notes_anon_select | architecture_notes | 048 | KEEP — shared docs corpus |
--   | anon_read | instruments | 055 | KEEP — instrument reference |
--   | prices_live_public_read | prices_live | 063 | KEEP — shared live quotes (anon+authenticated) |
--
--   Note: 098 claimed "eight anon_read policies" (the 001 set). The live anon
--   surface is larger — every row above with KEEP/DROP/NARROW. portfolio_ledger_*
--   and olympus_accounting_* base tables never granted anon SELECT (069/072/060).
--
-- PUBLIC VIEWS (GRANT SELECT TO anon — not CREATE POLICY, but privacy-adjacent)
--   After cutover Observer is authenticated (D1). Curated views that expose house
--   weights/NAV to the anon role must not remain publicly readable:
--     public_portfolio_positions, public_nav_history,
--     public_accounting_nav_history, public_finalized_nav,
--     public_daily_realized_attribution, public_accounting_period_status
--   Market-only view public_price_latest stays GRANT-able to anon.
-- ============================================================================

-- Unwrapped on purpose: when promoted, db-migrate.yml wraps the file + ledger
-- INSERT in one --single-transaction psql call. Every statement below is
-- DROP/REVOKE IF EXISTS / CREATE POLICY IF-pattern via DROP+CREATE, so a
-- replay against an already-cut-over database is a no-op, not an error.

-- ============================================================================
-- A. DROP anon policies on private book / portfolio tables
-- ============================================================================

-- positions — private book (spec §2); authenticated own-workspace via 098
DROP POLICY IF EXISTS "anon_read" ON public.positions;

-- position_events — private fills/events; authenticated own-workspace via 098
DROP POLICY IF EXISTS "anon_read" ON public.position_events;

-- nav_history — private NAV; authenticated own-workspace via 098
DROP POLICY IF EXISTS "anon_read" ON public.nav_history;

-- portfolio_metrics — private tearsheet metrics; authenticated own-workspace via 098
DROP POLICY IF EXISTS "anon_read" ON public.portfolio_metrics;

-- current_book_lookback — today's weights × trailing returns (private diagnostic).
-- Legacy name position_attribution_anon_select may linger on rebuilds that never
-- ran 073's rename path; drop both names.
DROP POLICY IF EXISTS current_book_lookback_anon_select ON public.current_book_lookback;
DROP POLICY IF EXISTS position_attribution_anon_select ON public.current_book_lookback;

-- benchmark_history — table removed in 010. DROP POLICY requires the relation;
-- guard so a normal core schema (no table) does not abort the cutover txn.
DO $$
BEGIN
    IF to_regclass('public.benchmark_history') IS NOT NULL THEN
        EXECUTE 'DROP POLICY IF EXISTS "anon_read" ON public.benchmark_history';
    END IF;
END $$;

-- ============================================================================
-- B. documents — NARROW (not blanket DROP)
-- ============================================================================
-- Spec §2 + user cutover brief: house/system research library stays shared;
-- non-house (overlay) rows must not be anon-readable. Requires 105
-- (documents.workspace_id). House / system ids are the 096 seeds.
-- Authenticated access remains the T4 policy authenticated_select_documents.

DROP POLICY IF EXISTS "anon_read" ON public.documents;

CREATE POLICY "anon_read_house_system_documents" ON public.documents
    FOR SELECT TO anon
    USING (
        workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid  -- house
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid  -- system
    );

COMMENT ON POLICY "anon_read_house_system_documents" ON public.documents IS
    'Cutover: anon may read house/system research library rows only; overlay '
    'workspace documents require authenticated membership (T4 policy).';

-- ============================================================================
-- C. KEEP — shared market / research (no DROP; documented for inventory)
-- ============================================================================
-- The following anon policies remain USING (true) by deliberate choice
-- (spec §2 shared / tenant-agnostic). Do not drop them in this file:
--   daily_snapshots.anon_read
--   theses.anon_read
--   price_history_anon_select
--   price_technicals_anon_select
--   macro_series_observations_anon_select
--   thesis_vehicles_anon_select
--   deliberation_sessions_anon_select
--   deliberation_rounds_anon_select
--   analyst_coverage_anon_select
--   deep_dive_triggers_anon_select
--   trading_calendar_anon_select
--   decision_log_anon_select
--   fx_economic_calendar_anon_select
--   onchain_cohort_positioning_anon_select
--   strategy_tearsheets_anon_select
--   economic_calendar_anon_select
--   architecture_notes_anon_select
--   instruments.anon_read
--   prices_live_public_read  (anon + authenticated)

-- ============================================================================
-- D. Public views that exposed house book / NAV to anon — revoke
-- ============================================================================
-- These are security_invoker / curated views (050/074/084/085) with GRANT
-- SELECT TO anon. Base-table RLS no longer returns private rows to anon, but
-- the views still project house portfolio/NAV. Observer (D1) is authenticated;
-- revoke anon so an ungated anon key cannot read weights/NAV via the view lane.

REVOKE SELECT ON public.public_portfolio_positions FROM anon;
REVOKE SELECT ON public.public_nav_history FROM anon;
REVOKE SELECT ON public.public_accounting_nav_history FROM anon;
REVOKE SELECT ON public.public_finalized_nav FROM anon;
REVOKE SELECT ON public.public_daily_realized_attribution FROM anon;
REVOKE SELECT ON public.public_accounting_period_status FROM anon;

-- public_price_latest stays GRANT SELECT TO anon (shared market marks).

-- ============================================================================
-- E. VERIFICATION (run as role anon after apply — expect 0 rows each)
-- ============================================================================
-- Paste into SQL editor after SET ROLE anon; (or use the anon key via PostgREST).
-- Every private table must return count = 0. Shared tables may still return rows.
--
-- BEGIN VERIFICATION BLOCK (manual — not executed by this migration)
--
--   SET LOCAL ROLE anon;
--
--   SELECT 'positions' AS t, count(*) FROM public.positions
--   UNION ALL SELECT 'position_events', count(*) FROM public.position_events
--   UNION ALL SELECT 'nav_history', count(*) FROM public.nav_history
--   UNION ALL SELECT 'portfolio_metrics', count(*) FROM public.portfolio_metrics
--   UNION ALL SELECT 'current_book_lookback', count(*) FROM public.current_book_lookback
--   UNION ALL SELECT 'documents_non_house', count(*) FROM public.documents
--     WHERE workspace_id NOT IN (
--       '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid,
--       '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid
--     )
--   UNION ALL SELECT 'public_portfolio_positions', count(*) FROM public.public_portfolio_positions
--   UNION ALL SELECT 'public_nav_history', count(*) FROM public.public_nav_history;
--
--   -- Expect every count = 0.
--   -- Spot-check shared corpus still readable:
--   --   SELECT count(*) > 0 FROM public.price_history;
--   --   SELECT count(*) > 0 FROM public.daily_snapshots;
--   --   SELECT count(*) > 0 FROM public.documents
--   --     WHERE workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid;
--
--   RESET ROLE;
--
-- END VERIFICATION BLOCK
