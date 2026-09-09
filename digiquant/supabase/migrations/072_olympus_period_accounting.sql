-- 072_olympus_period_accounting.sql
--
-- Private event-boundary period accounting schema (#2596, Phase 0 Task 3.1).
--
-- Closes the schema half of OLY-REV-007 / OLY-REV-008: exact-date target weights must
-- not own the return interval. Migration 069/070/071 established the fill/lot lineage;
-- this migration stores the reconciled EOD period, per-ticker contribution, and EOD
-- holdings that Task 3.2 will persist from the pure Decimal engine in
-- digiquant.olympus.accounting. This file is schema only — no writer, no curated
-- public views, no reader cutover (Tasks 3.2–3.4).
--
-- Privacy (vision brief): portfolio/accounting is user-private. RLS is enabled with
-- zero policies; PUBLIC/anon/authenticated are fully revoked; service_role is reset
-- then granted SELECT+INSERT only. Append-only triggers reject UPDATE/DELETE/TRUNCATE
-- so corrections append a superseding period row (supersedes_id), never rewrite.
-- Do not GRANT these base tables to anon/authenticated and do not expose them via
-- security-definer views in this migration.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one
-- psql single-transaction call. DDL is replay-safe through IF NOT EXISTS,
-- CREATE OR REPLACE, and DROP TRIGGER IF EXISTS before CREATE TRIGGER.

CREATE TABLE IF NOT EXISTS public.olympus_accounting_periods (
    id uuid PRIMARY KEY,
    period_date date NOT NULL,
    policy_version_id text NOT NULL CHECK (length(policy_version_id) BETWEEN 1 AND 100),
    status text NOT NULL CHECK (status IN ('final', 'estimated', 'incomplete', 'failed')),
    quality_reasons text[] NOT NULL DEFAULT '{}'::text[],
    opening_equity numeric NOT NULL,
    closing_equity numeric NOT NULL,
    opening_cash numeric NOT NULL CHECK (
        opening_cash >= 0
        AND NOT (opening_cash = 'NaN'::numeric)
        AND NOT (opening_cash = 'Infinity'::numeric)
    ),
    closing_cash numeric NOT NULL CHECK (
        NOT (closing_cash = 'NaN'::numeric)
        AND NOT (closing_cash = 'Infinity'::numeric)
        AND NOT (closing_cash = '-Infinity'::numeric)
    ),
    cash_pnl numeric NOT NULL CHECK (
        NOT (cash_pnl = 'NaN'::numeric)
        AND NOT (cash_pnl = 'Infinity'::numeric)
        AND NOT (cash_pnl = '-Infinity'::numeric)
    ),
    cash_contribution numeric CHECK (
        cash_contribution IS NULL
        OR (
            NOT (cash_contribution = 'NaN'::numeric)
            AND NOT (cash_contribution = 'Infinity'::numeric)
            AND NOT (cash_contribution = '-Infinity'::numeric)
        )
    ),
    gross_pnl_total numeric NOT NULL CHECK (
        NOT (gross_pnl_total = 'NaN'::numeric)
        AND NOT (gross_pnl_total = 'Infinity'::numeric)
        AND NOT (gross_pnl_total = '-Infinity'::numeric)
    ),
    net_pnl_total numeric NOT NULL CHECK (
        NOT (net_pnl_total = 'NaN'::numeric)
        AND NOT (net_pnl_total = 'Infinity'::numeric)
        AND NOT (net_pnl_total = '-Infinity'::numeric)
    ),
    fees_total numeric NOT NULL CHECK (
        fees_total >= 0
        AND NOT (fees_total = 'NaN'::numeric)
        AND NOT (fees_total = 'Infinity'::numeric)
    ),
    slippage_total numeric NOT NULL CHECK (
        NOT (slippage_total = 'NaN'::numeric)
        AND NOT (slippage_total = 'Infinity'::numeric)
        AND NOT (slippage_total = '-Infinity'::numeric)
    ),
    residual numeric NOT NULL CHECK (
        NOT (residual = 'NaN'::numeric)
        AND NOT (residual = 'Infinity'::numeric)
        AND NOT (residual = '-Infinity'::numeric)
    ),
    absolute_tolerance numeric NOT NULL CHECK (
        absolute_tolerance >= 0
        AND NOT (absolute_tolerance = 'NaN'::numeric)
        AND NOT (absolute_tolerance = 'Infinity'::numeric)
    ),
    relative_tolerance numeric NOT NULL CHECK (
        relative_tolerance >= 0
        AND relative_tolerance <= 1
        AND NOT (relative_tolerance = 'NaN'::numeric)
        AND NOT (relative_tolerance = 'Infinity'::numeric)
    ),
    benchmark_symbol text CHECK (
        benchmark_symbol IS NULL OR length(benchmark_symbol) BETWEEN 1 AND 20
    ),
    benchmark_return numeric CHECK (
        benchmark_return IS NULL
        OR (
            NOT (benchmark_return = 'NaN'::numeric)
            AND NOT (benchmark_return = 'Infinity'::numeric)
            AND NOT (benchmark_return = '-Infinity'::numeric)
        )
    ),
    supersedes_id uuid,
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_olympus_accounting_periods_id_period_date
        UNIQUE (id, period_date),
    CONSTRAINT fk_olympus_accounting_periods_supersedes
        FOREIGN KEY (supersedes_id, period_date)
        REFERENCES public.olympus_accounting_periods (id, period_date),
    CONSTRAINT chk_olympus_accounting_periods_no_self_supersede
        CHECK (supersedes_id IS NULL OR supersedes_id <> id),
    -- final requires empty quality_reasons; measured residual is stored even when
    -- within tolerance (engine never publishes final with unexplained residual).
    CONSTRAINT chk_olympus_accounting_periods_final_clean
        CHECK (status <> 'final' OR cardinality(quality_reasons) = 0)
);

CREATE TABLE IF NOT EXISTS public.olympus_accounting_contributions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    period_id uuid NOT NULL,
    period_date date NOT NULL,
    symbol text NOT NULL CHECK (length(symbol) BETWEEN 1 AND 20),
    opening_quantity numeric NOT NULL CHECK (
        opening_quantity >= 0
        AND NOT (opening_quantity = 'NaN'::numeric)
        AND NOT (opening_quantity = 'Infinity'::numeric)
    ),
    closing_quantity numeric NOT NULL CHECK (
        NOT (closing_quantity = 'NaN'::numeric)
        AND NOT (closing_quantity = 'Infinity'::numeric)
        AND NOT (closing_quantity = '-Infinity'::numeric)
    ),
    opening_mark numeric CHECK (
        opening_mark IS NULL
        OR (
            opening_mark > 0
            AND NOT (opening_mark = 'NaN'::numeric)
            AND NOT (opening_mark = 'Infinity'::numeric)
        )
    ),
    closing_mark numeric CHECK (
        closing_mark IS NULL
        OR (
            closing_mark > 0
            AND NOT (closing_mark = 'NaN'::numeric)
            AND NOT (closing_mark = 'Infinity'::numeric)
        )
    ),
    gross_pnl numeric NOT NULL CHECK (
        NOT (gross_pnl = 'NaN'::numeric)
        AND NOT (gross_pnl = 'Infinity'::numeric)
        AND NOT (gross_pnl = '-Infinity'::numeric)
    ),
    fees numeric NOT NULL CHECK (
        fees >= 0
        AND NOT (fees = 'NaN'::numeric)
        AND NOT (fees = 'Infinity'::numeric)
    ),
    slippage numeric NOT NULL CHECK (
        NOT (slippage = 'NaN'::numeric)
        AND NOT (slippage = 'Infinity'::numeric)
        AND NOT (slippage = '-Infinity'::numeric)
    ),
    net_pnl numeric NOT NULL CHECK (
        NOT (net_pnl = 'NaN'::numeric)
        AND NOT (net_pnl = 'Infinity'::numeric)
        AND NOT (net_pnl = '-Infinity'::numeric)
    ),
    contribution numeric CHECK (
        contribution IS NULL
        OR (
            NOT (contribution = 'NaN'::numeric)
            AND NOT (contribution = 'Infinity'::numeric)
            AND NOT (contribution = '-Infinity'::numeric)
        )
    ),
    quality_reasons text[] NOT NULL DEFAULT '{}'::text[],
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_olympus_accounting_contributions_period
        FOREIGN KEY (period_id, period_date)
        REFERENCES public.olympus_accounting_periods (id, period_date),
    CONSTRAINT uq_olympus_accounting_contributions_period_symbol
        UNIQUE (period_id, symbol)
);

