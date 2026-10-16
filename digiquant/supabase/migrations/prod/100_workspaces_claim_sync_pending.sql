-- 100_workspaces_claim_sync_pending.sql
--
-- T2 (Kairos + tenancy program, spec §5-T2 / roadmap P4) — Stripe webhook claim-sync
-- failure flag on `workspaces`.
--
-- When the webhook updates `workspaces.plan_tier` but
-- `auth.admin.updateUserById(..., { app_metadata: { plan_tier } })` fails for any
-- member, the handler sets `claim_sync_pending = true` and still returns 200 to
-- Stripe (do not force a retry storm). The next successfully-applied webhook for
-- that workspace retries claim sync and clears the flag on full success.
--
-- Numbering: K3 reserved 099 (`broker_connections`); this WP takes the next free
-- prefix (100). Unwrapped on purpose — db-migrate.yml applies file + ledger row in
-- one psql single-transaction call. Replay-safe via IF NOT EXISTS.

ALTER TABLE public.workspaces
    ADD COLUMN IF NOT EXISTS claim_sync_pending boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN public.workspaces.claim_sync_pending IS
    'T2 billing: true when workspace.plan_tier was updated but Supabase Auth '
    'app_metadata.plan_tier claim sync failed for one or more members. Cleared '
    'on the next successful claim sync. Webhook still returns 200 to Stripe.';
