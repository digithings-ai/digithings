-- 107_ensure_personal_workspace.sql
--
-- Kairos + tenancy — Observer (free) workspace bootstrap for new Auth users.
--
-- Problem: settings / checkout resolve the caller via workspace_members. After
-- Agentmail (or any) signup, auth.users can exist with zero memberships, so
-- every JWT settings call returns 403 WORKSPACE_FORBIDDEN. T0 seeded only the
-- system + house workspaces and left per-user provisioning unspecified;
-- HUMAN-UNBLOCK / COMPLETION_AUDIT call out the product gap.
--
-- Design (prefer existing surfaces, no parallel tenancy system):
--   1. SECURITY DEFINER RPC public.ensure_personal_workspace(p_user_id uuid)
--      — idempotent; creates a type='user' plan_tier='free' workspace + owner
--      membership when the user has none. Never touches system/house seeds.
--   2. Auth trigger AFTER INSERT ON auth.users → same RPC (new signups).
--   3. Settings / billing Edge Functions call the RPC via service_role when
--      resolveCallerWorkspace returns null (covers users created before this
--      migration, and any trigger miss).
--
-- Reserved slugs: system, house (096 seeds). Personal slug = 'u-' || hex(uuid)
-- (unique, ≤100 chars). Concurrent callers: ON CONFLICT on slug + membership
-- PK; re-select membership after insert.
--
-- Unwrapped on purpose: db-migrate.yml applies the file + ledger row in one
-- psql single-transaction call. Replay-safe via CREATE OR REPLACE / DROP
-- TRIGGER IF EXISTS.

CREATE OR REPLACE FUNCTION public.ensure_personal_workspace(p_user_id uuid)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_ws_id uuid;
    v_slug text;
BEGIN
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'ensure_personal_workspace: p_user_id required';
    END IF;

    -- Prefer existing owner membership; else any membership.
    SELECT wm.workspace_id
      INTO v_ws_id
      FROM public.workspace_members AS wm
     WHERE wm.user_id = p_user_id
     ORDER BY CASE WHEN wm.role = 'owner' THEN 0 ELSE 1 END, wm.created_at ASC
     LIMIT 1;

    IF v_ws_id IS NOT NULL THEN
        RETURN v_ws_id;
    END IF;

    v_slug := 'u-' || replace(p_user_id::text, '-', '');

    INSERT INTO public.workspaces (slug, type, name, plan_tier, subscription_status)
    VALUES (v_slug, 'user', 'Personal', 'free', 'none')
    ON CONFLICT (slug) DO NOTHING
    RETURNING id INTO v_ws_id;

    IF v_ws_id IS NULL THEN
        SELECT w.id INTO v_ws_id FROM public.workspaces AS w WHERE w.slug = v_slug;
    END IF;

    IF v_ws_id IS NULL THEN
        RAISE EXCEPTION 'ensure_personal_workspace: failed to create or resolve workspace';
    END IF;

    -- Never attach a new user to system/house via this path (slug is u-<uuid>).
    IF v_ws_id IN (
        '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid,
        '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
    ) THEN
        RAISE EXCEPTION 'ensure_personal_workspace: refused system/house workspace';
    END IF;

    INSERT INTO public.workspace_members (workspace_id, user_id, role)
    VALUES (v_ws_id, p_user_id, 'owner')
    ON CONFLICT (workspace_id, user_id) DO NOTHING;

    RETURN v_ws_id;
END;
$$;

COMMENT ON FUNCTION public.ensure_personal_workspace(uuid) IS
    'Idempotent Observer bootstrap: ensure a free personal workspace + owner '
    'membership for the given auth user. Used by auth.users trigger and '
    'settings/billing Edge Functions (service_role). Never mutates system/house.';

REVOKE ALL ON FUNCTION public.ensure_personal_workspace(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.ensure_personal_workspace(uuid) TO service_role;

-- Convenience wrapper for authenticated clients (auth.uid only).
CREATE OR REPLACE FUNCTION public.ensure_my_workspace()
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_uid uuid := auth.uid();
BEGIN
    IF v_uid IS NULL THEN
        RAISE EXCEPTION 'ensure_my_workspace: not authenticated';
    END IF;
    RETURN public.ensure_personal_workspace(v_uid);
END;
$$;

COMMENT ON FUNCTION public.ensure_my_workspace() IS
    'Authenticated wrapper around ensure_personal_workspace(auth.uid()).';

REVOKE ALL ON FUNCTION public.ensure_my_workspace() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.ensure_my_workspace() TO authenticated, service_role;

-- New Auth users get a personal workspace immediately.
CREATE OR REPLACE FUNCTION public.handle_new_auth_user_workspace()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    PERFORM public.ensure_personal_workspace(NEW.id);
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.handle_new_auth_user_workspace() IS
    'AFTER INSERT on auth.users — Observer personal workspace bootstrap.';

DROP TRIGGER IF EXISTS on_auth_user_created_ensure_workspace ON auth.users;
CREATE TRIGGER on_auth_user_created_ensure_workspace
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_auth_user_workspace();

-- Backfill: any existing auth.users row with zero memberships (e.g. Agentmail
-- user created before this migration). Idempotent.
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT u.id
          FROM auth.users AS u
         WHERE NOT EXISTS (
             SELECT 1 FROM public.workspace_members AS wm WHERE wm.user_id = u.id
         )
    LOOP
        PERFORM public.ensure_personal_workspace(r.id);
    END LOOP;
END;
$$;
