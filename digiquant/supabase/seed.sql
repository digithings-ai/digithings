-- Synthetic seed data for the digithings LOCAL reference stack (DIG-2774, plan section 5).
--
-- Synthetic only. No client data, no market data, no production rows.
--
-- Every id below is a uuid5 of a fixed label under the seed (42), so this file
-- is safe to apply repeatedly: every statement is an upsert on a natural key,
-- so a re-run converges instead of accumulating rows. It only ever touches
-- rows the seed itself owns and never collides with the `system` or `house`
-- workspaces that migration 096 already seeded under its own ids.
--
-- The ids are generated from scripts/seed/portfolio.py, the same module the
-- Supabase-client path uses, so the two paths write identical rows.
-- tests/scripts/test_seed_local_stack.py re-derives them and asserts equality,
-- so this file cannot silently drift away from the Python seeder.
--
-- Loaded by `supabase db reset` via [db.seed] in digiquant/supabase/config.toml.
-- doc_type values come from chk_documents_doc_type (migration 023); a value
-- outside that allow-list is refused by the constraint, not by this seed.

BEGIN;

-- ------------------------------------------------------------- demo tenants
INSERT INTO public.workspaces (id, slug, type, name, plan_tier)
VALUES ('0b4b7eca-d70e-59b9-ae05-4d95effd5536', 'seed-demo', 'user', 'Seed Demo Tenant', 'desk')
ON CONFLICT (id) DO UPDATE SET
  slug = EXCLUDED.slug,
  type = EXCLUDED.type,
  name = EXCLUDED.name,
  plan_tier = EXCLUDED.plan_tier;
INSERT INTO public.workspaces (id, slug, type, name, plan_tier)
VALUES ('8f774e89-3e65-5d6f-8828-ef0a5ef46a0a', 'seed-lab', 'user', 'Seed Lab Tenant', 'brief')
ON CONFLICT (id) DO UPDATE SET
  slug = EXCLUDED.slug,
  type = EXCLUDED.type,
  name = EXCLUDED.name,
  plan_tier = EXCLUDED.plan_tier;

-- ---------------------------------------------------------- demo members
-- ada@owner on seed-demo
INSERT INTO public.workspace_members (workspace_id, user_id, role)
VALUES ('0b4b7eca-d70e-59b9-ae05-4d95effd5536', 'af1e130b-3f41-59ac-baca-779eaecfe7c1', 'owner')
ON CONFLICT (workspace_id, user_id) DO UPDATE SET role = EXCLUDED.role;
-- grace@member on seed-demo
INSERT INTO public.workspace_members (workspace_id, user_id, role)
VALUES ('0b4b7eca-d70e-59b9-ae05-4d95effd5536', '5505a4c5-c2c1-5c4e-8440-076fb7a038f6', 'member')
ON CONFLICT (workspace_id, user_id) DO UPDATE SET role = EXCLUDED.role;
-- ada@owner on seed-lab
INSERT INTO public.workspace_members (workspace_id, user_id, role)
VALUES ('8f774e89-3e65-5d6f-8828-ef0a5ef46a0a', 'af1e130b-3f41-59ac-baca-779eaecfe7c1', 'owner')
ON CONFLICT (workspace_id, user_id) DO UPDATE SET role = EXCLUDED.role;
-- grace@member on seed-lab
INSERT INTO public.workspace_members (workspace_id, user_id, role)
VALUES ('8f774e89-3e65-5d6f-8828-ef0a5ef46a0a', '5505a4c5-c2c1-5c4e-8440-076fb7a038f6', 'member')
ON CONFLICT (workspace_id, user_id) DO UPDATE SET role = EXCLUDED.role;

