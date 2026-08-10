# digivault markdown notes (seed)

Obsidian-style vault management. Distinct from digisearch Chroma indexes.

## Layout

Notes live under client prefixes:

- `clients/digithings/` — digithings.ai/chat dogfood vault
- `clients/online-compliance-center/` — OCC help vault

`digivault_search_notes` accepts an optional `path_prefix` so tenants cannot see
each other's folders.

## Note format

YAML frontmatter (`title`, `tags`) plus markdown body. Wikilinks use `[[Note]]`
syntax; backlinks and tag search are first-class vault operations.

## Search

Profile A uses **local filesystem keyword search** over `DIGIVAULT_ROOT` (not
Supabase FTS) when the root is mounted. Ranking is token overlap on title + body
after dropping English stopwords.

## What this note does not cover

Chroma embeddings, RS256 JWTs, or LiteLLM model routing.
