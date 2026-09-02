---
title: digichat
type: module
status: reviewed
created: 2026-04-19
tags:
  - core
  - chat
---
# digichat

> The conversational interface for every digithings deployment — your models, your keys, your data.

**What it is:** digichat is the client-facing chat interface that powers every digithings deployment. It is a Next.js application with a backend-for-frontend layer that connects to digigraph for agent orchestration. Two core principles define it: (1) bring your own keys — users supply their own LLM provider API keys and pay their own compute costs; (2) adaptive UI — the interface surfaces only what the user has access to based on their digikey permission scope.

**The problem:** Most AI chat interfaces are locked to one model provider and one use case. Switching providers means switching platforms. Adding new data sources or tools means custom integration work. digichat inverts this — the orchestration and tooling are digithings, the compute and data are the user's own.

**BYOK model selector — core feature:**
A settings panel where users configure their LLM backend: API key input, provider selection (OpenAI, Anthropic, Gemini, Ollama, and others), optional OAuth login for providers that require it. Keys persist in the digichat Drizzle/Postgres store today, and migrate to digistore once that module ships. LiteLLM translates any provider into one standardized API language — translation only, not routing intelligence. The user pays their provider directly. digithings provides the orchestration, tooling, and graph layer.

**Adaptive UI driven by digikey JWT scopes:**
digichat reads the user's JWT on login and shows only what they're authorized to use. If a scope is absent, the feature doesn't appear — not locked, not visible.

Examples:
- digiquant:read → digiquant tools available as chat connections
- index:research → Research library digisearch index available
- subgraph:atlas → research sub-graph accessible (scope id unchanged until the path wave)
- tier:free → 3 questions, public index only, no proprietary sub-graphs

**Two live deployments:**

digithings.ai — platform demo (the flagship public digichat):
digithings' own architecture docs are published into a [[digivault]] vault hosted in the core Supabase (the `architecture_notes` table, synced from `docs/vision/`), and digichat retrieves from it with full-text search on every turn — answers are grounded in the real docs, never web search. It runs on OpenRouter's free model pool, so visitors can use it with no sign-up; a lightweight per-IP throttle only deters bot floods (the free pool's own account-wide daily quota still applies — a one-time small credit purchase lifts it ~20x). Served at the edge by a Cloudflare Pages Function (`/api/chat`) using the anon, RLS-gated read key, so no secrets ever reach the browser. The bot introduces itself and can explain its own architecture. Bring-your-own-key — paste a provider key for stronger models, forwarded per-request and never stored — is the planned next step. Sample questions guide exploration ("What does digigraph orchestrate?"). Goal: let any visitor experience the digithings stack directly.

digiquant.io — investment profiling:
Entry flow powered by a proprietary investment profiling sub-graph. User inputs investment preferences → digichat builds and saves an investment profile to digistore (user acquisition + personalization). Shows what strategies and allocations could be constructed for their profile. Paywall trigger: "Ready to build your first strategy? Start with execution." Free taste → paid conversion.

**Enterprise deployments (client pattern):**
A client organization deploys digichat pointed at their own digisearch index. Users log in via their corporate SSO (Microsoft, Google) — digikey identifies them, maps them to their organization's project, and issues a JWT with the appropriate index and tool scopes. The UI adapts: only their organization's indexes and approved tools appear. Index results are filtered by user access level.

**Current state (shipped):**
Next.js BFF + React UI, Auth.js sessions, Drizzle ORM, AI SDK, Postgres for conversation history, BYOK UI flow live — `frontend/digichat` itself is not deployed publicly today. The digithings.ai instance described above still runs a separate bespoke widget (direct OpenRouter calls, its own Supabase vault search) rather than this app; cutting it over to run as the real digichat gateway at `digithings.ai/chat` per [ADR-0018](../adr/0018-digichat-path-routing.md) is tracked in epic [#1248](https://github.com/digithings-ai/digithings/issues/1248).

**12-month roadmap:**
- Model selector settings panel (full provider list, BYOK per provider)
- Investment profiling sub-graph (digiquant.io entry flow)
- Microsoft SSO and Google OIDC login via digikey
- Adaptive UI: scope-driven connection visibility
- digithings.ai demo instance (docs indexed, 3-question free tier)
- User conversation history and session management
- Strategy exploration interface

**Open source vs. proprietary:** digichat application — open. Proprietary sub-graphs that power specific chat flows (investment profiling, research interface) — commercial.