-- ------------------------------------------------------------ brief fixtures
INSERT INTO public.documents (workspace_id, date, document_key, doc_type, payload)
VALUES ('0b4b7eca-d70e-59b9-ae05-4d95effd5536', '2026-10-09', 'seed/brief/rates/2026-10-09', 'Daily Digest',
  '{"conviction": 0.73, "seed": 42, "summary": "Synthetic rates brief for the local reference stack. No client data, no market data, not advice.", "synthetic": true, "title": "Seed brief \u2014 rates (2026-10-09)"}'::jsonb)
ON CONFLICT (workspace_id, date, document_key) DO UPDATE SET
  doc_type = EXCLUDED.doc_type,
  payload = EXCLUDED.payload;
INSERT INTO public.documents (workspace_id, date, document_key, doc_type, payload)
VALUES ('0b4b7eca-d70e-59b9-ae05-4d95effd5536', '2026-10-08', 'seed/brief/equities/2026-10-08', 'Daily Digest',
  '{"conviction": 0.44, "seed": 42, "summary": "Synthetic equities brief for the local reference stack. No client data, no market data, not advice.", "synthetic": true, "title": "Seed brief \u2014 equities (2026-10-08)"}'::jsonb)
ON CONFLICT (workspace_id, date, document_key) DO UPDATE SET
  doc_type = EXCLUDED.doc_type,
  payload = EXCLUDED.payload;
INSERT INTO public.documents (workspace_id, date, document_key, doc_type, payload)
VALUES ('0b4b7eca-d70e-59b9-ae05-4d95effd5536', '2026-10-07', 'seed/brief/credit/2026-10-07', 'Daily Digest',
  '{"conviction": 0.62, "seed": 42, "summary": "Synthetic credit brief for the local reference stack. No client data, no market data, not advice.", "synthetic": true, "title": "Seed brief \u2014 credit (2026-10-07)"}'::jsonb)
ON CONFLICT (workspace_id, date, document_key) DO UPDATE SET
  doc_type = EXCLUDED.doc_type,
  payload = EXCLUDED.payload;
INSERT INTO public.documents (workspace_id, date, document_key, doc_type, payload)
VALUES ('0b4b7eca-d70e-59b9-ae05-4d95effd5536', '2026-10-06', 'seed/brief/commodities/2026-10-06', 'Daily Digest',
  '{"conviction": 0.39, "seed": 42, "summary": "Synthetic commodities brief for the local reference stack. No client data, no market data, not advice.", "synthetic": true, "title": "Seed brief \u2014 commodities (2026-10-06)"}'::jsonb)
ON CONFLICT (workspace_id, date, document_key) DO UPDATE SET
  doc_type = EXCLUDED.doc_type,
  payload = EXCLUDED.payload;
INSERT INTO public.documents (workspace_id, date, document_key, doc_type, payload)
VALUES ('0b4b7eca-d70e-59b9-ae05-4d95effd5536', '2026-10-05', 'seed/brief/fx/2026-10-05', 'Daily Digest',
  '{"conviction": 0.55, "seed": 42, "summary": "Synthetic fx brief for the local reference stack. No client data, no market data, not advice.", "synthetic": true, "title": "Seed brief \u2014 fx (2026-10-05)"}'::jsonb)
ON CONFLICT (workspace_id, date, document_key) DO UPDATE SET
  doc_type = EXCLUDED.doc_type,
  payload = EXCLUDED.payload;
INSERT INTO public.documents (workspace_id, date, document_key, doc_type, payload)
VALUES ('0b4b7eca-d70e-59b9-ae05-4d95effd5536', '2026-10-04', 'seed/brief/policy/2026-10-04', 'Daily Digest',
  '{"conviction": 0.79, "seed": 42, "summary": "Synthetic policy brief for the local reference stack. No client data, no market data, not advice.", "synthetic": true, "title": "Seed brief \u2014 policy (2026-10-04)"}'::jsonb)
ON CONFLICT (workspace_id, date, document_key) DO UPDATE SET
  doc_type = EXCLUDED.doc_type,
  payload = EXCLUDED.payload;

COMMIT;
