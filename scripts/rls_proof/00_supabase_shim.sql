-- ============================================================================
-- Supabase-compatibility shim for vanilla PostgreSQL RLS proofs
-- ============================================================================
-- Purpose: let digiquant/supabase/migrations/*.sql apply on stock Postgres 16
-- without Docker / Supabase CLI. Every object below mimics a Supabase platform
-- primitive that migrations assume exists. SHIM LOG lines are raised as NOTICE
-- so the proof run captures the inventory.
--
-- NOT production. Do not apply against core. See README.md for deltas.
-- ============================================================================

\echo '=== SHIM: begin Supabase-compat bootstrap ==='

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS moddatetime; -- contrib; available, unused by chain
-- pg_cron: prefer real extension (shared_preload_libraries must include pg_cron)
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS pg_cron;
  RAISE NOTICE 'SHIM: extension pg_cron enabled (real postgresql-16-cron package)';
EXCEPTION
  WHEN OTHERS THEN
    RAISE NOTICE 'SHIM: pg_cron CREATE EXTENSION failed (%); migration 061 skips schedule when absent', SQLERRM;
END $$;

DO $$ BEGIN RAISE NOTICE 'SHIM: extension pgcrypto enabled'; END $$;
DO $$ BEGIN RAISE NOTICE 'SHIM: extension moddatetime enabled'; END $$;

-- ---------------------------------------------------------------------------
-- Roles (Supabase PostgREST triad)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN NOBYPASSRLS;
    RAISE NOTICE 'SHIM: CREATE ROLE anon NOLOGIN NOBYPASSRLS';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN NOBYPASSRLS;
    RAISE NOTICE 'SHIM: CREATE ROLE authenticated NOLOGIN NOBYPASSRLS';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    -- BYPASSRLS matches Supabase service_role (PostgREST service key)
    CREATE ROLE service_role NOLOGIN BYPASSRLS;
    RAISE NOTICE 'SHIM: CREATE ROLE service_role NOLOGIN BYPASSRLS';
  END IF;
  -- Optional authenticator stand-in (membership so non-superuser runners can SET ROLE)
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticator') THEN
    CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'rls_proof_local';
    RAISE NOTICE 'SHIM: CREATE ROLE authenticator (login stand-in for PostgREST)';
  END IF;
  GRANT anon TO authenticator;
  GRANT authenticated TO authenticator;
  GRANT service_role TO authenticator;
  GRANT anon TO CURRENT_USER;
  GRANT authenticated TO CURRENT_USER;
  GRANT service_role TO CURRENT_USER;
END $$;

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

-- Supabase bootstrap: GRANT ALL on public relations + default privileges for
-- anon/authenticated/service_role. Migration 060 later revokes write grants from
-- client roles; service_role keeps broad grants until per-table revokes.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;

DO $$ BEGIN
  RAISE NOTICE 'SHIM: default privileges ALL on tables/sequences/functions → anon, authenticated, service_role (mirrors Supabase bootstrap; 060 narrows writes)';
END $$;

-- ---------------------------------------------------------------------------
-- auth schema + auth.uid() / auth.jwt() (Supabase Auth JWT claim helpers)
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS auth;
GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS auth.users (
  id uuid PRIMARY KEY
);
-- Minimal stub — production auth.users has many columns; policies only need id.
DO $$ BEGIN RAISE NOTICE 'SHIM: auth.users(id uuid PK) minimal stub'; END $$;

CREATE OR REPLACE FUNCTION auth.uid()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(
    NULLIF(current_setting('request.jwt.claims', true), '')::json ->> 'sub',
    ''
  )::uuid
$$;

CREATE OR REPLACE FUNCTION auth.jwt()
RETURNS json
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE(
    NULLIF(current_setting('request.jwt.claims', true), '')::json,
    '{}'::json
  )
$$;

GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION auth.jwt() TO anon, authenticated, service_role;

DO $$ BEGIN
  RAISE NOTICE 'SHIM: auth.uid() reads request.jwt.claims ->> sub; auth.jwt() returns claims json';
END $$;

-- Alias used by unmerged 103_notification_prefs.sql (chain has trigger_set_updated_at only).
-- Honest shim: same body as migration 003's trigger_set_updated_at.
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;
DO $$ BEGIN
  RAISE NOTICE 'SHIM: public.set_updated_at() alias for trigger_set_updated_at (needed by 103)';
END $$;

-- ---------------------------------------------------------------------------
-- LangGraph checkpointer stubs (auto-created in prod by the checkpointer library;
-- migrations 036/061 ALTER them)
-- ---------------------------------------------------------------------------
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
DO $$ BEGIN
  RAISE NOTICE 'SHIM: stub LangGraph checkpointer tables (checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations)';
END $$;

-- ---------------------------------------------------------------------------
-- Realtime publication (migration 063 hard-requires supabase_realtime)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    CREATE PUBLICATION supabase_realtime;
    RAISE NOTICE 'SHIM: CREATE PUBLICATION supabase_realtime (empty stub; 063 ADDs prices_live)';
  ELSE
    RAISE NOTICE 'SHIM: publication supabase_realtime already exists';
  END IF;
END $$;

-- Grant current tables (none yet) — after migrations, seed runs as owner.

-- ---------------------------------------------------------------------------
-- Out-of-repo / platform tables that in-repo migrations ALTER but never CREATE
-- ---------------------------------------------------------------------------
-- 031 enables RLS on fx_economic_calendar, which entered prod via an out-of-repo
-- twelve-x port (see 031 header / 047 note). Minimal stub so 031 can apply.
CREATE TABLE IF NOT EXISTS public.fx_economic_calendar (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_date date NOT NULL,
  country text NOT NULL DEFAULT '',
  event_name text NOT NULL DEFAULT '',
  external_id text UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN
  RAISE NOTICE 'SHIM: stub public.fx_economic_calendar (out-of-repo prod table; 031 ALTERs it)';
END $$;

-- db-migrate.yml creates olympus_schema_migrations before applying files;
-- migration 057 locks it. Stub the ledger table here.
CREATE TABLE IF NOT EXISTS public.olympus_schema_migrations (
  filename text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN
  RAISE NOTICE 'SHIM: stub public.olympus_schema_migrations (normally created by db-migrate.yml)';
END $$;

\echo '=== SHIM: bootstrap complete ==='
