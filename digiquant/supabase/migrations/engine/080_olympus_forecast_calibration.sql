-- 080_olympus_forecast_calibration.sql
--
-- Private append-only forecast outcome / calibration registry (#2672 / WP5.1).
--
-- Stores immutable prospective ForecastOutcome labels, versioned
-- ForecastCalibration cohort metrics, and shadow CalibratedForecast subjects.
-- Schema + contracts only — no resolver/writer/H8 cutover (Tasks 5.2–5.4).
--
-- No historical INSERT ... SELECT. No prompt/reasoning bodies. No public base view.
--
-- Privacy: RLS enabled with zero policies; PUBLIC/anon/authenticated fully revoked;
-- service_role reset then SELECT+INSERT only. Append-only triggers reject
-- UPDATE/DELETE/TRUNCATE for every role.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in one
-- psql single-transaction call. DDL is replay-safe through IF NOT EXISTS,
-- CREATE OR REPLACE, and DROP TRIGGER IF EXISTS before CREATE TRIGGER.

CREATE TABLE IF NOT EXISTS public.olympus_forecast_outcomes (
    outcome_id uuid PRIMARY KEY,
    base_forecast_id uuid NOT NULL,
    effective_forecast_id uuid NOT NULL,
    ticker text NOT NULL CHECK (length(ticker) BETWEEN 1 AND 32),
    reference_session date NOT NULL,
    maturity_session date NOT NULL,
    reference_snapshot jsonb CHECK (
        reference_snapshot IS NULL OR jsonb_typeof(reference_snapshot) = 'object'
    ),
    maturity_snapshot jsonb CHECK (
        maturity_snapshot IS NULL OR jsonb_typeof(maturity_snapshot) = 'object'
    ),
    forecast_mean_return numeric CHECK (
        forecast_mean_return IS NULL
        OR (
            NOT (forecast_mean_return = 'NaN'::numeric)
            AND NOT (forecast_mean_return = 'Infinity'::numeric)
            AND NOT (forecast_mean_return = '-Infinity'::numeric)
        )
    ),
    realized_return numeric CHECK (
        realized_return IS NULL
        OR (
            NOT (realized_return = 'NaN'::numeric)
            AND NOT (realized_return = 'Infinity'::numeric)
            AND NOT (realized_return = '-Infinity'::numeric)
        )
    ),
    signed_residual numeric CHECK (
        signed_residual IS NULL
        OR (
            NOT (signed_residual = 'NaN'::numeric)
            AND NOT (signed_residual = 'Infinity'::numeric)
            AND NOT (signed_residual = '-Infinity'::numeric)
        )
    ),
    positive_label boolean,
    status text NOT NULL CHECK (status IN ('resolved', 'pending', 'unavailable')),
    unavailable_reason text CHECK (
        unavailable_reason IS NULL OR length(unavailable_reason) BETWEEN 1 AND 500
    ),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    event_time timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_olympus_forecast_outcomes_session_order
        CHECK (maturity_session >= reference_session),
    CONSTRAINT fk_olympus_forecast_outcomes_base
        FOREIGN KEY (base_forecast_id)
        REFERENCES public.olympus_forecast_assessments (forecast_id)
);

CREATE TABLE IF NOT EXISTS public.olympus_forecast_calibrations (
    calibration_id uuid PRIMARY KEY,
    cohort_key text NOT NULL CHECK (length(cohort_key) BETWEEN 1 AND 200),
    prior_definition text NOT NULL CHECK (length(prior_definition) BETWEEN 1 AND 500),
    method_version text NOT NULL CHECK (length(method_version) BETWEEN 1 AND 200),
    sample_count integer NOT NULL CHECK (sample_count >= 0),
    equivalent_sample_size numeric NOT NULL CHECK (
        equivalent_sample_size >= 0
        AND NOT (equivalent_sample_size = 'NaN'::numeric)
        AND NOT (equivalent_sample_size = 'Infinity'::numeric)
    ),
    bias numeric CHECK (
        bias IS NULL
        OR (
            NOT (bias = 'NaN'::numeric)
            AND NOT (bias = 'Infinity'::numeric)
            AND NOT (bias = '-Infinity'::numeric)
        )
    ),
    dispersion numeric CHECK (
        dispersion IS NULL
        OR (
            dispersion >= 0
            AND NOT (dispersion = 'NaN'::numeric)
            AND NOT (dispersion = 'Infinity'::numeric)
        )
    ),
    brier_score numeric CHECK (
        brier_score IS NULL
        OR (
            brier_score >= 0
            AND brier_score <= 1
            AND NOT (brier_score = 'NaN'::numeric)
        )
    ),
    log_score numeric CHECK (
        log_score IS NULL
        OR (
            NOT (log_score = 'NaN'::numeric)
            AND NOT (log_score = 'Infinity'::numeric)
            AND NOT (log_score = '-Infinity'::numeric)
        )
    ),
    reliability numeric NOT NULL CHECK (
        reliability >= 0
        AND reliability <= 1
        AND NOT (reliability = 'NaN'::numeric)
    ),
    status text NOT NULL CHECK (status IN ('available', 'unavailable')),
    unavailable_reason text CHECK (
        unavailable_reason IS NULL OR length(unavailable_reason) BETWEEN 1 AND 500
    ),
    outcome_ids uuid[] NOT NULL DEFAULT '{}'::uuid[],
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    effective_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.olympus_calibrated_forecasts (
    calibrated_forecast_id uuid PRIMARY KEY,
    base_forecast_id uuid NOT NULL,
    effective_forecast_id uuid NOT NULL,
    calibration_id uuid,
    ticker text NOT NULL CHECK (length(ticker) BETWEEN 1 AND 32),
    expected_gross_return numeric CHECK (
        expected_gross_return IS NULL
        OR (
            NOT (expected_gross_return = 'NaN'::numeric)
            AND NOT (expected_gross_return = 'Infinity'::numeric)
            AND NOT (expected_gross_return = '-Infinity'::numeric)
        )
    ),
    forecast_error_std numeric CHECK (
        forecast_error_std IS NULL
        OR (
            forecast_error_std > 0
            AND NOT (forecast_error_std = 'NaN'::numeric)
            AND NOT (forecast_error_std = 'Infinity'::numeric)
        )
    ),
    downside_quantiles numeric[],
    calibrated_positive_probability numeric CHECK (
        calibrated_positive_probability IS NULL
        OR (
            calibrated_positive_probability >= 0
            AND calibrated_positive_probability <= 1
            AND NOT (calibrated_positive_probability = 'NaN'::numeric)
        )
    ),
    reliability_weight numeric NOT NULL CHECK (
        reliability_weight >= 0
        AND reliability_weight <= 1
        AND NOT (reliability_weight = 'NaN'::numeric)
    ),
    effective_until timestamptz,
    status text NOT NULL CHECK (status IN ('available', 'unavailable')),
    unavailable_reason text CHECK (
        unavailable_reason IS NULL OR length(unavailable_reason) BETWEEN 1 AND 500
    ),
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    effective_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_olympus_calibrated_forecasts_base
        FOREIGN KEY (base_forecast_id)
        REFERENCES public.olympus_forecast_assessments (forecast_id),
    CONSTRAINT fk_olympus_calibrated_forecasts_calibration
        FOREIGN KEY (calibration_id)
        REFERENCES public.olympus_forecast_calibrations (calibration_id)
);

CREATE INDEX IF NOT EXISTS idx_olympus_forecast_outcomes_effective_maturity
    ON public.olympus_forecast_outcomes (effective_forecast_id, maturity_session);

CREATE INDEX IF NOT EXISTS idx_olympus_forecast_outcomes_ticker_known
    ON public.olympus_forecast_outcomes (ticker, known_at);

CREATE INDEX IF NOT EXISTS idx_olympus_forecast_calibrations_cohort_known
    ON public.olympus_forecast_calibrations (cohort_key, known_at);

CREATE INDEX IF NOT EXISTS idx_olympus_calibrated_forecasts_effective_known
    ON public.olympus_calibrated_forecasts (effective_forecast_id, known_at);

ALTER TABLE public.olympus_forecast_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_forecast_calibrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.olympus_calibrated_forecasts ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_forecast_outcomes FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_forecast_calibrations FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_calibrated_forecasts FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.olympus_forecast_outcomes FROM service_role;
REVOKE ALL ON public.olympus_forecast_calibrations FROM service_role;
REVOKE ALL ON public.olympus_calibrated_forecasts FROM service_role;

GRANT SELECT, INSERT ON public.olympus_forecast_outcomes TO service_role;
GRANT SELECT, INSERT ON public.olympus_forecast_calibrations TO service_role;
GRANT SELECT, INSERT ON public.olympus_calibrated_forecasts TO service_role;

CREATE OR REPLACE FUNCTION public.reject_olympus_forecast_calibration_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'forecast calibration registry is append-only (#2672)'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS reject_olympus_forecast_outcomes_mutation
    ON public.olympus_forecast_outcomes;
CREATE TRIGGER reject_olympus_forecast_outcomes_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_forecast_outcomes
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_forecast_calibration_mutation();
DROP TRIGGER IF EXISTS reject_olympus_forecast_outcomes_truncate
    ON public.olympus_forecast_outcomes;
CREATE TRIGGER reject_olympus_forecast_outcomes_truncate
    BEFORE TRUNCATE ON public.olympus_forecast_outcomes
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_forecast_calibration_mutation();

DROP TRIGGER IF EXISTS reject_olympus_forecast_calibrations_mutation
    ON public.olympus_forecast_calibrations;
CREATE TRIGGER reject_olympus_forecast_calibrations_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_forecast_calibrations
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_forecast_calibration_mutation();
DROP TRIGGER IF EXISTS reject_olympus_forecast_calibrations_truncate
    ON public.olympus_forecast_calibrations;
CREATE TRIGGER reject_olympus_forecast_calibrations_truncate
    BEFORE TRUNCATE ON public.olympus_forecast_calibrations
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_forecast_calibration_mutation();

DROP TRIGGER IF EXISTS reject_olympus_calibrated_forecasts_mutation
    ON public.olympus_calibrated_forecasts;
CREATE TRIGGER reject_olympus_calibrated_forecasts_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_calibrated_forecasts
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_forecast_calibration_mutation();
DROP TRIGGER IF EXISTS reject_olympus_calibrated_forecasts_truncate
    ON public.olympus_calibrated_forecasts;
CREATE TRIGGER reject_olympus_calibrated_forecasts_truncate
    BEFORE TRUNCATE ON public.olympus_calibrated_forecasts
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_forecast_calibration_mutation();

REVOKE ALL ON FUNCTION public.reject_olympus_forecast_calibration_mutation()
    FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.olympus_forecast_outcomes IS
    'Private append-only prospective ForecastOutcome labels (#2672 / WP5.1). '
    'Trading-session maturity; no portfolio contribution; no public view.';

COMMENT ON TABLE public.olympus_forecast_calibrations IS
    'Private append-only ForecastCalibration cohort versions (#2672 / WP5.1). '
    'Immutable metrics + prior/method identity; no mutable current row.';

COMMENT ON TABLE public.olympus_calibrated_forecasts IS
    'Private append-only shadow CalibratedForecast subjects (#2672 / WP5.1). '
    'Observational until Phase 2; never feeds incumbent H8 in Phase 1.';

COMMENT ON FUNCTION public.reject_olympus_forecast_calibration_mutation() IS
    'Rejects UPDATE, DELETE, and TRUNCATE on forecast calibration registry tables.';
