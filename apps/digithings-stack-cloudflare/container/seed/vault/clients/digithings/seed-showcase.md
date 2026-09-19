---
title: digithings chat — product showcase
tags: [digithings, seed, showcase]
---

# digithings chat — product showcase

**digithings.ai/chat is client #0:** the same self-hosted chat stack shipped to
customers — not a separate demo.

## Retrieval path

```text
digithings.ai/chat → digichat /embed → digigraph
  → digivault_search_notes (clients/digithings)
  → digisearch (digithings_docs)
```

## Same product customers deploy

Profile A Compose / Cloudflare Containers path. Public chat is embed-only
ungated; backend APIs still require scoped tokens.
