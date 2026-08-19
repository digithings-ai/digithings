-- 070_olympus_paper_execution_costs.sql
--
-- Explicit fee and slippage on the immutable fill row (#2420, Task 2.4).
--
-- Migration 069 booked a fill as (quantity, price) only, which forces every cost
-- reader to infer transaction cost from the difference between a fill price and
-- some other table's mark. That inference is exactly the prose-derived guessing
-- the portfolio ledger exists to remove, so the two cost components become
-- first-class columns on the fill that incurred them.
--
-- UNITS: both columns are TOTAL DOLLARS for the whole fill, not per-share and not
-- basis points. `fee + slippage` is therefore directly the cash cost of the fill,
-- and neither needs multiplying by `quantity` at read time. Mixed units in
-- adjacent numeric columns is a silent-wrongness bug rather than a loud one, so
-- the unit is stated here, in the column comments below, and in the writer.
--
-- SIGNS: `fee` is a cost and is therefore >= 0 — a negative fee would be a rebate,
-- which no paper venue here pays, and admitting one would let a fabricated credit
-- flatter realised performance. `slippage` is deliberately SIGNED: it records
-- (effective fill price - declared mark) * quantity, which is positive when the
-- fill was worse than the mark and negative when it was better. Both directions are
-- real, so clamping the sign would silently discard favourable execution.
--
-- ZERO IS A MEASURED VALUE, NOT A MISSING ONE. Contrast 069's header rule that an
-- unknown economic quantity stays NULL with no numeric DEFAULT: that rule is about
-- values the writer cannot know. Here the paper executor fills at the declared
-- open, so with no cost model configured the true fee and the true slippage are
-- both exactly 0.00 — a measurement, not an absence — and the writer always sends
-- an explicit value. The columns are still nullable, and still carry no numeric
-- DEFAULT, for one narrower reason: the append-only trigger on this table rejects
-- UPDATE, so any fill row written before this migration can never be backfilled.
-- NULL therefore means precisely "recorded before fees and slippage were tracked",
-- and a DEFAULT of 0 would erase that distinction by asserting a measurement that
-- was never taken.
--
-- ALTER TABLE ADD COLUMN is DDL, not DML, so the shared UPDATE/DELETE-rejecting
-- trigger from 069 does not block it; adding a column also leaves that migration's
-- RLS state and its SELECT+INSERT-only service_role grants untouched.

ALTER TABLE public.portfolio_ledger_paper_executions
    ADD COLUMN IF NOT EXISTS fee numeric,
    ADD COLUMN IF NOT EXISTS slippage numeric;

-- NaN/Infinity guard: see 069 — Postgres `numeric` NaN and Infinity both pass a
-- bare `>= 0`, and NaN poisons every downstream SUM it reaches, so both are
-- excluded explicitly. Each CHECK admits NULL (see the header) and is added
-- separately from the columns so the constraint names are explicit and reversible.
--
-- Wrapped in the repo's `EXCEPTION WHEN duplicate_object` idiom (see 002) because
-- `ADD CONSTRAINT` has no `IF NOT EXISTS` form: bare, a second run of this file
-- raises 42710 and fails the whole migration, while the `ADD COLUMN IF NOT EXISTS`
-- above would have succeeded — a half-idempotent file is worse than a plain one,
-- since it reads as re-runnable right up to the point where it isn't. Only the
-- name collision is swallowed; a CHECK that existing rows violate still raises
-- `check_violation` and still fails loudly, which is the outcome worth keeping.

DO $$ BEGIN
    ALTER TABLE public.portfolio_ledger_paper_executions
        ADD CONSTRAINT chk_portfolio_ledger_paper_executions_fee
            CHECK (
                fee IS NULL
                OR (
                    fee >= 0
                    AND NOT (fee = 'NaN'::numeric)
                    AND NOT (fee = 'Infinity'::numeric)
                )
            );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE public.portfolio_ledger_paper_executions
        ADD CONSTRAINT chk_portfolio_ledger_paper_executions_slippage
            CHECK (
                slippage IS NULL
                OR (
                    NOT (slippage = 'NaN'::numeric)
                    AND NOT (slippage = 'Infinity'::numeric)
                    AND NOT (slippage = '-Infinity'::numeric)
                )
            );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

COMMENT ON COLUMN public.portfolio_ledger_paper_executions.fee IS
    'Total commission/fee in dollars for this whole fill (not per-share, not bps). '
    '>= 0. 0 is a measured zero; NULL means the fill predates migration 070.';

COMMENT ON COLUMN public.portfolio_ledger_paper_executions.slippage IS
    'Signed total dollars of slippage for this whole fill: '
    '(effective fill price - declared mark) * quantity. Positive = filled worse '
    'than the mark, negative = better. 0 is a measured zero (a paper fill at the '
    'declared open); NULL means the fill predates migration 070.';
