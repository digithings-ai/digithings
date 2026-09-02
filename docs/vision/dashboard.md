---
title: digiquant dashboard
type: module
status: reviewed
created: 2026-06-15
tags:
  - support
  - dashboard
  - quant
---
# digiquant dashboard
> The human-facing operator surface for digiquant — research, portfolio deliberation, and execution in one place.

This page used to be titled dashboard. Product names are now digiquant plus job words (research / portfolio / execution). See [ADR-0026](../adr/0026-retire-dashboard-research-portfolio-execution.md) and [the rebrand scope](../plans/2026-08-30-product-rebrand-scope.md). The dashboard lives at `digiquant.io/dashboard/` (`frontend/dashboard`).

## What it is

The dashboard frontend (`frontend/dashboard`) for the finance sub-graphs that live inside digiquant as `digiquant.dashboard`. It turns pipeline output into a navigable, daily decision surface rather than raw research dumps: a "Morning Read" overview, surfaced bull/bear theses and risk debate, portfolio/NAV tracking, and entry points into strategy work.

Where digichat is the general-purpose chat UI, this is the purpose-built operator view for quantitative finance — the place a researcher starts their day and where deliberations are published for human review.

## The problem it solves

Autonomous research and portfolio deliberation generate a firehose of structured output. Without a deliberate surface, that output is unreadable and untrustworthy — there's no way to see *why* an allocation is proposed or to gate it behind human judgment. The dashboard presents reasoning, not just conclusions, and it is where the human approval gate before any execution actually happens.

## How it fits in the ecosystem

It reads from the `digiquant.dashboard` sub-graphs (research, portfolio, execution), which orchestrate through digigraph and persist their state and outputs. It is served under `digiquant.io` and sits behind an access gate (it is not anonymously reachable). The research vs portfolio boundary is defined in ADR-0015; the research package's move into `digiquant` is ADR-0014. Product names in those ADRs are historical (ADR-0026).

The three jobs it surfaces:
- **Research** — fundamental/research engine; daily batch research, structured and persisted. Package path: `digiquant.research`.
- **Portfolio** — deliberation (bull/bear theses, risk debate) with a human approval gate before any allocation change. Package path: `digiquant.portfolio`.
- **Execution** — order-intent routing and broker mirroring. Package path: `digiquant.execution`. Live venue cutover stays human-gated.

## Capabilities — Current

Shipped and in active use:

- "Morning Read" overview that frames the day as a decision document
- Deliberation surfaces — bull/bear theses, risk debate, rationale
- Paper portfolio / NAV tracking for pipeline-owned positions
- Access-gated entry (anonymous diagnostics access removed)
- Navigation across research, portfolio, and execution work

## Capabilities — 12-month roadmap

- Embedded digichat for navigation + research Q&A inside the dashboard
- Tiered views — free batch research vs. paid user-level preferences, prompts, portfolios, and custom domains
- Human-in-the-loop execution controls as the research → live-order path matures
- Deeper drill-down from a thesis to the underlying research and source documents

## Open source vs. proprietary

**Open (MIT/Apache):** generic dashboard scaffolding and any reusable visualization components.

**Proprietary (commercial):** the dashboard as the product surface for the closed finance sub-graphs. Because it renders domain output and is the locus of the human-gated execution path, it ships as part of the commercial digiquant offering, not the open core.
