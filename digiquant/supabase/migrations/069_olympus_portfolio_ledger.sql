-- 069_olympus_portfolio_ledger.sql
--
-- Private, append-only portfolio lineage ledger (#2415, closes Finding OLY-REV-009).
--
-- Today, "decision", "target", "order", and "fill" are conflated across mutable
-- snapshots and documents. This migration separates them into one explicit,
-- replayable chain of eight tables:
--
--   portfolio_ledger_commits            (daily lineage-chain anchor for one run_date)
--     -> portfolio_ledger_decision_intents   (H7/H8 symbol-level decision + required reason)
--       -> portfolio_ledger_requested_targets  (raw pre-adjustment weight/quantity)
--         -> portfolio_ledger_target_adjustments (cap/rounding/carry applied to a request)
--         -> portfolio_ledger_approved_targets   (final approved weight/quantity, supersedable)
--           -> portfolio_ledger_order_intents      (paper order intent, terminal once executed)
--             -> portfolio_ledger_paper_executions   (immutable fill, idempotent on retry)
--               -> portfolio_ledger_holding_lots       (position lot opened/closed by a fill)
--
-- Scope — contracts and schema only. This migration does not change H7/H8/H9 ownership
-- and does not touch any live-trading or broker path. `writers/commit_io.py` (H9) remains
-- the sole authoritative booking writer; it is untouched and is not dual-written by this
-- ledger yet (see digiquant/ARCHITECTURE.md). `portfolio_ledger_commits` is a read-side
-- lineage anchor these rows point back to — it is not a duplicate of H9's own commit
-- manifest.
--
-- Every economically meaningful column that can legitimately be unknown (a requested or
-- approved weight/quantity) is nullable with no numeric DEFAULT, so "unknown" stays NULL
-- rather than being fabricated as zero; an explicit 0 (e.g. a full-exit target) remains a
-- distinct, legal value from "missing". Columns that describe a real fill or lot
-- (quantity, price, open_price) are NOT NULL with a strictly-positive CHECK instead: "no
-- fill happened" is the absence of a `portfolio_ledger_paper_executions` row, never a
-- zero-valued one.
--
-- Lifecycle CHECK constraints below use `IS NULL` / `IS NOT NULL` rather than
-- `IS NOT DISTINCT FROM` (contrast migration 067's `no_artifact_reason` check). That
-- distinction matters only when a nullable column is compared to a specific literal via
-- bare `=` conditioned on another branch — Postgres CHECK admits a NULL result as passing,
-- so `TRUE AND (col = 'x')` silently passes when `col` is NULL. Every lifecycle CHECK here
-- instead tests nullability itself (`IS NULL` / `IS NOT NULL`) against a NOT NULL
-- discriminant column (`status`/`action`) — those operators never themselves evaluate to
-- NULL, so no three-valued-logic contamination is possible and `IS NOT DISTINCT FROM`
-- would be a cargo-cult addition, not a requirement.
--
-- RLS is enabled with no policies, and all privileges are revoked from client roles.
-- Privileges are revoked from service_role before the grant as well: a Supabase project
-- ships ALTER DEFAULT PRIVILEGES ... GRANT ALL ON TABLES TO service_role, so an additive
-- grant alone would leave the inherited UPDATE/DELETE/TRUNCATE in place. After the revoke,
-- service_role receives SELECT and INSERT only. A single shared trigger function rejects
-- UPDATE and DELETE per row and TRUNCATE per statement for every role that reaches these
-- tables through the normal grants above, including service_role, on all eight tables:
-- corrections always append a superseding record, never rewrite one in place. Triggers
-- cannot make a stronger claim than that — a table owner can `ALTER TABLE ... DISABLE
-- TRIGGER ALL` before an UPDATE, and a superuser session can set
-- `session_replication_role = 'replica'` to skip origin triggers entirely; neither
-- bypass is available to service_role itself, but both remain available to whoever
-- controls the database.
--
-- Lifecycle rows are written once, already in their final state, never patched toward it:
-- a `rejected`/`executed` row is INSERTed with that status already populated — it is
-- never a `pending` row later flipped in place (UPDATE is rejected by the trigger above;
-- re-INSERTing the same id is rejected by the PRIMARY KEY). Supersession is recorded the
-- same way, and every supersession link in this schema is backward-only: a new row's
-- `supersedes_id` (`commits.supersedes_id`, `approved_targets.supersedes_id`,
-- `order_intents.supersedes_id`) points back at the prior row it replaces. A forward
-- link — the row being replaced pointing at its not-yet-existing successor —
-- cannot be recorded under this same append-only rule: populating it after the successor
-- exists is an UPDATE (rejected by the trigger), and there is no other row to populate it
-- on at INSERT time, since the successor doesn't exist yet.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one psql
-- single-transaction call. All DDL is replay-safe through IF NOT EXISTS, CREATE OR
-- REPLACE, and DROP TRIGGER IF EXISTS before CREATE TRIGGER.

CREATE TABLE IF NOT EXISTS public.portfolio_ledger_commits (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_date date NOT NULL,
    policy_version_id text NOT NULL CHECK (length(policy_version_id) BETWEEN 1 AND 100),
    supersedes_id uuid,
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    -- Composite target for the FK below: lets supersedes_id's FK also pin run_date, so a
    -- row can only supersede a prior row from the same run_date's lineage.
    CONSTRAINT uq_portfolio_ledger_commits_id_run_date
        UNIQUE (id, run_date),
    -- Composite FK (not a plain id-only reference): default MATCH SIMPLE means a NULL
    -- supersedes_id (root rows) short-circuits the whole check, but a populated
    -- supersedes_id must match both id and run_date on the superseded row, so a commit
    -- can never "supersede" a row from an unrelated run_date.
    CONSTRAINT fk_portfolio_ledger_commits_supersedes
        FOREIGN KEY (supersedes_id, run_date)
        REFERENCES public.portfolio_ledger_commits (id, run_date),
    -- No status column: a same-date recommit is always a new row whose supersedes_id
    -- points back at the prior commit it replaces (mirroring approved_targets below),
    -- never a mutation of that prior row. Currency is purely structural — a commit is
    -- current for its run_date iff no later commit's supersedes_id points at it — and
    -- is enforced by uq_portfolio_ledger_commits_one_root below, not by a status value.
    CONSTRAINT chk_portfolio_ledger_commits_no_self_supersede
        CHECK (supersedes_id IS NULL OR supersedes_id <> id)
);

CREATE TABLE IF NOT EXISTS public.portfolio_ledger_decision_intents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_commit_id uuid NOT NULL,
    run_date date NOT NULL,
    symbol text NOT NULL CHECK (length(symbol) BETWEEN 1 AND 20),
    action text NOT NULL CHECK (action IN ('add', 'trim', 'exit', 'no_op', 'reject')),
    reason text NOT NULL CHECK (
        reason IN (
            'new_conviction',
            'conviction_reduced',
            'thesis_invalidated',
            'no_signal_change',
            'risk_cap_breach',
            'low_conviction',
            'data_unavailable'
        )
    ),
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_portfolio_ledger_decision_intents_commit
        FOREIGN KEY (portfolio_commit_id)
        REFERENCES public.portfolio_ledger_commits (id),
    -- reason is NOT NULL above, so every decision (including no_op/reject) always carries
    -- one — never a bare null. This CHECK additionally closes off the second axis of
    -- ambiguity: a technically-non-null reason that does not make sense for the action.
    CONSTRAINT chk_portfolio_ledger_decision_intents_action_reason
        CHECK (
            (action = 'add' AND reason = 'new_conviction')
            OR (action = 'trim' AND reason = 'conviction_reduced')
            OR (action = 'exit' AND reason = 'thesis_invalidated')
            OR (action = 'no_op' AND reason IN ('no_signal_change', 'data_unavailable'))
            OR (
                action = 'reject'
                AND reason IN ('risk_cap_breach', 'low_conviction', 'data_unavailable')
            )
        )
);

CREATE TABLE IF NOT EXISTS public.portfolio_ledger_requested_targets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_intent_id uuid NOT NULL,
    run_date date NOT NULL,
    symbol text NOT NULL CHECK (length(symbol) BETWEEN 1 AND 20),
    requested_weight numeric CHECK (
        requested_weight IS NULL OR requested_weight BETWEEN 0 AND 1
    ),
    -- `AND NOT (... = 'NaN'::numeric)` and `AND NOT (... = 'Infinity'::numeric)` are both
    -- required, not decorative: unlike IEEE floats, Postgres `numeric` treats NaN as equal
    -- to itself and greater than every other value, so `'NaN'::numeric >= 0` is TRUE, and
    -- `'Infinity'::numeric` is a legitimate positive `numeric` value that also passes a
    -- bare `>= 0`/`> 0` guard — neither fails closed without an explicit exclusion. Weight
    -- columns need neither guard: `NaN BETWEEN 0 AND 1` and `'Infinity'::numeric BETWEEN 0
    -- AND 1` are both false, so the BETWEEN already fails closed; every other economically
    -- meaningful numeric column in this migration (here and in target_adjustments,
    -- approved_targets, order_intents, paper_executions, holding_lots below) carries both
    -- explicit guards.
    requested_quantity numeric CHECK (
        requested_quantity IS NULL
        OR (
            requested_quantity >= 0
            AND NOT (requested_quantity = 'NaN'::numeric)
            AND NOT (requested_quantity = 'Infinity'::numeric)
        )
    ),
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_portfolio_ledger_requested_targets_decision
        FOREIGN KEY (decision_intent_id)
        REFERENCES public.portfolio_ledger_decision_intents (id),
    -- Neither column has a DEFAULT: an unknown weight/quantity stays NULL, never a
    -- coerced 0. An explicit 0 (e.g. a full-exit target) remains legal and distinct.
    -- Exactly one of the two is required (XOR, not OR): a row carrying both would leave
    -- every downstream target_adjustments row against it dimensionally ambiguous, since
    -- adjustments record a bare numeric original_value/adjusted_value with no unit
    -- column of their own and infer weight-vs-quantity from this parent's populated
    -- column.
    -- `<>` (not IS DISTINCT FROM) is deliberate and safe here, matching the header note
    -- above: `IS NOT NULL` never itself evaluates to NULL, so both sides are always a
    -- plain TRUE/FALSE and ordinary `<>` already gives exact XOR with no three-valued-
    -- logic risk.
    CONSTRAINT chk_portfolio_ledger_requested_targets_presence
        CHECK ((requested_weight IS NOT NULL) <> (requested_quantity IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS public.portfolio_ledger_target_adjustments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    requested_target_id uuid NOT NULL,
    run_date date NOT NULL,
    symbol text NOT NULL CHECK (length(symbol) BETWEEN 1 AND 20),
    adjustment_type text NOT NULL CHECK (adjustment_type IN ('cap', 'rounding', 'carry')),
    -- original_value/adjusted_value carry no unit column of their own: the dimension
    -- (weight vs. quantity) is the one that is populated on the parent row this points
    -- back to via requested_target_id. chk_portfolio_ledger_requested_targets_presence
    -- guarantees that parent has exactly one of requested_weight/requested_quantity set
    -- (XOR, not OR), so the dimension is always inferable, never ambiguous.
    -- NaN guard: see portfolio_ledger_requested_targets above.
    original_value numeric NOT NULL CHECK (
        original_value >= 0
        AND NOT (original_value = 'NaN'::numeric)
        AND NOT (original_value = 'Infinity'::numeric)
    ),
    adjusted_value numeric NOT NULL CHECK (
        adjusted_value >= 0
        AND NOT (adjusted_value = 'NaN'::numeric)
        AND NOT (adjusted_value = 'Infinity'::numeric)
    ),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 200),
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_portfolio_ledger_target_adjustments_requested_target
        FOREIGN KEY (requested_target_id)
        REFERENCES public.portfolio_ledger_requested_targets (id),
    CONSTRAINT chk_portfolio_ledger_target_adjustments_cap_reduces
        CHECK (adjustment_type <> 'cap' OR adjusted_value <= original_value)
);

CREATE TABLE IF NOT EXISTS public.portfolio_ledger_approved_targets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    requested_target_id uuid NOT NULL,
    run_date date NOT NULL,
    symbol text NOT NULL CHECK (length(symbol) BETWEEN 1 AND 20),
    approved_weight numeric CHECK (approved_weight IS NULL OR approved_weight BETWEEN 0 AND 1),
    -- NaN/Infinity guard: see portfolio_ledger_requested_targets above.
    approved_quantity numeric CHECK (
        approved_quantity IS NULL
        OR (
            approved_quantity >= 0
            AND NOT (approved_quantity = 'NaN'::numeric)
            AND NOT (approved_quantity = 'Infinity'::numeric)
        )
    ),
    supersedes_id uuid,
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_portfolio_ledger_approved_targets_requested_target
        FOREIGN KEY (requested_target_id)
        REFERENCES public.portfolio_ledger_requested_targets (id),
    -- Composite target for the FK below: see uq_portfolio_ledger_commits_id_run_date above.
    CONSTRAINT uq_portfolio_ledger_approved_targets_id_run_date_symbol
        UNIQUE (id, run_date, symbol),
    -- Composite FK: see fk_portfolio_ledger_commits_supersedes above — a row can never
    -- "supersede" a row from an unrelated (run_date, symbol) lineage.
    CONSTRAINT fk_portfolio_ledger_approved_targets_supersedes
        FOREIGN KEY (supersedes_id, run_date, symbol)
        REFERENCES public.portfolio_ledger_approved_targets (id, run_date, symbol),
    -- A changed same-date target is always a new row whose supersedes_id points back to
    -- the prior ApprovedTarget it replaces — never a mutation of that prior row.
    CONSTRAINT chk_portfolio_ledger_approved_targets_presence
        CHECK (approved_weight IS NOT NULL OR approved_quantity IS NOT NULL),
    CONSTRAINT chk_portfolio_ledger_approved_targets_no_self_supersede
        CHECK (supersedes_id IS NULL OR supersedes_id <> id)
);

