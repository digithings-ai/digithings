-- Unify portfolio_metrics.volatility / .max_drawdown on the PERCENT scale (#1748).
--
-- WHY (the column is mixed-unit today, and the fraction-scaled CHECKs are an armed fuse):
--
--   writer                                              value                scale
--   --------------------------------------------------  -------------------  --------
--   hermes/portfolio_materialize.py:342,354 (phase 9d)   std*sqrt(252)*100    percent
--   scripts/atlas/refresh_performance_metrics.py:233,248 std*sqrt(252)*100    percent
--   scripts/atlas/update_tearsheet.py:883,911            std*sqrt(252)        fraction
--
-- 002_schema_hardening.sql:153,160 constrained both columns as fractions
-- (volatility BETWEEN 0 AND 10, max_drawdown BETWEEN -1 AND 0). Two of the three
-- writers therefore cannot store a realistic value at all: the first computed
-- annualized volatility (~10-30%) trips chk_metrics_vol_range and the first computed
-- running drawdown (~-1.31%) trips chk_metrics_dd_range, raising PostgREST
-- APIError 23514 on every subsequent run — running max drawdown is monotonically
-- non-increasing, so once violated it is permanently violated.
--
-- Both writers are gated on nav_history reaching _MIN_NAV_HISTORY_ROWS = 20; the table
-- held 15 rows on 2026-08-01 and gained 11 in the preceding 15 calendar days, so the
-- fuse arms on its own around 2026-08-07.
--
-- Percent is the resolution, not fraction: it matches two of the three writers, the
-- `_pct` naming used by every neighbouring column (pnl_pct, net_return_pct,
-- benchmark_return_pct, relative_return_pct, cash_pct, invested_pct), and the only
-- reader that renames the fields — frontend/olympus/lib/portfolio-risk-metrics.ts:93-94
-- maps `volatility -> annVolPct` and `max_drawdown -> maxDrawdownPct`. The companion
-- change makes update_tearsheet.py emit percent so the column stops being mixed-unit;
-- widening the CHECK alone would legitimise the mixture and mis-scale readers by 100x.
--
-- Live state at authoring time (SELECT-only, 2026-08-01): 11 rows, all
-- computed_from='refresh_script_insufficient_history', volatility and max_drawdown
-- 100% NULL. Widening an all-NULL column is a pure relaxation and the one-shot
-- rescale below is provably a no-op in production.
--
-- Statement order is load-bearing: DROP the old CHECKs, THEN rescale, THEN ADD the
-- widened CHECKs. Rescaling first would turn a stored 0.15 into 15 and trip the old
-- volatility <= 10 bound, aborting the migration.
--
-- Left unwrapped on purpose — no top-level transaction block — so db-migrate.yml:85-88
-- pipes it and its olympus_schema_migrations INSERT through psql --single-transaction,
-- recording the version iff the DDL commits. Note db-migrate.yml:79 decides that by
-- grepping the file for a bare begin-statement, so no comment here may spell one.
--
-- Rollback (only meaningful before any percent-scale row is written):
--   ALTER TABLE public.portfolio_metrics DROP CONSTRAINT IF EXISTS chk_metrics_vol_range;
--   ALTER TABLE public.portfolio_metrics DROP CONSTRAINT IF EXISTS chk_metrics_dd_range;
--   ALTER TABLE public.portfolio_metrics ADD CONSTRAINT chk_metrics_vol_range
--     CHECK (volatility IS NULL OR (volatility >= 0 AND volatility <= 10));
--   ALTER TABLE public.portfolio_metrics ADD CONSTRAINT chk_metrics_dd_range
--     CHECK (max_drawdown IS NULL OR (max_drawdown >= -1 AND max_drawdown <= 0));

ALTER TABLE public.portfolio_metrics DROP CONSTRAINT IF EXISTS chk_metrics_vol_range;
ALTER TABLE public.portfolio_metrics DROP CONSTRAINT IF EXISTS chk_metrics_dd_range;

-- One-shot rescale of rows left behind by the fraction-scale writer.
--
-- Replay guard: the percent contract is recorded as a column COMMENT at the bottom of
-- this file, and its presence skips the rescale. This file can legitimately run twice —
-- applying it out-of-band writes supabase_migrations, not olympus_schema_migrations, so
-- db-migrate.yml:68-69 would not skip the checked-in copy on the next push to main. A
-- second multiplication by 100 must not happen.
--
-- Discriminator caveat, stated rather than hidden: computed_from carries
-- DEFAULT 'tearsheet' (012_positions_perf_refactor.sql:39) and phase 9d upserts without
-- setting it, so a phase-9d row inserted before any refresh_script row would also read
-- as 'tearsheet'. The magnitude bounds below keep such a row out of the rescale for any
-- value the old CHECKs could actually store alongside a realistic percent-scale pair,
-- and today the set is empty in production (0 of 11 rows). Labelling phase 9d's writes
-- honestly belongs to the package that owns portfolio_materialize.py (#1744/#1745).
DO $$
DECLARE
  contract_recorded boolean;
  rescaled integer := 0;
BEGIN
  SELECT coalesce(col_description(a.attrelid, a.attnum), '') ILIKE '%percent%'
    INTO contract_recorded
    FROM pg_attribute a
   WHERE a.attrelid = 'public.portfolio_metrics'::regclass
     AND a.attname = 'max_drawdown'
     AND NOT a.attisdropped;

  IF contract_recorded THEN
    RAISE NOTICE
      '058: percent contract already recorded on portfolio_metrics.max_drawdown; '
      'skipping the one-shot rescale (replay).';
  ELSE
    UPDATE public.portfolio_metrics
       SET volatility = volatility * 100,
           max_drawdown = max_drawdown * 100
     WHERE computed_from = 'tearsheet'
       AND (volatility IS NOT NULL OR max_drawdown IS NOT NULL)
       AND coalesce(volatility, 0) <= 10
       AND coalesce(max_drawdown, 0) >= -1;
    GET DIAGNOSTICS rescaled = ROW_COUNT;
    RAISE NOTICE
      '058: rescaled % fraction-scale tearsheet row(s) to percent (expected 0; '
      'volatility and max_drawdown were 100%% NULL in production on 2026-08-01).',
      rescaled;
  END IF;
END $$;

-- volatility: 0–1000 percent annualized (1000% would be extreme).
ALTER TABLE public.portfolio_metrics ADD CONSTRAINT chk_metrics_vol_range
  CHECK (volatility IS NULL OR (volatility >= 0 AND volatility <= 1000));

-- max_drawdown: -100–0 percent (a total loss is -100).
ALTER TABLE public.portfolio_metrics ADD CONSTRAINT chk_metrics_dd_range
  CHECK (max_drawdown IS NULL OR (max_drawdown >= -100 AND max_drawdown <= 0));

COMMENT ON COLUMN public.portfolio_metrics.volatility IS
  'Annualized standard deviation of daily NAV returns, in percent (e.g. 18.4 = 18.4%). '
  'Percent is the single scale for every writer as of migration 058 (#1748).';
COMMENT ON COLUMN public.portfolio_metrics.max_drawdown IS
  'Worst peak-to-trough NAV decline, in percent and non-positive (e.g. -12.5 = -12.5%). '
  'Percent is the single scale for every writer as of migration 058 (#1748).';
