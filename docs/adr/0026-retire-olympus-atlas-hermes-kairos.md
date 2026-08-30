# ADR-0026 — Retire olympus / atlas / hermes / kairos as product names

**Status:** Accepted
**Date:** 2026-08-30
**Amends:** [ADR-0014](0014-atlas-in-digiquant.md), [ADR-0015](0015-atlas-vs-hermes.md), [ADR-0019](0019-unified-atlas-workflow.md) (historical names stand in those texts; this ADR is the product-name source of truth going forward)

## Context

The operator dashboard and the three finance sub-graphs shipped under Greek proper nouns: **olympus** (the dashboard and Python umbrella), **atlas** (research), **hermes** (portfolio / deliberation), **kairos** (execution). Those names were a fourth brand beside digithings / digiquant / digichat, they collided with generic-mythology SEO, and they leaked into landing copy (`open olympus`, Atlas → Hermes → Kairos) while the dashboard nav was already functional (Brief, Portfolio, Pipeline, FX Hub).

A 2026-08-30 inventory ([docs/plans/2026-08-30-product-rebrand-scope.md](../plans/2026-08-30-product-rebrand-scope.md)) measured hundreds of files per name. Candidate replacements alphabox / autobox / aibox were evaluated; autobox and aibox are trademark collisions, and a second consumer brand is unnecessary when the site is already digiquant.io.

## Decision

1. **The product is digiquant.** There is no second dashboard brand. The mark is the dashboard mark. On digiquant.io the operator surface is the **dashboard**: compact nav is the teal mark alone (`aria-label` names the destination), full CTAs say `open dashboard` — not a repeat of the site name. PWA / document titles stay digiquant.
2. **Subsystems are jobs, not brands.** User-facing words are **research**, **portfolio**, and **execution**. Do not introduce replacement proper nouns for atlas / hermes / kairos.
3. **Internal phase IDs stay.** A0–A4 and H1–H9 remain graph coordinates.
4. **Do not rewrite history.** SQL migrations, historical ADR bodies, and `olympus_*` / `atlas_run_diagnostics` table names stay. Amend, do not edit-in-place.
5. **Rollout is layered.** The dashboard is served at `/dashboard/` only. `/olympus/` is retired — no Cloudflare 308, no twin export. Vendor consoles list dashboard callback URLs only. Python packages `digiquant.olympus.{atlas,hermes,kairos}` stay until a dedicated two-hop `module/digiquant` PR. Operator secrets and flags use `DIGIQUANT_*` (retired `OLYMPUS_*` / `KAIROS_*` / `ATLAS_*` names remain readable aliases). The kairos **package** rename is human-gated (execution path). The workspace folder is `frontend/dashboard` (npm package `dashboard`).

## Consequences

**Positive:** One product name on digiquant.io; landing and dashboard say the same thing; agent docs stop teaching four Greek names as the architecture.

**Negative / tradeoffs:** `/olympus/` is gone (no 308). Python packages `digiquant.olympus.atlas` stay until a two-hop `module/digiquant` PR. CSS (`.oly-*`) stays as an internal prefix. The workspace folder is `frontend/dashboard` (npm package `dashboard`). Historical issues and ADRs still say the old names. `pipeline-olympus.yml` keeps its filename until after the scheduled house proof (renaming a scheduled GHA on develop would skip the 12:00 UTC run).

## Amendment (2026-09-01)

Wave 5 of the rebrand plan said "prefer keeping `OLYMPUS_*`". Operator secrets, kill switches, and CLI paths now use `DIGIQUANT_*` / `scripts/digiquant_*.py` so merge and env dashboards stay on the product name. Retired names are read-only aliases so live empty kill-switches stay off. Do not set `DIGIQUANT_EXECUTION_ROUTING=1` without an explicit human decision. Do not rewrite SQL, historical ADR bodies, or `.oly-*` CSS.

## Links

- Scope: [docs/plans/2026-08-30-product-rebrand-scope.md](../plans/2026-08-30-product-rebrand-scope.md)
- Copy: [frontend/digiweb/design/COPY_GUIDE.md](../../frontend/digiweb/design/COPY_GUIDE.md)
- Supersedes product-name claims in ADR-0014 / 0015 / 0019 without rewriting those files
