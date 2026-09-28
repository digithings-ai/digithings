---
title: digivault prefixes and wikilinks
tags: [digithings, seed, digivault]
---

# digivault prefixes and wikilinks

Notes under `clients/digithings/` and `clients/online-compliance-center/`.
`path_prefix` isolates tenants. Frontmatter carries `title` + `tags`; bodies use
`[[wikilinks]]`. Profile A search is local filesystem keyword overlap (stopwords
dropped), not Supabase FTS, when `DIGIVAULT_ROOT` is set.
