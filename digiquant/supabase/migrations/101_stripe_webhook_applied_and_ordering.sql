-- 101_stripe_webhook_applied_and_ordering.sql
--
-- T2 review follow-up — webhook apply durability + atomic out-of-order guard.
--
-- 1. `stripe_events.applied_at` — NULL until workspace+claim apply succeeds.
--    Insert-first idempotency without this marker is a poison pill: a later
--    workspaces-update failure returns 500, Stripe retries, PK 23505 ⇒
--    duplicate ⇒ 200 no-op, billing never applied. T0 granted service_role
--    INSERT-only on stripe_events, so the poison row cannot be deleted.
--    Column-level UPDATE (applied_at) lets the webhook flip the marker without
--    rewriting payload/event_type.
--
-- 2. `workspaces.last_stripe_event_created` — Stripe event `created` (unix
--    seconds) of the last successfully CAS-applied billing event. Concurrent
--    Edge isolates compare-and-set via
--      WHERE last_stripe_event_created IS NULL OR last_stripe_event_created < $created
--    so stale events are no-ops without a last-50 jsonb race.
--
-- Numbering: 100 landed claim_sync_pending; this is the next free prefix.
-- Unwrapped — db-migrate.yml single-transaction apply. Replay-safe.

ALTER TABLE public.stripe_events
    ADD COLUMN IF NOT EXISTS applied_at timestamptz;

COMMENT ON COLUMN public.stripe_events.applied_at IS
    'T2 billing: NULL while the event is inserted but not yet applied. Set to '
    'now() only after the workspace billing write (+ claim sync attempt) '
    'succeeds. A duplicate webhook with applied_at NULL re-applies; applied_at '
    'NOT NULL is the true idempotent no-op.';

-- service_role already has SELECT + INSERT (096). Grant UPDATE only on the
-- applied marker so the webhook cannot rewrite payload / event_type / ids.
GRANT UPDATE (applied_at) ON public.stripe_events TO service_role;

ALTER TABLE public.workspaces
    ADD COLUMN IF NOT EXISTS last_stripe_event_created bigint;

COMMENT ON COLUMN public.workspaces.last_stripe_event_created IS
    'T2 billing: Stripe event.created (unix seconds) of the last CAS-applied '
    'billing webhook for this workspace. Stale events (created <= this value) '
    'are marked applied without mutating billing columns.';
