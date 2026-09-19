---
type: repo-guide
title: Repo Workflow
description: Branching model, make targets, review/merge policy, and cloudflare dev loop for the digithings monorepo.
tags: [repo, branching, make, review-policy, cloudflare, monorepo]
sources:
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-4b2266e051b2270b6ec5aa4f
    resource: repo://BRANCHING.md
  - id: openwiki-source-a49bd70bd0f6d776441b838b
    resource: repo://docs/agents/CODE_REVIEW_POLICY.md
  - id: openwiki-source-c35e65f8f146fe8c8830b207
    resource: repo://docs/plans/2026-09-18-dev-cloudflare-containers.md
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-5b54a58d1b51cd490b0e7162
    resource: repo://package.json
  - id: openwiki-source-b65ebdde03cc47633165ae2e
    resource: repo://scripts/hooks/pre-push.sh
verified:
  - by: openwiki/0.5.0
    at: 2026-09-19T12:20:11.463Z
generated: { by: "openwiki/0.5.0", at: "2026-09-19T12:20:11.463Z" }
---

# Repo Workflow

This page is a pointer map, not a duplicate of the source docs. Normative
detail lives in `BRANCHING.md`, `AGENTS.md`, and
`docs/agents/CODE_REVIEW_POLICY.md`.

## Branching model

