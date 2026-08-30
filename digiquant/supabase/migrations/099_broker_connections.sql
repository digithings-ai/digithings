-- 099_broker_connections.sql
--
-- Sealed broker credential store (K3, Kairos milestone 1). At most one *active* row per
-- (workspace_id, broker, env); the credential itself is an AES-256-GCM envelope produced
-- by `digiquant/src/digiquant/vault/envelope.py` and never exists in this table (or in any
-- log, API response, or repr) as plaintext.
--
-- HUMAN GATE: cryptography. This migration is the storage half of the credential vault;
-- it must not be applied without the human review the K3 work package requires.
--
-- MIGRATION NUMBER — READ BEFORE RENUMBERING: 099 was taken by coordination, not by
-- "next free". T0 (workspaces + RLS privacy boundary) is concurrently allocating 096, 097
-- and 098 on a sibling branch, so this file skips ahead to leave that block intact. If the
-- sequence still has gaps once both branches have merged, renumber THIS file down at merge
-- time — it has not been applied anywhere, so its number is free to change, and
-- `db-migrate.yml` keys its ledger on the filename (an applied file's name is never
-- rewritten). Move `tests/dq/atlas/test_migration_099.py` with it.
--
-- What this table holds, column by column:
--   ciphertext  AES-256-GCM output with the 16-byte tag appended. The sealed plaintext is
--               canonical JSON: {"kind":"oauth","access_token":…[,"refresh_token":…]} or
--               {"kind":"api_key","key_id":…,"secret":…}.
--   nonce       The 96-bit nonce for that seal, fresh per seal. Stored in the clear (a GCM
--               nonce is not a secret); the CHECK pins the length so a mis-decoded value
--               fails here rather than as an opaque authentication error at open time.
--   key_id      The MASTER-KEY version (`DIGIQUANT_VAULT_KEY_ID`, e.g. 'v1') that sealed
--               this row — NOT any broker-side key identifier. An API key's own key_id is
--               part of the sealed payload above. The spec §3 sketch uses the name for
--               both; here it only ever means the master-key version, and rotation (a
--               second key plus a re-seal job) is out of K3's scope.
--   fingerprint First 8 hex characters of sha256 over the secret material. This is the
--               only artifact any API, UI, or log line may display for a connection. It
--               is a label, not an identity: 32 bits collide long before a large table,
--               so nothing may compare fingerprints to decide two rows carry the same
--               credential.
--   status      active | revoked | expired. Nothing in K3 writes 'expired' — no token
--               refresh exists yet — but the vocabulary is complete for the OAuth work
--               package, and the runner already fails closed on it
--               (`connections.open_credential` raises ConnectionRevokedError for any
--               non-active row before attempting decryption).
--
-- The AAD binding (`f"{workspace_id}:{broker}:{env}"`, applied in the Python envelope, not
-- here) is why moving one row's ciphertext onto another row does not yield a usable
-- credential: the opener derives the AAD from the row it read, so a transplanted
-- ciphertext fails its tag check. The database cannot enforce that on its own — it is
-- recorded here because the columns' meaning depends on it.
--
-- Privileges — deny by default, then the narrowest thing that works:
--   * RLS enabled with NO policies, so anon/authenticated reach nothing even if a future
--     migration accidentally grants them a privilege.
--   * ALL revoked from PUBLIC/anon/authenticated, then from service_role as well: a
--     Supabase project ships ALTER DEFAULT PRIVILEGES ... GRANT ALL ON TABLES TO
--     service_role, so an additive grant alone would leave inherited UPDATE/DELETE/
--     TRUNCATE in place (same reasoning as migration 069).
--   * service_role then receives SELECT, INSERT, and a COLUMN-LEVEL
--     UPDATE (status, revoked_at, last_used_at). Every credential column is therefore
--     immutable at the privilege layer: an UPDATE that touches ciphertext, nonce, key_id,
--     fingerprint, auth_kind, broker, env, workspace_id, scopes, or created_at is refused
--     before any trigger runs. Re-connecting is revoke + insert, never a credential
--     rewrite in place.
--   * A BEFORE UPDATE trigger re-asserts that immutability per row (defense in depth for
--     any role that reaches this table with broader grants), and a BEFORE TRUNCATE trigger
--     rejects statement-level wipes. Triggers cannot make a stronger claim than that: a
--     table owner can ALTER TABLE ... DISABLE TRIGGER ALL, and a superuser can set
--     session_replication_role = 'replica'; neither bypass is available to service_role.
--
-- DELIBERATELY NOT append-only, unlike migration 069: DELETE is simply not granted to
-- service_role, but no trigger blocks it either. A credential store must stay erasable —
-- a workspace deletion or a data-subject erasure request has to be able to remove the
-- sealed bytes, and secrets should not be retained forever by construction. The
-- corrections-append-a-row rule that 069 enforces is about audit lineage; this table is
-- current-state, and its lineage lives in the audit trail, not in superseded credential
-- rows.
--
-- workspace_id carries no FK: `workspaces` does not exist yet.
-- T0 will constrain it (matching the spec §3 sketch's own note); until then the house
-- operator row uses the system workspace id.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one psql
-- single-transaction call. All DDL is replay-safe through IF NOT EXISTS, CREATE OR
-- REPLACE, and DROP TRIGGER IF EXISTS before CREATE TRIGGER.

CREATE TABLE IF NOT EXISTS public.broker_connections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- T0 will constrain this to public.workspaces(id); FK-less until that table exists.
    workspace_id uuid NOT NULL,
    broker text NOT NULL CHECK (broker IN ('alpaca', 'ibkr')),
    env text NOT NULL DEFAULT 'paper' CHECK (env IN ('paper', 'live')),
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
    -- status is NOT NULL, so `IS NULL`/`IS NOT NULL` against it never evaluates to NULL
    -- and no three-valued-logic contamination is possible (see migration 069's header).
    CONSTRAINT chk_broker_connections_revoked_at
        CHECK (
            (status = 'revoked' AND revoked_at IS NOT NULL)
            OR (status <> 'revoked' AND revoked_at IS NULL)
        ),
    -- No ordering CHECK on revoked_at/last_used_at against created_at: both are supplied
    -- by the runner's clock over PostgREST (which cannot call now() in a payload), and a
    -- skew-induced constraint violation must never be able to block a REVOCATION. Ordering
    -- is an analytics nicety; refusing to revoke is a security failure.
    CONSTRAINT chk_broker_connections_scopes_no_nulls
        CHECK (array_position(scopes, NULL) IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_broker_connections_workspace
    ON public.broker_connections (workspace_id);
-- One *active* connection per (workspace, broker, env). Partial so a revoked (or expired)
-- row can coexist with a newly inserted active row: re-connect is revoke + insert, DELETE
-- is deliberately not granted to service_role, and an unconditional UNIQUE would make that
-- documented flow collide. This unique index also covers the active-row lookup the runner
-- uses, so a separate non-unique active index is unnecessary.
CREATE UNIQUE INDEX IF NOT EXISTS uq_broker_connections_active
    ON public.broker_connections (workspace_id, broker, env) WHERE status = 'active';

ALTER TABLE public.broker_connections ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.broker_connections FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.broker_connections FROM service_role;

GRANT SELECT, INSERT ON public.broker_connections TO service_role;
-- Column-level UPDATE: the lifecycle columns only. Every credential column is immutable
-- at the privilege layer, not merely by trigger.
GRANT UPDATE (status, revoked_at, last_used_at) ON public.broker_connections TO service_role;

CREATE OR REPLACE FUNCTION public.reject_broker_connection_credential_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'broker_connections cannot be truncated'
            USING ERRCODE = '55000';
    END IF;
    -- Only status, revoked_at and last_used_at may ever change. Compared with IS DISTINCT
    -- FROM (not <>) because every one of these columns except the NOT NULL ones can hold
    -- NULL, and `NULL <> NULL` is NULL — which an IF would treat as false and wave through.
    IF NEW.id IS DISTINCT FROM OLD.id
        OR NEW.workspace_id IS DISTINCT FROM OLD.workspace_id
        OR NEW.broker IS DISTINCT FROM OLD.broker
        OR NEW.env IS DISTINCT FROM OLD.env
        OR NEW.auth_kind IS DISTINCT FROM OLD.auth_kind
        OR NEW.ciphertext IS DISTINCT FROM OLD.ciphertext
        OR NEW.nonce IS DISTINCT FROM OLD.nonce
        OR NEW.key_id IS DISTINCT FROM OLD.key_id
        OR NEW.fingerprint IS DISTINCT FROM OLD.fingerprint
        OR NEW.scopes IS DISTINCT FROM OLD.scopes
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION
            'broker_connections credential columns are immutable; revoke the row and '
            'insert a new one instead of re-sealing in place'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS reject_broker_connections_credential_mutation
    ON public.broker_connections;
CREATE TRIGGER reject_broker_connections_credential_mutation
    BEFORE UPDATE ON public.broker_connections
    FOR EACH ROW EXECUTE FUNCTION public.reject_broker_connection_credential_mutation();

DROP TRIGGER IF EXISTS reject_broker_connections_truncate
    ON public.broker_connections;
CREATE TRIGGER reject_broker_connections_truncate
    BEFORE TRUNCATE ON public.broker_connections
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_broker_connection_credential_mutation();

REVOKE ALL ON FUNCTION public.reject_broker_connection_credential_mutation()
    FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.broker_connections IS
    'Sealed broker credentials (K3). At most one active row per (workspace_id, broker, env) '
    '(partial unique index); revoked/expired history may coexist so re-connect is revoke + '
    'insert without DELETE. The secret lives only inside ciphertext as an AES-256-GCM '
    'envelope whose AAD is workspace_id:broker:env, so a ciphertext cannot be replayed '
    'onto another row. RLS on with no policies; service_role may SELECT/INSERT and UPDATE '
    'only (status, revoked_at, last_used_at).';

COMMENT ON COLUMN public.broker_connections.key_id IS
    'Master-key version that sealed this row (DIGIQUANT_VAULT_KEY_ID, e.g. v1) — not a '
    'broker-side key id; an API key''s own key_id is inside the sealed payload.';

COMMENT ON COLUMN public.broker_connections.fingerprint IS
    'First 8 hex chars of sha256 over the secret material: the only display-safe artifact '
    'for a connection. A label, never an identity — 32 bits collide, so never compare '
    'fingerprints to conclude two rows hold the same credential.';

COMMENT ON COLUMN public.broker_connections.workspace_id IS
    'Owning workspace. FK-less until T0 creates public.workspaces, which will constrain '
    'it; the house operator row uses the system workspace id.';

COMMENT ON FUNCTION public.reject_broker_connection_credential_mutation() IS
    'Rejects any UPDATE that changes a credential/identity column, and rejects TRUNCATE. '
    'Defense in depth behind the column-level UPDATE grant. DELETE is deliberately not '
    'blocked: a credential store must stay erasable.';
