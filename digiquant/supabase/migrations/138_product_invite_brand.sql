-- 138_product_invite_brand.sql
--
-- Branded invite signup: a product_invite_codes row can now carry display
-- branding for the pre-signup card — a short team marker (e.g. '12X') plus
-- an optional line (e.g. 'Purpose-built for the 12X desk'). Served by the
-- public GET /access/invite-brand (display-only, no grant signal); NULL
-- marker renders the default card.

ALTER TABLE public.product_invite_codes
    ADD COLUMN IF NOT EXISTS brand_marker text
        CONSTRAINT product_invite_codes_brand_marker_short
            CHECK (brand_marker is null or (char_length(brand_marker) between 1 and 24)),
    ADD COLUMN IF NOT EXISTS brand_line text
        CONSTRAINT product_invite_codes_brand_line_short
            CHECK (brand_line is null or (char_length(brand_line) between 1 and 120));

COMMENT ON COLUMN public.product_invite_codes.brand_marker IS
    'Short client marker shown on the invite signup card (e.g. 12X). NULL = default card.';
COMMENT ON COLUMN public.product_invite_codes.brand_line IS
    'Optional line under the marker on the invite signup card. NULL = marker only.';
