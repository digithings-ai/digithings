-- 122_archive_objects_rls.sql
--
-- Run with:  supabase db push   (or apply via MCP against the core project).
-- Unwrapped on purpose: db-migrate.yml applies the file + ledger in one
-- transaction. Do not write an unbackticked begin-statement in this file
-- (comments included) — that grep drops the wrapping transaction.
--
-- Follow-up lockdown for public.archive_objects (created in 119 without
-- RLS / REVOKE). Same class as #3256 / 109 house-teaser and the 090
-- evidence-bundle pattern: migration 060 stripped write defaults but
-- SELECT remains via platform ACLs, so PostgREST could expose the R2
-- pointer registry to the published anon JWT.
--
-- Defense: RLS enabled with zero policies (deny for non-bypass roles) +
-- REVOKE ALL from PUBLIC/anon/authenticated + service_role DML only.
-- Privilege revoke is the defense if RLS is later disabled (#3793).

ALTER TABLE public.archive_objects ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.archive_objects FROM PUBLIC, anon, authenticated;

REVOKE ALL ON public.archive_objects FROM service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.archive_objects TO service_role;

-- Identity PK owns a backing sequence; mirror 118 knowledge_notes so
-- service_role can insert without relying on owner defaults.
DO $$
DECLARE
  seq_name text;
BEGIN
  seq_name := pg_get_serial_sequence('public.archive_objects', 'id');
  IF seq_name IS NOT NULL THEN
    EXECUTE format(
      'REVOKE ALL ON SEQUENCE %s FROM PUBLIC, anon, authenticated',
      seq_name
    );
    EXECUTE format(
      'GRANT USAGE, SELECT ON SEQUENCE %s TO service_role',
      seq_name
    );
  END IF;
END $$;
