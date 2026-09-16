-- 126_product_invite_plan_floor.sql
--
-- Tiered invites: a product_invite_codes row can now also carry a
-- plan_floor, so a single fx_hub invite link can both grant the product AND
-- raise the redeemer's entitlement_grants.plan_floor (migration 115's
-- brief/desk/studio/enterprise scale). Redemption never downgrades an
-- existing higher tier (see invite.ts planFloorOutranks).
--
-- Tier-only codes (no product_key) are NOT enabled here — product_key stays
-- NOT NULL; ClientProductKey (dashboard lib/access.ts) only knows 'fx_hub'
-- today. Revisit if/when a second client product ships.

ALTER TABLE public.product_invite_codes
    ADD COLUMN IF NOT EXISTS plan_floor text
        CONSTRAINT product_invite_codes_plan_floor_known
            CHECK (plan_floor is null or plan_floor in ('brief', 'desk', 'studio', 'enterprise'));

COMMENT ON COLUMN public.product_invite_codes.plan_floor IS
    'Optional entitlement_grants.plan_floor bump applied alongside the product grant on redemption. NULL = product grant only.';
