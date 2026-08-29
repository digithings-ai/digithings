-- 097_workspaces_tenant_columns.sql
--
-- T0 (Kairos + tenancy program, spec §5-T0 / roadmap P2b) — Wave 3 multi-tenant schema,
-- part 2 of 3: `workspace_id` on the private set. Requires 096 (workspaces table +
-- house/system seeds) to have run first.
--
-- Pattern for every table below, per the briefing: add the column NULLable, backfill
-- every existing row to the house workspace (097's own migration, one UPDATE per
-- table), THEN `SET NOT NULL`, in that explicit order — never a single-step NOT NULL
-- add, which would fail against rows that already exist.
--
-- ============================================================================
-- Tables touched by this migration, and the reasoning per group
-- ============================================================================
--
-- Group A — legacy single-tenant tables with many pre-existing Python writers
-- (`positions`, `position_events`, `nav_history`, `portfolio_metrics`):
--   * `workspace_id` carries a column DEFAULT of the house workspace id. This is a
--     deliberate safety net, NOT a substitute for patching writers: roadmap P6 lists
--     these tables' remaining legacy writers (`scripts/update_tearsheet.py` chief among
--     them) as a SEPARATE, later phase ("Wave 2 invokes; Wave 3 extends with
--     --workspace-id"). The writers this T0 WP is scoped to patch (`commit_io.py`,
--     `execute_at_open.py` — see the accompanying Python changes in this PR) pass
--     `workspace_id` explicitly and do not rely on the default. Writers P6 has not
--     reached yet (`update_tearsheet.py`) keep inserting without the column and
--     silently land in the house workspace via the DEFAULT — correct today, since only
--     the house workspace has any data, and a documented, tracked gap once a second
--     workspace exists. Their `ON CONFLICT` arbiter DOES need updating to the widened
--     key once this migration ships to a live database — that is exactly the P6 follow
--     -up work, called out here so it is not lost.
--   * UNIQUE constraints widen per roadmap P2b. Every constraint this migration
--     changes (enumerate for reviewers / T0 acceptance):
--       DROP positions_date_ticker_key
--         → ADD uq_positions_workspace_date_ticker UNIQUE (workspace_id, date, ticker)
--       DROP position_events_date_ticker_key
--         → ADD uq_position_events_workspace_date_ticker UNIQUE (workspace_id, date, ticker)
--       DROP nav_history_pkey
--         → ADD nav_history_pkey PRIMARY KEY (workspace_id, date)
--       DROP portfolio_metrics_date_key
--         → ADD uq_portfolio_metrics_workspace_date UNIQUE (workspace_id, date)
--     Plus new FK `fk_<table>_workspace` on every table that gains the column.
--
-- Group B — private, service-role-only, fully-patched-in-this-PR tables
-- (`portfolio_ledger_commits`, `portfolio_ledger_decision_intents`,
-- `portfolio_ledger_requested_targets`, `portfolio_ledger_target_adjustments`,
-- `portfolio_ledger_approved_targets`, `portfolio_ledger_order_intents`,
-- `portfolio_ledger_paper_executions`, `portfolio_ledger_holding_lots`,
-- `olympus_accounting_periods`, `olympus_accounting_contributions`,
-- `olympus_accounting_holdings`):
--   * NO column DEFAULT — every writer that reaches these tables
--     (`ledger_io._insert`, `accounting.io._insert`, and everything that calls through
--     them: `execution_io`, `opening_snapshot`) is patched in this same PR to stamp
--     the house workspace id explicitly (see the accompanying Python changes). A
--     missing `workspace_id` on insert is a real bug here, not a legacy gap, so it
--     should fail loudly (NOT NULL violation) rather than silently default.
--   * NOT widening the existing lineage UNIQUE/composite-FK constraints
--     (`uq_..._id_run_date`, `uq_..._one_root`, the `(supersedes_id, run_date[,
--     symbol])` composite FKs, etc.) — roadmap P2b's enumerated constraint list does
--     NOT include these tables, and every writer here is single-workspace (house) for
--     the life of this WP, so `run_date`/`(run_date, symbol)` already uniquely scope
--     each lineage in practice. Widening the composite FK chains to also carry
--     `workspace_id` is real, non-trivial follow-up work (every composite FK and
--     partial unique index in migrations 069/072 would need a matching rebuild) that
--     belongs to whichever later WP actually lands multi-workspace writers for these
--     tables (T4), not to this schema-only WP. Called out loudly here per the T0
--     acceptance criteria ("enumerate every constraint you change") — this migration
--     changes ZERO constraints on these eleven tables beyond adding the column, the
--     backfill, the NOT NULL, and a new FK to `workspaces(id)`.
--
-- Group C — `olympus_profile_config` overlay rows:
--   * The existing house row (`is_house_default = true`, `profile_key = 'house'`) maps
--     to the **system** workspace per the briefing ("house row maps to the system
--     workspace") — it is the digithings-owned always-on default that every workspace
--     reads, so it belongs to shared/system space, not the house *book* workspace
--     Group A/B backfill to. No overlay (`is_house_default = false`) rows exist yet in
--     this codebase (T3/T4 land the first writer), so there is nothing else to
--     backfill. NO column DEFAULT — the day a real overlay writer lands, it must pass
--     its own workspace_id explicitly; there is no sensible fallback for "which user's
--     overlay is this."
--
-- Skipped entirely (per the T0 briefing): `broker_connections`, `broker_orders`,
-- `broker_executions`, `broker_position_snapshots`, `notification_prefs` — these K3/K4/
-- K5 tables do not exist in this codebase yet. They pick up `workspace_id` at CREATE
-- TABLE time in their own K-track migrations, not retrofitted here.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one psql
-- single-transaction call. Every step below is replay-safe (IF NOT EXISTS / IF EXISTS
-- guards on every ADD/DROP), so a second run against an already-migrated database is a
-- no-op, not an error.

-- ============================================================================
-- Group A: positions, position_events, nav_history, portfolio_metrics
-- ============================================================================

ALTER TABLE public.positions
    ADD COLUMN IF NOT EXISTS workspace_id uuid
        DEFAULT '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid;
UPDATE public.positions SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
    WHERE workspace_id IS NULL;
ALTER TABLE public.positions ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.positions
        ADD CONSTRAINT fk_positions_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
ALTER TABLE public.positions DROP CONSTRAINT IF EXISTS positions_date_ticker_key;
DO $$ BEGIN
    ALTER TABLE public.positions
        ADD CONSTRAINT uq_positions_workspace_date_ticker
        UNIQUE (workspace_id, date, ticker);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_positions_workspace_date
    ON public.positions (workspace_id, date DESC);

ALTER TABLE public.position_events
    ADD COLUMN IF NOT EXISTS workspace_id uuid
        DEFAULT '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid;
UPDATE public.position_events SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
    WHERE workspace_id IS NULL;
ALTER TABLE public.position_events ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.position_events
        ADD CONSTRAINT fk_position_events_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
ALTER TABLE public.position_events DROP CONSTRAINT IF EXISTS position_events_date_ticker_key;
DO $$ BEGIN
    ALTER TABLE public.position_events
        ADD CONSTRAINT uq_position_events_workspace_date_ticker
        UNIQUE (workspace_id, date, ticker);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_position_events_workspace_date
    ON public.position_events (workspace_id, date DESC);

ALTER TABLE public.nav_history
    ADD COLUMN IF NOT EXISTS workspace_id uuid
        DEFAULT '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid;
UPDATE public.nav_history SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
    WHERE workspace_id IS NULL;
ALTER TABLE public.nav_history ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.nav_history
        ADD CONSTRAINT fk_nav_history_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
-- nav_history's original migration-001 PK is `date` alone (no surrogate id column) —
-- widening it means dropping and rebuilding the PRIMARY KEY itself, not a separate
-- UNIQUE constraint.
ALTER TABLE public.nav_history DROP CONSTRAINT IF EXISTS nav_history_pkey;
DO $$ BEGIN
    ALTER TABLE public.nav_history
        ADD CONSTRAINT nav_history_pkey PRIMARY KEY (workspace_id, date);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE public.portfolio_metrics
    ADD COLUMN IF NOT EXISTS workspace_id uuid
        DEFAULT '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid;
UPDATE public.portfolio_metrics SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
    WHERE workspace_id IS NULL;
ALTER TABLE public.portfolio_metrics ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.portfolio_metrics
        ADD CONSTRAINT fk_portfolio_metrics_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
ALTER TABLE public.portfolio_metrics DROP CONSTRAINT IF EXISTS portfolio_metrics_date_key;
DO $$ BEGIN
    ALTER TABLE public.portfolio_metrics
        ADD CONSTRAINT uq_portfolio_metrics_workspace_date
        UNIQUE (workspace_id, date);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_portfolio_metrics_workspace_date
    ON public.portfolio_metrics (workspace_id, date DESC);

-- ============================================================================
-- Group B: portfolio_ledger_* (migration 069) — no DEFAULT, no widened constraints
-- ============================================================================

ALTER TABLE public.portfolio_ledger_commits ADD COLUMN IF NOT EXISTS workspace_id uuid;
UPDATE public.portfolio_ledger_commits SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
    WHERE workspace_id IS NULL;
ALTER TABLE public.portfolio_ledger_commits ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.portfolio_ledger_commits
        ADD CONSTRAINT fk_portfolio_ledger_commits_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_commits_workspace
    ON public.portfolio_ledger_commits (workspace_id);

ALTER TABLE public.portfolio_ledger_decision_intents ADD COLUMN IF NOT EXISTS workspace_id uuid;
UPDATE public.portfolio_ledger_decision_intents
    SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid WHERE workspace_id IS NULL;
ALTER TABLE public.portfolio_ledger_decision_intents ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.portfolio_ledger_decision_intents
        ADD CONSTRAINT fk_portfolio_ledger_decision_intents_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_decision_intents_workspace
    ON public.portfolio_ledger_decision_intents (workspace_id);

ALTER TABLE public.portfolio_ledger_requested_targets ADD COLUMN IF NOT EXISTS workspace_id uuid;
UPDATE public.portfolio_ledger_requested_targets
    SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid WHERE workspace_id IS NULL;
ALTER TABLE public.portfolio_ledger_requested_targets ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.portfolio_ledger_requested_targets
        ADD CONSTRAINT fk_portfolio_ledger_requested_targets_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_requested_targets_workspace
    ON public.portfolio_ledger_requested_targets (workspace_id);

ALTER TABLE public.portfolio_ledger_target_adjustments ADD COLUMN IF NOT EXISTS workspace_id uuid;
UPDATE public.portfolio_ledger_target_adjustments
    SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid WHERE workspace_id IS NULL;
ALTER TABLE public.portfolio_ledger_target_adjustments ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.portfolio_ledger_target_adjustments
        ADD CONSTRAINT fk_portfolio_ledger_target_adjustments_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_target_adjustments_workspace
    ON public.portfolio_ledger_target_adjustments (workspace_id);

ALTER TABLE public.portfolio_ledger_approved_targets ADD COLUMN IF NOT EXISTS workspace_id uuid;
UPDATE public.portfolio_ledger_approved_targets
    SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid WHERE workspace_id IS NULL;
ALTER TABLE public.portfolio_ledger_approved_targets ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.portfolio_ledger_approved_targets
        ADD CONSTRAINT fk_portfolio_ledger_approved_targets_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_approved_targets_workspace
    ON public.portfolio_ledger_approved_targets (workspace_id);

ALTER TABLE public.portfolio_ledger_order_intents ADD COLUMN IF NOT EXISTS workspace_id uuid;
UPDATE public.portfolio_ledger_order_intents
    SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid WHERE workspace_id IS NULL;
ALTER TABLE public.portfolio_ledger_order_intents ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.portfolio_ledger_order_intents
        ADD CONSTRAINT fk_portfolio_ledger_order_intents_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_order_intents_workspace
    ON public.portfolio_ledger_order_intents (workspace_id);

ALTER TABLE public.portfolio_ledger_paper_executions ADD COLUMN IF NOT EXISTS workspace_id uuid;
UPDATE public.portfolio_ledger_paper_executions
    SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid WHERE workspace_id IS NULL;
ALTER TABLE public.portfolio_ledger_paper_executions ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.portfolio_ledger_paper_executions
        ADD CONSTRAINT fk_portfolio_ledger_paper_executions_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_paper_executions_workspace
    ON public.portfolio_ledger_paper_executions (workspace_id);

ALTER TABLE public.portfolio_ledger_holding_lots ADD COLUMN IF NOT EXISTS workspace_id uuid;
UPDATE public.portfolio_ledger_holding_lots
    SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid WHERE workspace_id IS NULL;
ALTER TABLE public.portfolio_ledger_holding_lots ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.portfolio_ledger_holding_lots
        ADD CONSTRAINT fk_portfolio_ledger_holding_lots_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_portfolio_ledger_holding_lots_workspace
    ON public.portfolio_ledger_holding_lots (workspace_id);

-- ============================================================================
-- Group B: olympus_accounting_* (migration 072) — same rules as portfolio_ledger_*
-- ============================================================================

ALTER TABLE public.olympus_accounting_periods ADD COLUMN IF NOT EXISTS workspace_id uuid;
UPDATE public.olympus_accounting_periods
    SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid WHERE workspace_id IS NULL;
ALTER TABLE public.olympus_accounting_periods ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.olympus_accounting_periods
        ADD CONSTRAINT fk_olympus_accounting_periods_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_olympus_accounting_periods_workspace
    ON public.olympus_accounting_periods (workspace_id);

ALTER TABLE public.olympus_accounting_contributions ADD COLUMN IF NOT EXISTS workspace_id uuid;
UPDATE public.olympus_accounting_contributions
    SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid WHERE workspace_id IS NULL;
ALTER TABLE public.olympus_accounting_contributions ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.olympus_accounting_contributions
        ADD CONSTRAINT fk_olympus_accounting_contributions_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_olympus_accounting_contributions_workspace
    ON public.olympus_accounting_contributions (workspace_id);

ALTER TABLE public.olympus_accounting_holdings ADD COLUMN IF NOT EXISTS workspace_id uuid;
UPDATE public.olympus_accounting_holdings
    SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid WHERE workspace_id IS NULL;
ALTER TABLE public.olympus_accounting_holdings ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.olympus_accounting_holdings
        ADD CONSTRAINT fk_olympus_accounting_holdings_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_olympus_accounting_holdings_workspace
    ON public.olympus_accounting_holdings (workspace_id);

-- ============================================================================
-- Group C: olympus_profile_config (migration 075) — house row -> SYSTEM workspace
-- ============================================================================

ALTER TABLE public.olympus_profile_config ADD COLUMN IF NOT EXISTS workspace_id uuid;
-- The house row is the digithings-owned always-on default every workspace reads —
-- shared space, not the house *book* Groups A/B backfill to.
UPDATE public.olympus_profile_config
    SET workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid
    WHERE workspace_id IS NULL AND is_house_default = true;
-- No non-house rows exist yet in this codebase (T3/T4 land the first overlay writer),
-- but guard anyway: any row this UPDATE cannot classify blocks the NOT NULL below
-- loudly rather than silently landing in the wrong workspace.
ALTER TABLE public.olympus_profile_config ALTER COLUMN workspace_id SET NOT NULL;
DO $$ BEGIN
    ALTER TABLE public.olympus_profile_config
        ADD CONSTRAINT fk_olympus_profile_config_workspace
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_olympus_profile_config_workspace
    ON public.olympus_profile_config (workspace_id);

COMMENT ON COLUMN public.positions.workspace_id IS
    'Tenant scope (T0, #5-T0). DEFAULTs to the house workspace as a safety net for '
    'writers roadmap P6 has not yet extended (e.g. scripts/update_tearsheet.py); every '
    'writer this WP patches passes it explicitly.';
COMMENT ON COLUMN public.portfolio_ledger_commits.workspace_id IS
    'Tenant scope (T0, #5-T0). No DEFAULT — every writer reaching this table is '
    'patched in the same PR that added this column to stamp it explicitly.';
COMMENT ON COLUMN public.olympus_accounting_periods.workspace_id IS
    'Tenant scope (T0, #5-T0). No DEFAULT — accounting.io._insert stamps it '
    'explicitly on every row.';
COMMENT ON COLUMN public.olympus_profile_config.workspace_id IS
    'Tenant scope (T0, #5-T0). The house row (is_house_default=true) maps to the '
    'SYSTEM workspace, not the house book workspace — it is shared, always-on '
    'default config every tenant reads.';