CREATE TABLE IF NOT EXISTS public.olympus_accounting_holdings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    period_id uuid NOT NULL,
    period_date date NOT NULL,
    symbol text NOT NULL CHECK (length(symbol) BETWEEN 1 AND 20),
    quantity numeric NOT NULL CHECK (
        quantity >= 0
        AND NOT (quantity = 'NaN'::numeric)
        AND NOT (quantity = 'Infinity'::numeric)
    ),
    mark numeric CHECK (
        mark IS NULL
        OR (
            mark > 0
            AND NOT (mark = 'NaN'::numeric)
            AND NOT (mark = 'Infinity'::numeric)
        )
    ),
    market_value numeric CHECK (
        market_value IS NULL
        OR (
            NOT (market_value = 'NaN'::numeric)
            AND NOT (market_value = 'Infinity'::numeric)
            AND NOT (market_value = '-Infinity'::numeric)
        )
    ),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_olympus_accounting_holdings_period
        FOREIGN KEY (period_id, period_date)
        REFERENCES public.olympus_accounting_periods (id, period_date),
    CONSTRAINT uq_olympus_accounting_holdings_period_symbol
        UNIQUE (period_id, symbol)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_olympus_accounting_periods_one_root
    ON public.olympus_accounting_periods (period_date) WHERE supersedes_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_olympus_accounting_periods_supersedes
    ON public.olympus_accounting_periods (supersedes_id) WHERE supersedes_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_olympus_accounting_periods_status_date
    ON public.olympus_accounting_periods (status, period_date DESC);
