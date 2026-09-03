# digithings Roadmap

**Last reviewed:** 2026-04-18

High-level phases. Vision and strategy: [docs/VISION.md](docs/VISION.md). Architecture: [ARCHITECTURE.md](ARCHITECTURE.md). Shipping history: [RELEASES.md](RELEASES.md). Per-component depth: each folder's `DIGIxxx.md`. Open work: [GitHub Project](https://github.com/users/chrizefan/projects) and [docs/agent-backlog/](docs/agent-backlog/).

---

## Phase 1 — shipped core ✅

Component foundations in place:

- **Orchestration:** digigraph LangGraph workflows (supervisor + subgraphs), digikey JWT for protected HTTP, vertical dispatch via `/v1/orchestrator_tools` and `/v1/orchestrator_invoke`.
- **Verticals:** digisearch (RAG, ingest, search backends), digiquant (NautilusTrader backtest/optimize, Polars-only).
- **Platform:** Docker Compose core stack, LiteLLM proxy, digismith health/`/v1/status`, optional digichat (Postgres + Next.js BFF).
- **MCP:** digigraph, digiquant, digisearch MCP servers for IDE and external clients.
- **First pilot:** the client pilot (projects/client-pilot/) running digigraph + digisearch against an Azure AI Search unified-content index.

## Phase 2 — hardening + project spec (in progress)

Goal: make the ecosystem **production-credible** and **project-composable**.

- **Hardening pass (cold review)** — security audit, dead-code removal, type-checking, test coverage gaps, dependency bump. Informed by `docs/CODE_REVIEW_BASELINE.md` and `docs/IMPROVEMENT_PLAN.md`.
- **digithings Project Spec v1alpha1** — formalize the client pilot pattern (see [ADR-0001](docs/adr/0001-project-spec.md)): `digiproject.yaml` + `docker-compose.yml` + `.env.example` as the unit of a client engagement. Refactor the client pilot to the formal spec; ship `projects/template/` starter.
- **Observability:** Prometheus-friendly metrics, centralized dashboards; digisearch audit sink alignment.
- **digigraph:** Auth-bound checkpoints, per-key RBAC, optional `X-Digi-Tenant` routing.
- **digikey:** Production revocation via Redis `jti` blocklist (`DIGIKEY_BLOCKLIST_REDIS_URL`); multi-tenant RBAC remains Phase 2+.
- **digiclaw:** MCP attachment to digigraph and richer gateway skills.
- **Rate limiting / cache:** Redis-backed distributed limits where today is in-process.

## Phase 3 — domain unification & ecosystem surface

Goal: a prospect landing on digithings.ai can **try the stack** in one click, and the finance product has its own home.

See [ADR-0002: Domain Unification](docs/adr/0002-domain-unification.md) for the full migration plan.

- **Phase 3a** — consolidate current frontends under `digithings.ai` + `digithings.ai/chat`. Add "Chat with digithings" CTA.
- **Phase 3b** — digichat as ecosystem guide. Build digisearch index over digithings docs; wire to digigraph; add bring-your-own-key flow in `digithings.ai/chat`.
- **Phase 3c** — stand up `digiquant.io` domain, minimal digiquant product UI.
- **Client Pilot Phase 2** — deliver POC improvements (see `projects/client-pilot/IMPROVEMENT_IDEAS.md`): surface stored_datasets to LLM, orchestrator list/profile tools, ECharts rendering, search quality improvements.

## Phase 4 — research on digigraph

Goal: research engine runs on the digithings stack.

- Define research outputs as Pydantic models (analyst → PM hand-off, asset allocations, narrative bias).
- Implement research subgraph in digigraph.
- Migrate research frontend to consume digigraph API; deploy at `digiquant.io/research`.
- DB persistence layer for research runs (digibase credential broker likely first real customer).

## Phase 5 — research tiering & execution

Goal: turn research into a product with free + paid tiers and a path from research → execution.

- **Free tier:** daily batch research per domain with analyst/PM agent deliberation; shared outputs.
- **Paid tier:** user-level investment preferences, prompts, domains, portfolio tracking.
- **research-embedded digichat** — in-product navigation + research Q&A.
- **Execution layer** — research biases feed digiquant strategy parameters; human gate before any live trade (non-negotiable).

## Phase 6 — platform roadmap

Longer-term component work that unblocks everything above:

- **digibase service:** Credential broker for Postgres/Redis/object storage per tenant; today digibase is primarily a shared library.
- **Remote MCP:** Enumeration and attachment of arbitrary third-party MCP servers from digigraph.
- **Kubernetes:** Production deployment profile beyond single-host Compose.
- **Managed hosting:** Host a customer's `digiproject.yaml` manifest as a paid service.

---

## Agent operations (this repo)

Task queue and conventions for coding agents: [docs/agent-backlog/README.md](docs/agent-backlog/README.md) and [docs/agent-backlog/INDEX.md](docs/agent-backlog/INDEX.md).

The **GitHub Project** is the live backlog; issues in this repo are the units of work; `docs/agent-backlog/` holds longer task specs when an issue body isn't enough.
