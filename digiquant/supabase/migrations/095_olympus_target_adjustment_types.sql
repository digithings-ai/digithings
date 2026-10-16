-- 095_olympus_target_adjustment_types.sql
--
-- Widen portfolio_ledger_target_adjustments.adjustment_type to the full
-- TargetAdjustmentType vocabulary (#2768 / WP2 residual). Migration 069 only
-- allowed the coarse legacy trio (cap/rounding/carry). H8 has emitted the 12
-- fine-grained SizingAdjustmentType reason codes in-memory since #2417; H9 now
-- persists matching TargetAdjustment rows, so the CHECK must accept them.
--
-- Also restates the reduce-only CHECK to cover every reduce-only member of
-- TargetAdjustmentType (mirrors hermes.models.portfolio_ledger._REDUCING_ADJUSTMENT_TYPES),
-- not only the legacy 'cap' token.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one
-- psql single-transaction call. No historical backfill — Phase 0 wrote zero rows.

ALTER TABLE public.portfolio_ledger_target_adjustments
    DROP CONSTRAINT IF EXISTS portfolio_ledger_target_adjustments_adjustment_type_check;

ALTER TABLE public.portfolio_ledger_target_adjustments
    ADD CONSTRAINT portfolio_ledger_target_adjustments_adjustment_type_check
    CHECK (adjustment_type IN (
        'cap',
        'rounding',
        'carry',
        'conviction_floor',
        'single_name_cap',
        'sector_cap',
        'correlation_dedup',
        'volatility_scale',
        'drawdown_breaker',
        'grid_rounding',
        'cadence_hold',
        'minimum_hold_override',
        'continuity_carry',
        'final_gross_scale',
        'flat_exit'
    ));

ALTER TABLE public.portfolio_ledger_target_adjustments
    DROP CONSTRAINT IF EXISTS chk_portfolio_ledger_target_adjustments_cap_reduces;

ALTER TABLE public.portfolio_ledger_target_adjustments
    ADD CONSTRAINT chk_portfolio_ledger_target_adjustments_reducing_types
    CHECK (
        adjustment_type NOT IN (
            'cap',
            'single_name_cap',
            'sector_cap',
            'correlation_dedup',
            'drawdown_breaker',
            'grid_rounding',
            'flat_exit'
        )
        OR adjusted_value <= original_value
    );

COMMENT ON TABLE public.portfolio_ledger_target_adjustments IS
    'Private append-only requested→approved adjustment steps (#2415, #2768). '
    'Vocabulary is TargetAdjustmentType (legacy cap/rounding/carry plus the 12 H8 '
    'SizingAdjustmentType reason codes). Reduce-only types cannot increase value. '
    'H9 (ledger_io.append_commit_chain) is the sole producer.';
