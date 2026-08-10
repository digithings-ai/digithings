---
title: digithings Profile A architecture
tags: [digithings, seed, architecture]
---

# digithings Profile A architecture

Website chat Container runs digigraph `:8000` and digikey `:8005` on the edge.
digisearch `:8002`, digivault `:8004`, LiteLLM `:4000`, and Redis are loopback-only.

## Always-retrieve tools

For digithings.ai/chat, digigraph prefetches digisearch against `digithings_docs`
and digivault_search_notes under `clients/digithings` before answering.

## Tenant routing

- Tenant **digithings** → index `digithings_docs`, vault `clients/digithings`
- Tenant **occ** → index `occ_help`, vault `clients/online-compliance-center`

Corpus keys live on WorkflowState so LangGraph does not drop header overrides.
