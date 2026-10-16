-- 116_authenticated_read_public_reference.sql
--
-- Hotfix (2026-09-02): finish the job 109 started.
--
-- 109 fixed the same defect for three teaser tables (daily_snapshots, theses,
-- instruments) plus the four workspace-scoped house book tables. It did not
-- sweep the rest of the legacy `*_anon_select` surface, so eighteen tables were
-- left with RLS enabled, a SELECT grant to `authenticated`, and **no policy for
-- that role**. Postgres answers "grant present, no policy matched" with zero
-- rows, and PostgREST turns that into a perfectly healthy-looking `200 []`.
-- Nothing logs, nothing 4xxs, and the dashboard renders its empty state.
--
-- Net effect: signed-out visitors saw MORE than signed-in ones. Observed on
-- production the same day, reading as a user-facing data outage:
--
--   * `decision_log`        → Attribution "No resolved directional decisions
--                             are available yet"; Brief's latest decision blank
--   * `price_history`       → Performance benchmark selector empty, no SPY
--     + `price_history_tickers` (security_invoker view over it) comparison
--                             series in the return-contribution chart
--   * `position_attribution` (security_invoker view reading the above)
--                           → Book attribution empty
--
-- Verified against core on 2026-09-02 with `SET LOCAL ROLE authenticated`:
-- decision_log 0/962 rows, price_history 0/…, position_attribution 0/250 —
-- while anon read all of them, and theses/daily_snapshots/positions (the tables
-- 109 did cover) returned in full.
--
-- WHAT THIS DOES
--   Mirror each table's existing anon SELECT policy for `authenticated`. Every
--   one of the eighteen is `USING (true)` today, so the mirror is `USING (true)`.
--
-- WHY THIS IS NOT A WIDENING
--   These rows are already world-readable through the publishable anon key.
--   Granting the signed-in role the same view exposes nothing new; it removes an
--   inversion where authenticating *lost* you access. Tables that are
--   deliberately anon-denied are NOT touched — `atlas_run_diagnostics`
--   (revoke_anon_run_diagnostics), the `checkpoint*` tables
--   (enable_rls_checkpointer_tables), `strategy_calibrations`, and every
--   `portfolio_ledger_*` / `olympus_accounting_*` private book table keep their
--   own-workspace-only posture.
--
-- CUTOVER COUPLING — READ BEFORE PROMOTING 900
--   `migrations/cutover/900_drop_anon_read_cutover.sql` drops the anon policies.
--   These eighteen mirrors are the authenticated half of that story and must be
--   re-scoped (not merely dropped) in the same change: after 900, "public
--   reference data" still needs a signed-in reader, but house-derived rows
--   (`decision_log`, `portfolio_lots`, `portfolio_trades`,
--   `portfolio_holdings_daily`, `current_book_lookback`) must fall under the
--   plan-tier gate rather than `USING (true)`. 900 already carries that rule for
--   the 109 policies; extend its checklist to the names created here.
--
-- Idempotent: DROP POLICY IF EXISTS before CREATE.

-- ============================================================================
-- Market + reference data (not house-derived; public by design)
-- ============================================================================

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.price_history;
CREATE POLICY "authenticated_read_public_reference" ON public.price_history
    FOR SELECT TO authenticated
    USING (true);

COMMENT ON POLICY "authenticated_read_public_reference" ON public.price_history IS
    'Mirrors price_history_anon_select (109 follow-up). Without it a signed-in '
    'session reads zero rows and the Performance benchmark selector renders empty.';

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.price_technicals;
CREATE POLICY "authenticated_read_public_reference" ON public.price_technicals
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.trading_calendar;
CREATE POLICY "authenticated_read_public_reference" ON public.trading_calendar
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.fx_economic_calendar;
CREATE POLICY "authenticated_read_public_reference" ON public.fx_economic_calendar
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.macro_series_observations;
CREATE POLICY "authenticated_read_public_reference" ON public.macro_series_observations
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.onchain_cohort_positioning;
CREATE POLICY "authenticated_read_public_reference" ON public.onchain_cohort_positioning
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.strategy_tearsheets;
CREATE POLICY "authenticated_read_public_reference" ON public.strategy_tearsheets
    FOR SELECT TO authenticated
    USING (true);

-- ============================================================================
-- Research artefacts (same teaser posture as theses in 109)
-- ============================================================================

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.decision_log;
CREATE POLICY "authenticated_read_public_reference" ON public.decision_log
    FOR SELECT TO authenticated
    USING (true);

COMMENT ON POLICY "authenticated_read_public_reference" ON public.decision_log IS
    'Mirrors decision_log_anon_select (109 follow-up). Drives the Attribution '
    'decision scorecard and the Brief latest-decision line; zero rows here is '
    'indistinguishable from an unscored book.';

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.analyst_coverage;
CREATE POLICY "authenticated_read_public_reference" ON public.analyst_coverage
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.thesis_vehicles;
CREATE POLICY "authenticated_read_public_reference" ON public.thesis_vehicles
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.deep_dive_triggers;
CREATE POLICY "authenticated_read_public_reference" ON public.deep_dive_triggers
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.deliberation_sessions;
CREATE POLICY "authenticated_read_public_reference" ON public.deliberation_sessions
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.deliberation_rounds;
CREATE POLICY "authenticated_read_public_reference" ON public.deliberation_rounds
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.architecture_notes;
CREATE POLICY "authenticated_read_public_reference" ON public.architecture_notes
    FOR SELECT TO authenticated
    USING (true);

-- ============================================================================
-- House book projections already public to anon
--
-- These are house-derived. They are mirrored because anon reads them today and
-- an inconsistent split is worse than a consistent one — but they are the rows
-- 900 must re-scope behind the plan-tier gate, not simply re-grant.
-- ============================================================================

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.portfolio_lots;
CREATE POLICY "authenticated_read_public_reference" ON public.portfolio_lots
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.portfolio_trades;
CREATE POLICY "authenticated_read_public_reference" ON public.portfolio_trades
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.portfolio_holdings_daily;
CREATE POLICY "authenticated_read_public_reference" ON public.portfolio_holdings_daily
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "authenticated_read_public_reference" ON public.current_book_lookback;
CREATE POLICY "authenticated_read_public_reference" ON public.current_book_lookback
    FOR SELECT TO authenticated
    USING (true);
