-- 117_security_advisor_now_pile.sql
--
-- # score:allow todo
-- Intentional TODO(T5) markers preserved from migration 098 policy text (tier
-- CHECK deferred; do not remove while recreating policies for initplan).
--
-- #3461 — live core security/performance advisors "Now" pile only.
-- Does NOT touch security_definer public_* views (public tape), pg_net,
-- unused indexes, or cutover 113/900.
--
-- 1. Pin mutable search_path (lint 0011) on listed functions.
-- 2. Revoke anon EXECUTE on workspace-bootstrap SECURITY DEFINER RPCs
--    (lint 0028). Keep authenticated on ensure_my_workspace / my_access.
--    handle_new_auth_user_workspace is trigger-only — no client EXECUTE.
-- 3. Wrap auth.uid() in (select ...) on the 19 authenticated policies that
--    still call it bare (lint 0003). Policy names and USING logic unchanged.
--
-- Leaked-password protection is Auth dashboard config — not SQL; see SCHEMA.md.
-- Unwrapped on purpose: db-migrate.yml applies file + ledger in one transaction.
-- Idempotent ALTER / DROP POLICY IF EXISTS / CREATE POLICY / REVOKE / GRANT.

-- ============================================================================
-- 1. Mutable search_path (lint 0011)
-- ============================================================================

