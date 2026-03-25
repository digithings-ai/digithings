# DigiThings component releases

Monorepo components ship as **independent Python packages** (`digibase`, `digigraph`, `digiquant`, `digisearch`, `digismith`). Use **git tags** or Docker image digests in production.

**Local / CI install order:** `pip install -e ./digibase` first, then editable installs of components that depend on it (`digigraph`, `digiquant`, `digisearch`, `digismith`). Dockerfiles use a **repo-root build context** so `digibase` is copied and installed before each service package. A root `uv` workspace meta-package is optional future work; the `Makefile` and CI workflows install `digibase` explicitly.

## Pinning policy (recommended)

- Deploy **one git SHA** across services built from this repo, or
- Follow the **compatibility matrix** in [ARCHITECTURE.md](ARCHITECTURE.md).

## Changelog (high level)

### Unreleased (main)

- **Federated hub:** DigiSearch/DigiQuant expose **`POST /v1/orchestrator_tools`** + **`POST /v1/orchestrator_invoke`** (manifest + dispatch). DigiGraph caches vertical tool schemas and invokes them (same JWT chain). `DIGI_HUB_MODE=federated` additionally registers `digisearch_research_delegate` / `digiquant_pipeline_delegate` for hub-style prompts. DigiQuant: `POST /v1/workflow`, MCP `digiquant_run_pipeline`. DigiSearch: optional `digisearch[agent]`, `POST /v1/research_turn`, MCP `digisearch_research_turn`. DigiChat: `DIGICHAT_ENABLED_SERVICES`, optional `DIGISEARCH_INTERNAL_URL`, trace `service` field in UI.
- **Infra / LiteLLM:** Compose uses **`docker.litellm.ai/berriai/litellm:main-stable`**, explicit **`--config`**, **`/health/liveliness`** healthcheck, DigiGraph **`depends_on: litellm` healthy**; optional **`litellm-cache`** profile (Redis). **`LITELLM_PROXY_API_KEY`** for DigiGraph Bearer vs upstream **`OPENAI_API_KEY`** in **LiteLLM**; proxy **`litellm_settings`** cache, retries, timeouts, and Ollama Cloud → local fallbacks in **`config/litellm.yaml`**.
- **digibase** (new): shared HTTP headers, API error envelope, audit redaction helper, optional OTel FastAPI wiring. **Docs:** [digibase/DIGIBASE.md](digibase/DIGIBASE.md) describes the shipped **library** vs the **roadmap** DigiBase **data-plane** service (central Postgres/cache/object policy).
- **digigraph**: depends on `digibase`; standardized errors; policy module; optional tool entry points `digigraph.tools`; `quant_artifact_uri` in workflow state.
- **digiquant**: `POST /v1/jobs/backtest`, `GET /v1/jobs/{id}/status`; `digibase` errors and OTel.
- **digisearch**: `workspace_id` on query; `digisearch-worker` CLI stub; `embeddings.config`; `digibase` integration.
- **digismith**: `digibase` errors and OTel; correlation middleware.
- **digiclaw**: optional `AUDIT_SINK_URL` for NDJSON POST mirror.

## Tagging convention (suggestion)

- `digigraph-v0.1.0`, `digiquant-v0.1.0`, … or a single `v0.1.0` repo tag with matching image builds.
