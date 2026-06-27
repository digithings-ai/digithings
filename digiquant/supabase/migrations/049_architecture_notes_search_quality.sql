-- 049_architecture_notes_search_quality.sql
--
-- Run with:  supabase db push   (or apply via MCP against this project).
--
-- Docs-chat retrieval quality (#1087), from the live anon-key RPC test on the seeded
-- vault. Two fixes:
--   (1) Weight the FTS vector — title = A, tags + summary = B, body = C — so an on-topic
--       note (e.g. DigiKey for "authentication") outranks the broad ecosystem overview.
--   (2) OR the query terms. websearch_to_tsquery ANDs by default, so a natural multi-
--       keyword question ("backtesting and optimizing quant trading strategies") matched
--       ZERO notes (no single note carried all five stems). We loosen the top-level AND
--       to OR by rewriting the parsed tsquery (phrases via <-> are preserved), and rank
--       by ts_rank so the most relevant note still wins.
--
-- ADDITIVE/forward-only: regenerates the derived `fts` column (no row data lost — it is
-- recomputed from title/summary/body) and replaces the search function. Re-runnable.

alter table public.architecture_notes drop column if exists fts;
alter table public.architecture_notes add column fts tsvector generated always as (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', array_to_string(tags, ' ') || ' ' || coalesce(summary, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(body_markdown, '')), 'C')
) stored;
create index if not exists idx_architecture_notes_fts on public.architecture_notes using gin (fts);

create or replace function public.search_architecture_notes(query text, match_limit int default 7)
returns table (
    vault_path text, title text, note_type text, summary text,
    body_markdown text, tags text[], wikilinks text[], rank real
)
language sql
stable
as $$
    with q as (
        -- websearch_to_tsquery ANDs terms; loosen the top-level AND to OR so any matching
        -- term contributes. nullif('') guards an all-stopword query (=> no rows, no error).
        select nullif(replace(websearch_to_tsquery('english', query)::text, '&', '|'), '')::tsquery as ts
    )
    select n.vault_path, n.title, n.note_type, n.summary, n.body_markdown, n.tags, n.wikilinks,
           ts_rank('{0.1,0.2,0.4,1.0}'::float4[], n.fts, q.ts) as rank
    from public.architecture_notes n, q
    where q.ts is not null and n.fts @@ q.ts
    order by rank desc
    limit greatest(1, least(match_limit, 20));
$$;

grant execute on function public.search_architecture_notes(text, int) to anon;
