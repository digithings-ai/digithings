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
-- 110 (pre-cutover, top-level) already narrowed ``anon_read`` on workspace-scoped
-- private books to the house UUID (documents: house+system). This file still
-- DROPs those policies so anon cannot read house weights/NAV after cutover.
-- Do not skip the DROPs because 110 ran.
--
--   1. Confirm preconditions below.
--   2. cp this file to digiquant/supabase/migrations/<next>_drop_anon_read_cutover.sql
--      on a short-lived cutover branch; open PR → merge → promote to main
--      (db-migrate.yml + production environment approval) OR run manually via
--      psql against core (see docs/agent-backlog/kairos-tenancy/DEPLOYMENT.md).
--   3. Record the basename in olympus_schema_migrations (db-migrate does this).
--
-- CUTOVER PRECONDITIONS (required before rename/apply)
--   * T1 flag flipped on digiquant.io Cloudflare Pages:
--       NEXT_PUBLIC_OLYMPUS_AUTH=1  (rebuild + deploy Olympus static export)
--   * Supabase Auth providers enabled on core (Google + GitHub) and redirect
--     URLs include https://digiquant.io/olympus/auth/callback/
--   * Migrations 096–105 applied on core (workspaces + RLS, vault, Stripe,
--     broker mirror, notification_prefs, BYOK, documents.workspace_id)
--   * Authenticated own-workspace policies from 098 (+ T4 documents policy)
--     already live — this file narrows anon AND closes authenticated leak
--     paths for house weights/NAV (governing rule below)
--   * Cloudflare Access remains ON for production /olympus/* through apply +
--     verification (see VERIFICATION block). Access removal is the LAST
--     cutover step — after queries prove zero weight/NAV for anon and free
--     JWT (matches DEPLOYMENT.md §6). Do NOT remove Access before apply.
--
-- GOVERNING RULE (post-cutover)
--   No anon request and no free-tier JWT may retrieve house weights / NAV /
--   fills by any path — base table, jsonb payload, or view. Baseline+ is the
--   paid surface for house_weights_nav / glassbox_economics (T5 matrix).
--
-- SPEC BINDING
--   Privacy boundary: docs/superpowers/specs/2026-08-29-kairos-tenancy-implementation-spec.md §2
--   T5 artifact matrix: §5-T5 / frontend/olympus/lib/entitlements.ts
--     research / narrative → Observer (free, authenticated) + anon research view
--     house_weights_nav / glassbox_economics → Baseline+
--   T0 deferred anon drop to "T1's release train"; T1 shipped flag-gated UI only.
--
-- INVENTORY (every CREATE POLICY … TO anon in migration history)
--
--   | Policy | Table | Origin | Cutover action |
--   |--------|-------|--------|----------------|
--   | anon_read | daily_snapshots | 001/006/011 | DROP — weights in snapshot.portfolio + digest_markdown; research via public_daily_research |
--   | anon_read | positions | 001 | DROP — private book |
--   | anon_read | theses | 001 | KEEP — research theses (shared; T5 research) |
--   | anon_read | position_events | 001 | DROP — private book / fills |
--   | anon_read | documents | 001/006/011 | NARROW — house+system AND NOT weight-bearing keys |
--   | anon_read | nav_history | 001 | DROP — private NAV |
--   | anon_read | benchmark_history | 001 | TABLE_GONE (010) — guarded IF EXISTS |
--   | anon_read | portfolio_metrics | 001 | DROP — private metrics |
--   | price_history_anon_select | price_history | 005 | KEEP — shared market OHLCV |
--   | price_technicals_anon_select | price_technicals | 007 | KEEP — shared technicals |
--   | macro_series_observations_anon_select | macro_series_observations | 015 | KEEP — shared macro |
--   | sec_recent_filings_anon_select | sec_recent_filings | 016 | DROPPED in 017 |
--   | thesis_vehicles_anon_select | thesis_vehicles | 024 | KEEP — research |
--   | deliberation_sessions_anon_select | deliberation_sessions | 024 | KEEP — Hermes narrative (T5) |
--   | deliberation_rounds_anon_select | deliberation_rounds | 024 | KEEP — Hermes narrative |
--   | analyst_coverage_anon_select | analyst_coverage | 024 | KEEP — research |
--   | deep_dive_triggers_anon_select | deep_dive_triggers | 024 | KEEP — research audit |
--   | trading_calendar_anon_select | trading_calendar | 025 | KEEP — venue calendar |
--   | decision_log_anon_select | decision_log | 026 | KEEP — Atlas analyst narrative (T5 research/narrative; no weight_pct columns — stance/action prose only; not house_weights_nav) |
--   | fx_economic_calendar_anon_select | fx_economic_calendar | 031 | KEEP — macro calendar |
--   | atlas_run_diagnostics_anon_select | atlas_run_diagnostics | 032 | DROPPED in 033 |
--   | position_attribution_anon_select | position_attribution | 040 | renamed → current_book_lookback (073) |
--   | current_book_lookback_anon_select | current_book_lookback | 073 | DROP — book-weight diagnostic |
--   | onchain_cohort_positioning_anon_select | onchain_cohort_positioning | 042 | KEEP — shared research |
--   | strategies_anon_select | strategies | 046 | DROPPED in 051 |
--   | strategy_signals_anon_select | strategy_signals | 046 | DROPPED in 051 |
--   | strategy_trades_anon_select | strategy_trades | 046 | DROPPED in 051 |
--   | strategy_tearsheets_anon_select | strategy_tearsheets | 046 | KEEP — intentional delayed public strategy-store surface (051 kept tearsheets when locking live signals/trades; not the Olympus house book; digiquant.io strategy pages, not T5 house_weights_nav) |
--   | economic_calendar_anon_select | economic_calendar | 047 | KEEP — shared calendar |
--   | architecture_notes_anon_select | architecture_notes | 048 | KEEP — shared docs corpus |
--   | anon_read | instruments | 055 | KEEP — instrument reference |
--   | prices_live_public_read | prices_live | 063 | KEEP — shared live quotes |
--
-- WEIGHT-BEARING document_key denylist (publishers audited 2026-08-30)
--   pm-rebalance              — Hermes H8/H9; recommended_portfolio / target_pct
--   rebalance-decision.json   — legacy PM rebalance_table / weights
--   commit-run/%              — H9 commit manifests (weights_fingerprint / book)
--   digest / digest-delta     — may embed snapshot.portfolio; research via view
--   (pm-direction-memo KEEP — H7 direction/conviction only; no weight fields)
-- ============================================================================

-- Unwrapped on purpose: when promoted, db-migrate.yml wraps the file + ledger
-- INSERT in one --single-transaction psql call. Replay-safe throughout.

-- ============================================================================
-- A. DROP anon policies on private book / portfolio tables
-- ============================================================================

DROP POLICY IF EXISTS "anon_read" ON public.positions;
DROP POLICY IF EXISTS "anon_read" ON public.position_events;
DROP POLICY IF EXISTS "anon_read" ON public.nav_history;
DROP POLICY IF EXISTS "anon_read" ON public.portfolio_metrics;

DROP POLICY IF EXISTS current_book_lookback_anon_select ON public.current_book_lookback;
DROP POLICY IF EXISTS position_attribution_anon_select ON public.current_book_lookback;

DO $$
BEGIN
    IF to_regclass('public.benchmark_history') IS NOT NULL THEN
        EXECUTE 'DROP POLICY IF EXISTS "anon_read" ON public.benchmark_history';
    END IF;
END $$;

-- ============================================================================
-- A2. Revert 109 authenticated house-teaser on the private book
-- ============================================================================
-- 109 (pre-cutover hotfix) expanded authenticated_select_own_workspace on
-- positions / position_events / nav_history / portfolio_metrics with the house
-- workspace UUID so Auth Pages JWTs could still read Brief/Portfolio while
-- anon_read stayed TO anon. That is correct until this file runs.
--
-- Post-cutover governing rule: no free-tier JWT (and no anon) may retrieve
-- house weights / NAV / fills from the base tables. Baseline+ house book is
-- the documented follow-up in section E (Edge/BFF or a later GRANT) — this
-- file must not leave 109's house UUID on authenticated SELECT.
-- Restore 098 membership-only policies. Drop the daily_snapshots teaser
-- policy too (section B already REVOKEs SELECT on that table).
-- theses / instruments teasers stay — T5 research, no weight_pct.

DROP POLICY IF EXISTS "authenticated_read_house_teaser" ON public.daily_snapshots;

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.positions;
CREATE POLICY "authenticated_select_own_workspace" ON public.positions
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.position_events;
CREATE POLICY "authenticated_select_own_workspace" ON public.position_events
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.nav_history;
CREATE POLICY "authenticated_select_own_workspace" ON public.nav_history
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.portfolio_metrics;
CREATE POLICY "authenticated_select_own_workspace" ON public.portfolio_metrics
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
        )
    );

COMMENT ON POLICY "authenticated_select_own_workspace" ON public.positions IS
    'Cutover: authenticated SELECT is own-workspace membership only. 109 house '
    'teaser UUID removed so free JWTs cannot read house weights/NAV/fills.';

-- ============================================================================
-- B. daily_snapshots — DROP full-row anon; research via projection view
-- ============================================================================
-- snapshot jsonb (operator digest-snapshot + SnapshotEnvelope shapes) carries
-- portfolio.positions[].weight_pct / proposed_positions[].weight_pct.
-- digest_markdown is rendered with weight tables (render_digest_markdown).
-- No weight-stripped digest variant exists in-repo — exclude the column.

DROP POLICY IF EXISTS "anon_read" ON public.daily_snapshots;

-- Deny PostgREST base-table reads for client roles. Without this, any
-- authenticated policy USING (true) would re-open full jsonb (governing rule).
REVOKE SELECT ON public.daily_snapshots FROM PUBLIC, anon, authenticated;

-- public_daily_research — research/narrative facets only (T5 Observer+).
-- WHY security_invoker = false (definer), not true:
--   Invoker=true requires the caller to hold SELECT on daily_snapshots. Leaving
--   GRANT+RLS on the base table lets PostgREST SELECT snapshot/digest_markdown
--   directly (weight leak). Revoking base GRANT (required) makes an invoker
--   view return permission-denied for anon/authenticated. Definer + curated
--   projection is the same intentional pattern as migration 050's public_*
--   views — the SELECT list IS the allowlist.
CREATE OR REPLACE VIEW public.public_daily_research
WITH (security_invoker = false) AS
SELECT
    ds.date,
    ds.run_type,
    ds.baseline_date,
    ds.created_at,
    CASE
        -- SnapshotEnvelope (atlas_snapshot.v1): strip portfolio_recommendations
        -- prose (may embed target weights); keep other digest narrative.
        WHEN jsonb_typeof(ds.snapshot) = 'object'
             AND (ds.snapshot ? 'digest')
        THEN jsonb_build_object(
            'schema_version', ds.snapshot -> 'schema_version',
            'run_date', ds.snapshot -> 'run_date',
            'run_type', ds.snapshot -> 'run_type',
            'baseline_date', ds.snapshot -> 'baseline_date',
            'published_at', ds.snapshot -> 'published_at',
            'digest', COALESCE(ds.snapshot -> 'digest', '{}'::jsonb)
                      - 'portfolio_recommendations'
        )
        -- Operator digest-snapshot shape: drop portfolio object; strip
        -- narrative.portfolio_recs (PM weight-bearing prose).
        WHEN jsonb_typeof(ds.snapshot) = 'object'
        THEN (ds.snapshot - 'portfolio')
             || jsonb_build_object(
                    'narrative',
                    COALESCE(ds.snapshot -> 'narrative', '{}'::jsonb)
                        - 'portfolio_recs'
                )
        ELSE '{}'::jsonb
    END AS research_snapshot
    -- deliberately omitted: digest_markdown, raw snapshot, id
FROM public.daily_snapshots AS ds;

COMMENT ON VIEW public.public_daily_research IS
    'Cutover research surface for anon + authenticated Observer. Projects '
    'date/run_type/baseline_date/created_at + research-only jsonb (excludes '
    'portfolio / proposed_positions / portfolio_recs / portfolio_recommendations '
    '/ digest_markdown). security_invoker=false by necessity — see migration '
    'header. Dashboard must switch Observer/anon reads here at cutover '
    '(DEPLOYMENT.md §6 frontend follow-up); do not SELECT daily_snapshots.';

REVOKE ALL ON public.public_daily_research FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.public_daily_research TO anon, authenticated;
GRANT SELECT ON public.public_daily_research TO service_role;

-- ============================================================================
-- C. documents — NARROW anon; tier-gate weight-bearing keys for authenticated
-- ============================================================================
-- House/system research library stays shared; overlay rows stay member-only.
-- Weight-bearing keys (audit above) are Baseline+ for authenticated JWTs.

DROP POLICY IF EXISTS "anon_read" ON public.documents;
DROP POLICY IF EXISTS "anon_read_house_system_documents" ON public.documents;

CREATE POLICY "anon_read_house_system_research_documents" ON public.documents
    FOR SELECT TO anon
    USING (
        (
            workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
            OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid
        )
        AND document_key NOT IN (
            'pm-rebalance',
            'rebalance-decision.json',
            'digest',
            'digest-delta'
        )
        AND document_key NOT LIKE 'commit-run/%'
    );

COMMENT ON POLICY "anon_read_house_system_research_documents" ON public.documents IS
    'Cutover: anon may read house/system research docs only; excludes '
    'weight-bearing keys (pm-rebalance, rebalance-decision.json, commit-run/*, '
    'digest, digest-delta). Overlay workspaces denied.';

-- Replace T4 authenticated_select_documents so free JWT cannot read house
-- weight docs. Policy shape (Baseline+ claim on weight-bearing keys):
DROP POLICY IF EXISTS "authenticated_select_documents" ON public.documents;

CREATE POLICY "authenticated_select_documents" ON public.documents
    FOR SELECT TO authenticated
    USING (
        (
            workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
            OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid
            OR workspace_id IN (
                SELECT wm.workspace_id
                FROM public.workspace_members AS wm
                WHERE wm.user_id = auth.uid()
            )
        )
        AND (
            CASE
                WHEN document_key IN (
                    'pm-rebalance',
                    'rebalance-decision.json',
                    'digest',
                    'digest-delta'
                )
                  OR document_key LIKE 'commit-run/%'
                THEN COALESCE(
                    auth.jwt() -> 'app_metadata' ->> 'plan_tier',
                    'free'
                ) IN ('brief', 'desk', 'studio', 'enterprise')
                ELSE TRUE
            END
        )
    );

COMMENT ON POLICY "authenticated_select_documents" ON public.documents IS
    'Cutover: house/system + own-workspace documents; weight-bearing keys '
    'require JWT app_metadata.plan_tier in (brief, desk, studio, enterprise). '
    'Observer (free) uses public_daily_research + non-weight document keys.';

-- ============================================================================
-- D. KEEP — shared market / research (annotated; no DROP)
-- ============================================================================
--   theses.anon_read                         — T5 research
--   price_history / technicals / macro / …   — shared market
--   deliberation_* / analyst_coverage / …    — T5 narrative/research
--   decision_log_anon_select                 — analyst narrative; not weights
--   strategy_tearsheets_anon_select          — delayed public strategy store
--                                              (051); not Olympus house book
--   instruments / prices_live / calendars / architecture_notes

-- ============================================================================
-- E. Public weight/NAV views — REVOKE anon AND authenticated (fail closed)
-- ============================================================================
-- 050/074/084/085 views are security_invoker=false (definer) and project
-- weight_pct / NAV. Observer IS authenticated (D1) — revoking anon alone
-- leaves the Baseline product free. Fail closed for both client roles.
--
-- Follow-up (NOT in this file — honest smaller scope): restore Baseline+
-- access via either (a) Edge/BFF that checks plan_tier then uses service_role,
-- or (b) a later migration that re-GRANTs only after claim-synced RLS / a
-- tier-aware wrapper is proven. Shipping a half-done 901 that re-GRANTs to
-- authenticated without a working claim gate would re-open the free-JWT leak.
-- See DEPLOYMENT.md §6 "Tier-gated house book views".

REVOKE SELECT ON public.public_portfolio_positions FROM PUBLIC, anon, authenticated;
REVOKE SELECT ON public.public_nav_history FROM PUBLIC, anon, authenticated;
REVOKE SELECT ON public.public_accounting_nav_history FROM PUBLIC, anon, authenticated;
REVOKE SELECT ON public.public_finalized_nav FROM PUBLIC, anon, authenticated;
REVOKE SELECT ON public.public_daily_realized_attribution FROM PUBLIC, anon, authenticated;
REVOKE SELECT ON public.public_accounting_period_status FROM PUBLIC, anon, authenticated;

-- public_price_latest stays GRANT SELECT TO anon, authenticated (shared marks).

-- service_role keeps SELECT for runners / Edge Functions that assemble
-- Baseline payloads server-side once the follow-up lands.
GRANT SELECT ON public.public_portfolio_positions TO service_role;
GRANT SELECT ON public.public_nav_history TO service_role;
GRANT SELECT ON public.public_accounting_nav_history TO service_role;
GRANT SELECT ON public.public_finalized_nav TO service_role;
GRANT SELECT ON public.public_daily_realized_attribution TO service_role;
GRANT SELECT ON public.public_accounting_period_status TO service_role;

-- ============================================================================
-- F. VERIFICATION (manual — after apply, BEFORE removing Cloudflare Access)
-- ============================================================================
-- BEGIN VERIFICATION BLOCK (not executed by this migration)
--
--   -- 1) As anon: private tables + weight views + weight docs + base snapshots = 0
--   SET LOCAL ROLE anon;
--   SELECT 'positions' AS t, count(*) FROM public.positions
--   UNION ALL SELECT 'position_events', count(*) FROM public.position_events
--   UNION ALL SELECT 'nav_history', count(*) FROM public.nav_history
--   UNION ALL SELECT 'portfolio_metrics', count(*) FROM public.portfolio_metrics
--   UNION ALL SELECT 'current_book_lookback', count(*) FROM public.current_book_lookback
--   UNION ALL SELECT 'daily_snapshots_base', count(*) FROM public.daily_snapshots
--   UNION ALL SELECT 'public_portfolio_positions', count(*) FROM public.public_portfolio_positions
--   UNION ALL SELECT 'public_nav_history', count(*) FROM public.public_nav_history
--   UNION ALL SELECT 'docs_pm_rebalance', count(*) FROM public.documents
--     WHERE document_key = 'pm-rebalance'
--   UNION ALL SELECT 'docs_non_house', count(*) FROM public.documents
--     WHERE workspace_id NOT IN (
--       '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid,
--       '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid
--     );
--   -- Expect every count = 0.
--   -- Research surface still works:
--   --   SELECT count(*) > 0 FROM public.public_daily_research;
--   --   SELECT research_snapshot ? 'portfolio' AS has_portfolio FROM public.public_daily_research LIMIT 1;
--   --   -- has_portfolio must be false
--   RESET ROLE;
--
--   -- 2) As free-tier JWT (authenticated, app_metadata.plan_tier missing/'free'):
--   --    public_portfolio_positions / public_nav_history / pm-rebalance → 0 rows
--   --    public_daily_research → rows; analyst/* documents → rows
--
--   -- 3) ONLY THEN remove Cloudflare Access from production /olympus/* (D7).
--
-- END VERIFICATION BLOCK
