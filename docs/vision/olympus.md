---
title: Olympus
type: module
status: reviewed
created: 2026-06-15
tags:
  - support
  - dashboard
  - quant
---
# Olympus
> The human-facing dashboard for DigiQuant's finance sub-graphs — Atlas research, Hermes deliberation, and Kairos strategy work in one surface.

## What it is

Olympus is the dashboard frontend (`frontend/olympus`) for the finance sub-graph trio that lives inside DigiQuant as `digiquant.olympus`. It turns the outputs of Atlas, Hermes, and Kairos into a navigable, daily decision surface rather than raw research dumps: a "Morning Read" overview, surfaced bull/bear theses and risk debate, portfolio/NAV tracking, and entry points into interactive strategy work.

Where DigiChat is the general-purpose chat UI, Olympus is the purpose-built operator view for quantitative finance — the place a researcher starts their day and where Hermes's deliberations are published for human review.

## The problem it solves

Autonomous research and portfolio deliberation generate a firehose of structured output. Without a deliberate surface, that output is unreadable and untrustworthy — there's no way to see *why* an allocation is proposed or to gate it behind human judgment. Olympus gives the sub-graph trio a face: it presents reasoning, not just conclusions, and it is where the human approval gate before any execution actually happens.

## How it fits in the ecosystem

Olympus reads from the three `digiquant.olympus` sub-graphs (Atlas, Hermes, Kairos), which themselves orchestrate through DigiGraph and persist their state and outputs. It is served under `digiquant.io` and sits behind an access gate (it is not anonymously reachable). The boundary between Atlas (research) and Hermes (portfolio deliberation) is defined in ADR-0015; Atlas's move into `digiquant` is ADR-0014.

The three sub-graphs it surfaces:
- **Atlas** — fundamental/research engine; daily batch research, structured and persisted.
- **Hermes** — portfolio deliberation (bull/bear theses, risk debate) with a human approval gate before any allocation change.
- **Kairos** — chat-based strategy development; the quant researcher's interactive workbench.

## Capabilities — Current

Shipped and in active use:

- "Morning Read" overview that frames the day as a decision document
- Hermes deliberation surfaces — bull/bear theses, risk debate, rationale
- Paper portfolio / NAV tracking for pipeline-owned positions
- Access-gated entry (anonymous diagnostics access removed)
- Navigation across Atlas research, Hermes deliberations, and Kairos strategy work

## Capabilities — 12-month roadmap

- Embedded DigiChat for navigation + research Q&A inside the Olympus UI
- Tiered views — free batch research vs. paid user-level preferences, prompts, portfolios, and custom domains
- Human-in-the-loop execution controls as the research → live-order path matures
- Deeper drill-down from a thesis to the underlying research and source documents

## Open source vs. proprietary

**Open (MIT/Apache):** generic dashboard scaffolding and any reusable visualization components.

**Proprietary (commercial):** Olympus as the product surface for the closed finance sub-graphs. Because it renders Atlas/Hermes/Kairos domain output and is the locus of the human-gated execution path, the dashboard ships as part of the commercial DigiQuant offering, not the open core.
