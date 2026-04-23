# ADR 0002: Domain Unification — digithings.ai + digiquant.io

**Status:** proposed
**Date:** 2026-04-18

## Context

DigiThings currently has three disconnected public surfaces:

1. **`website/`** — static landing at digithings.ai (vanilla HTML/CSS/JS, canvas starfield).
2. **`digichat/`** — production Next.js chat app; a separate Vite POC was recently removed. Nav link from the static site points at `chat.digithings.ai` but there is no canonical deployment target documented.
3. **Atlas** — research engine frontend (outside this repo at time of writing), currently standalone.

There is no clear story for a prospect arriving at digithings.ai: they land on marketing copy, but cannot *try* anything, cannot *explore* the ecosystem conversationally, and cannot easily find their way to the financial-AI product surface.

Simultaneously, the financial-AI product line (DigiQuant + Atlas) deserves its own brand identity separate from the open-core ecosystem — different audience (quant funds, prop traders), different trust bar, different pricing.

## Decision

**Two domains, three product surfaces, clear routing.**

### `digithings.ai` — ecosystem home (open-core oriented)

- **`digithings.ai`** — marketing site (current `website/`). Landing, components, open-source story, case studies, link into DigiChat.
- **`chat.digithings.ai`** — production DigiChat (current `digichat/`). Two user paths:
  - **"Bring your own key"** — user enters an OpenAI/Anthropic/etc. key, chats with DigiGraph over an index of DigiThings docs + high-level READMEs. This is the ecosystem discovery guide.
  - **Metered guest tier** (future) — we front a pool for anonymous prospects with strict rate limits.
- **`docs.digithings.ai`** (future) — published component documentation.

### `digiquant.io` — financial AI hub (commercial)

- **`digiquant.io`** — DigiQuant product marketing and login.
- **`digiquant.io/atlas`** — Atlas research engine. Migrates to use DigiGraph as its AI backend (structured Pydantic outputs, DB-persisted research).
- **`digiquant.io/atlas` (Phase 2)** — embedded DigiChat for in-product navigation and research Q&A.
- Future tiered access: free (daily batch research), paid (user prefs, custom domains, execution layer).

### Cross-domain

- Single-sign-on via **DigiKey** (JWT issuer) so a `digithings.ai` account works on `digiquant.io` when appropriate.
- Shared component releases: both domains deploy the same component images, differently composed.

## Consequences

**Positive**
- Clear audience split: `digithings.ai` for developers / open-core / consultancy leads; `digiquant.io` for finance buyers.
- Prospects on digithings.ai can immediately *use* the stack (DigiChat as discovery tool) — major conversion lever.
- Atlas gets a home that matches its audience (quant finance) rather than being buried under a generic ecosystem site.
- Subdomain split (`chat.`, `docs.`) keeps the marketing site cacheable/static while the app surfaces run on separate infra.

**Negative / tradeoffs**
- Two domains to maintain, two DNS configs, two TLS setups, two analytics properties.
- SSO adds moving parts to DigiKey (currently single-issuer → multi-audience).
- Atlas migration from current backend to DigiGraph is a non-trivial project on its own — this ADR commits to the *destination*, not the migration scope.
- The "bring-your-own-key" model for `chat.digithings.ai` requires careful handling of user secrets; simplest path is client-side-only storage, never server-persisted.

## Alternatives considered

1. **Single domain (digithings.ai) for everything, with `/quant` and `/atlas` paths.** Cheaper infra. Rejected because the finance audience expects a dedicated brand, and mixing open-source positioning with a commercial finance product dilutes both.
2. **Separate domain for every component.** Nine domains, nine sites. Clearly over-engineered for current scale.
3. **Keep Atlas on its current infra.** Short-term simpler but locks in duplicate orchestration logic; defeats the point of having DigiGraph.

## Migration plan

**Phase A — consolidate what exists (weeks, not months)**
- Confirm DNS + Pages routing: `digithings.ai` → `website/`, `chat.digithings.ai` → `digichat/` production build.
- Retire any remaining duplicate frontends (Vite DigiChat was already removed per recent commits).
- Add a "Chat with DigiThings" CTA on `digithings.ai` → `chat.digithings.ai`.

**Phase B — DigiChat as ecosystem guide**
- Build a DigiSearch index over component `ARCHITECTURE.md` + `DIGIxxx.md` + root `README`/`VISION`/`ROADMAP`.
- Wire DigiChat to a DigiGraph deployment configured with that index.
- Add BYOK flow (user-entered API key, stored client-side only).

**Phase C — `digiquant.io` stand-up**
- Register domain, set up landing.
- Port current DigiQuant UI (if any) or build minimal one.
- Decide Atlas migration timeline (separate ADR when ready).

**Phase D — Atlas on DigiGraph**
- Define Atlas research outputs as Pydantic models.
- Implement DigiGraph subgraph for the Atlas research flow.
- Migrate Atlas frontend to consume DigiGraph API.
- Mount at `digiquant.io/atlas`.

Each phase is a roadmap milestone (see `ROADMAP.md`) and will break into GitHub issues on the Project board.

## Links

- Related: ADR-0001 (Project Spec)
- Related: `docs/VISION.md`
- Current static site: `frontend/digithings/`
- Current chat app: `frontend/digichat/`

## Amendment (2026-04-19)

The *domain* plan in this ADR stands, but the *repository* layout it
implied has been revised by [ADR-0009 — Frontend umbrella](0009-frontend-umbrella.md).
Specifically, this ADR's language suggested `digichat/` would live in
its own deployment repo (matching the historical
`.gitignore` exclusion and the stale `ci.yml` comment). That is
superseded. All three web surfaces — `digithings.ai`, `digiquant.io`, and
`chat.digithings.ai` — now ship from this monorepo under
`frontend/{website,digiquant-web,digichat}`, with a shared
`@digithings/design` workspace package.
