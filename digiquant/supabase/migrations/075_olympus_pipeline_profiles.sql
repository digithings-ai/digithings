-- 075_olympus_pipeline_profiles.sql
--
-- Track B / #2607 — PipelineProfile / ProfileConfig DB seam.
--
-- Versioned investment/run policy (universe, risk prefs, research themes,
-- planner budgets) for the same Atlas→Hermes topology. digithings owns the
-- house default profile/run — always-on and immutable. Overlay rows may request
-- additional shared-corpus research; they must not cancel, replace, or mutate
-- house run identity. This is not DigiChat InvestmentProfile UI prefs.
--
-- Privacy: service_role SELECT+INSERT+UPDATE (config rows, not portfolio books).
-- RLS enabled with zero policies; PUBLIC/anon/authenticated fully revoked.
-- House row is immutable via trigger. No public views in this migration.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in
-- one psql single-transaction call.

CREATE TABLE IF NOT EXISTS public.olympus_pipeline_profiles (
    profile_id text PRIMARY KEY
        CHECK (length(profile_id) BETWEEN 1 AND 100),
    kind text NOT NULL
        CHECK (kind IN ('house', 'overlay')),
    display_name text NOT NULL
        CHECK (length(display_name) BETWEEN 1 AND 200),
    schema_version integer NOT NULL DEFAULT 1
        CHECK (schema_version >= 1),
    config jsonb NOT NULL
        CHECK (jsonb_typeof(config) = 'object'),
    house_run_id text NOT NULL DEFAULT 'digithings-house-run'
        CHECK (length(house_run_id) BETWEEN 1 AND 100),
    always_on boolean NOT NULL DEFAULT false,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_olympus_pipeline_profiles_house_identity
        CHECK (
            (kind = 'house'
                AND profile_id = 'digithings-house'
                AND house_run_id = 'digithings-house-run'
                AND always_on IS TRUE)
            OR
            (kind = 'overlay'
                AND profile_id <> 'digithings-house'
                AND house_run_id = 'digithings-house-run'
                AND always_on IS FALSE)
        )
);

-- Exactly one house profile row.
CREATE UNIQUE INDEX IF NOT EXISTS uq_olympus_pipeline_profiles_one_house
    ON public.olympus_pipeline_profiles (kind)
    WHERE kind = 'house';

CREATE INDEX IF NOT EXISTS idx_olympus_pipeline_profiles_enabled_kind
    ON public.olympus_pipeline_profiles (enabled, kind);

CREATE OR REPLACE FUNCTION public.reject_olympus_pipeline_profile_house_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.kind = 'house' OR OLD.profile_id = 'digithings-house' THEN
            RAISE EXCEPTION
                'olympus_pipeline_profiles house row is immutable (#2607); cannot DELETE'
                USING ERRCODE = '55000';
        END IF;
        RETURN OLD;
    END IF;

    -- UPDATE
    IF OLD.kind = 'house' OR OLD.profile_id = 'digithings-house' THEN
        RAISE EXCEPTION
            'olympus_pipeline_profiles house row is immutable (#2607); cannot UPDATE'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.kind = 'house' OR NEW.profile_id = 'digithings-house' THEN
        RAISE EXCEPTION
            'olympus_pipeline_profiles cannot promote an overlay to house (#2607)'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.house_run_id IS DISTINCT FROM 'digithings-house-run' THEN
        RAISE EXCEPTION
            'olympus_pipeline_profiles cannot replace digithings house_run_id (#2607)'
            USING ERRCODE = '55000';
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

ALTER TABLE public.olympus_pipeline_profiles ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_pipeline_profiles FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_pipeline_profiles FROM service_role;
GRANT SELECT, INSERT, UPDATE ON public.olympus_pipeline_profiles TO service_role;

DROP TRIGGER IF EXISTS reject_olympus_pipeline_profiles_house_mutation
    ON public.olympus_pipeline_profiles;
CREATE TRIGGER reject_olympus_pipeline_profiles_house_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_pipeline_profiles
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_pipeline_profile_house_mutation();

REVOKE ALL ON FUNCTION public.reject_olympus_pipeline_profile_house_mutation()
    FROM PUBLIC, anon, authenticated;

-- digithings house baseline seed (idempotent).
INSERT INTO public.olympus_pipeline_profiles (
    profile_id,
    kind,
    display_name,
    schema_version,
    config,
    house_run_id,
    always_on,
    enabled
) VALUES (
    'digithings-house',
    'house',
    'digithings house ETF baseline',
    1,
    jsonb_build_object(
        'schema_version', 1,
        'universe', jsonb_build_object(
            'include_tickers', '[]'::jsonb,
            'exclude_tickers', '[]'::jsonb,
            'asset_classes', jsonb_build_array('etf')
        ),
        'risk', jsonb_build_object(
            'risk_tolerance', 'moderate',
            'max_position_pct', NULL,
            'max_gross_exposure', NULL
        ),
        'research_themes', '[]'::jsonb,
        'planner_budgets', jsonb_build_object(
            'max_theme_refreshes', 0,
            'max_asset_refreshes', 0,
            'max_llm_calls', NULL
        )
    ),
    'digithings-house-run',
    true,
    true
)
ON CONFLICT (profile_id) DO NOTHING;

COMMENT ON TABLE public.olympus_pipeline_profiles IS
    'PipelineProfile / ProfileConfig seam (#2607). digithings house row is always-on '
    'and immutable. Overlays request shared-corpus research; they cannot cancel or '
    'replace the house run. Not user InvestmentProfile UI prefs. service_role '
    'SELECT+INSERT+UPDATE; RLS with zero policies; no anon grants.';

COMMENT ON COLUMN public.olympus_pipeline_profiles.config IS
    'Versioned ProfileConfig JSONB: universe, risk, research_themes, planner_budgets.';

COMMENT ON COLUMN public.olympus_pipeline_profiles.house_run_id IS
    'Immutable digithings house run identity; overlays must keep digithings-house-run.';
