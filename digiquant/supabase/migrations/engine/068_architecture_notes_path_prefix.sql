-- 068_architecture_notes_path_prefix.sql
--
-- Optional path_prefix filter on search_architecture_notes for multi-tenant
-- corpora in the shared architecture_notes table (e.g. clients/digithings vs
-- clients/online-compliance-center).
--
-- Signature change: PostgreSQL matches CREATE OR REPLACE FUNCTION by the full
-- argument list. Adding path_prefix creates a new 3-arg overload alongside the
-- 2-arg function from migration 049. Because path_prefix has a default, a
-- two-argument call matches both overloads and fails with "is not unique".
-- Drop the 2-arg function first, then define the 3-arg replacement.

drop function if exists public.search_architecture_notes(text, int);

create or replace function public.search_architecture_notes(
    query text,
    match_limit int default 7,
    path_prefix text default null
)
returns table (
    vault_path text, title text, note_type text, summary text,
    body_markdown text, tags text[], wikilinks text[], rank real
)
language sql
stable
as $$
    with q as (
        select nullif(replace(websearch_to_tsquery('english', query)::text, '&', '|'), '')::tsquery as ts
    ),
    pref as (
        select nullif(trim(both '/' from coalesce(path_prefix, '')), '') as p
    )
    select n.vault_path, n.title, n.note_type, n.summary, n.body_markdown, n.tags, n.wikilinks,
           ts_rank('{0.1,0.2,0.4,1.0}'::float4[], n.fts, q.ts) as rank
    from public.architecture_notes n, q, pref
    where q.ts is not null
      and n.fts @@ q.ts
      and (
          pref.p is null
          or n.vault_path = pref.p
          or n.vault_path like pref.p || '/%'
      )
    order by rank desc
    limit greatest(1, least(match_limit, 20));
$$;

grant execute on function public.search_architecture_notes(text, int, text) to anon;
