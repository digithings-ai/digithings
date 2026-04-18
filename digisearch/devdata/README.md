# Dev data (DigiSearch)

## `edgar_sample/`

Generated files `edgar_*.md` / `edgar_*.yaml` are **not committed** (see repo root `.gitignore`).

1. **Export** a small slice from Hugging Face `eloukas/edgar-corpus`:  
   `make export-edgar-digisearch-dev`  
   (requires `pip install -e "./digisearch[edgar-corpus]"`; the export script passes `trust_remote_code=True`).

   **Troubleshooting:** `datasets` **4.5+** rejects repository loading scripts. If export fails with *Dataset scripts are no longer supported*, temporarily run `pip install 'datasets>=3.2,<4.5'`, export, then upgrade again if needed.

2. **Ingest** into Chroma index `edgar_dev`:  
   - Docker: `make seed-digisearch-edgar-dev`  
   - Host DigiSearch (`make stack-local`): `make seed-digisearch-edgar-dev-host`

3. Set **`DIGISEARCH_INDEX=edgar_dev`** for DigiGraph (see `docs/LOCAL_STACK.md`).

**Corpus:** Loukas et al., *EDGAR-CORPUS*, ECONLP 2021 — public SEC filings. Dev/testing only; see `SECURITY.md`.
