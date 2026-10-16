-- 102_kairos_broker_mirror.sql
--
-- Broker mirror tables (K4, Kairos milestone 1). Append-only submission / fill /
-- position-snapshot mirrors for external venues (D10): the broker is authoritative
-- for fills and positions; digithings never forges internal paper executions from
-- them. Status changes append a new `broker_orders` row with backward
-- `supersedes_id` (same convention as `portfolio_ledger_order_intents`).
--
-- HUMAN GATE: broker adapters / live-trading path adjacency. This migration is not
-- applied live without the repository's human migration review gate.
--
-- MIGRATION NUMBER — READ BEFORE RENUMBERING: 102 was taken deliberately, not as
-- "next free after 099". Sibling T2 work holds 100 (+ possibly 101) for Stripe /
-- claim-sync schema. If the sequence still has gaps once those branches merge,
-- renumber THIS file down at merge time — it has not been applied anywhere, so
-- its number is free to change, and `db-migrate.yml` keys its ledger on the
-- filename (an applied file's name is never rewritten). Move
-- `tests/dq/olympus/kairos/test_migration_102.py` with it.
--
-- Deterministic ids (Python writers; comments here are the contract):
--   broker_orders (submit): uuid5(ns_orders, f"{order_intent_id}:{broker}:{date}")
--   broker_orders (status): uuid5(ns_orders, f"status:{prior_id}:{status}:{iso_ts}")
--   broker_executions:      uuid5(connection_id, external_fill_id)
--   broker_position_snapshots: uuid5(ns_snap, f"{connection_id}:{as_of.isoformat()}")
-- A retry recomputes the same id and collides — never duplicates. `upsert` is
-- forbidden in the K4 writers (same rule as `execution_io`).
--
-- workspace_id is REAL and FK'd: T0 (096–098) is on this branch, so every mirror
-- row stamps the owning workspace and REFERENCES public.workspaces(id). This
-- migration also back-fills the FK on broker_connections.workspace_id that K3
-- left deferred.
--
-- Privileges — deny by default, then the narrowest thing that works (069 pattern):
--   * RLS enabled with NO policies (anon/authenticated reach nothing).
--   * ALL revoked from PUBLIC/anon/authenticated, then from service_role.
--   * service_role receives SELECT + INSERT only (append-only).
--   * BEFORE UPDATE/DELETE/TRUNCATE triggers reject mutation.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one
-- psql single-transaction call. All DDL is replay-safe through IF NOT EXISTS,
-- CREATE OR REPLACE, and DROP TRIGGER IF EXISTS before CREATE TRIGGER.

-- ---------------------------------------------------------------------------
-- K3 follow-up: constrain broker_connections.workspace_id now that workspaces
-- exists (T0). Idempotent — skip if the FK is already present.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'broker_connections_workspace_id_fkey'
          AND conrelid = 'public.broker_connections'::regclass
    ) THEN
        ALTER TABLE public.broker_connections
            ADD CONSTRAINT broker_connections_workspace_id_fkey
            FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- broker_orders — append-only submission / status mirror
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.broker_orders (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES public.workspaces (id),
    connection_id uuid NOT NULL REFERENCES public.broker_connections (id),
    -- Nullable: manual / UI-originated orders have no Hermes intent.
    order_intent_id uuid,
    client_order_id text NOT NULL,
    external_order_id text,
    symbol text NOT NULL,
    side text NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity numeric CHECK (quantity IS NULL OR quantity > 0),
    notional numeric CHECK (notional IS NULL OR notional > 0),
    order_type text NOT NULL DEFAULT 'market',
    time_in_force text NOT NULL DEFAULT 'day',
    status text NOT NULL CHECK (
        status IN (
            'submitted',
            'accepted',
            'partially_filled',
            'filled',
            'canceled',
            'rejected',
            'expired'
        )
    ),
    supersedes_id uuid REFERENCES public.broker_orders (id),
    raw_payload_sha256 text CHECK (
        raw_payload_sha256 IS NULL OR raw_payload_sha256 ~ '^[0-9a-f]{64}$'
    ),
    submitted_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT broker_orders_quantity_xor_notional CHECK (
        (quantity IS NULL) <> (notional IS NULL)
        OR (quantity IS NULL AND notional IS NULL)
    ),
    CONSTRAINT broker_orders_no_self_supersede CHECK (
        supersedes_id IS NULL OR supersedes_id <> id
    )
);

