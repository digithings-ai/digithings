-- 115_plan_tier_brief_desk_studio.sql
--
-- Consumer ladder (2026-09-01): Observer (free) + three paid SKUs
-- Brief / Desk / Studio, plus invoice-only Enterprise.
-- Replaces D1 `baseline` / `custom` ids. House-run jargon "baseline"
-- (Sunday run_type, delta-vs-baseline dates) is unchanged.
--
-- Mapping of existing rows:
--   workspaces.plan_tier baseline → desk, custom → studio
--   entitlement_grants.plan_floor baseline → desk, custom → studio
-- Creator seed floor becomes studio (overlay + BYOK without Stripe).
--
-- Numbering: 115. 113 is cutover 113 (human gate). 114 is economic calendar.
-- Do not --apply cutover 113/900 from this hop.

-- Drop D1 CHECKs (Postgres names inline column CHECKs `{table}_{column}_check`).
ALTER TABLE public.workspaces
    DROP CONSTRAINT IF EXISTS workspaces_plan_tier_check;

ALTER TABLE public.entitlement_grants
    DROP CONSTRAINT IF EXISTS entitlement_grants_plan_floor_check;

UPDATE public.workspaces
SET plan_tier = CASE plan_tier
    WHEN 'baseline' THEN 'desk'
    WHEN 'custom' THEN 'studio'
    ELSE plan_tier
END
WHERE plan_tier IN ('baseline', 'custom');

UPDATE public.entitlement_grants
SET
    plan_floor = CASE plan_floor
        WHEN 'baseline' THEN 'desk'
        WHEN 'custom' THEN 'studio'
        ELSE plan_floor
    END,
    updated_at = now()
WHERE plan_floor IN ('baseline', 'custom');

ALTER TABLE public.workspaces
    ADD CONSTRAINT workspaces_plan_tier_check
    CHECK (plan_tier IN ('free', 'brief', 'desk', 'studio', 'enterprise'));

ALTER TABLE public.entitlement_grants
    ADD CONSTRAINT entitlement_grants_plan_floor_check
    CHECK (plan_floor IN ('brief', 'desk', 'studio', 'enterprise'));

INSERT INTO public.entitlement_grants (email, plan_floor, note)
VALUES (
    'chris.stefan@proton.me',
    'studio',
    'olympus creator / ops — studio overlay + Kairos surfaces without Stripe'
)
ON CONFLICT (email) DO UPDATE
SET
    plan_floor = EXCLUDED.plan_floor,
    note = EXCLUDED.note,
    updated_at = now();

CREATE OR REPLACE FUNCTION public.plan_tier_rank(p_tier text)
RETURNS integer
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE lower(coalesce(p_tier, 'free'))
        WHEN 'free' THEN 0
        WHEN 'brief' THEN 1
        WHEN 'desk' THEN 2
        WHEN 'studio' THEN 3
        WHEN 'enterprise' THEN 4
        ELSE 0
    END;
$$;

CREATE OR REPLACE FUNCTION public.max_plan_tier(p_a text, p_b text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN public.plan_tier_rank(p_a) >= public.plan_tier_rank(p_b) THEN
            CASE lower(coalesce(p_a, 'free'))
                WHEN 'brief' THEN 'brief'
                WHEN 'desk' THEN 'desk'
                WHEN 'studio' THEN 'studio'
                WHEN 'enterprise' THEN 'enterprise'
                ELSE 'free'
            END
        ELSE
            CASE lower(coalesce(p_b, 'free'))
                WHEN 'brief' THEN 'brief'
                WHEN 'desk' THEN 'desk'
                WHEN 'studio' THEN 'studio'
                WHEN 'enterprise' THEN 'enterprise'
                ELSE 'free'
            END
    END;
$$;

COMMENT ON COLUMN public.workspaces.plan_tier IS
    'Consumer plan: free (Observer teaser) | brief | desk | studio | enterprise. '
    'Paid SKUs map from Stripe price ids (STRIPE_PRICE_{BRIEF,DESK,STUDIO}_*). '
    'Supersedes D1 baseline/custom (migration 115).';

COMMENT ON COLUMN public.entitlement_grants.plan_floor IS
    'Ops/creator floor: brief | desk | studio | enterprise. Effective tier = '
    'max(workspaces.plan_tier, plan_floor). Seeded creator → studio.';
