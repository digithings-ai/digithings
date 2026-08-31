# ADR-0026 — Retire olympus / atlas / hermes / kairos as product names

**Status:** Accepted
**Date:** 2026-08-30
**Amends:** [ADR-0014](0014-atlas-in-digiquant.md), [ADR-0015](0015-atlas-vs-hermes.md), [ADR-0019](0019-unified-atlas-workflow.md) (historical names stand in those texts; this ADR is the product-name source of truth going forward)

## Context

The operator dashboard and the three finance sub-graphs shipped under Greek proper nouns: **olympus** (the dashboard and Python umbrella), **atlas** (research), **hermes** (portfolio / deliberation), **kairos** (execution). Those names were a fourth brand beside digithings / digiquant / digichat, they collided with generic-mythology SEO, and they leaked into landing copy (`open olympus`, Atlas → Hermes → Kairos) while the dashboard nav was already functional (Brief, Portfolio, Pipeline, FX Hub).

A 2026-08-30 inventory ([docs/plans/2026-08-30-product-rebrand-scope.md](../plans/2026-08-30-product-rebrand-scope.md)) measured hundreds of files per name. Candidate replacements alphabox / autobox / aibox were evaluated; autobox and aibox are trademark collisions, and a second consumer brand is unnecessary when the site is already digiquant.io.

## Decision

1. **The product is digiquant.** There is no second dashboard brand. User-facing copy, titles, CTAs, and PWA names say digiquant. The mark (nested arcs) is the digiquant dashboard mark.
2. **Subsystems are jobs, not brands.** User-facing words are **research**, **portfolio**, and **execution**. Do not introduce replacement proper nouns for atlas / hermes / kairos.
3. **Internal phase IDs stay.** A0–A4 and H1–H9 remain graph coordinates.
4. **Do not rewrite history.** SQL migrations, historical ADR bodies, and `olympus_*` / `atlas_run_diagnostics` table names stay. Amend, do not edit-in-place.
5. **Rollout is layered.** Copy and chrome first. The public path `/olympus/` and OAuth callbacks stay until vendor consoles (GitHub, Supabase, Alpaca, Cloudflare Access) can move together. Python packages `digiquant.olympus.{atlas,hermes,kairos}` and env `OLYMPUS_*` stay until a dedicated two-hop `module/digiquant` PR. The kairos **package** rename is human-gated (execution path).

## Consequences

**Positive:** One product name on digiquant.io; landing and dashboard say the same thing; agent docs stop teaching four Greek names as the architecture.

**Negative / tradeoffs:** `/olympus/` remains in the address bar and in OAuth redirect URLs until wave 2. Python packages `digiquant.olympus.atlas` and env `OLYMPUS_*` stay until a two-hop `module/digiquant` PR. CSS (`.oly-*`, `.olympus-mark`) and the `frontend/olympus` folder stay until a `feat/` or `task/<N>-slug` branch can edit `.github/workflows`. TypeScript identifiers (`DigiquantMark`, `PerformanceTearsheetView`, `DashboardMark`) move in wave 3 with one-release aliases. Historical issues and ADRs still say the old names.

## Links

- Scope: [docs/plans/2026-08-30-product-rebrand-scope.md](../plans/2026-08-30-product-rebrand-scope.md)
- Copy: [frontend/digiweb/design/COPY_GUIDE.md](../../frontend/digiweb/design/COPY_GUIDE.md)
- Supersedes product-name claims in ADR-0014 / 0015 / 0019 without rewriting those files
