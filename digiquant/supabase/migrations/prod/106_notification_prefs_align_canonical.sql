-- 106_notification_prefs_align_canonical.sql
--
-- Live `core` had pre-existing notification_prefs / notification_log shapes that
-- did not match 103 (CREATE TABLE IF NOT EXISTS no-op'd). Columns were
-- digest_enabled / holding_change_enabled / execution_alerts_enabled (+
-- suppressed_until) and a richer notification_log. Canonical K5 + T3 settings
-- handlers + digiquant.notify expect daily_digest / holding_change_alerts /
-- execution_alerts and the slim append-only log from 103.
--
-- Safe because both tables were empty on apply (2026-08-30 agent verify).
-- Unwrapped: db-migrate.yml single-transaction + olympus_schema_migrations.

-- ---------------------------------------------------------------------------
-- notification_prefs → canonical 103 columns
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS set_updated_at_notification_prefs ON public.notification_prefs;
DROP TABLE IF EXISTS public.notification_prefs;

CREATE TABLE public.notification_prefs (
    workspace_id uuid PRIMARY KEY REFERENCES public.workspaces (id),
    email text NOT NULL CHECK (email ~ '^[^@]+@[^@]+\.[^@]+$'),
    daily_digest boolean NOT NULL DEFAULT false,
    holding_change_alerts boolean NOT NULL DEFAULT false,
    execution_alerts boolean NOT NULL DEFAULT false,
    digest_hour_utc smallint NOT NULL DEFAULT 12 CHECK (digest_hour_utc BETWEEN 0 AND 23),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER set_updated_at_notification_prefs
    BEFORE UPDATE ON public.notification_prefs
    FOR EACH ROW EXECUTE FUNCTION public.trigger_set_updated_at();

ALTER TABLE public.notification_prefs ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.notification_prefs FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.notification_prefs FROM service_role;
GRANT SELECT, INSERT, UPDATE ON public.notification_prefs TO service_role;

COMMENT ON TABLE public.notification_prefs IS
    'K5 per-workspace email notification toggles. T3 settings UI is the product writer; '
    'digest_hour_utc gates cron dispatch (UTC).';

-- ---------------------------------------------------------------------------
-- notification_log → canonical 103 append-only dedupe ledger
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS reject_notification_log_mutation ON public.notification_log;
DROP TRIGGER IF EXISTS reject_notification_log_truncate ON public.notification_log;
DROP TABLE IF EXISTS public.notification_log;

CREATE TABLE public.notification_log (
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
    'before send; duplicate PK means skip. Append-only — triggers reject UPDATE/DELETE.';

CREATE OR REPLACE FUNCTION public.reject_notification_log_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'notification_log is append-only'
        USING ERRCODE = '55000';
END
$$;

CREATE TRIGGER reject_notification_log_mutation
    BEFORE UPDATE OR DELETE ON public.notification_log
    FOR EACH ROW EXECUTE FUNCTION public.reject_notification_log_mutation();
CREATE TRIGGER reject_notification_log_truncate
    BEFORE TRUNCATE ON public.notification_log
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_notification_log_mutation();

REVOKE ALL ON FUNCTION public.reject_notification_log_mutation()
    FROM PUBLIC, anon, authenticated;