CREATE TABLE IF NOT EXISTS public.portfolio_ledger_order_intents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    approved_target_id uuid NOT NULL,
    run_date date NOT NULL,
    symbol text NOT NULL CHECK (length(symbol) BETWEEN 1 AND 20),
    -- NaN/Infinity guard: see portfolio_ledger_requested_targets above.
    quantity numeric NOT NULL CHECK (
        quantity > 0
        AND NOT (quantity = 'NaN'::numeric)
        AND NOT (quantity = 'Infinity'::numeric)
    ),
    status text NOT NULL CHECK (status IN ('pending', 'executed', 'rejected')),
    supersedes_id uuid,
    rejection_reason text CHECK (
        rejection_reason IS NULL
        OR rejection_reason IN (
            'risk_limit',
            'insufficient_cash',
            'stale_target',
            'market_closed',
            'data_unavailable'
        )
    ),
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_portfolio_ledger_order_intents_approved_target
        FOREIGN KEY (approved_target_id)
        REFERENCES public.portfolio_ledger_approved_targets (id),
    -- Composite target for the FK below: see uq_portfolio_ledger_commits_id_run_date above.
    CONSTRAINT uq_portfolio_ledger_order_intents_id_run_date_symbol
        UNIQUE (id, run_date, symbol),
    -- Composite FK: see fk_portfolio_ledger_commits_supersedes above — a row can never
    -- "supersede" a row from an unrelated (run_date, symbol) lineage.
    CONSTRAINT fk_portfolio_ledger_order_intents_supersedes
        FOREIGN KEY (supersedes_id, run_date, symbol)
        REFERENCES public.portfolio_ledger_order_intents (id, run_date, symbol),
    -- supersedes_id is orthogonal to status and, like approved_targets above, always
    -- backward: a changed same-date order is a new row pointing back at the prior one it
    -- replaces, never a forward link recorded on the row being replaced. An executed row
    -- is still terminal — no other field lets a later write rewrite it in place — but a
    -- fresh replacement order is free to reach its own pending/executed/rejected status
    -- independently of whether it happens to supersede an earlier row.
    CONSTRAINT chk_portfolio_ledger_order_intents_rejection
        CHECK (
            (status = 'rejected' AND rejection_reason IS NOT NULL)
            OR (status <> 'rejected' AND rejection_reason IS NULL)
        ),
    CONSTRAINT chk_portfolio_ledger_order_intents_no_self_supersede
        CHECK (supersedes_id IS NULL OR supersedes_id <> id)
);

