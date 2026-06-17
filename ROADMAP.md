# DigiThings Roadmap

**Last reviewed:** 2026-04-18

High-level phases. Vision and strategy: [docs/VISION.md](docs/VISION.md). Architecture: [ARCHITECTURE.md](ARCHITECTURE.md). Shipping history: [RELEASES.md](RELEASES.md). Per-component depth: each folder's `DIGIxxx.md`. Open work: [GitHub Project](https://github.com/users/chrizefan/projects) and [docs/agent-backlog/](docs/agent-backlog/).

---

## Phase 1 — shipped core ✅

Component foundations in place:

- **Orchestration:** DigiGraph LangGraph workflows (supervisor + subgraphs), DigiKey JWT for protected HTTP, vertical dispatch via `/v1/orchestrator_tools` and `/v1/orchestrator_invoke`.
- **Verticals:** DigiSearch (RAG, ingest, search backends), DigiQuant (NautilusTrader backtest/optimize, Polars-only).
- **Platform:** Docker Compose core stack, LiteLLM proxy, DigiSmith health/`/v1/status`, optional DigiChat (Postgres + Next.js BFF).
- **MCP:** DigiGraph, DigiQuant, DigiSearch MCP servers for IDE and external clients.
- **First pilot:** SITAAS (projects/sitaas/) running DigiGraph + DigiSearch against an Azure AI Search unified-content index.

## Phase 2 — hardening + project spec (in progress)

Goal: make the ecosystem **production-credible** and **project-composable**.

- **Hardening pass (cold review)** — security audit, dead-code removal, type-checking, test coverage gaps, dependency bump. Informed by `docs/CODE_REVIEW_BASELINE.md` and `docs/IMPROVEMENT_PLAN.md`.
- **DigiThings Project Spec v1alpha1** — formalize SITAAS pattern (see [ADR-0001](docs/adr/0001-project-spec.md)): `digiproject.yaml` + `docker-compose.yml` + `.env.example` as the unit of a client engagement. Refactor SITAAS to the formal spec; ship `projects/template/` starter.
- **Observability:** Prometheus-friendly metrics, centralized dashboards; DigiSearch audit sink alignment.
- **DigiGraph:** Auth-bound checkpoints, per-key RBAC, optional `X-Digi-Tenant` routing.
- **DigiKey:** Production revocation via Redis `jti` blocklist (`DIGIKEY_BLOCKLIST_REDIS_URL`); multi-tenant RBAC remains Phase 2+.
- **DigiClaw:** MCP attachment to DigiGraph and richer gateway skills.
- **Rate limiting / cache:** Redis-backed distributed limits where today is in-process.

## Phase 3 — domain unification & ecosystem surface

Goal: a prospect landing on digithings.ai can **try the stack** in one click, and the finance product has its own home.

See [ADR-0002: Domain Unification](docs/adr/0002-domain-unification.md) for the full migration plan.

- **Phase 3a** — consolidate current frontends under `digithings.ai` + `chat.digithings.ai`. Add "Chat with DigiThings" CTA.
- **Phase 3b** — DigiChat as ecosystem guide. Build DigiSearch index over DigiThings docs; wire to DigiGraph; add bring-your-own-key flow in `chat.digithings.ai`.
- **Phase 3c** — stand up `digiquant.io` domain, minimal DigiQuant product UI.
- **SITAAS Phase 2** — deliver POC improvements (see `projects/sitaas/IMPROVEMENT_IDEAS.md`): surface stored_datasets to LLM, orchestrator list/profile tools, ECharts rendering, search quality improvements.

## Phase 4 — Atlas on DigiGraph

Goal: Atlas research engine runs on the DigiThings stack.

- Define Atlas research outputs as Pydantic models (analyst → PM hand-off, asset allocations, narrative bias).
- Implement Atlas research subgraph in DigiGraph.
- Migrate Atlas frontend to consume DigiGraph API; deploy at `digiquant.io/atlas`.
- DB persistence layer for research runs (DigiBase credential broker likely first real customer).

## Phase 5 — Atlas tiering & execution

Goal: turn Atlas into a product with free + paid tiers and a path from research → execution.

- **Free tier:** daily batch research per domain with analyst/PM agent deliberation; shared outputs.
- **Paid tier:** user-level investment preferences, prompts, domains, portfolio tracking.
- **Atlas-embedded DigiChat** — in-product navigation + research Q&A.
- **Execution layer** — Atlas research biases feed DigiQuant strategy parameters; human gate before any live trade (non-negotiable).

## Phase 6 — platform roadmap

Longer-term component work that unblocks everything above:

- **DigiBase service:** Credential broker for Postgres/Redis/object storage per tenant; today DigiBase is primarily a shared library.
- **Remote MCP:** Enumeration and attachment of arbitrary third-party MCP servers from DigiGraph.
- **Kubernetes:** Production deployment profile beyond single-host Compose.
- **Managed hosting:** Host a customer's `digiproject.yaml` manifest as a paid service.

---

## Agent operations (this repo)

Task queue and conventions for coding agents: [docs/agent-backlog/README.md](docs/agent-backlog/README.md) and [docs/agent-backlog/INDEX.md](docs/agent-backlog/INDEX.md).

The **GitHub Project** is the live backlog; issues in this repo are the units of work; `docs/agent-backlog/` holds longer task specs when an issue body isn't enough.
