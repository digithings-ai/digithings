-- DRAFT ONLY. Do not apply. Chris reviews before any schema change.
-- Generation directives. PUT /fx/directives stays 503 until this table is applied.
-- One row per user id injected by the edge (x-digi-user). No auth lives here.

CREATE TABLE IF NOT EXISTS public.fx_directives (
  user_id        text PRIMARY KEY,
  allow_pairs    text[] NOT NULL DEFAULT '{}',
  deny_pairs     text[] NOT NULL DEFAULT '{}',
  risk_style     text,
  ignore_sources text[] NOT NULL DEFAULT '{}',
  updated_at     timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.fx_directives ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.fx_directives FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.fx_directives TO service_role;
