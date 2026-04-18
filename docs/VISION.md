# DigiThings Vision

**Last reviewed:** 2026-04-18
**Status:** living document — source of truth for product direction. Implementation detail belongs in `ARCHITECTURE.md`, component `DIGIxxx.md` files, and ADRs under `docs/adr/`.

## One-liner

DigiThings is an **open-core modular agentic stack** for conversational agents that research, search, analyze, and act — with a flagship vertical in **quantitative finance**. The same components power client solutions, internal products, and the open ecosystem.

## Why this exists

AI-solutions work today is either:
- **Too shallow** — thin wrappers over a single model, no retrieval, no execution, no audit.
- **Too bespoke** — every engagement rebuilds orchestration, search, auth, and deployment from scratch.

DigiThings is the middle path: a set of **composable, open-core components** (`digigraph`, `digisearch`, `digiquant`, `digichat`, `digikey`, `digiclaw`, `digismith`, `digibase`) that snap together into a running stack for any given client, product, or research project. Each engagement becomes a thin **configuration layer** over the shared platform — not a rewrite.

## Product surfaces

Two public domains, three product surfaces.

### `digithings.ai` — ecosystem home
- **Marketing site** (current `website/`) — landing, components, open-source story, case studies.
- **Embedded DigiChat** at `chat.digithings.ai` — user brings their own API key (or uses a metered tier), chats against an index of DigiThings documentation and high-level component READMEs. Acts as a **"discover the ecosystem"** guide: prospects can ask "I need X, which DigiThings components solve it?" and get grounded answers.

### `digiquant.io` — financial AI hub
- **DigiQuant product** — algorithmic strategy generation, backtesting, optimization, broker connections, deployment.
- **Atlas** at `digiquant.io/atlas` — high-level fundamental/research engine. Migrates to use **DigiGraph** as its AI orchestration backend (structured outputs, DB-persisted research). Future phases add:
  - **Execution layer** — Atlas research biases feed DigiQuant strategies.
  - **Tiering** — free tier: daily batch research across domains; paid tier: user-level preferences, prompts, portfolios, custom domains.
  - **Atlas-embedded DigiChat** — navigation + research Q&A inside the Atlas UI.

### Client and pilot projects
Stored under `projects/` (confidential — never pushed to public remotes). Each is a **DigiThings Project** (see ADR-0001): a thin config-driven composition of components.

Current and near-term:
- **SITAAS** — POC with external client, DigiGraph + DigiSearch over a unified content index (emails, Teams, SharePoint). First pilot; template for future engagements.

## Core concept: the DigiThings Project Spec

> **A DigiThings "project" is a declarative manifest (`config.yaml` + per-index YAMLs) plus a thin `docker-compose.yml` that composes published DigiThings component images.**

This is the generalization of the SITAAS pattern. It lets us:
- Spin up a new client engagement in hours, not weeks.
- Keep component code in the monorepo; keep project-specific config out-of-tree or under `projects/`.
- Version components independently from projects.
- Ship the same stack on a laptop, a single VM, or Kubernetes with no code change.

See **ADR-0001: DigiThings Project Spec** for the formal definition and **ADR-0002: Domain Unification** for how the public surfaces map onto the two domains.

## Composition map

```
                          ┌─────────────────────────┐
    digithings.ai ───────▶│  Marketing site         │
                          │  (website/, static)     │
                          └───────────┬─────────────┘
                                      │ link / embed
                          ┌───────────▼─────────────┐
                          │  DigiChat               │
                          │  (digichat/, Next.js)   │
                          └───────────┬─────────────┘
                                      │ BFF
                          ┌───────────▼─────────────┐
                          │  DigiGraph              │
                          │  (orchestration)        │
                          └─┬──────────┬────────────┘
                            │          │
              ┌─────────────▼─┐    ┌───▼───────────┐
              │  DigiSearch    │    │  DigiQuant    │
              │  (RAG/search) │    │  (Nautilus)   │
              └────────────────┘    └───────────────┘

    digiquant.io ────▶  DigiQuant product UI
         /atlas  ────▶  Atlas research engine ──▶ DigiGraph ──▶ DigiSearch
                                                           └─▶ DigiQuant (execution, future)

    projects/sitaas ──▶  DigiGraph + DigiSearch + LiteLLM (no DigiQuant)
    projects/<next> ──▶  any subset, via Project Spec
```

