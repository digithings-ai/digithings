-- 133_notification_claim.sql
-- Split the K5 dedupe claim out of the append-only send log (#4384).
--
-- `notification_log` is append-only by design (see
-- 106_notification_prefs_align_canonical.sql: DELETE revoked from service_role and
-- `reject_notification_log_mutation` raises 55000). But the insert-first dedupe in
-- digiquant.notify.dispatch has to be undoable: when the email service suppresses a
-- recipient the send did not happen, and a claim left behind would stop that digest
-- (or that event) from ever being retried once the address is unsuppressed. #4370
-- released the claim with a DELETE, which can never run against a migrated database
-- — the privilege is gone and the trigger refuses.
--
-- So the two responsibilities get one table each:
--   notification_claim — the mutable dedupe window, released when a send is refused
--   notification_log   — the append-only record of what was actually sent
--
-- REQUIRED APPLY ORDER. Every dispatch claims a slot, so `notification_claim` must
-- exist BEFORE the code that reads it runs: `try_claim_send_slot` re-raises a
-- non-duplicate insert error, which would block all notification dispatch. This
-- migration is additive and harmless while the old code still runs (`notification_log`
-- keeps working), so land it alone, let the `production` db-migrate run apply it, and
-- only then promote the code.
--
-- Replay-safe: unwrapped (the db-migrate loop runs this file plus its ledger INSERT
-- inside one transaction) and every statement here is idempotent.

CREATE TABLE IF NOT EXISTS public.notification_claim (
    workspace_id uuid NOT NULL REFERENCES public.workspaces (id),
    event_key text NOT NULL,
    sent_date date NOT NULL,
    claimed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, event_key, sent_date)
);

CREATE INDEX IF NOT EXISTS idx_notification_claim_claimed_at
    ON public.notification_claim (claimed_at);

ALTER TABLE public.notification_claim ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.notification_claim FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.notification_claim FROM service_role;
-- DELETE is the point of this table: it is what releases a suppressed send.
GRANT SELECT, INSERT, DELETE ON public.notification_claim TO service_role;

COMMENT ON TABLE public.notification_claim IS
    'K5 dedupe window: one row per (workspace, event_key, calendar day), inserted before '
    'send. Mutable by design — released when the service refuses the send, so the '
    'notification can be retried. The append-only guarantee stays on notification_log.';
COMMENT ON COLUMN public.notification_claim.claimed_at IS
    'When the slot was claimed; rows older than the dedupe window can be pruned.';
