-- 068_architecture_notes_path_prefix.sql
--
-- Optional path_prefix filter on search_architecture_notes for multi-tenant
-- corpora in the shared architecture_notes table (e.g. clients/digithings vs
-- clients/online-compliance-center). Additive: replaces the function with a
-- compatible signature that defaults path_prefix to null (same behaviour as 049).

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
-- Keep prior 2-arg grants working for older clients.
grant execute on function public.search_architecture_notes(text, int) to anon;