CREATE INDEX IF NOT EXISTS broker_orders_workspace_recorded_idx
    ON public.broker_orders (workspace_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS broker_orders_connection_recorded_idx
    ON public.broker_orders (connection_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS broker_orders_order_intent_idx
    ON public.broker_orders (order_intent_id)
    WHERE order_intent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS broker_orders_external_order_idx
    ON public.broker_orders (connection_id, external_order_id)
    WHERE external_order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS broker_orders_supersedes_idx
    ON public.broker_orders (supersedes_id)
    WHERE supersedes_id IS NOT NULL;

COMMENT ON TABLE public.broker_orders IS
    'K4 append-only broker order mirror. Status change = new row with supersedes_id. '
    'Deterministic submit id: uuid5(ns, order_intent_id:broker:date).';

-- ---------------------------------------------------------------------------
-- broker_executions — append-only fill mirror (idempotent on broker fill id)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.broker_executions (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES public.workspaces (id),
    broker_order_id uuid NOT NULL REFERENCES public.broker_orders (id),
    external_fill_id text NOT NULL,
    symbol text NOT NULL,
    quantity numeric NOT NULL CHECK (quantity > 0),
    price numeric NOT NULL CHECK (price > 0),
    fee numeric CHECK (fee IS NULL OR fee >= 0),
    executed_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (broker_order_id, external_fill_id)
);

CREATE INDEX IF NOT EXISTS broker_executions_workspace_executed_idx
    ON public.broker_executions (workspace_id, executed_at DESC);
CREATE INDEX IF NOT EXISTS broker_executions_order_idx
    ON public.broker_executions (broker_order_id);

COMMENT ON TABLE public.broker_executions IS
    'K4 append-only broker fill mirror. id = uuid5(connection_id, external_fill_id). '
    'UNIQUE (broker_order_id, external_fill_id) makes a retry collide, never duplicate.';

-- ---------------------------------------------------------------------------
-- broker_position_snapshots — point-in-time broker truth + reconciliation flag
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.broker_position_snapshots (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES public.workspaces (id),
    connection_id uuid NOT NULL REFERENCES public.broker_connections (id),
    as_of timestamptz NOT NULL,
    positions jsonb NOT NULL,
    account jsonb NOT NULL,
    -- Set when mirrored fill-implied positions disagree with the broker snapshot.
    -- Never triggers auto-corrective orders (D10).
    reconciliation_diverged boolean NOT NULL DEFAULT false,
    reconciliation_report jsonb,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (connection_id, as_of)
);

CREATE INDEX IF NOT EXISTS broker_position_snapshots_workspace_as_of_idx
    ON public.broker_position_snapshots (workspace_id, as_of DESC);
CREATE INDEX IF NOT EXISTS broker_position_snapshots_diverged_idx
    ON public.broker_position_snapshots (connection_id, as_of DESC)
    WHERE reconciliation_diverged;

COMMENT ON TABLE public.broker_position_snapshots IS
    'K4 broker account/positions snapshot. reconciliation_diverged surfaces mirror '
    'disagreement; digithings never auto-submits corrective orders (D10).';

-- ---------------------------------------------------------------------------
-- Append-only enforcement (069 pattern)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.reject_broker_mirror_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'kairos broker mirror is append-only'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS reject_broker_orders_mutation ON public.broker_orders;
CREATE TRIGGER reject_broker_orders_mutation
    BEFORE UPDATE OR DELETE ON public.broker_orders
    FOR EACH ROW EXECUTE FUNCTION public.reject_broker_mirror_mutation();
DROP TRIGGER IF EXISTS reject_broker_orders_truncate ON public.broker_orders;
CREATE TRIGGER reject_broker_orders_truncate
    BEFORE TRUNCATE ON public.broker_orders
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_broker_mirror_mutation();

DROP TRIGGER IF EXISTS reject_broker_executions_mutation ON public.broker_executions;
CREATE TRIGGER reject_broker_executions_mutation
    BEFORE UPDATE OR DELETE ON public.broker_executions
    FOR EACH ROW EXECUTE FUNCTION public.reject_broker_mirror_mutation();
DROP TRIGGER IF EXISTS reject_broker_executions_truncate ON public.broker_executions;
CREATE TRIGGER reject_broker_executions_truncate
    BEFORE TRUNCATE ON public.broker_executions
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_broker_mirror_mutation();

DROP TRIGGER IF EXISTS reject_broker_position_snapshots_mutation
    ON public.broker_position_snapshots;
CREATE TRIGGER reject_broker_position_snapshots_mutation
    BEFORE UPDATE OR DELETE ON public.broker_position_snapshots
    FOR EACH ROW EXECUTE FUNCTION public.reject_broker_mirror_mutation();
DROP TRIGGER IF EXISTS reject_broker_position_snapshots_truncate
    ON public.broker_position_snapshots;
CREATE TRIGGER reject_broker_position_snapshots_truncate
    BEFORE TRUNCATE ON public.broker_position_snapshots
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_broker_mirror_mutation();

REVOKE ALL ON FUNCTION public.reject_broker_mirror_mutation()
    FROM PUBLIC, anon, authenticated;

-- ---------------------------------------------------------------------------
-- RLS deny-by-default + service_role SELECT/INSERT
-- ---------------------------------------------------------------------------
ALTER TABLE public.broker_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.broker_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.broker_position_snapshots ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.broker_orders FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.broker_executions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.broker_position_snapshots FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.broker_orders FROM service_role;
REVOKE ALL ON public.broker_executions FROM service_role;
REVOKE ALL ON public.broker_position_snapshots FROM service_role;

GRANT SELECT, INSERT ON public.broker_orders TO service_role;
GRANT SELECT, INSERT ON public.broker_executions TO service_role;
GRANT SELECT, INSERT ON public.broker_position_snapshots TO service_role;
