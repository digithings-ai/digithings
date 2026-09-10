---
title: digithings Profile A architecture
tags: [digithings, seed, architecture]
---

# digithings Profile A architecture

| Service | Port |
|---|---|
| digigraph | 8000 |
| digikey | 8005 |
| digisearch | 8002 |
| digivault | 8004 |
| LiteLLM | 4000 |

Persistence: Chroma `/data/chroma`, vault `/data/vault`, digikey SQLite
`/data/digikey.db`.

Tenant map: digithings → `digithings_docs` + `clients/digithings`; occ →
`occ_help` + `clients/online-compliance-center`.