CREATE TABLE IF NOT EXISTS public.portfolio_ledger_paper_executions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_intent_id uuid NOT NULL,
    executed_date date NOT NULL,
    symbol text NOT NULL CHECK (length(symbol) BETWEEN 1 AND 20),
    -- NaN/Infinity guard: see portfolio_ledger_requested_targets above.
    quantity numeric NOT NULL CHECK (
        quantity > 0
        AND NOT (quantity = 'NaN'::numeric)
        AND NOT (quantity = 'Infinity'::numeric)
    ),
    price numeric NOT NULL CHECK (
        price > 0
        AND NOT (price = 'NaN'::numeric)
        AND NOT (price = 'Infinity'::numeric)
    ),
    executed_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_portfolio_ledger_paper_executions_order_intent
        FOREIGN KEY (order_intent_id)
        REFERENCES public.portfolio_ledger_order_intents (id),
    -- The application derives id deterministically from (order_intent_id, executed_date)
    -- (see paper_execution_id() in hermes/models/portfolio_ledger.py); this UNIQUE
    -- constraint is the database-level idempotency guard: an exact same-date retry
    -- collides here instead of inserting a second, divergent fill row.
    CONSTRAINT uq_portfolio_ledger_paper_executions_idempotency
        UNIQUE (order_intent_id, executed_date)
);

