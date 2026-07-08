# ADR-0012 — digiquant.io served from a separate publish repo

> **Historical note (2026-06):** Production deploy also uses **Cloudflare Pages** (`scripts/build-digiquant.sh`, `.github/workflows/deploy-digiquant-cloudflare.yml`). The split-repo `deploy-digiquant.yml` sync path below may still apply for `digithings-ai/digiquant.io`.

**Status:** Accepted (2026-04-23)
**Amends:** [ADR-0002](0002-domain-unification.md) (two-domain plan) and [ADR-0009](0009-frontend-umbrella.md) (frontend umbrella).
**Context:** Issues [#174](https://github.com/digithings-ai/digithings/issues/174) (live-websites epic), [#301](https://github.com/digithings-ai/digithings/issues/301) (digiquant.io deploy).

## Context

ADR-0002 committed to two live domains — `digithings.ai` and `digiquant.io` — both served from this monorepo. ADR-0009 consolidated every web surface under `frontend/*`. In this session (2026-04-23) we hit the hard constraint: **GitHub Pages supports exactly one custom domain per repository**. The monorepo's Pages slot was assigned to `digithings.ai` (legacy `static.yml`, now retired in favor of Cloudflare Pages), so `digiquant.io` cannot be served from the same repo.

## Options considered

1. **Cloudflare Pages for digiquant.io.** Free, handles multiple domains per account, PR previews out of the box. Rejected because the user prefers GitHub-native tooling across the board for auditability and reduced vendor surface.
2. **Subpath hosting** at `digithings-ai.github.io/digiquant/`. Loses the `.io` vanity domain, which is a product-marketing requirement.
3. **Move digithings.ai to a separate repo too.** Symmetric, but displaces a working deploy for no functional benefit — three repos where two suffice.
4. **Split-repo publish target for digiquant.io only** (this ADR). Keeps digithings.ai where it is; adds a thin publish repo for digiquant.io; monorepo stays the single source of truth for content.

## Decision

`digiquant.io` is served from a dedicated publish repo, `digithings-ai/digiquant.io`, whose GitHub Pages config serves its `main` branch root. A sync workflow in this monorepo (`.github/workflows/deploy-digiquant.yml`) builds `dist/` from `frontend/digiquant/` + `frontend/digiweb/design/` on every push to `develop`/`main` touching those paths, and force-pushes the result to the publish repo using a fine-grained PAT (`DIGIQUANT_IO_DEPLOY_TOKEN`, scoped to the publish repo, contents: read/write).

**The publish repo is deploy-only.** No human commits there; its history is a byproduct of deploys. The monorepo remains the sole source of truth.

## Consequences

### Positive

- digithings.ai deploy is untouched — zero risk to the live site.
- `frontend/digiquant/` keeps a single canonical location in the monorepo for content + review.
- Fast iteration: `push` to `develop` on the relevant paths triggers a deploy within a few minutes.
- Future split of other subdomains (e.g., `atlas.digiquant.io`) follows the same pattern — one publish repo per custom domain.

### Negative

- One additional repo to monitor (minimal surface — README + `dist/` content, no code).
- A PAT is now a supply-chain-relevant secret; rotate on the usual cadence. Fine-grained PAT limits blast radius to the publish repo's contents.
- Force-pushing to the publish repo's `main` means no meaningful git history there; if you need a forensic record, check the monorepo.

### Neutral

- Force-push was chosen over diff-and-commit because the publish repo's `main` is a deploy artifact, not a codebase. Retaining history would mean meaningful-looking commits that aren't meaningful.

## Follow-ups

- If a third custom domain appears (e.g., a client pilot subdomain outside the two-domain plan), reassess whether Cloudflare Pages' PR-preview ergonomics justify adopting it as the delivery layer for all marketing sites, with GitHub Pages retained only for internal tools. Not urgent.
- The publish repo `README.md` should make its one-way-ness obvious to anyone who lands there from GitHub search.
