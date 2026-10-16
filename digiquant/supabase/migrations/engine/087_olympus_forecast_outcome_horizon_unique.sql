-- 087_olympus_forecast_outcome_horizon_unique.sql
--
-- WP5 follow-up (#2797): stamp horizon_sessions on outcomes for Gate-2 cohort
-- filtering, and uniquely enforce (effective_forecast_id, maturity_session).
--
-- Replay-safe: ADD COLUMN IF NOT EXISTS; unique index IF NOT EXISTS.
-- No historical fabrication of horizon values (NULL allowed for pre-087 rows;
-- writer + pydantic require positive horizon on new resolved outcomes).
-- Unwrapped: db-migrate.yml applies file + ledger in one psql transaction.

ALTER TABLE public.olympus_forecast_outcomes
    ADD COLUMN IF NOT EXISTS horizon_sessions integer
    CHECK (
        horizon_sessions IS NULL
        OR horizon_sessions > 0
    );

COMMENT ON COLUMN public.olympus_forecast_outcomes.horizon_sessions IS
    'Trading-session horizon from the effective forecast terms (#2797). '
    'Used to filter calibration cohorts; NULL only for pre-087 rows.';

-- Natural-key uniqueness (app idempotency was select-before-insert only).
CREATE UNIQUE INDEX IF NOT EXISTS uq_olympus_forecast_outcomes_effective_maturity
    ON public.olympus_forecast_outcomes (effective_forecast_id, maturity_session);