CREATE TABLE IF NOT EXISTS public.portfolio_ledger_holding_lots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opened_by_execution_id uuid NOT NULL,
    closed_by_execution_id uuid,
    run_date date NOT NULL,
    symbol text NOT NULL CHECK (length(symbol) BETWEEN 1 AND 20),
    -- See portfolio_ledger_paper_executions above: Postgres `numeric` NaN (and Infinity)
    -- both pass a bare `> 0` guard, so both columns exclude them explicitly.
    quantity numeric NOT NULL CHECK (
        quantity > 0
        AND NOT (quantity = 'NaN'::numeric)
        AND NOT (quantity = 'Infinity'::numeric)
    ),
    open_price numeric NOT NULL CHECK (
        open_price > 0
        AND NOT (open_price = 'NaN'::numeric)
        AND NOT (open_price = 'Infinity'::numeric)
    ),
    status text NOT NULL CHECK (status IN ('open', 'closed')),
    opened_at timestamptz NOT NULL,
    closed_at timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_portfolio_ledger_holding_lots_opened_by
        FOREIGN KEY (opened_by_execution_id)
        REFERENCES public.portfolio_ledger_paper_executions (id),
    CONSTRAINT fk_portfolio_ledger_holding_lots_closed_by
        FOREIGN KEY (closed_by_execution_id)
        REFERENCES public.portfolio_ledger_paper_executions (id),
    CONSTRAINT chk_portfolio_ledger_holding_lots_lifecycle
        CHECK (
            (status = 'open' AND closed_at IS NULL AND closed_by_execution_id IS NULL)
            OR (
                status = 'closed'
                AND closed_at IS NOT NULL
                AND closed_by_execution_id IS NOT NULL
            )
        ),
    CONSTRAINT chk_portfolio_ledger_holding_lots_time_order
        CHECK (closed_at IS NULL OR closed_at >= opened_at),
    CONSTRAINT chk_portfolio_ledger_holding_lots_distinct_executions
        CHECK (closed_by_execution_id IS NULL OR closed_by_execution_id <> opened_by_execution_id)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_commits_run_date
    ON public.portfolio_ledger_commits (run_date);
