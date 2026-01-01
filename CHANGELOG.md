# Changelog

digithings releases each component on its own, so each one keeps its own changelog. [release-please](https://github.com/googleapis/release-please) writes them from the [conventional commits](https://www.conventionalcommits.org/) that land on `develop`, and a release is the matching `<component>-vX.Y.Z` tag. See [RELEASES.md](RELEASES.md) for the process.

| Component | Changelog | Tag |
|---|---|---|
| digichat | [apps/digichat/CHANGELOG.md](apps/digichat/CHANGELOG.md) | `digichat-vX.Y.Z` |
| digiskills | [digiskills/CHANGELOG.md](digiskills/CHANGELOG.md) | `digiskills-vX.Y.Z` |

The Python services (`digibase`, `digigraph`, `digiquant`, `digisearch`, `digitrace`, `digikey`, `digivault`) are not on release-please yet. Until they are, pin them by git SHA or image digest, as [RELEASES.md § Pinning policy](RELEASES.md#pinning-policy) describes.

## Before per-component changelogs

The entries below predate release-please. They are kept as written.

- **Baseline cleanup (Phase 1–7):** AI-hallucinated docs removed; root docs rewritten; digibot repackaged (Phase 4); code dedup into `digibase`; test baseline for digibot; full details in [#31](https://github.com/digithings-ai/digithings/issues/31).
- **Strategic docs:** [docs/VISION.md](docs/VISION.md) captures two-domain plan (digithings.ai + digiquant.io) and strategic decisions. First ADRs landed: [0001 Project Spec](docs/adr/0001-project-spec.md), [0002 Domain Unification](docs/adr/0002-domain-unification.md).
- **Federated hub:** digisearch/digiquant expose `POST /v1/orchestrator_tools` + `POST /v1/orchestrator_invoke` (manifest + dispatch). digigraph caches vertical tool schemas and invokes them (same JWT chain). `DIGI_HUB_MODE=federated` additionally registers `digisearch_research_delegate` / `digiquant_pipeline_delegate`. digiquant: `POST /v1/workflow`, MCP `digiquant_run_pipeline`. digisearch: optional `digisearch[agent]`, `POST /v1/research_turn`, MCP `digisearch_research_turn`. digichat: `DIGICHAT_ENABLED_SERVICES`, optional `DIGISEARCH_INTERNAL_URL`, trace `service` field in UI.
- **Infra / LiteLLM:** Compose uses `docker.litellm.ai/berriai/litellm:main-stable`, explicit `--config`, `/health/liveliness` healthcheck, digigraph `depends_on: litellm` healthy; optional `litellm-cache` profile (Redis). `LITELLM_PROXY_API_KEY` for digigraph Bearer vs upstream `OPENAI_API_KEY` in LiteLLM; proxy `litellm_settings` cache, retries, timeouts, and Ollama Cloud → local fallbacks in `config/litellm.yaml`.
- **digibase** (new): shared HTTP headers, API error envelope, audit redaction helper, optional OTel FastAPI wiring. Docs: [digibase/ARCHITECTURE.md](digibase/ARCHITECTURE.md) describes the shipped **library** vs the **roadmap** digibase **data-plane** service.
- **digigraph:** depends on `digibase`; standardized errors; policy module; optional tool entry points `digigraph.tools`; `quant_artifact_uri` in workflow state.
- **digiquant:** `POST /v1/jobs/backtest`, `GET /v1/jobs/{id}/status`; `digibase` errors and OTel.
- **digisearch:** `workspace_id` on query; `digisearch-worker` CLI stub; `embeddings.config`; `digibase` integration.
- **digitrace:** `digibase` errors and OTel; correlation middleware.
- **digibot:** optional `AUDIT_SINK_URL` for NDJSON POST mirror. Renamed from `digiclaw` (PR #5441); the module is parked, so it gets no release tag of its own. The self-host `heartbeat` profile in `infra/self-host/compose.ghcr.yml` now pulls `ghcr.io/digithings-ai/digibot`, and **no workflow publishes that image yet** — build it locally (`make up-heartbeat`) until a publish workflow lands.
