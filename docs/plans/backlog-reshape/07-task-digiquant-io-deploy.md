# Task: Deploy digiquant.io via GitHub Pages (separate publish repo)

**Title:** `[agent] Set up digiquant.io deploy — separate Pages publish repo + sync workflow`

**Labels:** `agent-task`, `component:root`, `priority:critical`, `complexity:M`, `type:infra`, `risk:med`

**Component:** website / root docs
**Risk:** med (DNS + cross-repo deploy; reversible but visible if broken)
**Execution tier:** claude (needs judgment on DNS + cross-repo perms)
**Model:** sonnet

## Goal

digiquant.io serves the content in `frontend/digiquant/` (post-rename; currently `frontend/digiquant/`). GitHub Pages only supports one custom domain per repo, and `digithings-ai/digithings` already owns the `digithings.ai` slot. Solution: a thin `digithings-ai/digiquant-web` publish repo that Pages serves as `digiquant.io`, fed by a deploy workflow in the monorepo.

Blocker-removal for epic #174 (live website demos) and user-stated P0.

## Acceptance criteria

### Repo + Pages
- [ ] New repo `digithings-ai/digiquant-web` created (public, minimal README noting it's a publish target — source of truth is the monorepo).
- [ ] Pages enabled on that repo, source = `main` branch root (or `gh-pages` — pick one convention and document it).
- [ ] CNAME `digiquant.io` set in Pages settings.

### DNS (at registrar)
- [ ] Apex `digiquant.io` → A records `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` (and AAAA equivalents for IPv6).
- [ ] `www.digiquant.io` → CNAME `digithings-ai.github.io`.
- [ ] HTTPS enforced + cert issued by GH (wait for propagation; verify via `curl -I https://digiquant.io`).

### Sync workflow (in monorepo)
- [ ] `.github/workflows/deploy-digiquant.yml` added. Triggers: `push` to `develop` touching `frontend/digiquant/**` or `frontend/design/**`, plus `workflow_dispatch`.
- [ ] Builds the same dist shape as `static.yml` but from `frontend/digiquant/`:
  - `dist/` ← `frontend/digiquant/.`
  - `dist/design/` ← `frontend/design/`
- [ ] Pushes `dist/` to `digithings-ai/digiquant-web` `main` via a deploy key or PAT stored as monorepo secret `DIGIQUANT_WEB_DEPLOY_TOKEN`. Commit message references the source SHA.
- [ ] Workflow runs cleanly on a `workflow_dispatch` before merge.

### Verification
- [ ] `https://digiquant.io` serves the `frontend/digiquant/` content end-to-end with design assets loading.
- [ ] `https://www.digiquant.io` redirects/serves correctly.
- [ ] Pushing a trivial change to `frontend/digiquant/` on `develop` triggers a new deploy within ~5 minutes.

### Documentation
- [ ] `CLAUDE.md` frontend-umbrella section notes the split-repo Pages setup for digiquant.io.
- [ ] `docs/adr/0002-domain-unification.md` amended or a new ADR filed: "digiquant.io served from separate publish repo due to one-domain-per-repo Pages limit."
- [ ] `frontend/digiquant/README.md` documents the deploy path so nobody wonders where the site comes from.

## Rejected alternatives

- **Cloudflare Pages**: simpler (same monorepo, no sync), free previews per PR. Rejected per user preference for GH Pages.
- **Subpath hosting on digithings-ai.github.io/digiquant/**: loses the `.io` vanity domain.

## Context / links

- Pages config for digithings.ai (for reference): `gh api repos/digithings-ai/digithings/pages` → currently `build_type: workflow`, CNAME `digithings.ai`.
- Existing workflow `.github/workflows/static.yml` is the template for the build step.
- Sequenced after task 06 (rename) so paths are stable.

## Non-goals

- Any change to digithings.ai deploy.
- Content changes to digiquant.io.
- Atlas subdomain setup (`atlas.digiquant.io`) — separate task, post-Atlas-frontend-move.