-- Live-only trigger from the knowledge_notes shape (#1087); may be absent on
-- fresh local chains that never imported that out-of-repo DDL.
DO $$
BEGIN
    ALTER FUNCTION public.knowledge_notes_set_updated_at() SET search_path = '';
EXCEPTION
    WHEN undefined_function THEN
        NULL;
END;
$$;

ALTER FUNCTION public.ensure_position_instrument() SET search_path = public;
ALTER FUNCTION public.set_instruments_updated_at() SET search_path = '';

ALTER FUNCTION public.search_architecture_notes(text, integer, text)
    SET search_path = '';

ALTER FUNCTION public.reject_olympus_accounting_mutation() SET search_path = '';
ALTER FUNCTION public.reject_olympus_profile_config_mutation() SET search_path = '';
ALTER FUNCTION public.reject_olympus_research_corpus_mutation() SET search_path = '';

ALTER FUNCTION public.plan_tier_rank(text) SET search_path = '';
ALTER FUNCTION public.max_plan_tier(text, text) SET search_path = '';

-- ============================================================================
-- 2. SECURITY DEFINER EXECUTE grants (lint 0028 / 0029)
-- ============================================================================
-- Supabase grants EXECUTE to anon/authenticated/service_role by default
-- (not only PUBLIC). REVOKE FROM PUBLIC alone does not drop the anon grant
-- (same note as migration 108 for my_access).

REVOKE ALL ON FUNCTION public.ensure_personal_workspace(uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ensure_personal_workspace(uuid)
    TO service_role;

REVOKE ALL ON FUNCTION public.ensure_my_workspace()
    FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.ensure_my_workspace()
    TO authenticated, service_role;

REVOKE ALL ON FUNCTION public.handle_new_auth_user_workspace()
    FROM PUBLIC, anon, authenticated;
-- Trigger fires as owner; no PostgREST / client EXECUTE needed.

REVOKE ALL ON FUNCTION public.my_access() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.my_access() TO authenticated, service_role;

-- ============================================================================
-- 3. RLS initplan — wrap auth.uid() (lint 0003)
-- ============================================================================
-- House / system UUIDs match migrations 096 / 105 / 109.

-- workspaces / workspace_members
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.workspaces;
CREATE POLICY "authenticated_select_own_workspace" ON public.workspaces
    FOR SELECT TO authenticated
    USING (
        id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
        OR type = 'system' -- TODO(T5): gate by plan_tier once the tier CHECK policy pass lands
    );

DROP POLICY IF EXISTS "authenticated_select_own_membership" ON public.workspace_members;
CREATE POLICY "authenticated_select_own_membership" ON public.workspace_members
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

-- Group A private book (109: house teaser OR own membership)
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.positions;
CREATE POLICY "authenticated_select_own_workspace" ON public.positions
    FOR SELECT TO authenticated
    USING (
        workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
        OR workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.position_events;
CREATE POLICY "authenticated_select_own_workspace" ON public.position_events
    FOR SELECT TO authenticated
    USING (
        workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
        OR workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.nav_history;
CREATE POLICY "authenticated_select_own_workspace" ON public.nav_history
    FOR SELECT TO authenticated
    USING (
        workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
        OR workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.portfolio_metrics;
CREATE POLICY "authenticated_select_own_workspace" ON public.portfolio_metrics
    FOR SELECT TO authenticated
    USING (
        workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
        OR workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

-- documents (105: house + system + own membership)
DROP POLICY IF EXISTS "authenticated_select_documents" ON public.documents;
CREATE POLICY "authenticated_select_documents" ON public.documents
    FOR SELECT TO authenticated
    USING (
        workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid
        OR workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

-- portfolio_ledger_*
DROP POLICY IF EXISTS "authenticated_select_own_workspace"
    ON public.portfolio_ledger_commits;
CREATE POLICY "authenticated_select_own_workspace"
    ON public.portfolio_ledger_commits
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace"
    ON public.portfolio_ledger_decision_intents;
CREATE POLICY "authenticated_select_own_workspace"
    ON public.portfolio_ledger_decision_intents
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace"
    ON public.portfolio_ledger_requested_targets;
CREATE POLICY "authenticated_select_own_workspace"
    ON public.portfolio_ledger_requested_targets
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace"
    ON public.portfolio_ledger_target_adjustments;
CREATE POLICY "authenticated_select_own_workspace"
    ON public.portfolio_ledger_target_adjustments
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace"
    ON public.portfolio_ledger_approved_targets;
CREATE POLICY "authenticated_select_own_workspace"
    ON public.portfolio_ledger_approved_targets
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace"
    ON public.portfolio_ledger_order_intents;
CREATE POLICY "authenticated_select_own_workspace"
    ON public.portfolio_ledger_order_intents
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace"
    ON public.portfolio_ledger_paper_executions;
CREATE POLICY "authenticated_select_own_workspace"
    ON public.portfolio_ledger_paper_executions
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace"
    ON public.portfolio_ledger_holding_lots;
CREATE POLICY "authenticated_select_own_workspace"
    ON public.portfolio_ledger_holding_lots
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

-- olympus_accounting_*
DROP POLICY IF EXISTS "authenticated_select_own_workspace"
    ON public.olympus_accounting_periods;
CREATE POLICY "authenticated_select_own_workspace"
    ON public.olympus_accounting_periods
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace"
    ON public.olympus_accounting_contributions;
CREATE POLICY "authenticated_select_own_workspace"
    ON public.olympus_accounting_contributions
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

DROP POLICY IF EXISTS "authenticated_select_own_workspace"
    ON public.olympus_accounting_holdings;
CREATE POLICY "authenticated_select_own_workspace"
    ON public.olympus_accounting_holdings
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
    );

-- olympus_profile_config (system house-default branch retained)
DROP POLICY IF EXISTS "authenticated_select_own_workspace"
    ON public.olympus_profile_config;
CREATE POLICY "authenticated_select_own_workspace"
    ON public.olympus_profile_config
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (
            SELECT workspace_id
            FROM public.workspace_members
            WHERE user_id = (SELECT auth.uid())
        )
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid -- system; TODO(T5): tier gate
    );

COMMENT ON POLICY "authenticated_select_own_workspace" ON public.olympus_profile_config IS
    'T0 (#5-T0). System-workspace branch is load-bearing here: the house-default row '
    'lives in the system workspace so every tenant reads the shared default overlay. '
    'TODO(T5): gate the system-workspace branch by plan_tier once the tier CHECK policy '
    'pass lands. Initplan wrap on uid helper per #3461 lint 0003.';
