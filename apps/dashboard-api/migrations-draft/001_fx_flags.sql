-- DRAFT ONLY. Do not apply. Chris reviews before any schema change.
-- Research flags for one FX pair. Display-only; never an input to generation.
-- RLS on, no policies: service_role only (same posture as fx_intraday_observations).

CREATE TABLE IF NOT EXISTS public.fx_flags (
  pair       text PRIMARY KEY,
  flagged    boolean NOT NULL DEFAULT false,
  level      double precision,
  note       text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.fx_flags ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.fx_flags FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.fx_flags TO service_role;
