# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

digiweb is the shared design suite behind two customer-facing domains, both co-primary:

- **digithings.ai visitors** — evaluating the open-core agentic stack (quant finance, RAG, chat) as a platform hub.
- **digiquant.io visitors** — evaluating the quant product (research, portfolio, execution) as an investment-research/profiling demo.

Both audiences are in a persuade/explore posture — deciding whether to try or adopt, not operating an already-installed tool.

## Product Purpose

digiweb is not itself a product surface — it is the single central design suite (tokens, components, reference app, motion/livery rules) that every digithings.ai and digiquant.io page is assembled from, so both domains read as one coherent system instead of drifting into one-off UI per surface. Success is consistency: any new page reuses an existing pattern from the reference or adds one there first.

## Positioning

digithings' core, truthful differentiator: an **open-core, self-hostable stack** aimed at the small/personal segment, not institutional buyers. Every default is free/self-hostable (HuggingFace models over paid APIs, pgvector over managed cloud DBs); the project acts as a curator/filter over best-of-breed pieces behind clean abstractions rather than absorbing and locking users into a monolith. A competing product built on paid-API defaults or a closed, vendor-locked stack could not truthfully make the same claim.

## Operating Context

- Two live frontend deployments consume digiweb's packages by name: `@digithings/design` (tokens) and `@digithings/web` (shared React components) — not by on-disk path, so digiweb can move without breaking consumers.
- The reference app (`reference/`) is the live, browsable canon at `http://127.0.0.1:4013` — the first place to check before building any new pattern.
- `MANIFEST.json` is a machine-readable index of every reusable component (name, path, family, purpose) that agents are expected to consult before adding new UI.
- **Consuming surfaces with their own PRODUCT.md-eligible context** (recorded here as durable facts only; visual specifics stay out of PRODUCT.md per init's own rule):
  - **dashboard** (`frontend/olympus/`) — the digiquant operator surface (task completion, not persuasion): research pipeline runs, portfolio/tearsheet views, performance monitoring. Its patterns live in the reference under `/finance` (dashboard workspace, tearsheet, performance metrics, order book) and `/layout-patterns` (the dashboard app's phone mockup frame) and `/effects` (the pipeline workflow viz).
  - **digichat** (`frontend/digichat/`, `frontend/digichat-ui/`) — the chat UI, presented as a terminal-style CLI chatbot: monospace scrollback, `>` prompt, thinking chain, collapsible tool-call chain, inline charts/route graphs, custom action widgets embedded in the terminal. Its pattern lives in the reference under `/chatbot` (and shares grammar with the diegetic `/terminal` family). Persuade-adjacent on marketing surfaces, Operate-mode once a user is actually chatting.

## Capabilities and Constraints

- **Tokens, never literals** — all colour comes from `@digithings/design/tokens.css`; no ad-hoc hex/rgb in surface code.
- **Monochrome is the default livery** — colour is opt-in per product, not a baseline choice.
- **Money colours** (`--up` / `--down`) are P&L-only and never follow a livery override.
- **One motion moment per surface** — motion is deliberate and singular, always honoring `prefers-reduced-motion`.
- **Token-backed Tailwind utilities + semantic classes** are preferred over ad-hoc CSS values, so spacing/colour stay consistent across both domains.
- Digi product/module names are always lowercase in prose and UI copy (e.g. digithings, digiquant, digichat) — see the repo's `CLAUDE.md` naming table; this is a hard constraint on any UI copy digiweb work touches.
- `frontend/digiweb/design/` and `**.css` are exempt from the repo's Python-oriented `make score` gate — design work here is meant to iterate live via preview servers, not against that rubric.

## Brand Commitments

- No Digi module name is ever rendered in CamelCase or with internal spacing in prose/UI copy (DigiChat, Digi Things, etc. are all wrong) — see `CLAUDE.md`'s naming table for the canonical list.
- No naming-philosophy commitments beyond the "digi + lowercase rest" rule are binding at the digiweb-suite level; job words (research, portfolio, execution) are decided per product, not per surface.

## Evidence on Hand

- `reference/README.md` — canonical page map, two-voice type system, livery model, motion laws, chart house-rules.
- `ARCHITECTURE.md`, `MIGRATION.md`, `CHARTS.md` — structural/deploy history for the suite.
- No testimonials, benchmarks, case studies, or pricing claims exist for digiweb itself; none should be fabricated. (Product-level testimonials, if any, belong to digithings.ai/digiquant.io content, not this suite.)

## Product Principles

1. One system, two domains — every surface on digithings.ai and digiquant.io draws from the same tokens, components, and motion laws; divergence is the failure mode to design against.
2. Reuse before invention — the reference app is checked and extended before any one-off component is built in a consuming app.
3. Free and self-hostable by default — visual and technical choices favor the small/personal target market, not institutional assumptions.
4. Restraint as the baseline — monochrome-default livery and single-motion-moment rules mean boldness is opt-in per surface, not the default state.
