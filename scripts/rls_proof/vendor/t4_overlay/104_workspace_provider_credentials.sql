-- VENDORED FOR PROOF ONLY — do not apply to core; canonical file lives on cursor/t4-overlay-runs-3d52.
-- 104_workspace_provider_credentials.sql
--
-- T4 (Kairos + tenancy program, spec §5-T4 / D9) — sealed BYOK LLM provider keys.
-- Mirrors migration 099 (`broker_connections`) exactly: same envelope columns, RLS-none,
-- column-level UPDATE grant, partial unique on the active row, credential-column
-- immutability trigger. Do NOT invent new crypto — the ciphertext is an AES-256-GCM
-- envelope produced by `digiquant.vault.envelope` (K3). The AAD binding is
-- `workspace_id:provider:llm` (build_aad(workspace_id, provider, "llm")), so a
-- ciphertext cannot be replayed onto another workspace or provider row, and cannot be
-- confused with a broker row whose AAD uses `workspace_id:broker:env`.
--
-- job_runs.status (migration 096) is also extended here: T0 stubbed
-- pending|running|succeeded|failed. Overlay dispatch needs `skipped` (visible
-- not_entitled / no_credentials) and `budget_exhausted` (UI-visible hard stop).
-- Reason text stays in the existing `error` column — no new skip_reason column.
--
-- HUMAN GATE: cryptography. This migration is the storage half of BYOK LLM keys;
-- it must not be applied without the human review the K3 envelope already required.
--
-- MIGRATION NUMBER: next free after K5's 103 (T2 took 100/101; K4 took 102; K5 took
-- 103). Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in
-- one psql single-transaction call. All DDL is replay-safe through IF NOT EXISTS,
-- CREATE OR REPLACE, and DROP CONSTRAINT/TRIGGER IF EXISTS before CREATE.

-- --- job_runs status vocabulary (T4 overlay dispatch) ---------------------------
-- The inline CHECK from 096 is named job_runs_status_check by Postgres.
ALTER TABLE public.job_runs DROP CONSTRAINT IF EXISTS job_runs_status_check;
ALTER TABLE public.job_runs ADD CONSTRAINT job_runs_status_check
    CHECK (status IN (
        'pending', 'running', 'succeeded', 'failed', 'skipped', 'budget_exhausted'
    ));

COMMENT ON COLUMN public.job_runs.status IS
    'T0 stub plus T4 overlay: pending|running|succeeded|failed|skipped|'
    'budget_exhausted. skipped.error holds not_entitled|no_credentials; '
    'budget_exhausted is the research_budget_usd hard stop (UI-visible).';

-- --- workspace_provider_credentials --------------------------------------------

