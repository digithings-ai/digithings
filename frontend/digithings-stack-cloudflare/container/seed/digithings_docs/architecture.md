# digithings stack architecture (seed)

Profile A chat stack used by digithings.ai/chat and local dogfood.

## Services and ports

| Service | Port | Exposure |
|---|---|---|
| digigraph | 8000 | Edge (graph.digithings.ai) — LangGraph workflow API |
| digikey | 8005 | Edge (key.digithings.ai) — JWT / BFF token exchange |
| digisearch | 8002 | Loopback only — RAG query + ingest |
| digivault | 8004 | Loopback only — note search under DIGIVAULT_ROOT |
| LiteLLM | 4000 | Loopback only — model routing |
| Redis | 6379 | Loopback — digikey blocklist / cache |

## Orchestration

digigraph runs a **research_rag** workflow profile. For website chat it always
prefetches:

1. **digisearch** against the tenant corpus index (`digithings_docs` for tenant
   digithings, `occ_help` for tenant occ)
2. **digivault_search_notes** scoped by vault path prefix
   (`clients/digithings` or `clients/online-compliance-center`)

Tenant corpus overrides arrive via digichat headers / `DIGI_TENANT_CORPUS_MAP`
and are preserved on LangGraph `WorkflowState` (`digisearch_index`,
`vault_path_prefix`).

## Auth

- Browser → digichat BFF (embed ungated for digithings.ai)
- digichat → digikey BFF session grant → JWT
- digigraph → digisearch / digivault with scoped bearer tokens

## Persistence

- Chroma at `CHROMA_PATH` (/data/chroma) — digisearch collections
- Vault at `DIGIVAULT_ROOT` (/data/vault) — markdown notes
- digikey SQLite at /data/digikey.db

## Naming

Always lowercase Digi product names in prose: digithings, digichat, digigraph,
digikey, digivault, digisearch, digillm.
