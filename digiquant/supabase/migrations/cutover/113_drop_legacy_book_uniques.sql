-- ============================================================================
-- STAGED — HUMAN-GATED — NOT AUTO-APPLIED — DO NOT COPY TO TOP-LEVEL YET
-- ============================================================================
-- Filename (when promoted): NNN_drop_legacy_book_uniques.sql
--   where NNN = the then-next free prefix under digiquant/supabase/migrations/
--   (113 if still free after 112_product_invite_codes; check olympus_schema_migrations).
--
-- WHY THIS PATH IS INERT TODAY
--   .github/workflows/db-migrate.yml applies with:
--     find digiquant/supabase/migrations -maxdepth 1 -name '*.sql' | sort
--   digiquant/scripts/atlas/verify-supabase-migrations.sh uses the same
--   -maxdepth 1 glob. scripts/rls_proof/run.sh applies top-level files plus
--   cutover/900 only — it does NOT apply this file. Subdirectories are never
--   listed, never ledger-keyed, and never EXECUTED by db-migrate. This file
--   lives under migrations/cutover/ so a merge to develop/main that only adds
--   it may *trigger* the workflow (paths filter is migrations/**) but the
--   apply loop finds zero new top-level files → no DDL.
--   Do NOT move this file to the migrations/ root until the preconditions
--   below are true.
--
-- HUMAN GATE — DO NOT APPLY ON CORE FROM THIS PR
--   origin/main house GHA writers still upsert Group A books with date-only
--   conflict targets:
--     commit_io.py            on_conflict="date" / "date,ticker"
--     portfolio_materialize   portfolio_metrics / nav_history / positions
--                             on_conflict="date" / "date,ticker"
--   pipeline-olympus.yml checks out `ref: main`. Dropping the legacy
--   UNIQUE(date) / UNIQUE(date, ticker) / PRIMARY KEY (date) while those
--   writers remain date-only raises Postgres 42P10 on the next house
--   metrics/book job (same class of outage as documents after 105, fixed
--   on main by #3278 for documents only).
--
--   Copy this file to digiquant/supabase/migrations/<next>_drop_legacy_book_uniques.sql
--   on a short-lived cutover branch ONLY AFTER:
--     1. origin/main house writers target the widened
--        (workspace_id, date[, ticker]) UNIQUEs (develop already does:
--        #3280 materialize, #3281 metrics, P6 ops-book).
--     2. A successful scheduled pipeline-olympus run on main has proven
--        those widened upserts against core.
--     3. A human approves applying the drop on the target (core).
--   Then open PR → merge → promote to main (db-migrate.yml + production
--   environment approval) OR run manually via psql against core (see
--   docs/agent-backlog/kairos-tenancy/DEPLOYMENT.md). Record the basename
--   in olympus_schema_migrations (db-migrate does this).
--
--   Do NOT remove require_overlay_legacy_book_safe / OverlayLegacyBookBlocked
--   until this file has actually been applied on the target. Staging it
--   here does not lift the Python fail-closed.
--
-- WHAT THIS DROPS (097 leftover single-tenant arbiters)
--   positions          DROP positions_date_ticker_key          UNIQUE(date, ticker)
--   position_events    DROP position_events_date_ticker_key    UNIQUE(date, ticker)
--   nav_history        DROP nav_history_pkey                   PRIMARY KEY (date)
--   portfolio_metrics  DROP portfolio_metrics_date_key         UNIQUE(date)
--
-- WHAT THIS KEEPS (097 widened keys — overlay + house same-date rows)
--   uq_positions_workspace_date_ticker          (workspace_id, date, ticker)
--   uq_position_events_workspace_date_ticker    (workspace_id, date, ticker)
--   uq_nav_history_workspace_date               (workspace_id, date)
--   uq_portfolio_metrics_workspace_date         (workspace_id, date)
--
-- WHAT THIS ALSO WIDENS (069 one-root-per-run_date — overlay + house ledger)
--   uq_portfolio_ledger_commits_one_root
--     FROM (run_date) WHERE supersedes_id IS NULL
--     TO   (workspace_id, run_date) WHERE supersedes_id IS NULL
--   uq_portfolio_ledger_approved_targets_one_root
--     FROM (run_date, symbol) WHERE supersedes_id IS NULL
--     TO   (workspace_id, run_date, symbol) WHERE supersedes_id IS NULL
--   uq_portfolio_ledger_order_intents_one_root
--     FROM (run_date, symbol) WHERE supersedes_id IS NULL
--     TO   (workspace_id, run_date, symbol) WHERE supersedes_id IS NULL
--   Anti-fork supersedes_id indexes stay as-is (row id is globally unique).
--
-- WHAT THIS MUST NOT TOUCH
--   daily_snapshots UNIQUE(date) — house-only Brief; overlay publish skips it.
--   documents unique — already (workspace_id, date, document_key) from 105.
--   Cutover 900 anon/RLS policies — this file is uniqueness only.
--
-- SPEC BINDING
--   Overlay private books: docs/superpowers/specs/2026-08-29-kairos-tenancy-implementation-spec.md §5-T4
--   097 KEEP list: digiquant/supabase/migrations/097_workspaces_tenant_columns.sql header
--   Fail-closed until applied: digiquant.olympus.overlay.persist.require_overlay_legacy_book_safe
--
-- Replay-safe: DROP CONSTRAINT/INDEX IF EXISTS; CREATE UNIQUE INDEX IF NOT EXISTS.
-- Apply in one transaction (db-migrate wraps the file).
-- ============================================================================

-- Group A: drop 097 leftover date-only unique / PK. Widened UNIQUEs stay.
ALTER TABLE public.positions
    DROP CONSTRAINT IF EXISTS positions_date_ticker_key;

ALTER TABLE public.position_events
    DROP CONSTRAINT IF EXISTS position_events_date_ticker_key;

-- nav_history PK (date) is the leftover single-tenant arbiter. The widened
-- UNIQUE (workspace_id, date) already exists as uq_nav_history_workspace_date
-- and is the upsert target for develop writers (on_conflict=workspace_id,date).
ALTER TABLE public.nav_history
    DROP CONSTRAINT IF EXISTS nav_history_pkey;

ALTER TABLE public.portfolio_metrics
    DROP CONSTRAINT IF EXISTS portfolio_metrics_date_key;

-- Group B: widen 069 one-root indexes to include workspace_id.
DROP INDEX IF EXISTS public.uq_portfolio_ledger_commits_one_root;
CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_ledger_commits_one_root
    ON public.portfolio_ledger_commits (workspace_id, run_date)
    WHERE supersedes_id IS NULL;

DROP INDEX IF EXISTS public.uq_portfolio_ledger_approved_targets_one_root;
CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_ledger_approved_targets_one_root
    ON public.portfolio_ledger_approved_targets (workspace_id, run_date, symbol)
    WHERE supersedes_id IS NULL;

DROP INDEX IF EXISTS public.uq_portfolio_ledger_order_intents_one_root;
CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_ledger_order_intents_one_root
    ON public.portfolio_ledger_order_intents (workspace_id, run_date, symbol)
    WHERE supersedes_id IS NULL;
