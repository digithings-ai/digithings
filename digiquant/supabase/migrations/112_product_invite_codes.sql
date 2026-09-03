-- 112_product_invite_codes.sql
--
-- Hashed invite codes for client products (fx_hub / 12x). JWT redeem
-- (settings POST /access/redeem-invite) inserts client_product_grants for the
-- caller's email. Plaintext is never stored. Login remains required — this is
-- not a client-side passphrase on the static export.
--
-- Migration 111 is reserved for the Group A unique-drop; do not reuse 111.

CREATE TABLE IF NOT EXISTS public.product_invite_codes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_key text NOT NULL,
    code_hash text NOT NULL,
    label text,
    max_redemptions integer,
    redemption_count integer NOT NULL DEFAULT 0,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT product_invite_codes_product_key_nonempty
        CHECK (length(trim(product_key)) > 0),
    CONSTRAINT product_invite_codes_hash_sha256
        CHECK (code_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT product_invite_codes_max_positive
        CHECK (max_redemptions IS NULL OR max_redemptions > 0)
);

COMMENT ON TABLE public.product_invite_codes IS
    'SHA-256 hex of product invite codes. Operator inserts hashes; settings EF redeems.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_product_invite_codes_hash
    ON public.product_invite_codes (product_key, code_hash);

CREATE TABLE IF NOT EXISTS public.product_invite_redemptions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    invite_code_id uuid REFERENCES public.product_invite_codes (id),
    product_key text NOT NULL,
    user_id uuid NOT NULL,
    email text NOT NULL,
    source text NOT NULL CHECK (source IN ('env', 'table')),
    redeemed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT product_invite_redemptions_email_lower
        CHECK (email = lower(email) AND email ~ '^[^@]+@[^@]+\.[^@]+$')
);

COMMENT ON TABLE public.product_invite_redemptions IS
    'Audit of who redeemed a product invite. Operator-readable via service_role.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_product_invite_redemptions_user_product
    ON public.product_invite_redemptions (user_id, product_key);

CREATE TABLE IF NOT EXISTS public.product_invite_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    product_key text NOT NULL,
    ok boolean NOT NULL,
    attempted_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.product_invite_attempts IS
    'Rate-limit ledger for invite redeem (8 attempts / user / hour in the EF).';

CREATE INDEX IF NOT EXISTS idx_product_invite_attempts_user_time
    ON public.product_invite_attempts (user_id, attempted_at DESC);

ALTER TABLE public.product_invite_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_invite_redemptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_invite_attempts ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.product_invite_codes FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.product_invite_redemptions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.product_invite_attempts FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.product_invite_codes TO service_role;
GRANT SELECT, INSERT ON TABLE public.product_invite_redemptions TO service_role;
GRANT SELECT, INSERT ON TABLE public.product_invite_attempts TO service_role;
