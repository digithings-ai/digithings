-- DRAFT ONLY. Do not apply. Chris reviews before any schema change.
-- Paper FX lines. gross is summed by the reader from lines; it is not stored,
-- so a missing notional stays null instead of a synthetic zero.

CREATE TABLE IF NOT EXISTS public.fx_paper_exposure (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  pair         text NOT NULL,
  side         text,
  notional_usd double precision,
  venue        text,
  as_of        date
);

ALTER TABLE public.fx_paper_exposure ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.fx_paper_exposure FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.fx_paper_exposure TO service_role;
