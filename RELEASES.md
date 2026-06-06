# Releases

Monorepo components ship as **independent Python packages** (`digibase`, `digigraph`, `digiquant`, `digisearch`, `digismith`). Use **git tags** or Docker image digests in production.

## Release process

There is no automated release pipeline yet. To ship a release:

1. Confirm CI is green on `develop`.
2. Pick a version per the tagging convention below.
3. Tag: `git tag <component>-vX.Y.Z` (or a single repo-wide `vX.Y.Z`).
4. Push the tag: `git push origin <tag>`.
5. Build and publish Docker images (one per service) pinned to the same git SHA.
6. Append a changelog entry under "Unreleased" below, then move it under a new dated heading.

Formal automation (release workflow, PyPI publish, Docker image publish) is tracked under the hardening epic ([#2](https://github.com/digithings-ai/digithings/issues/2)).

## Tagging convention

- Per-component: `digigraph-v0.1.0`, `digiquant-v0.1.0`, etc.
- Or a single repo-wide `v0.1.0` with matching image builds across services.

Either works; pick one and stay consistent within a release cycle.

## Pinning policy

- Deploy **one git SHA** across services built from this repo, or
- Follow the compatibility matrix in [ARCHITECTURE.md](ARCHITECTURE.md).

## Install order (local / CI)

`pip install -e ./digibase` first, then editable installs of dependents (`digigraph`, `digiquant`, `digisearch`, `digismith`). Dockerfiles use a **repo-root build context** so `digibase` is copied and installed before each service package.

## Changelog (high level)

### Unreleased

- **Branch cleanup:** Confirmed removal of stale merged branch `task/149-w1e-price-pipeline` (already deleted from origin; merged into `develop` via PR #286 / #288 for issue #149 — Atlas price pipeline migration).

- **Baseline cleanup (Phase 1–7):** AI-hallucinated docs removed; root docs rewritten; DigiClaw repackaged (Phase 4); code dedup into `digibase`; test baseline for DigiClaw; full details in [#31](https://github.com/digithings-ai/digithings/issues/31).
- **Strategic docs:** [docs/VISION.md](docs/VISION.md) captures two-domain plan (digithings.ai + digiquant.io) and strategic decisions. First ADRs landed: [0001 Project Spec](docs/adr/0001-project-spec.md), [0002 Domain Unification](docs/adr/0002-domain-unification.md).
- **Federated hub:** DigiSearch/DigiQuant expose `POST /v1/orchestrator_tools` + `POST /v1/orchestrator_invoke` (manifest + dispatch). DigiGraph caches vertical tool schemas and invokes them (same JWT chain). `DIGI_HUB_MODE=federated` additionally registers `digisearch_research_delegate` / `digiquant_pipeline_delegate`. DigiQuant: `POST /v1/workflow`, MCP `digiquant_run_pipeline`. DigiSearch: optional `digisearch[agent]`, `POST /v1/research_turn`, MCP `digisearch_research_turn`. DigiChat: `DIGICHAT_ENABLED_SERVICES`, optional `DIGISEARCH_INTERNAL_URL`, trace `service` field in UI.
- **Infra / LiteLLM:** Compose uses `docker.litellm.ai/berriai/litellm:main-stable`, explicit `--config`, `/health/liveliness` healthcheck, DigiGraph `depends_on: litellm` healthy; optional `litellm-cache` profile (Redis). `LITELLM_PROXY_API_KEY` for DigiGraph Bearer vs upstream `OPENAI_API_KEY` in LiteLLM; proxy `litellm_settings` cache, retries, timeouts, and Ollama Cloud → local fallbacks in `config/litellm.yaml`.
- **digibase** (new): shared HTTP headers, API error envelope, audit redaction helper, optional OTel FastAPI wiring. Docs: [digibase/ARCHITECTURE.md](digibase/ARCHITECTURE.md) describes the shipped **library** vs the **roadmap** DigiBase **data-plane** service.
- **digigraph:** depends on `digibase`; standardized errors; policy module; optional tool entry points `digigraph.tools`; `quant_artifact_uri` in workflow state.
- **digiquant:** `POST /v1/jobs/backtest`, `GET /v1/jobs/{id}/status`; `digibase` errors and OTel.
- **digisearch:** `workspace_id` on query; `digisearch-worker` CLI stub; `embeddings.config`; `digibase` integration.
- **digismith:** `digibase` errors and OTel; correlation middleware.
- **digiclaw:** optional `AUDIT_SINK_URL` for NDJSON POST mirror.