-- Partial UNIQUE indexes, not table CONSTRAINTs: Postgres UNIQUE constraints admit no
-- WHERE clause, so "at most one current row" is only expressible as a unique index.
-- One ROOT commit per run_date: a second row for the same run_date is only ever a
-- superseding recommit (supersedes_id populated), never a second untethered root.
CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_ledger_commits_one_root
    ON public.portfolio_ledger_commits (run_date) WHERE supersedes_id IS NULL;
-- Anti-fork: at most one row may supersede any given commit, so the lineage chain never
-- forks into two competing successors.
CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_ledger_commits_supersedes
    ON public.portfolio_ledger_commits (supersedes_id) WHERE supersedes_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_decision_intents_commit
    ON public.portfolio_ledger_decision_intents (portfolio_commit_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_decision_intents_run_date_symbol
    ON public.portfolio_ledger_decision_intents (run_date, symbol);

CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_requested_targets_decision
    ON public.portfolio_ledger_requested_targets (decision_intent_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_requested_targets_run_date_symbol
    ON public.portfolio_ledger_requested_targets (run_date, symbol);

CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_target_adjustments_requested_target
    ON public.portfolio_ledger_target_adjustments (requested_target_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_target_adjustments_run_date_symbol
    ON public.portfolio_ledger_target_adjustments (run_date, symbol);

CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_approved_targets_requested_target
    ON public.portfolio_ledger_approved_targets (requested_target_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_approved_targets_run_date_symbol
    ON public.portfolio_ledger_approved_targets (run_date, symbol);
-- One current (non-superseded) approved target per (run_date, symbol) — the literal
-- OLY-REV-009 MEDIUM finding this migration closes.
CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_ledger_approved_targets_one_root
    ON public.portfolio_ledger_approved_targets (run_date, symbol) WHERE supersedes_id IS NULL;
-- Anti-fork, same rationale as commits above.
CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_ledger_approved_targets_supersedes
    ON public.portfolio_ledger_approved_targets (supersedes_id) WHERE supersedes_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_order_intents_approved_target
    ON public.portfolio_ledger_order_intents (approved_target_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_order_intents_run_date_symbol
    ON public.portfolio_ledger_order_intents (run_date, symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_order_intents_status
    ON public.portfolio_ledger_order_intents (status);
-- One current (non-superseded) order per (run_date, symbol) — the literal OLY-REV-009
-- MEDIUM finding for order_intents, closed the same way as commits/approved_targets above.
-- An earlier version of this index scoped the predicate to `status = 'pending'` as well
-- as `supersedes_id IS NULL`, which let any row with supersedes_id populated skip the
-- constraint on the status check alone — so once a root left 'pending' (rejected or
-- executed), a brand-new, unrelated pending root could be inserted for the same
-- (run_date, symbol) without colliding, defeating the "at most one live lineage" intent.
-- Scoping on supersedes_id IS NULL alone, independent of status (mirroring
-- commits/approved_targets), closes that gap: a genuine superseding replacement is still
-- exempt because its own supersedes_id is populated, but a second untethered root is not.
CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_ledger_order_intents_one_root
    ON public.portfolio_ledger_order_intents (run_date, symbol) WHERE supersedes_id IS NULL;
-- Anti-fork, same rationale as commits above.
CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_ledger_order_intents_supersedes
    ON public.portfolio_ledger_order_intents (supersedes_id) WHERE supersedes_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_paper_executions_order_intent
    ON public.portfolio_ledger_paper_executions (order_intent_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_paper_executions_executed_date
    ON public.portfolio_ledger_paper_executions (executed_date);

CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_holding_lots_opened_by
    ON public.portfolio_ledger_holding_lots (opened_by_execution_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_holding_lots_closed_by
    ON public.portfolio_ledger_holding_lots (closed_by_execution_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_holding_lots_run_date_symbol
    ON public.portfolio_ledger_holding_lots (run_date, symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_holding_lots_status
    ON public.portfolio_ledger_holding_lots (status);

ALTER TABLE public.portfolio_ledger_commits ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolio_ledger_decision_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolio_ledger_requested_targets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolio_ledger_target_adjustments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolio_ledger_approved_targets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolio_ledger_order_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolio_ledger_paper_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolio_ledger_holding_lots ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.portfolio_ledger_commits FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.portfolio_ledger_decision_intents FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.portfolio_ledger_requested_targets FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.portfolio_ledger_target_adjustments FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.portfolio_ledger_approved_targets FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.portfolio_ledger_order_intents FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.portfolio_ledger_paper_executions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.portfolio_ledger_holding_lots FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.portfolio_ledger_commits FROM service_role;
REVOKE ALL ON public.portfolio_ledger_decision_intents FROM service_role;
REVOKE ALL ON public.portfolio_ledger_requested_targets FROM service_role;
REVOKE ALL ON public.portfolio_ledger_target_adjustments FROM service_role;
REVOKE ALL ON public.portfolio_ledger_approved_targets FROM service_role;
REVOKE ALL ON public.portfolio_ledger_order_intents FROM service_role;
REVOKE ALL ON public.portfolio_ledger_paper_executions FROM service_role;
REVOKE ALL ON public.portfolio_ledger_holding_lots FROM service_role;

GRANT SELECT, INSERT ON public.portfolio_ledger_commits TO service_role;
GRANT SELECT, INSERT ON public.portfolio_ledger_decision_intents TO service_role;
GRANT SELECT, INSERT ON public.portfolio_ledger_requested_targets TO service_role;
GRANT SELECT, INSERT ON public.portfolio_ledger_target_adjustments TO service_role;
GRANT SELECT, INSERT ON public.portfolio_ledger_approved_targets TO service_role;
GRANT SELECT, INSERT ON public.portfolio_ledger_order_intents TO service_role;
GRANT SELECT, INSERT ON public.portfolio_ledger_paper_executions TO service_role;
GRANT SELECT, INSERT ON public.portfolio_ledger_holding_lots TO service_role;

CREATE OR REPLACE FUNCTION public.reject_portfolio_ledger_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'portfolio lineage ledger is append-only'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS reject_portfolio_ledger_commits_mutation
    ON public.portfolio_ledger_commits;
CREATE TRIGGER reject_portfolio_ledger_commits_mutation
    BEFORE UPDATE OR DELETE ON public.portfolio_ledger_commits
    FOR EACH ROW EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();
DROP TRIGGER IF EXISTS reject_portfolio_ledger_commits_truncate
    ON public.portfolio_ledger_commits;
CREATE TRIGGER reject_portfolio_ledger_commits_truncate
    BEFORE TRUNCATE ON public.portfolio_ledger_commits
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();

DROP TRIGGER IF EXISTS reject_portfolio_ledger_decision_intents_mutation
    ON public.portfolio_ledger_decision_intents;
CREATE TRIGGER reject_portfolio_ledger_decision_intents_mutation
    BEFORE UPDATE OR DELETE ON public.portfolio_ledger_decision_intents
    FOR EACH ROW EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();
DROP TRIGGER IF EXISTS reject_portfolio_ledger_decision_intents_truncate
    ON public.portfolio_ledger_decision_intents;
CREATE TRIGGER reject_portfolio_ledger_decision_intents_truncate
    BEFORE TRUNCATE ON public.portfolio_ledger_decision_intents
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();

DROP TRIGGER IF EXISTS reject_portfolio_ledger_requested_targets_mutation
    ON public.portfolio_ledger_requested_targets;
CREATE TRIGGER reject_portfolio_ledger_requested_targets_mutation
    BEFORE UPDATE OR DELETE ON public.portfolio_ledger_requested_targets
    FOR EACH ROW EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();
DROP TRIGGER IF EXISTS reject_portfolio_ledger_requested_targets_truncate
    ON public.portfolio_ledger_requested_targets;
CREATE TRIGGER reject_portfolio_ledger_requested_targets_truncate
    BEFORE TRUNCATE ON public.portfolio_ledger_requested_targets
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();

DROP TRIGGER IF EXISTS reject_portfolio_ledger_target_adjustments_mutation
    ON public.portfolio_ledger_target_adjustments;
CREATE TRIGGER reject_portfolio_ledger_target_adjustments_mutation
    BEFORE UPDATE OR DELETE ON public.portfolio_ledger_target_adjustments
    FOR EACH ROW EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();
DROP TRIGGER IF EXISTS reject_portfolio_ledger_target_adjustments_truncate
    ON public.portfolio_ledger_target_adjustments;
CREATE TRIGGER reject_portfolio_ledger_target_adjustments_truncate
    BEFORE TRUNCATE ON public.portfolio_ledger_target_adjustments
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();

DROP TRIGGER IF EXISTS reject_portfolio_ledger_approved_targets_mutation
    ON public.portfolio_ledger_approved_targets;
CREATE TRIGGER reject_portfolio_ledger_approved_targets_mutation
    BEFORE UPDATE OR DELETE ON public.portfolio_ledger_approved_targets
    FOR EACH ROW EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();
DROP TRIGGER IF EXISTS reject_portfolio_ledger_approved_targets_truncate
    ON public.portfolio_ledger_approved_targets;
CREATE TRIGGER reject_portfolio_ledger_approved_targets_truncate
    BEFORE TRUNCATE ON public.portfolio_ledger_approved_targets
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();

DROP TRIGGER IF EXISTS reject_portfolio_ledger_order_intents_mutation
    ON public.portfolio_ledger_order_intents;
CREATE TRIGGER reject_portfolio_ledger_order_intents_mutation
    BEFORE UPDATE OR DELETE ON public.portfolio_ledger_order_intents
    FOR EACH ROW EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();
DROP TRIGGER IF EXISTS reject_portfolio_ledger_order_intents_truncate
    ON public.portfolio_ledger_order_intents;
CREATE TRIGGER reject_portfolio_ledger_order_intents_truncate
    BEFORE TRUNCATE ON public.portfolio_ledger_order_intents
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();

DROP TRIGGER IF EXISTS reject_portfolio_ledger_paper_executions_mutation
    ON public.portfolio_ledger_paper_executions;
CREATE TRIGGER reject_portfolio_ledger_paper_executions_mutation
    BEFORE UPDATE OR DELETE ON public.portfolio_ledger_paper_executions
    FOR EACH ROW EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();
DROP TRIGGER IF EXISTS reject_portfolio_ledger_paper_executions_truncate
    ON public.portfolio_ledger_paper_executions;
CREATE TRIGGER reject_portfolio_ledger_paper_executions_truncate
    BEFORE TRUNCATE ON public.portfolio_ledger_paper_executions
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();

DROP TRIGGER IF EXISTS reject_portfolio_ledger_holding_lots_mutation
    ON public.portfolio_ledger_holding_lots;
CREATE TRIGGER reject_portfolio_ledger_holding_lots_mutation
    BEFORE UPDATE OR DELETE ON public.portfolio_ledger_holding_lots
    FOR EACH ROW EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();
DROP TRIGGER IF EXISTS reject_portfolio_ledger_holding_lots_truncate
    ON public.portfolio_ledger_holding_lots;
CREATE TRIGGER reject_portfolio_ledger_holding_lots_truncate
    BEFORE TRUNCATE ON public.portfolio_ledger_holding_lots
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_portfolio_ledger_mutation();

REVOKE ALL ON FUNCTION public.reject_portfolio_ledger_mutation()
    FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.portfolio_ledger_commits IS
    'Private append-only daily lineage-chain anchor (#2415). Not H9''s commit manifest — '
    'a read-side anchor the rest of the ledger points back to. A same-date recommit is a '
    'new superseding row, never a mutation of the old one.';

COMMENT ON TABLE public.portfolio_ledger_decision_intents IS
    'Private append-only H7/H8 symbol-level decisions (#2415). reason is NOT NULL on '
    'every row, including no_op/reject, and is cross-checked against action.';

COMMENT ON TABLE public.portfolio_ledger_requested_targets IS
    'Private append-only raw pre-adjustment weight/quantity (#2415). Missing values stay '
    'NULL; an explicit 0 (full exit) remains legal and distinct from unknown.';

COMMENT ON TABLE public.portfolio_ledger_target_adjustments IS
    'Private append-only cap/rounding/carry adjustments applied to a requested target '
    '(#2415). A cap adjustment can only reduce the original value.';

COMMENT ON TABLE public.portfolio_ledger_approved_targets IS
    'Private append-only final approved weight/quantity (#2415). A changed same-date '
    'target is a new row whose supersedes_id links back to the one it replaces.';

COMMENT ON TABLE public.portfolio_ledger_order_intents IS
    'Private append-only paper order intents (#2415). Once status is executed or rejected '
    'the row is terminal: append-only forbids the UPDATE and the PRIMARY KEY forbids '
    're-INSERTing the same id, so no later write can rewrite it. supersedes_id is a '
    'backward link only, orthogonal to status.';

COMMENT ON TABLE public.portfolio_ledger_paper_executions IS
    'Private append-only immutable fill ledger (#2415). id is derived deterministically '
    'from (order_intent_id, executed_date) by the application; the UNIQUE constraint here '
    'is the database-level guarantee that an exact same-date retry is idempotent.';

COMMENT ON TABLE public.portfolio_ledger_holding_lots IS
    'Private append-only position lots opened/closed by a paper execution (#2415). '
    'closed_at/closed_by_execution_id nullability is tied strictly to status.';

COMMENT ON FUNCTION public.reject_portfolio_ledger_mutation() IS
    'Rejects UPDATE, DELETE, and TRUNCATE on every portfolio lineage ledger table; '
    'corrections append a superseding record instead.';