Three tiers: `main ← develop ← module/<component> ← task/<N>-slug`.
Task branches cut from their module branch via `make task ISSUE=N`
(auto-detected from the issue's `component:` label); module sprints batch
into `develop` via `make module-pr MODULE=<component>`. Some components
skip the module tier and branch straight from `develop` —
`scripts/project_routing.json` is the source of truth (read its `branches`
map; as of 2026-09 `component:digivault`, `component:website`, and
`component:root` route to `develop`; the `default` fallback also routes to
`develop`).

`main` is what is deployed; `develop` is the default integration branch.
Name enforcement is client-side only via `make hooks-install` (installs
`scripts/hooks/pre-push.sh` from `origin/develop`). The pre-push hook
enforces three guards:

1. **Origin gate** — refuses pushes to any remote besides
   `github.com/digithings-ai/digithings`.
2. **Branch taxonomy** — rejects branch names outside the allowed patterns
   (deletions are exempt). No server-side naming ruleset exists;
   `scripts/github-rulesets/01-branch-naming.json` is desired state that
   was never applied.
3. **Main gate** — blocks pushes to `main` without `ALLOW_MAIN_PUSH=1`.
4. **Live-trading guard** — scans the diff for
   `live_trading|execute_trade|place_order|digiquant/(.*/)?live/` and
   requires a `Human-Approved-By:` git trailer (via `git interpret-trailers`)
   in at least one commit in the pushed range.

Server-side, the only ruleset is `module-branch-protection` on
`refs/heads/module/**` (blocks force-push and deletion). Classic branch
protection also applies: `main` requires a PR plus the `Every commit
reaching main was reviewed` status check; `develop` has no PR gate but
requires three status checks with `strict: true`. `release/v*` has no
protection — it can be force-pushed or deleted.

Module branches managed by the tooling (`scripts/module_branches.sh`
`MODULES` array): `module/digigraph`, `module/digiquant`,
`module/digisearch`, `module/digichat`, `module/digikey`,
`module/digismith`, `module/digiclaw`, `module/digibase`. Other
`module/*` branches on `origin` (e.g. `module/website`,
`module/dashboard`, `module/digiskills`) are not managed by any command
here. Short-lived branch patterns include `feat/*`, `fix/*`, `docs/*`,
`chore/*`, `claude/*`, `codex/*`, `cursor/*`, `copilot/*`,
`<handle>/*`, `bot/*`, and `release-please--branches--*--components--*`.

## Monorepo layout

npm workspaces: `cloudflare/*` and `cloudflare/digiweb/*`
(`repo://package.json#L4-L7`). The frontends and Workers live under
`cloudflare/`:

| Directory | Purpose |
|-----------|---------|
| `cloudflare/digichat/` | chat UI (Next.js, port 3005/3000) |
| `cloudflare/dashboard/` | digiquant operator dashboard (Next.js, `/dashboard/`) |
| `cloudflare/digiweb/` | design system, brand, shared UI (`design/` is presentation-only) |
| `cloudflare/digichat-cloudflare/` | Cloudflare Containers Worker for digichat |
| `cloudflare/digithings-stack-cloudflare/` | Cloudflare Containers Worker for the backend stack |
| `cloudflare/digithings-cron/` | Cloudflare Worker cron scheduler |
| `cloudflare/digithings-web/` | marketing/docs website |
| `cloudflare/digiquant-web/` | digiquant web frontend |
| `cloudflare/digichat-ui/` | shared digichat UI components |

## Make targets

Targets are grouped by concern in the Makefile. Key categories:

**Stack lifecycle:**
`make up` / `down` (full Docker Compose stack), `make up-ghcr` /
`pull-ghcr` (prebuilt GHCR images, no local build), `make stack-local` /
`stack-local-stop` (host-native Python services, no Docker),
`make up-heartbeat` / `up-observability` / `down-observability`.

**digichat:**
`make up-digichat` / `down-digichat` (local build from monorepo),
`make digichat-release-up VERSION=…` / `digichat-release-down VERSION=…`
(pull pinned GHCR release), `make digichat-profile-a-up` / `-down`
(digichat + digikey + digigraph + digivault from GHCR),
`make digichat-profile-a-bundle-up` / `-down` (single supervisord image
for CF Containers parity), `make digichat-dev` (Next.js dev server on
`:3000`), `make digichat-health` (curl `/api/health`),
`make up-digichat-db` / `down-digichat-db` (Postgres 16 on host port 5433).

**Tests:**
`make test` (unit + e2e if stack up), `make test-unit` (Python unit +
digichat Vitest, no stack), `make test-baseline` (imports + schemas + CLI
help, always green, no Docker/network), `make test-e2e` (requires stack),
`make test-cov` / `test-cov-html` (coverage for digigraph + digiquant +
digismith).

**Module/orchestration:**
`make module-status` / `module-sync` / `module-switch MODULE=<x>` /
`module-pr MODULE=<x>`, `make task ISSUE=N` (isolated worktree for a
backlog task), `make status` (list open issues), `make new-task`,
`make batch-candidates`, `make pr` (create PR via gh CLI),
`make commit MSG="…"` (conventional commit helper).

**Agent/dev setup:**
`make hooks-install` (install pre-push hook from `origin/develop`),
`make agents-init` (generate `.cursor/rules/digithings.mdc` and
`.github/copilot-instructions.md` from `agents.yml`).

**Docs/data:**
`make doc-check` (internal markdown links), `make adr-check` (ADR numbering),
`make vault-check` (digivault-managed docs lint), `make openapi-export` /
`openapi-check` (FastAPI OpenAPI specs), `make gen-api-vault` (digivault
API-reference notes), `make seed-digisearch-local`,
`make edgar-digisearch-dev`, `make export-edgar-digisearch-dev`.

**Quality/health:**
`make score` / `score-delta` (optional 4-dimension rubric, human/CI tool
only — not an agent pre-flight), `make readiness` (repo-health panel,
advisory), `make clean-imports`, `make find-stale`, `make secrets-scan`
(local gitleaks), `make secrets-audit`.

## Dev loop for cloudflare frontends

**Local digichat (Next.js):**
```bash
# host-native backends (no Docker)
make stack-local

# optional: Postgres for digichat
make up-digichat-db

# Next.js dev server (hot reload, http://127.0.0.1:3000)
make digichat-dev

# smoke check
make digichat-health
```

**Local dashboard:**
```bash
npm --workspace cloudflare/dashboard run dev
# serves at http://127.0.0.1:3001/dashboard/
```

Configure `.env.local` files under `cloudflare/digichat/` and
`cloudflare/dashboard/` to point at the local or dev-container backends.

**Presentation-only frontend** (`cloudflare/digiweb/design/**`,
`**.css`, static marketing pages): iterate on one branch off `develop`
with a live preview (`.claude/launch.json` dev servers); open a single PR
when the look is approved. `cloudflare/**` is excluded from the optional
`score` CI filter. Gates that still apply: gitleaks, app builds, and the
digithings deploy build-check.

## Review and merge policy

Default is **in-session review** on a fresh-context subagent (`/review <N>`)
with findings posted as `<!-- in-session-review -->` plus the
`reviewed:agent` label for the `main` coverage gate. Metered bots are
on-demand only: Bugbot `bugbot run` once per final diff; CodeRabbit
re-requests only for fixed majors. The CodeRabbit Cursor plugin must stay
disabled (`.cursor/settings.json`); `.cursor/rules/no-coderabbit.mdc`
counter-instructs agents to ignore plugin routing.

The review-coverage gate (`scripts/check_review_coverage.py`) runs on
every PR into `main` and asserts each commit in the range was reviewed at
its own task PR. Five hatches clear a commit, strongest first:

| hatch | claim | self-grantable? |
|-------|-------|-----------------|
| `Cursor Bugbot` concluded **success** | machine reviewed it | no |
| **APPROVED** review | someone else read it | no |
| completed **agent-tool review** | bot finished a pass | no |
| label `reviewed:agent` + `<!-- in-session-review -->` comment | in-session review in fresh context | yes, but comment required |
| label `reviewed:owner` | "I read this myself" | yes |

A commit pushed straight to a branch (no PR) has a sixth fallback: a
comment carrying `<!-- in-session-review -->` **and** the commit's 8-char
sha on an issue or PR itself labelled `reviewed:agent`. Both halves
required.

### Merge-when-ready

When required CI is green, threads are triaged, and a coverage hatch is
on record, the authoring agent merges into the PR's **base** — unless a
human-gate exception applies:

- `digikey/` auth, JWT, or crypto changes
- Live-trading paths (`digiquant/brokers/`)
- New external network exposure or service dependency
- PRs into `main` (production cutover)
- release-please PRs (deliberate release decisions)

Everything else merges on green CI + review coverage. `gh pr merge <N>`
(merge commit or squash to match how the target branch lands). Do not
`--auto` unless that is how the stacked PR is supposed to land.
