-- 096_workspaces_tenancy_tables.sql
--
-- T0 (Kairos + tenancy program, spec §5-T0 / roadmap P2a) — Wave 3 multi-tenant schema,
-- part 1 of 3: new tables only. No existing table is touched by this file (097 adds
-- workspace_id to the private set; 098 adds the new `authenticated` RLS policies).
--
-- Goal: one workspaces registry (system + per-user), membership, and the handful of
-- tenancy-adjacent operational tables (stripe idempotency, job runs, audit log) the rest
-- of the Kairos + tenancy program needs. `plan_tier` is `free | baseline | custom |
-- enterprise` per the locked spec decision D1 — NOT the roadmap sketch's `free | pro |
-- enterprise`; this migration follows the spec, the roadmap's own delta note.
--
-- Privacy / sequencing (binding, restated from docs/agent-backlog/kairos-tenancy/T0.md):
-- this WP only ADDS tables, columns, seeds, and new `authenticated` policies. It does
-- NOT drop, narrow, or otherwise touch any existing `anon` policy anywhere in the
-- schema — that is a separate, explicitly flagged migration that ships inside T1's
-- release train (Supabase Auth login), once the dashboard can actually authenticate.
-- Until then, every `anon_read` policy from migration 001 forward keeps working exactly
-- as today.
--
-- Seeds (idempotent — `ON CONFLICT (id) DO NOTHING`, safe to re-run):
--   - the one `type='system'` workspace (shared, tenant-agnostic research corpus)
--   - the `house` workspace (the digithings operator's own book — a `type='user'` row,
--     NOT the system workspace; 097 backfills every pre-T0 private-set row to this id)
-- Both ids are deterministic (`uuid5`, namespace `digithings.olympus.tenancy`) so
-- Python (`digiquant.olympus.tenancy.system_workspace_id()` /
-- `house_workspace_id()`), this migration, and the structural test all agree without a
-- database round trip:
--   namespace = uuid5(NAMESPACE_URL, 'digithings.olympus.tenancy')
--             = f6170a00-e195-5e92-8c41-2178302e37a8
--   system    = uuid5(namespace, 'workspace:system') = 1105372f-4109-5815-be5a-21091ccfc8ad
--   house     = uuid5(namespace, 'workspace:house')  = 6b753576-ced9-5319-9bfa-c5d0aacd9319
--
-- K3/K4/K5 tables (`broker_connections`, `broker_orders`, `broker_executions`,
-- `broker_position_snapshots`, `notification_prefs`) do NOT exist yet in this codebase —
-- skipped here per the T0 briefing; those land with their own K-track migrations and
-- pick up `workspace_id` at creation time, not retrofitted here.
--
-- RLS: every table below enables RLS. `workspaces` and `workspace_members` get real
-- `authenticated` policies now (an authenticated user must see their own workspace to
-- exist as a product at all) — the remaining tables (`stripe_events`, `job_runs`,
-- `audit_log`) are `service_role`-only, zero client policies, following the migration
-- 069/072/075 idiom exactly (RLS enabled, PUBLIC/anon/authenticated fully revoked,
-- service_role reset then granted only what it needs). No table in this migration grants
-- anything to `anon`.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one psql
-- single-transaction call. All DDL is replay-safe through IF NOT EXISTS, CREATE OR
-- REPLACE, and DROP POLICY/TRIGGER IF EXISTS before CREATE.

CREATE TABLE IF NOT EXISTS public.workspaces (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text UNIQUE CHECK (slug IS NULL OR length(slug) BETWEEN 1 AND 100),
    type text NOT NULL CHECK (type IN ('system', 'user')),
    name text,
    created_at timestamptz NOT NULL DEFAULT now(),
    -- Billing (denormalized for RLS simplicity — roadmap A.4 D5).
    stripe_customer_id text,
    stripe_subscription_id text,
    subscription_status text NOT NULL DEFAULT 'none'
        CHECK (subscription_status IN ('none', 'active', 'past_due', 'canceled')),
    plan_tier text NOT NULL DEFAULT 'free'
        CHECK (plan_tier IN ('free', 'baseline', 'custom', 'enterprise')),
    -- Config (paid tiers; validated server-side by the BFF PATCH T3/P5 introduces —
    -- this migration only needs the column to exist and round-trip).
    investment_profile jsonb,
    preferences jsonb,
    rebalancing_policy jsonb,
    settings jsonb,
    published_profile_version integer NOT NULL DEFAULT 0 CHECK (published_profile_version >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Exactly one `type='system'` workspace may ever exist — a second one would split the
-- shared research corpus across two ids with no way to reconcile which is canonical.
-- Partial unique index on `type` itself (mirrors migration 075's
-- `uq_olympus_profile_config_one_house_root` idiom): every indexed row has the same
-- constant value 'system', so uniqueness over that filtered set means at most one row.
CREATE UNIQUE INDEX IF NOT EXISTS uq_workspaces_one_system_row
    ON public.workspaces (type) WHERE type = 'system';

CREATE INDEX IF NOT EXISTS idx_workspaces_type ON public.workspaces (type);

CREATE TABLE IF NOT EXISTS public.workspace_members (
    workspace_id uuid NOT NULL REFERENCES public.workspaces (id),
    user_id uuid NOT NULL,
    role text NOT NULL DEFAULT 'owner' CHECK (role IN ('owner', 'member')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_user
    ON public.workspace_members (user_id);

-- stripe_events — webhook idempotency (T2 writes; schema lands now so the T0→T2
-- sequencing note in the spec has somewhere to point).
CREATE TABLE IF NOT EXISTS public.stripe_events (
    stripe_event_id text PRIMARY KEY,
    event_type text NOT NULL CHECK (length(event_type) BETWEEN 1 AND 100),
    workspace_id uuid REFERENCES public.workspaces (id),
    processed_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb
);

-- job_runs — generic per-workspace job telemetry (roadmap P2a "Phase 7 can add"; stubbed
-- here so T4's `(workspace_id, job_type, run_date)` dispatch key has a home).
CREATE TABLE IF NOT EXISTS public.job_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid REFERENCES public.workspaces (id),
    job_type text NOT NULL CHECK (length(job_type) BETWEEN 1 AND 100),
    status text NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    started_at timestamptz,
    finished_at timestamptz,
    error text,
    idempotency_key text UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_job_runs_workspace_job_type
    ON public.job_runs (workspace_id, job_type);

-- audit_log — connect/revoke/settings-change trail (K3 references this table for vault
-- connect/revoke events; created here per K3's own note: "create it here if T0 has not
-- landed").
CREATE TABLE IF NOT EXISTS public.audit_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid REFERENCES public.workspaces (id),
    user_id uuid,
    action text NOT NULL CHECK (length(action) BETWEEN 1 AND 200),
    metadata jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_workspace_created
    ON public.audit_log (workspace_id, created_at DESC);

-- Seeds — deterministic ids, idempotent inserts (see header for the uuid5 derivation).
INSERT INTO public.workspaces (id, slug, type, name, plan_tier, subscription_status)
VALUES (
    '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid,
    'system',
    'system',
    'digithings system',
    'enterprise',
    'none'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.workspaces (id, slug, type, name, plan_tier, subscription_status)
VALUES (
    '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid,
    'house',
    'user',
    'digithings house',
    'enterprise',
    'active'
)
ON CONFLICT (id) DO NOTHING;

-- updated_at auto-bump (roadmap P2a). Project already has trigger_set_updated_at()
-- from migration 003 — reuse it rather than enabling the moddatetime extension.
DROP TRIGGER IF EXISTS set_updated_at_workspaces ON public.workspaces;
CREATE TRIGGER set_updated_at_workspaces
    BEFORE UPDATE ON public.workspaces
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

ALTER TABLE public.workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspace_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stripe_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

-- workspaces / workspace_members: authenticated policies land in migration 098 (P2c),
-- alongside every other new authenticated policy in this program, so all the new-policy
-- SQL for T0 lives in one reviewable file. This file only establishes the tables +
-- seeds + revoke-then-grant baseline.
REVOKE ALL ON public.workspaces FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.workspace_members FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.stripe_events FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.job_runs FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.audit_log FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.workspaces FROM service_role;
REVOKE ALL ON public.workspace_members FROM service_role;
REVOKE ALL ON public.stripe_events FROM service_role;
REVOKE ALL ON public.job_runs FROM service_role;
REVOKE ALL ON public.audit_log FROM service_role;

GRANT SELECT, INSERT, UPDATE ON public.workspaces TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.workspace_members TO service_role;
GRANT SELECT, INSERT ON public.stripe_events TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.job_runs TO service_role;
GRANT SELECT, INSERT ON public.audit_log TO service_role;

COMMENT ON TABLE public.workspaces IS
    'Multi-tenant registry (T0, #5-T0). Exactly one type=''system'' row (shared '
    'research corpus); every other row is a per-user (or per-org, future) workspace. '
    'The house workspace (slug=''house'') is a regular type=''user'' row that pre-T0 '
    'single-tenant data backfills to (migration 097) — it is not the system workspace.';

COMMENT ON TABLE public.workspace_members IS
    'Workspace membership (T0, #5-T0). user_id references auth.users once T1 ships '
    'Supabase Auth login; no FK to auth.users yet because T0 predates real sessions.';

COMMENT ON TABLE public.stripe_events IS
    'Stripe webhook idempotency ledger (T0 schema, T2 writer). PK is the Stripe event '
    'id itself so a replayed webhook is a no-op INSERT conflict, not a second charge.';

COMMENT ON TABLE public.job_runs IS
    'Per-workspace job telemetry (T0 schema; T4 overlay dispatch is the first real '
    'writer). idempotency_key lets a job scheduler retry safely.';

COMMENT ON TABLE public.audit_log IS
    'Connect/revoke/settings-change audit trail (T0 schema; K3 vault connect/revoke is '
    'the first writer). Never grant to anon/authenticated — this is an operator surface.';