CREATE TABLE IF NOT EXISTS public.workspace_provider_credentials (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES public.workspaces (id),
    provider text NOT NULL CHECK (
        provider IN ('openai', 'anthropic', 'groq', 'openrouter', 'xai', 'gemini')
    ),
    auth_kind text NOT NULL CHECK (auth_kind IN ('oauth', 'api_key')),
    -- > 16, not >= 16: AES-GCM appends a 16-byte tag, so anything at or below that length
    -- carries no payload at all and is treated as truncated.
    ciphertext bytea NOT NULL CHECK (octet_length(ciphertext) > 16),
    nonce bytea NOT NULL CHECK (octet_length(nonce) = 12),
    key_id text NOT NULL CHECK (key_id ~ '^[a-z0-9][a-z0-9._-]{0,31}$'),
    fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{8}$'),
    scopes text[] NOT NULL DEFAULT '{}',
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired')),
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    last_used_at timestamptz,
    CONSTRAINT chk_workspace_provider_credentials_revoked_at
        CHECK (
            (status = 'revoked' AND revoked_at IS NOT NULL)
            OR (status <> 'revoked' AND revoked_at IS NULL)
        ),
    CONSTRAINT chk_workspace_provider_credentials_scopes_no_nulls
        CHECK (array_position(scopes, NULL) IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_workspace_provider_credentials_workspace
    ON public.workspace_provider_credentials (workspace_id);

-- One *active* LLM key per (workspace, provider). Partial so revoke + insert can
-- reconnect without DELETE (not granted to service_role).
CREATE UNIQUE INDEX IF NOT EXISTS uq_workspace_provider_credentials_active
    ON public.workspace_provider_credentials (workspace_id, provider)
    WHERE status = 'active';

ALTER TABLE public.workspace_provider_credentials ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.workspace_provider_credentials FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.workspace_provider_credentials FROM service_role;

GRANT SELECT, INSERT ON public.workspace_provider_credentials TO service_role;
GRANT UPDATE (status, revoked_at, last_used_at)
    ON public.workspace_provider_credentials TO service_role;

CREATE OR REPLACE FUNCTION public.reject_workspace_provider_credential_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'workspace_provider_credentials cannot be truncated'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
        OR NEW.workspace_id IS DISTINCT FROM OLD.workspace_id
        OR NEW.provider IS DISTINCT FROM OLD.provider
        OR NEW.auth_kind IS DISTINCT FROM OLD.auth_kind
        OR NEW.ciphertext IS DISTINCT FROM OLD.ciphertext
        OR NEW.nonce IS DISTINCT FROM OLD.nonce
        OR NEW.key_id IS DISTINCT FROM OLD.key_id
        OR NEW.fingerprint IS DISTINCT FROM OLD.fingerprint
        OR NEW.scopes IS DISTINCT FROM OLD.scopes
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION
            'workspace_provider_credentials credential columns are immutable; '
            'revoke the row and insert a new one instead of re-sealing in place'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS reject_workspace_provider_credentials_credential_mutation
    ON public.workspace_provider_credentials;
CREATE TRIGGER reject_workspace_provider_credentials_credential_mutation
    BEFORE UPDATE ON public.workspace_provider_credentials
    FOR EACH ROW EXECUTE FUNCTION public.reject_workspace_provider_credential_mutation();

DROP TRIGGER IF EXISTS reject_workspace_provider_credentials_truncate
    ON public.workspace_provider_credentials;
CREATE TRIGGER reject_workspace_provider_credentials_truncate
    BEFORE TRUNCATE ON public.workspace_provider_credentials
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_workspace_provider_credential_mutation();

REVOKE ALL ON FUNCTION public.reject_workspace_provider_credential_mutation()
    FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.workspace_provider_credentials IS
    'Sealed BYOK LLM keys (T4, D9). At most one active row per (workspace_id, provider) '
    '(partial unique index); revoked/expired history may coexist so re-connect is revoke '
    '+ insert without DELETE. The secret lives only inside ciphertext as an AES-256-GCM '
    'envelope whose AAD is workspace_id:provider:llm (K3 envelope, not new crypto), so a '
    'ciphertext cannot be replayed onto another row. RLS on with no policies; '
    'service_role may SELECT/INSERT and UPDATE only (status, revoked_at, last_used_at).';

COMMENT ON COLUMN public.workspace_provider_credentials.key_id IS
    'Master-key version that sealed this row (DIGIQUANT_VAULT_KEY_ID, e.g. v1) — not a '
    'provider-side key id; an API key''s own key_id is inside the sealed payload.';

COMMENT ON COLUMN public.workspace_provider_credentials.fingerprint IS
    'First 8 hex chars of sha256 over the secret material: the only display-safe artifact '
    'for a BYOK row. A label, never an identity — 32 bits collide, so never compare '
    'fingerprints to conclude two rows hold the same credential.';

COMMENT ON COLUMN public.workspace_provider_credentials.workspace_id IS
    'Owning workspace. FK to public.workspaces (T0 has landed).';

COMMENT ON FUNCTION public.reject_workspace_provider_credential_mutation() IS
    'Rejects any UPDATE that changes a credential/identity column, and rejects TRUNCATE. '
    'Defense in depth behind the column-level UPDATE grant. DELETE is deliberately not '
    'blocked: a credential store must stay erasable.';
