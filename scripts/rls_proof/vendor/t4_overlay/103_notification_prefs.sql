-- 103_notification_prefs.sql
--
-- Email notification preferences (K5) + dedupe log for fail-soft Mailgun dispatch.
-- `notification_prefs` per spec §3; `notification_log` insert-first dedupe per
-- (workspace_id, event_key, sent_date) so pipeline retries never double-send.
--
-- MIGRATION NUMBER — READ BEFORE RENUMBERING: 103 was taken for K5 on the K4 base
-- (099 broker_connections, 102 broker mirror). Sibling T2 holds 100/101 for Stripe.
-- If the sequence shifts at merge, renumber this file and
-- tests/dq/notify/test_migration_103.py together — filename is the ledger key.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one
-- psql single-transaction call. DDL is replay-safe via IF NOT EXISTS / DROP IF EXISTS.

-- ---------------------------------------------------------------------------
-- notification_prefs — per-workspace email toggles (T3 settings UI writes later)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.notification_prefs (
    workspace_id uuid PRIMARY KEY REFERENCES public.workspaces (id),
    email text NOT NULL CHECK (email ~ '^[^@]+@[^@]+\.[^@]+$'),
    daily_digest boolean NOT NULL DEFAULT false,
    holding_change_alerts boolean NOT NULL DEFAULT false,
    execution_alerts boolean NOT NULL DEFAULT false,
    digest_hour_utc smallint NOT NULL DEFAULT 12 CHECK (digest_hour_utc BETWEEN 0 AND 23),
    updated_at timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS set_updated_at_notification_prefs ON public.notification_prefs;
CREATE TRIGGER set_updated_at_notification_prefs
    BEFORE UPDATE ON public.notification_prefs
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.notification_prefs ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.notification_prefs FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.notification_prefs FROM service_role;
GRANT SELECT, INSERT, UPDATE ON public.notification_prefs TO service_role;

COMMENT ON TABLE public.notification_prefs IS
    'K5 per-workspace email notification toggles. T3 settings UI is the product writer; '
    'digest_hour_utc gates cron dispatch (UTC).';

-- ---------------------------------------------------------------------------
-- notification_log — dedupe ledger (insert-first; PK collision = already sent)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.notification_log (
    workspace_id uuid NOT NULL REFERENCES public.workspaces (id),
    event_key text NOT NULL CHECK (char_length(event_key) BETWEEN 1 AND 200),
    sent_date date NOT NULL,
    sent_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, event_key, sent_date)
);

CREATE INDEX IF NOT EXISTS idx_notification_log_workspace_sent_date
    ON public.notification_log (workspace_id, sent_date DESC);

ALTER TABLE public.notification_log ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.notification_log FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.notification_log FROM service_role;
GRANT SELECT, INSERT ON public.notification_log TO service_role;

COMMENT ON TABLE public.notification_log IS
    'K5 dedupe ledger: one row per (workspace, event_key, calendar day). Writers insert '
    'before send; duplicate PK means skip. Append-only — no UPDATE grant.';
