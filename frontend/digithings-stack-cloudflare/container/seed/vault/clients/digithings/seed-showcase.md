---
title: digithings chat — product showcase
tags: [digithings, seed, showcase]
---

# digithings chat — product showcase

**digithings.ai/chat is client #0:** the same self-hosted digichat + digigraph +
digivault + digisearch stack shipped to customers — not a separate demo.

## Layers

- **digichat** — Next.js UI + BFF (`/embed`, ungated on digithings.ai)
- **digigraph** — LangGraph research_rag workflow, tool routing
- **digikey** — JWT + BFF session grants
- **digivault** — notes under `clients/digithings/`
- **digisearch** — RAG index `digithings_docs`
- **digillm** — LiteLLM model proxy

## Retrieval path

```text
digithings.ai/chat → digichat /embed → digigraph
  → digivault_search_notes (clients/digithings)
  → digisearch (digithings_docs)
```

## Same product customers deploy

Profile A self-host (Compose / Cloudflare Containers) uses the same components.
Public chat is embed-only ungated; digikey still protects backend APIs.