CREATE INDEX IF NOT EXISTS idx_olympus_accounting_contributions_period
    ON public.olympus_accounting_contributions (period_id);
CREATE INDEX IF NOT EXISTS idx_olympus_accounting_holdings_period
    ON public.olympus_accounting_holdings (period_id);

CREATE OR REPLACE FUNCTION public.reject_olympus_accounting_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'olympus accounting tables are append-only (#2596); corrections must INSERT a superseding row'
        USING ERRCODE = '55000';
END;
$$;

ALTER TABLE public.olympus_accounting_periods ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_accounting_contributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_accounting_holdings ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_accounting_periods FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_accounting_contributions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_accounting_holdings FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.olympus_accounting_periods FROM service_role;
REVOKE ALL ON public.olympus_accounting_contributions FROM service_role;
REVOKE ALL ON public.olympus_accounting_holdings FROM service_role;

GRANT SELECT, INSERT ON public.olympus_accounting_periods TO service_role;
GRANT SELECT, INSERT ON public.olympus_accounting_contributions TO service_role;
GRANT SELECT, INSERT ON public.olympus_accounting_holdings TO service_role;

DROP TRIGGER IF EXISTS reject_olympus_accounting_periods_mutation
    ON public.olympus_accounting_periods;
CREATE TRIGGER reject_olympus_accounting_periods_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_accounting_periods
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_accounting_mutation();
DROP TRIGGER IF EXISTS reject_olympus_accounting_periods_truncate
    ON public.olympus_accounting_periods;
CREATE TRIGGER reject_olympus_accounting_periods_truncate
    BEFORE TRUNCATE ON public.olympus_accounting_periods
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_accounting_mutation();

DROP TRIGGER IF EXISTS reject_olympus_accounting_contributions_mutation
    ON public.olympus_accounting_contributions;
CREATE TRIGGER reject_olympus_accounting_contributions_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_accounting_contributions
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_accounting_mutation();
DROP TRIGGER IF EXISTS reject_olympus_accounting_contributions_truncate
    ON public.olympus_accounting_contributions;
CREATE TRIGGER reject_olympus_accounting_contributions_truncate
    BEFORE TRUNCATE ON public.olympus_accounting_contributions
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_accounting_mutation();

DROP TRIGGER IF EXISTS reject_olympus_accounting_holdings_mutation
    ON public.olympus_accounting_holdings;
CREATE TRIGGER reject_olympus_accounting_holdings_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_accounting_holdings
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_accounting_mutation();
DROP TRIGGER IF EXISTS reject_olympus_accounting_holdings_truncate
    ON public.olympus_accounting_holdings;
CREATE TRIGGER reject_olympus_accounting_holdings_truncate
    BEFORE TRUNCATE ON public.olympus_accounting_holdings
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_accounting_mutation();

REVOKE ALL ON FUNCTION public.reject_olympus_accounting_mutation()
    FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.olympus_accounting_periods IS
    'Private append-only EOD accounting periods (#2596). User-private; service_role '
    'SELECT+INSERT only. status=final requires empty quality_reasons. Task 3.2 writes; '
    'this migration is schema only.';

COMMENT ON TABLE public.olympus_accounting_contributions IS
    'Private per-ticker (and cash-adjacent) contribution rows for one accounting period '
    '(#2596). Never grant to anon/authenticated.';

COMMENT ON TABLE public.olympus_accounting_holdings IS
    'Private EOD holdings marked at period close (#2596). User-private; no public grants.';
