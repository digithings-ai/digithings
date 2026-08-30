-- 108_entitlement_grants_and_products.sql
--
-- Product gating (2026-08-30):
--   * entitlement_grants.plan_floor — creator/ops email → effective plan floor
--     without Stripe (seed: creator → custom so baseline pipeline + broker
--     connect work for Kairos staging once vendor keys land).
--   * client_product_grants — per-email custom products (fx_hub now; future
--     Olympus client products use the same table).
--   * my_access() RPC — authenticated snapshot for Olympus UI + settings EF.
--
-- Free (Observer) stays teaser-only in the T5 matrix; this migration does not
-- widen free. Cutover 900 untouched.

CREATE TABLE IF NOT EXISTS public.entitlement_grants (
    email text NOT NULL,
    plan_floor text NOT NULL
        CHECK (plan_floor IN ('baseline', 'custom', 'enterprise')),
    note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT entitlement_grants_email_pkey PRIMARY KEY (email),
    CONSTRAINT entitlement_grants_email_lower
        CHECK (email = lower(email) AND email ~ '^[^@]+@[^@]+\.[^@]+$')
);

COMMENT ON TABLE public.entitlement_grants IS
    'Ops/creator plan floor by email. Effective tier = max(workspaces.plan_tier, plan_floor). '
    'Does not replace Stripe for paying customers; seeds creator access without checkout.';

CREATE TABLE IF NOT EXISTS public.client_product_grants (
    email text NOT NULL,
    product_key text NOT NULL,
    note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT client_product_grants_pkey PRIMARY KEY (email, product_key),
    CONSTRAINT client_product_grants_email_lower
        CHECK (email = lower(email) AND email ~ '^[^@]+@[^@]+\.[^@]+$'),
    CONSTRAINT client_product_grants_product_key_nonempty
        CHECK (length(trim(product_key)) > 0)
);

COMMENT ON TABLE public.client_product_grants IS
    'Per-email custom product visibility (fx_hub, future client Olympus products). '
    'Creators are also seeded here; 12x client emails land via ops insert.';

CREATE INDEX IF NOT EXISTS idx_client_product_grants_product
    ON public.client_product_grants (product_key);

ALTER TABLE public.entitlement_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.client_product_grants ENABLE ROW LEVEL SECURITY;

-- Deny-by-default for anon/authenticated direct table reads. Access goes through
-- SECURITY DEFINER my_access() (or service_role for ops).
REVOKE ALL ON TABLE public.entitlement_grants FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.client_product_grants FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.entitlement_grants TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.client_product_grants TO service_role;

-- Creator seed (GitHub Olympus user on core). Empty 12x list — human supplies later.
INSERT INTO public.entitlement_grants (email, plan_floor, note)
VALUES (
    'chris.stefan@proton.me',
    'custom',
    'olympus creator / ops — baseline pipeline + Kairos surfaces without Stripe'
)
ON CONFLICT (email) DO UPDATE
SET
    plan_floor = EXCLUDED.plan_floor,
    note = EXCLUDED.note,
    updated_at = now();

INSERT INTO public.client_product_grants (email, product_key, note)
VALUES (
    'chris.stefan@proton.me',
    'fx_hub',
    'creator seed — FX Hub (twelve-x) client product'
)
ON CONFLICT (email, product_key) DO NOTHING;

CREATE OR REPLACE FUNCTION public.plan_tier_rank(p_tier text)
RETURNS integer
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE lower(coalesce(p_tier, 'free'))
        WHEN 'free' THEN 0
        WHEN 'baseline' THEN 1
        WHEN 'custom' THEN 2
        WHEN 'enterprise' THEN 3
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
                WHEN 'baseline' THEN 'baseline'
                WHEN 'custom' THEN 'custom'
                WHEN 'enterprise' THEN 'enterprise'
                ELSE 'free'
            END
        ELSE
            CASE lower(coalesce(p_b, 'free'))
                WHEN 'baseline' THEN 'baseline'
                WHEN 'custom' THEN 'custom'
                WHEN 'enterprise' THEN 'enterprise'
                ELSE 'free'
            END
    END;
$$;

CREATE OR REPLACE FUNCTION public.my_access()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_uid uuid := auth.uid();
    v_email text;
    v_ws_id uuid;
    v_ws_tier text := 'free';
    v_floor text;
    v_products text[];
    v_effective text;
BEGIN
    IF v_uid IS NULL THEN
        RAISE EXCEPTION 'my_access: authentication required';
    END IF;

    SELECT lower(u.email)
    INTO v_email
    FROM auth.users u
    WHERE u.id = v_uid;

    IF v_email IS NULL OR v_email = '' THEN
        v_email := '';
    END IF;

    SELECT wm.workspace_id, w.plan_tier
    INTO v_ws_id, v_ws_tier
    FROM public.workspace_members wm
    JOIN public.workspaces w ON w.id = wm.workspace_id
    WHERE wm.user_id = v_uid
      AND w.type = 'user'
    ORDER BY wm.created_at ASC
    LIMIT 1;

    IF v_ws_tier IS NULL OR v_ws_tier = '' THEN
        v_ws_tier := 'free';
    END IF;

    IF v_email <> '' THEN
        SELECT eg.plan_floor
        INTO v_floor
        FROM public.entitlement_grants eg
        WHERE eg.email = v_email;

        SELECT coalesce(array_agg(cpg.product_key ORDER BY cpg.product_key), '{}')
        INTO v_products
        FROM public.client_product_grants cpg
        WHERE cpg.email = v_email;
    ELSE
        v_products := '{}';
    END IF;

    -- Creators with a plan_floor always see fx_hub even if the product row lags.
    IF v_floor IS NOT NULL
       AND NOT (coalesce(v_products, '{}') @> ARRAY['fx_hub']::text[])
    THEN
        v_products := array_append(coalesce(v_products, '{}'), 'fx_hub');
    END IF;

    v_effective := public.max_plan_tier(v_ws_tier, v_floor);

    RETURN jsonb_build_object(
        'email', nullif(v_email, ''),
        'workspace_id', v_ws_id,
        'workspace_plan_tier', v_ws_tier,
        'plan_floor', v_floor,
        'effective_plan_tier', v_effective,
        'products', to_jsonb(coalesce(v_products, '{}'::text[]))
    );
END;
$$;

COMMENT ON FUNCTION public.my_access() IS
    'Authenticated entitlement snapshot: workspace plan_tier, ops plan_floor, '
    'effective tier, and client_product_grants keys (fx_hub, …).';

REVOKE ALL ON FUNCTION public.my_access() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.my_access() TO authenticated;
GRANT EXECUTE ON FUNCTION public.my_access() TO service_role;

REVOKE ALL ON FUNCTION public.plan_tier_rank(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.plan_tier_rank(text) TO service_role;

REVOKE ALL ON FUNCTION public.max_plan_tier(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.max_plan_tier(text, text) TO service_role;
