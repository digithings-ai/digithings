-- 118_knowledge_notes_vault_namespace.sql
--
-- Run with:  supabase db push   (or apply via MCP against the core project).
-- Unwrapped on purpose: db-migrate.yml applies the file + ledger in one
-- transaction. Do not write an unbackticked begin-statement in this file
-- (comments included) — that grep drops the wrapping transaction.
--
-- Phase 1 of the unified DB-backed vault KB (#1142 / epic #1141 / #3603):
-- give `knowledge_notes` a `vault` namespace column so one table can hold
-- multiple corpora (finance theory, product-suite docs, …).
--
-- Uniqueness policy (explicit, no silent data loss):
--   * Unique identity is `(vault, vault_path)` only.
--   * Duplicate filename stems in different directories are legal — the
--     filesystem vault keeps them and reports `duplicate_note` via lint.
--     Do not add UNIQUE (vault, slug): live pre-118 rows already contain
--     that shape, and the constraint aborts the whole migration chain.
--   * If an earlier draft of 118 added `knowledge_notes_vault_slug_key`,
--     this file drops it.
--
-- History: the live digiquant `knowledge_notes` table was created outside
-- the numbered chain (referenced as 20260625 from #1087). Fresh
-- environments may not have the table — `CREATE TABLE IF NOT EXISTS` is
-- the canonical schema; the ALTER path upgrades the live table.
-- COMMENT ON COLUMN vault runs *after* ADD COLUMN so a pre-118 table
-- does not abort. Fresh and upgrade paths both attach
-- `knowledge_notes_set_updated_at` (live already has it; CREATE TABLE
-- alone used to omit it).
--
-- Tenant / client ACL: revoke PUBLIC / anon / authenticated, grant
-- service_role DML. RLS stays on with no client policies so a later RLS
-- misconfiguration still cannot read or mutate without a GRANT.
--
-- ADDITIVE / IDEMPOTENT: no DROP of rows. Safe to re-run.
--
-- Human apply: after merge, run `supabase db push` (or equivalent) against
-- the core Supabase project. No secrets are committed here.

create table if not exists public.knowledge_notes (
    id            bigint generated always as identity primary key,
    slug          text not null,
    vault_path    text not null,
    title         text not null,
    note_type     text not null default 'reference',
    status        text not null default 'stub',
    tags          text[] not null default '{}',
    relevance     text[] not null default '{}',
    summary       text not null default '',
    body_markdown text not null default '',
    frontmatter   jsonb  not null default '{}'::jsonb,
    sources       jsonb  not null default '[]'::jsonb,
    wikilinks     text[] not null default '{}',
    vault         text not null default 'finance',
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    constraint knowledge_notes_vault_vault_path_key unique (vault, vault_path)
);

-- Live table may predate this migration and lack the vault column.
alter table public.knowledge_notes
    add column if not exists vault text not null default 'finance';

comment on table public.knowledge_notes is
    'digivault knowledge vault(s): Obsidian-style notes keyed by (vault, vault_path). '
    'Duplicate stems in different paths are allowed; uniqueness is (vault, vault_path) '
    'only (#1142 / #3603). Seeded by scripts/seed_knowledge_vault.py.';

comment on column public.knowledge_notes.vault is
    'Vault namespace (e.g. finance, product). Default finance for the digiquant KB.';

-- Old single-column uniqueness (live + any pre-118 create) → per-vault path.
-- Drop the mistaken (vault, slug) unique from the original 118 draft.
alter table public.knowledge_notes
    drop constraint if exists knowledge_notes_vault_path_key;
alter table public.knowledge_notes
    drop constraint if exists knowledge_notes_vault_path_unique;
alter table public.knowledge_notes
    drop constraint if exists knowledge_notes_vault_slug_key;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'knowledge_notes_vault_vault_path_key'
          and conrelid = 'public.knowledge_notes'::regclass
    ) then
        alter table public.knowledge_notes
            add constraint knowledge_notes_vault_vault_path_key unique (vault, vault_path);
    end if;
end $$;

create index if not exists idx_knowledge_notes_vault
    on public.knowledge_notes (vault);
create index if not exists idx_knowledge_notes_tags
    on public.knowledge_notes using gin (tags);
create index if not exists idx_knowledge_notes_wikilinks
    on public.knowledge_notes using gin (wikilinks);

-- Align fresh CREATE with the live updated_at trigger (#1087 / #3603).
create or replace function public.knowledge_notes_set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists knowledge_notes_set_updated_at on public.knowledge_notes;
drop trigger if exists set_updated_at_knowledge_notes on public.knowledge_notes;
create trigger knowledge_notes_set_updated_at
  before update on public.knowledge_notes
  for each row execute function public.knowledge_notes_set_updated_at();

-- Service-role-only by design: enable RLS with no anon/authenticated policies.
-- Unlike architecture_notes (public docs chat, anon SELECT in migration 048),
-- knowledge_notes holds the digiquant finance KB and must not be client-readable.
-- service_role bypasses RLS; digivault PostgresStore / seed scripts use the
-- service key. Do not add a public SELECT policy here without an explicit
-- product decision (epic #1141 Phase 4 covers a separate product corpus).
alter table public.knowledge_notes enable row level security;

revoke all on table public.knowledge_notes from public, anon, authenticated;
grant select, insert, update, delete on table public.knowledge_notes to service_role;

do $$
declare
  seq_name text;
begin
  seq_name := pg_get_serial_sequence('public.knowledge_notes', 'id');
  if seq_name is not null then
    execute format(
      'revoke all on sequence %s from public, anon, authenticated',
      seq_name
    );
    execute format(
      'grant usage, select on sequence %s to service_role',
      seq_name
    );
  end if;
end $$;
