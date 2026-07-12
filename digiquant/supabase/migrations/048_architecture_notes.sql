-- 048_architecture_notes.sql
--
-- Run with:  supabase db push   (or apply via MCP against this project).
--
-- DigiThings architecture vault — the Supabase-backed twin of the DigiVault-managed
-- `docs/vision/` Obsidian vault. Mirrors the proven `knowledge_notes` shape (the
-- DigiQuant financial KB, migration 20260625, #1087) so the same DigiVault store
-- protocol + MCP read tools serve both vaults. Synced from docs/vision/ on every
-- push by scripts/sync_architecture_vault.py (DigiVault parses, digibase upserts).
--
-- This powers the digithings.ai docs chat: the public Cloudflare Function reads it
-- with the anon key (anon SELECT below) and searches via search_architecture_notes()
-- — the vault is the chatbot's ONLY knowledge source, no web search.
--
-- ADDITIVE ONLY: one new table + one read function, no FKs to existing objects,
-- no DROP/ALTER/TRUNCATE of anything else. Idempotent.
--
-- RLS: enabled with anon SELECT (public open-core docs — README/ARCHITECTURE/ADRs/
-- vision, never projects/ which is confidential). Writes via service_role (RLS bypass).

create table if not exists public.architecture_notes (
    id            bigint generated always as identity primary key,
    slug          text not null,                       -- note name (filename stem)
    vault_path    text not null,                       -- path within the vault, no .md
    title         text not null,
    note_type     text not null default 'reference',   -- module | moc | concept | reference
    status        text not null default 'stub',        -- stub | summarized | reviewed
    tags          text[] not null default '{}',
    relevance     text[] not null default '{}',        -- module stems that consume/depend on this
    summary       text not null default '',            -- the note's one-line tagline
    body_markdown text not null default '',            -- Obsidian markdown body (post-frontmatter)
    frontmatter   jsonb  not null default '{}'::jsonb,  -- full parsed YAML frontmatter
    sources       jsonb  not null default '[]'::jsonb,  -- [{title,author,url,kind,accessed}]
    wikilinks     text[] not null default '{}',        -- outbound [[targets]] for the backlink graph
    -- Full-text search vector over title + summary + body. knowledge_notes deferred
    -- pgvector to #1087; a Postgres FTS column is cheap and immediately answer-capable,
    -- which is exactly what the docs chat needs.
    fts tsvector generated always as (
        to_tsvector(
            'english',
            coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(body_markdown, '')
        )
    ) stored,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    constraint architecture_notes_vault_path_key unique (vault_path)
);

comment on table public.architecture_notes is
    'DigiThings architecture vault: Obsidian-style notes (frontmatter + markdown body + [[wikilinks]]), DigiVault-managed, synced from docs/vision/ by scripts/sync_architecture_vault.py. anon SELECT for the digithings.ai docs chat; service_role writes. Mirrors knowledge_notes (#1087).';

create index if not exists idx_architecture_notes_fts
    on public.architecture_notes using gin (fts);
create index if not exists idx_architecture_notes_tags
    on public.architecture_notes using gin (tags);
create index if not exists idx_architecture_notes_note_type
    on public.architecture_notes (note_type);

alter table public.architecture_notes enable row level security;

-- drop-if-exists/create so the migration is safely re-runnable (CREATE POLICY has no
-- IF NOT EXISTS; the policy may already exist where the schema was applied before).
drop policy if exists architecture_notes_anon_select on public.architecture_notes;
create policy architecture_notes_anon_select on public.architecture_notes
    for select to anon using (true);

-- Full-text search the docs chat calls via PostgREST RPC with the anon key. SECURITY
-- INVOKER (default): anon reads through the RLS policy above. websearch_to_tsquery
-- parses user input safely. match_limit is clamped to [1, 20].
create or replace function public.search_architecture_notes(query text, match_limit int default 7)
returns table (
    vault_path    text,
    title         text,
    note_type     text,
    summary       text,
    body_markdown text,
    tags          text[],
    wikilinks     text[],
    rank          real
)
language sql
stable
as $$
    select
        n.vault_path,
        n.title,
        n.note_type,
        n.summary,
        n.body_markdown,
        n.tags,
        n.wikilinks,
        ts_rank(n.fts, websearch_to_tsquery('english', query)) as rank
    from public.architecture_notes n
    where n.fts @@ websearch_to_tsquery('english', query)
    order by rank desc
    limit greatest(1, least(match_limit, 20));
$$;

grant execute on function public.search_architecture_notes(text, int) to anon;
