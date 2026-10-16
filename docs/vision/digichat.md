---
title: digichat
type: module
status: reviewed
created: 2026-04-19
updated: 2026-10-11
tags:
  - core
  - chat
---
# digichat

> Stand up digichat for any company in ~5 minutes — through a setup-agent chat.

## Locked product (2026-10-01)

Last locked 2026-10-01. This is the product, not a backlog sketch.

digichat is **not** only personal chat-form customization.

**Goal:** a **demo kit**. Stand up digichat for any company in ~5 minutes via a **setup-agent chat**. The entire plan and deploy happens through back-and-forth chat:

1. User gives a public company website
2. Agent scrapes that site and related public domains
3. Builds a knowledge base
4. Deploys a [[digisearch]] + [[digivault]] index
5. Creates the chat
6. Probes prefs: web search, compact view, theme (look like the site / ChatGPT / Claude / digichat defaults)
7. Emits config
8. Deploys a client demo container on Cloudflare

**Backend:** efficient **multi-tenant demos** — many concurrent trials, with survival of about two weeks to 30 days.

## Sequencing (constraints)

These are hard sequencing constraints, not a roadmap:

- After the three UI craft lanes (home / dashboard / digiquant-web) are inspected and unified.
- Does **not** jump ahead of GitHub issue/PR [#4761](https://github.com/digithings-ai/digithings/issues/4761) Phase 3 house-run.
- The parked digichat workbench on `module/digichat` ([#4692](https://github.com/digithings-ai/digithings/pull/4692)) until UI review **still stands**.

## Runtime: BYOK, adaptive UI, deployments

> The conversational interface for every digithings deployment — your models, your keys, your data.

**What it is:** digichat is the client-facing chat interface that powers every digithings deployment. It is a Next.js application with a backend-for-frontend layer that connects to digigraph for agent orchestration. Two runtime principles still hold: (1) bring your own keys — users supply their own LLM provider API keys and pay their own compute costs; (2) adaptive UI — the interface surfaces only what the user has access to based on their digikey permission scope. Those are how the client behaves. They are not the product lock above.

**The problem:** Most AI chat interfaces are locked to one model provider and one use case. Switching providers means switching platforms. Adding new data sources or tools means custom integration work. digichat inverts this — the orchestration and tooling are digithings, the compute and data are the user's own.

**BYOK model selector — core feature:**
A settings panel where users configure their LLM backend: API key input, provider selection (OpenAI, Anthropic, Gemini, Ollama, and others), optional OAuth login for providers that require it. Keys persist in the digichat Drizzle/Postgres store today, and migrate to digistore once that module ships. LiteLLM translates any provider into one standardized API language — translation only, not routing intelligence. The user pays their provider directly. digithings provides the orchestration, tooling, and graph layer.

**Adaptive UI driven by digikey JWT scopes:**
digichat reads the user's JWT on login and shows only what they're authorized to use. If a scope is absent, the feature doesn't appear — not locked, not visible.

Examples:
- digiquant:read → digiquant tools available as chat connections
- index:research → Research library digisearch index available
- subgraph:research → research sub-graph accessible (scope id unchanged until the path wave)
- tier:free → 3 questions, public index only, no proprietary sub-graphs

**Two live deployments:**

digithings.ai — platform demo (the flagship public digichat):
digithings' own architecture docs are published into a [[digivault]] vault hosted in the core Supabase (the `architecture_notes` table, synced from `docs/vision/`), and answers are grounded in the real docs, never web search. Grounding runs through digigraph to the vault hub, not through a digichat-owned query. The model path is digichat → digigraph → digillm (LiteLLM) in the stack Container; the digichat Container declares no OpenRouter credential and enables digigraph only (`DIGICHAT_ENABLED_SERVICES = "digigraph"`), so it is not an OpenRouter free-pool path. The BFF applies a per-IP throttle (`checkEmbedIpRateLimit`, `checkBffRateLimit`). The bot introduces itself and can explain its own architecture. Bring-your-own-key — paste a provider key for stronger models, forwarded per-request and never stored — is live, not planned. Sample questions guide exploration ("What does digigraph orchestrate?"). Goal: let any visitor experience the digithings stack directly.

**Route map (verified 2026-10-11 against `digithings.ai`):**

| Path | Serves |
| --- | --- |
| `/chat`, `/chat/*` | Cloudflare Pages marketing shell; embeds `/embed?host=…` in an iframe (`digichat-frame`) |
| `/embed*`, `/_dtchat*` | digichat Container, via the digichat Worker's zone routes |
| `/api/chat*`, `/api/byok*`, `/api/plan-proof*`, `/api/embed*` | digichat BFF in the same Container |
| `/api/health` | digichat health: reports `version` equal to `apps/digichat/package.json` and `digraph: ok` |

`POST /api/chat` without a credential answers `401` from digichat's own `requireDigiChatAuth`, which names the digichat machine-key prefix — not the retired Pages Function, which answers `410`. The Worker's own unrouted-path reply is `digichat Worker: path not routed. Marketing /chat shells are on Pages.`

digiquant.io — investment profiling:
Entry flow powered by a proprietary investment profiling sub-graph. User inputs investment preferences → digichat builds and saves an investment profile to digistore (user acquisition + personalization). Shows what strategies and allocations could be constructed for their profile. Paywall trigger: "Ready to build your first strategy? Start with execution." Free taste → paid conversion.

**Enterprise deployments (client pattern):**
A client organization deploys digichat pointed at their own digisearch index. Users log in via their corporate SSO (Microsoft, Google) — digikey identifies them, maps them to their organization's project, and issues a JWT with the appropriate index and tool scopes. The UI adapts: only their organization's indexes and approved tools appear. Index results are filtered by user access level.

**Current state (shipped):**
Next.js BFF + React UI, Auth.js sessions, Drizzle ORM, AI SDK, Postgres for conversation history, BYOK UI flow live — and `apps/digichat` is deployed publicly. The digichat Worker owns the `digithings.ai` zone routes listed above and proxies them to the digichat Cloudflare Container (`DigiChatContainer`); the Pages site serves the `/chat` shell per [ADR-0018](../adr/0018-digichat-path-routing.md). The bespoke widget this section used to describe is retired: `apps/digithings-web/functions/api/chat.ts` is now a `410` stub. Epic [#1248](https://github.com/digithings-ai/digithings/issues/1248) is closed (2026-07-06) and ADR-0018 was amended 2026-08-10 for the Container move.

**12-month roadmap:**
Does not override the locked product or the sequencing constraints above.

- Model selector settings panel (full provider list, BYOK per provider)
- Investment profiling sub-graph (digiquant.io entry flow)
- Microsoft SSO and Google OIDC login via digikey
- Adaptive UI: scope-driven connection visibility
- ~~digithings.ai demo instance (docs indexed, 3-question free tier)~~ — shipped; see Current state
- User conversation history and session management
- Strategy exploration interface

**Open source vs. proprietary:** digichat application — open. Proprietary sub-graphs that power specific chat flows (investment profiling, research interface) — commercial.
