-- digiquant/supabase/roles.sql: LOCAL bootstrap for `supabase start` / `supabase db reset`.
--
-- The Supabase CLI runs this file BEFORE migrations/*.sql. It stubs the objects
-- that the migration chain ALTERs but never CREATEs, because they reached the
-- managed project out of repo (config/self-host/parity-baseline.json lists the
-- from-empty gaps). Without it a clean `supabase start` stops at 031
-- (`relation "public.fx_economic_calendar" does not exist`). Migration bytes stay
-- unchanged: they are already applied on the managed project.
--
-- Never push this file: do not run `supabase db push --include-roles`. The
-- managed project already has every object below, and 128 dropped some of them.
-- Every statement is IF NOT EXISTS, so a re-run converges.

-- 031 / 116: twelve-x calendar port (dropped again by 128).
CREATE TABLE IF NOT EXISTS public.fx_economic_calendar (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_date date NOT NULL,
  country text NOT NULL DEFAULT '',
  event_name text NOT NULL DEFAULT '',
  external_id text UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- 036 / 061 / 121 / 129: LangGraph checkpointer tables (created by the library).
CREATE TABLE IF NOT EXISTS public.checkpoints (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT '',
  checkpoint_id text NOT NULL,
  parent_checkpoint_id text,
  type text,
  checkpoint jsonb NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
CREATE TABLE IF NOT EXISTS public.checkpoint_blobs (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT '',
  channel text NOT NULL,
  version text NOT NULL,
  type text NOT NULL,
  blob bytea,
  PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);
CREATE TABLE IF NOT EXISTS public.checkpoint_writes (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT '',
  checkpoint_id text NOT NULL,
  task_id text NOT NULL,
  idx integer NOT NULL,
  channel text NOT NULL,
  type text,
  blob bytea NOT NULL,
  PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
CREATE TABLE IF NOT EXISTS public.checkpoint_migrations (
  v integer PRIMARY KEY
);

-- 057 / 136: the migration ledgers db-migrate.yml used to create.
CREATE TABLE IF NOT EXISTS public.olympus_schema_migrations (
  filename text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.digithings_schema_migrations (
  version text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);

-- 116 adds policies to these; 128 drops them.
CREATE TABLE IF NOT EXISTS public.portfolio_lots (id bigint PRIMARY KEY);
CREATE TABLE IF NOT EXISTS public.portfolio_trades (id bigint PRIMARY KEY);
CREATE TABLE IF NOT EXISTS public.portfolio_holdings_daily (id bigint PRIMARY KEY);

-- 139 revokes on schema net (pg_net is preinstalled on the managed project).
CREATE EXTENSION IF NOT EXISTS pg_net;
