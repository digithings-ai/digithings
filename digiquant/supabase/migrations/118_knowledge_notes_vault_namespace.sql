-- 118_knowledge_notes_vault_namespace.sql
--
-- Run with:  supabase db push   (or apply via MCP against the core project).
--
-- Phase 1 of the unified DB-backed vault KB (#1142 / epic #1141): give
-- `knowledge_notes` a `vault` namespace column so one table can hold multiple
-- corpora (finance theory, product-suite docs, …) with per-vault uniqueness on
-- `(vault, vault_path)`.
--
-- History: the live digiquant `knowledge_notes` table was created outside the
-- numbered migration chain (referenced as migration 20260625 from #1087 /
-- architecture_notes). Fresh environments and CI therefore may not have the
-- table at all — `CREATE TABLE IF NOT EXISTS` below is the canonical schema;
-- the ALTER path upgrades an existing live table safely.
--
-- ADDITIVE / IDEMPOTENT: no DROP of data. Unique constraint swap is
-- drop-if-exists + add-if-missing.
--
-- Human apply: after merge, run `supabase db push` (or equivalent) against the
-- core Supabase project. No secrets are committed here — operators use their
-- existing CORE_SUPABASE_* credentials.

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
    constraint knowledge_notes_vault_vault_path_key unique (vault, vault_path),
    constraint knowledge_notes_vault_slug_key unique (vault, slug)
);

comment on table public.knowledge_notes is
    'digivault knowledge vault(s): Obsidian-style notes keyed by (vault, vault_path). '
    'Namespace column added in migration 118 (#1142). Seeded by scripts/seed_knowledge_vault.py.';

comment on column public.knowledge_notes.vault is
    'Vault namespace (e.g. finance, product). Default finance for the digiquant KB.';

-- Live table may predate this migration and lack the vault column / composite unique.
alter table public.knowledge_notes
    add column if not exists vault text not null default 'finance';

-- Old single-column uniqueness (live + any pre-118 create) → per-vault uniqueness.
alter table public.knowledge_notes
    drop constraint if exists knowledge_notes_vault_path_key;
alter table public.knowledge_notes
    drop constraint if exists knowledge_notes_vault_path_unique;

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
    if not exists (
        select 1
        from pg_constraint
        where conname = 'knowledge_notes_vault_slug_key'
          and conrelid = 'public.knowledge_notes'::regclass
    ) then
        alter table public.knowledge_notes
            add constraint knowledge_notes_vault_slug_key unique (vault, slug);
    end if;
end $$;

create index if not exists idx_knowledge_notes_vault
    on public.knowledge_notes (vault);
create index if not exists idx_knowledge_notes_tags
    on public.knowledge_notes using gin (tags);
create index if not exists idx_knowledge_notes_wikilinks
    on public.knowledge_notes using gin (wikilinks);

-- Service-role-only by design: enable RLS with no anon/authenticated policies.
-- Unlike architecture_notes (public docs chat, anon SELECT in migration 048),
-- knowledge_notes holds the digiquant finance KB and must not be anon-readable.
-- service_role bypasses RLS; digivault PostgresStore / seed scripts use the
-- service key. Do not add a public SELECT policy here without an explicit
-- product decision (epic #1141 Phase 4 covers a separate product corpus).
alter table public.knowledge_notes enable row level security;
