-- 075_olympus_profile_config.sql
--
-- Track B ProfileConfig (#2609): private, append-only versioned investment
-- overlay pins for Olympus preflight. The digithings-owned house profile is
-- the immutable always-on default run; overlays must not claim profile_key
-- 'house' or cancel/replace that run.
--
-- Schema only for durable storage + house seed. Loader/models live in
-- digiquant.olympus.profile_config. No curated public views and no graph forks.
--
-- Privacy: profile overlays may contain user preference data. RLS enabled with
-- zero policies; PUBLIC/anon/authenticated fully revoked; service_role reset
-- then SELECT+INSERT only. Append-only triggers reject UPDATE/DELETE/TRUNCATE.
--
-- Unwrapped on purpose: db-migrate.yml applies the file and its ledger row in
-- one psql single-transaction call.

CREATE TABLE IF NOT EXISTS public.olympus_profile_config (
    id uuid PRIMARY KEY,
    profile_key text NOT NULL CHECK (length(profile_key) BETWEEN 1 AND 100),
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    is_house_default boolean NOT NULL,
    label text NOT NULL CHECK (length(label) BETWEEN 1 AND 200),
    payload jsonb NOT NULL,
    supersedes_id uuid REFERENCES public.olympus_profile_config (id),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_olympus_profile_config_house_key CHECK (
        (is_house_default = true AND profile_key = 'house')
        OR (is_house_default = false AND profile_key <> 'house')
    )
);

COMMENT ON TABLE public.olympus_profile_config IS
  'Versioned Olympus ProfileConfig pins (#2609). House row is digithings-owned '
  'always-on default; overlays are additional pins only. Append-only; corrections '
  'INSERT a superseding row.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_olympus_profile_config_one_house_root
    ON public.olympus_profile_config (is_house_default)
    WHERE is_house_default = true AND supersedes_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_olympus_profile_config_supersedes
    ON public.olympus_profile_config (supersedes_id)
    WHERE supersedes_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_olympus_profile_config_key_recorded
    ON public.olympus_profile_config (profile_key, recorded_at DESC);

-- Deterministic house seed id matches
-- digiquant.olympus.profile_config.profile_config_version_id('house', 1)
-- = uuid5(uuid5(NAMESPACE_URL, 'digithings.olympus.profile_config'), 'house:v1')
-- = 4ee97e91-7b5b-5a50-b562-37d34250b0f9
INSERT INTO public.olympus_profile_config (
    id,
    profile_key,
    schema_version,
    is_house_default,
    label,
    payload,
    supersedes_id
)
VALUES (
    '4ee97e91-7b5b-5a50-b562-37d34250b0f9'::uuid,
    'house',
    1,
    true,
    'digithings house',
    '{
      "version_id": "4ee97e91-7b5b-5a50-b562-37d34250b0f9",
      "profile_key": "house",
      "schema_version": 1,
      "is_house_default": true,
      "label": "digithings house",
      "watchlist": [],
      "themes": [],
      "research_budget_usd": null,
      "investment": {
        "schema_version": 1,
        "risk_tolerance": "moderate",
        "horizon_years": 10,
        "liquidity_needs": "medium",
        "base_currency": "USD",
        "tax_jurisdiction": "US",
        "esg_preference": "none",
        "excluded_sectors": [],
        "experience_level": "intermediate"
      },
      "assets": null
    }'::jsonb,
    NULL
)
ON CONFLICT (id) DO NOTHING;

CREATE OR REPLACE FUNCTION public.reject_olympus_profile_config_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'olympus_profile_config is append-only (#2609); corrections must INSERT a superseding row'
        USING ERRCODE = '55000';
END;
$$;

ALTER TABLE public.olympus_profile_config ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.olympus_profile_config FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_profile_config FROM service_role;
GRANT SELECT, INSERT ON public.olympus_profile_config TO service_role;

DROP TRIGGER IF EXISTS reject_olympus_profile_config_mutation
    ON public.olympus_profile_config;
CREATE TRIGGER reject_olympus_profile_config_mutation
    BEFORE UPDATE OR DELETE ON public.olympus_profile_config
    FOR EACH ROW EXECUTE FUNCTION public.reject_olympus_profile_config_mutation();

DROP TRIGGER IF EXISTS reject_olympus_profile_config_truncate
    ON public.olympus_profile_config;
CREATE TRIGGER reject_olympus_profile_config_truncate
    BEFORE TRUNCATE ON public.olympus_profile_config
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_olympus_profile_config_mutation();