Cross-cutting:
- **DigiKey** — auth for every service-to-service and user-to-service call.
- **DigiSmith** — tracing/observability across all components.
- **DigiClaw** — heartbeat, audit, deployment gateway for 24/7 agent work.
- **DigiBase** — shared HTTP/audit library; future credential broker for multi-tenant deployments.

## Strategic posture

- **Open core.** Components MIT/Apache; client-specific configuration and deployment stay private under `projects/`.
- **Consultancy + product.** Revenue from (a) client engagements using the stack as the delivery vehicle, and (b) hosted products (DigiQuant, Atlas) that dogfood the stack.
- **Hedge-fund-in-a-box is the flagship** but not the only shape — RAG, document search, and general agent workflows share the same substrate.
- **Financial tier gets the highest bar.** Security ≥8, Accuracy ≥9, human gates before live trades — these are non-negotiable for DigiQuant/Atlas and raise the quality floor for everything else.

## What this document is not

- Not an implementation plan — see `ROADMAP.md`.
- Not an architecture reference — see `ARCHITECTURE.md` and each `DIGIxxx.md`.
- Not a backlog — see the GitHub Project and `docs/agent-backlog/`.

## Strategic decisions

**Last updated:** 2026-04-18.

### Atlas tiering — hybrid

- **Free tier:** daily batch research across shared domains, public outputs, no customization.
- **Paid seats:** flat monthly subscription unlocks user-level preferences, custom prompts, custom domains, portfolio tracking, Atlas-embedded DigiChat.
- **Metered API:** developer/programmatic access priced per research run or per token, for users who want to integrate Atlas output into their own systems.

Seat pricing and metered unit cost are TBD — will be nailed down when Phase 5 planning starts or when the first prospect asks.

### `chat.digithings.ai` launch — BYOK + small metered guest tier

- **Primary path:** bring-your-own-key. User pastes an OpenAI/Anthropic/etc. key, stored client-side only, never server-persisted. Verified by code review.
- **Guest tier:** a small metered pool behind the "Try it now" button on `digithings.ai`. Strict rate limits per IP/session (exact limits TBD). Funded as a marketing expense, not a revenue line.

The BYOK requirement from ADR-0002 stands: zero server-side persistence of user API keys. The metered guest pool uses a separate, DigiThings-owned key never exposed to the client.

### Open-source vs. managed — core open, some premium closed

- **Open core** (MIT/Apache): `digigraph`, `digisearch`, `digiquant` (backtest/optimize only), `digichat`, `digikey`, `digiclaw`, `digismith`, `digibase` (single-tenant library).
- **Closed / commercial:** Atlas execution layer (research → live orders), multi-tenant DigiBase credential broker, managed hosting of DigiThings Projects, any client-specific IP developed under `projects/`.
- **Consultancy** stays its own revenue line, independent of the open/closed split.

The exact boundary evolves. Guardrail: anything that's a meaningful moat for the commercial product (execution, multi-tenancy, hosting) can be closed; anything a user could reasonably want to self-host for their own agent work stays open.

### Incorporation — after 2–3 paying clients and some MRR

- Hold off on incorporation until there's demonstrated market demand — 2–3 paying clients and visible recurring revenue.
- SITAAS is the first pilot; its conversion to a paid engagement is the clock-start for this decision.
- Jurisdiction (Delaware C-corp vs Canadian Inc. vs other) is deferred until incorporation is the next action. When that time comes, choice will be driven by where the paying customers are and where investors (if any) want to see the entity.

## Open questions

- Atlas seat price point and metered unit cost (defer to Phase 5 planning).
- Guest-tier rate limits on `chat.digithings.ai` (defer to Phase 3b implementation).
- Exact list of "closed" components — only execution layer + multi-tenant DigiBase + hosting are committed today; others may migrate into the closed column as commercial value becomes clear.
