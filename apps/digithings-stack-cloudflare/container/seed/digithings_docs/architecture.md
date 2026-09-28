# digithings Profile A architecture (seed)

Ports and persistence for the website-chat Container — not a product glossary.

## Services and ports

| Service | Port | Exposure |
|---|---|---|
| digigraph | 8000 | Edge — LangGraph workflow API |
| digikey | 8005 | Edge — JWT / BFF token exchange |
| digisearch | 8002 | Loopback — RAG query + ingest |
| digivault | 8004 | Loopback — note search under DIGIVAULT_ROOT |
| LiteLLM | 4000 | Loopback — model routing |
| Redis | 6379 | Loopback — digikey blocklist / cache |

## Persistence paths

- Chroma at `CHROMA_PATH` (`/data/chroma`) — named collections
- Vault at `DIGIVAULT_ROOT` (`/data/vault`) — markdown notes
- digikey SQLite at `/data/digikey.db`

## Tenant corpus map

- Tenant **digithings** → index `digithings_docs`, vault `clients/digithings`
- Tenant **occ** → index `occ_help`, vault `clients/online-compliance-center`

Overrides arrive via digichat headers / `DIGI_TENANT_CORPUS_MAP` onto LangGraph
`WorkflowState` (`digisearch_index`, `vault_path_prefix`).
