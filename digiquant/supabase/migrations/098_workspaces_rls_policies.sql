-- 098_workspaces_rls_policies.sql
--
-- # score:allow todo
-- Intentional TODO(T5) markers required by T0 binding behavior #4 (tier CHECK in
-- research policies lands in T5's policy pass; do not remove).
--
-- T0 (Kairos + tenancy program, spec §5-T0 / roadmap P2c) — Wave 3 multi-tenant schema,
-- part 3 of 3: new `authenticated` RLS policies. Requires 096 (workspaces table + seeds)
-- and 097 (workspace_id on the private set) to have run first.
--
-- ============================================================================
-- BINDING: this migration does NOT drop, narrow, or replace any existing `anon` policy
-- ============================================================================
-- Every `anon_read` policy created by migration 001 (and every later migration that
-- never granted anon anything beyond that) is untouched by this file. Removing or
-- narrowing anon `USING (true)` access is a SEPARATE, explicitly flagged migration that
-- ships inside T1's release train (Supabase Auth login) — production anon/dashboard
-- behavior does not change one bit until that migration lands. The eight anon_read
-- policies this migration leaves alone (grep confirms these are the only `TO anon`
-- policies in the schema as of migration 097):
--   daily_snapshots, positions, theses, position_events, documents, nav_history,
--   benchmark_history, portfolio_metrics
-- `tests/dq/olympus/test_migration_tenancy.py::test_no_anon_policy_touched` asserts
-- this file contains zero `TO anon` / `FOR ... TO ... anon` policy statements and zero
-- `DROP POLICY` targeting an `anon_read` policy name.
--
-- ============================================================================
-- What this migration adds
-- ============================================================================
-- New `authenticated` SELECT policies, own-workspace-only, on:
--   1. workspaces, workspace_members (T0 binding behavior #4) — an authenticated user
--      must be able to see their own workspace membership to exist as a product at all.
--   2. Every table in the private set that gained `workspace_id` in migration 097:
--      positions, position_events, nav_history, portfolio_metrics,
--      portfolio_ledger_commits, portfolio_ledger_decision_intents,
--      portfolio_ledger_requested_targets, portfolio_ledger_target_adjustments,
--      portfolio_ledger_approved_targets, portfolio_ledger_order_intents,
--      portfolio_ledger_paper_executions, portfolio_ledger_holding_lots,
--      olympus_accounting_periods, olympus_accounting_contributions,
--      olympus_accounting_holdings, olympus_profile_config.
--
-- Every policy uses the same shape: an authenticated user may SELECT a row if their
-- `auth.uid()` is a member of that row's `workspace_id` (via `workspace_members`), OR
-- the row belongs to the system workspace (shared, tenant-agnostic — e.g. the
-- `olympus_profile_config` house-default overlay every workspace reads). The system-
-- workspace branch is a `TODO(T5)`: today it grants ANY authenticated user read access
-- to system-workspace rows with no `plan_tier` gate; T5's policy pass adds the tier
-- CHECK this decision explicitly defers (T0 briefing binding behavior #4: "system
-- workspace research readable per tier — the tier CHECK itself lands in T5's policy
-- pass"). For `positions`/`portfolio_ledger_*`/`olympus_accounting_*` no system-
-- workspace row will ever exist (Groups A/B backfill only to `house`, a `type='user'`
-- workspace), so the branch is inert there today; it is only load-bearing for
-- `olympus_profile_config`'s house-default row.
--
-- `service_role` is untouched throughout — it already bypasses RLS entirely and keeps
-- its existing SELECT/INSERT grants from migrations 069/072/075/096. Nothing in this
-- migration changes Python writer behavior (T0 binding behavior #5): writers use
-- `service_role`, never `authenticated`.
--
-- ============================================================================
-- GRANT SELECT TO authenticated — deliberate, scoped change on 12 tables
-- ============================================================================
-- Migrations 069/072/075 each state "do not GRANT these base tables to
-- anon/authenticated" and `REVOKE ALL ... FROM PUBLIC, anon, authenticated` left
-- `authenticated` with zero grants, not even SELECT, on `portfolio_ledger_*`,
-- `olympus_accounting_*`, and `olympus_profile_config`. That statement predates this
-- migration's workspace-scoping: it was true when "authenticated" meant "any signed-in
-- user can read every row in this schema-tenant-agnostic table", which was correctly
-- refused. Now that a `workspace_id` + RLS policy exists to scope exactly which rows an
-- authenticated user may see, granting SELECT (gated by the policy below, not by the
-- grant) is precisely what T0 binding behavior #4 asks for. This migration is the
-- explicit, reviewed place that changes that stance — called out loudly here rather than
-- silently reversing a prior migration's stated intent. `positions`, `position_events`,
-- `nav_history`, and `portfolio_metrics` already carry a standing SELECT grant to
-- `authenticated` from the Supabase project bootstrap default ACL (preserved by
-- migration 060's `REVOKE ... INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER`,
-- which deliberately left SELECT alone) — no new GRANT is needed for those four; only
-- the policy is new. `workspaces`/`workspace_members` had SELECT revoked from
-- `authenticated` by migration 096 (096 declared the tables + revoke-then-grant
-- baseline, deferring the authenticated policy to this file) — GRANT SELECT here is that
-- deferred half landing.
--
-- No INSERT/UPDATE/DELETE grant is added anywhere in this migration — every table here
-- remains service_role-write-only (append-only triggers on the ledger/accounting/
-- profile_config tables reject mutation regardless of role; `workspaces`/
-- `workspace_members` simply get no write grant to `authenticated` in this WP — T2/T3
-- own the first authenticated write path, e.g. settings PATCH via the BFF).
--
-- ============================================================================
-- Two-JWT RLS test plan (documented per T0 acceptance criteria; executable proof with
-- real Supabase Auth JWTs lands in T1 — this WP only has service_role/no-JWT access to
-- verify against, so here it is pgTAP-style structural assertions instead, in
-- tests/dq/olympus/test_migration_tenancy.py)
-- ============================================================================
-- Given two workspaces A and B (each with one member: user A in workspace A via a
-- workspace_members row, user B in workspace B similarly) and one row of `positions`
-- (or any private-set table) per workspace:
--   1. A request authenticated as user A's JWT (`role=authenticated`, `sub=<user A>`)
--      against PostgREST must return ONLY workspace A's row from a `SELECT * FROM
--      positions` — workspace B's row must not appear.
--   2. Symmetric for user B: only workspace B's row appears.
--   3. A request authenticated as a user with NO `workspace_members` row (freshly
--      signed up, not yet provisioned a workspace) must see zero private-set rows, but
--      DOES see the system workspace's `olympus_profile_config` house-default row (the
--      `OR ... = system workspace` branch).
--   4. The anon key (no JWT / `role=anon`) must see EXACTLY the same eight tables it saw
--      before this migration (`daily_snapshots`, `positions`, `theses`,
--      `position_events`, `documents`, `nav_history`, `benchmark_history`,
--      `portfolio_metrics`, all rows, all workspaces) and NOTHING from
--      `portfolio_ledger_*`/`olympus_accounting_*`/`olympus_profile_config`/`workspaces`/
--      `workspace_members` (unchanged from before this migration — those tables never
--      granted anon anything).
-- Standing up two real `auth.users` + JWTs requires Supabase Auth (T1); until then this
-- plan is the reviewable contract T1's cutover work executes against.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one psql
-- single-transaction call. Every `DROP POLICY IF EXISTS` before `CREATE POLICY` and every
-- `GRANT` is replay-safe.

-- ============================================================================
-- workspaces / workspace_members
-- ============================================================================

GRANT SELECT ON public.workspaces TO authenticated;
GRANT SELECT ON public.workspace_members TO authenticated;

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.workspaces;
CREATE POLICY "authenticated_select_own_workspace" ON public.workspaces
    FOR SELECT TO authenticated
    USING (
        id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR type = 'system' -- TODO(T5): gate by plan_tier once the tier CHECK policy pass lands
    );

DROP POLICY IF EXISTS "authenticated_select_own_membership" ON public.workspace_members;
CREATE POLICY "authenticated_select_own_membership" ON public.workspace_members
    FOR SELECT TO authenticated
    USING (user_id = auth.uid());

-- ============================================================================
-- Group A: positions, position_events, nav_history, portfolio_metrics
-- (already carry a standing SELECT grant to authenticated — see header; no new GRANT)
-- ============================================================================

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.positions;
CREATE POLICY "authenticated_select_own_workspace" ON public.positions
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.position_events;
CREATE POLICY "authenticated_select_own_workspace" ON public.position_events
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.nav_history;
CREATE POLICY "authenticated_select_own_workspace" ON public.nav_history
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.portfolio_metrics;
CREATE POLICY "authenticated_select_own_workspace" ON public.portfolio_metrics
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

-- ============================================================================
-- Group B: portfolio_ledger_* (migration 069) — new GRANT SELECT + policy
-- ============================================================================

GRANT SELECT ON public.portfolio_ledger_commits TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.portfolio_ledger_commits;
CREATE POLICY "authenticated_select_own_workspace" ON public.portfolio_ledger_commits
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

GRANT SELECT ON public.portfolio_ledger_decision_intents TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.portfolio_ledger_decision_intents;
CREATE POLICY "authenticated_select_own_workspace" ON public.portfolio_ledger_decision_intents
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

GRANT SELECT ON public.portfolio_ledger_requested_targets TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.portfolio_ledger_requested_targets;
CREATE POLICY "authenticated_select_own_workspace" ON public.portfolio_ledger_requested_targets
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

GRANT SELECT ON public.portfolio_ledger_target_adjustments TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.portfolio_ledger_target_adjustments;
CREATE POLICY "authenticated_select_own_workspace" ON public.portfolio_ledger_target_adjustments
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

GRANT SELECT ON public.portfolio_ledger_approved_targets TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.portfolio_ledger_approved_targets;
CREATE POLICY "authenticated_select_own_workspace" ON public.portfolio_ledger_approved_targets
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

GRANT SELECT ON public.portfolio_ledger_order_intents TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.portfolio_ledger_order_intents;
CREATE POLICY "authenticated_select_own_workspace" ON public.portfolio_ledger_order_intents
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

GRANT SELECT ON public.portfolio_ledger_paper_executions TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.portfolio_ledger_paper_executions;
CREATE POLICY "authenticated_select_own_workspace" ON public.portfolio_ledger_paper_executions
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

GRANT SELECT ON public.portfolio_ledger_holding_lots TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.portfolio_ledger_holding_lots;
CREATE POLICY "authenticated_select_own_workspace" ON public.portfolio_ledger_holding_lots
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

-- ============================================================================
-- Group B: olympus_accounting_* (migration 072) — new GRANT SELECT + policy
-- ============================================================================

GRANT SELECT ON public.olympus_accounting_periods TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.olympus_accounting_periods;
CREATE POLICY "authenticated_select_own_workspace" ON public.olympus_accounting_periods
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

GRANT SELECT ON public.olympus_accounting_contributions TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.olympus_accounting_contributions;
CREATE POLICY "authenticated_select_own_workspace" ON public.olympus_accounting_contributions
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

GRANT SELECT ON public.olympus_accounting_holdings TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.olympus_accounting_holdings;
CREATE POLICY "authenticated_select_own_workspace" ON public.olympus_accounting_holdings
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

-- ============================================================================
-- Group C: olympus_profile_config (migration 075) — new GRANT SELECT + policy
-- ============================================================================
-- This is the one table in this migration where the system-workspace branch is load-
-- bearing today: the house-default row (is_house_default=true) was backfilled to the
-- SYSTEM workspace in migration 097, specifically so every authenticated user — not
-- just house-workspace members — can read the shared default overlay every workspace's
-- Olympus preflight run reads. Any future overlay row (is_house_default=false) belongs
-- to a real per-user workspace and is only visible to that workspace's members.

GRANT SELECT ON public.olympus_profile_config TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.olympus_profile_config;
CREATE POLICY "authenticated_select_own_workspace" ON public.olympus_profile_config
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

COMMENT ON POLICY "authenticated_select_own_workspace" ON public.olympus_profile_config IS
    'T0 (#5-T0). System-workspace branch is load-bearing here: the house-default row '
    'lives in the system workspace so every tenant reads the shared default overlay. '
    'TODO(T5): gate the system-workspace branch by plan_tier once the tier CHECK policy '
    'pass lands.';
