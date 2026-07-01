# CLAUDE.md

Rules and context for Claude Code in this repo. See also [docs/agents/AGENT_WORKFLOW.md](docs/agents/AGENT_WORKFLOW.md) for the full development protocol.

## What this is

DigiThings — open-core agentic stack (quant finance, RAG, chat). Services: **digigraph** (8000, LangGraph orchestration), **digiquant** (8001, NautilusTrader quant + Atlas + Hermes sub-graphs), **digisearch** (8002, RAG), **digikey** (8005, JWT + API keys), **digismith** (8003, tracing), **digivault** (8004, Obsidian-style markdown vault management — profile `digivault`), **digiclaw** (heartbeat + audit), **digibase** (shared library). Frontends: **digichat** (3005, chat UI), **olympus** (Atlas + Hermes dashboard). Sub-graphs in digiquant: Atlas at `digiquant/src/digiquant/olympus/atlas/`, Hermes at `digiquant/src/digiquant/olympus/hermes/`. Old `apps/digiquant-atlas/` is gone.

## Non-negotiable rules

- Polars only — never pandas
- Pydantic v2 everywhere; strict typing; ruff-compliant (line length 100)
- LangGraph supervisor + sub-graph orchestration; LiteLLM with caching
- NautilusTrader for all backtest / optimize / live paths
- MCP-first: every capability is a discoverable tool
- Every change traces to a GitHub Issue: `task/<N>-slug` branch or `Fixes #N` in the PR body
- Never touch live-trading paths without explicit human approval
- `projects/` is confidential — never push to public remotes

## Before modifying a component

1. Read `{component}/AGENTS.md` — pre-flight checklist and anti-patterns
2. Read `{component}/ARCHITECTURE.md` — module map, API, data models, extension guide
3. Update `{component}/ARCHITECTURE.md` after any interface or behavior change

## Scoring gate

Run `make score` on staged changes before every PR. All dimensions must pass.

| Dimension    | Minimum |
|--------------|---------|
| Security     | ≥ 8     |
| Quality      | ≥ 8     |
| Optimization | ≥ 7     |
| Accuracy     | ≥ 9     |

Rubrics live in `docs/scoring/` (10 criteria each).

## Human gate (always requires human review)

- Auth, JWT, or crypto changes (`digikey/`)
- Broker adapters or live-trading paths
- Score below threshold after two fix attempts
- New external service dependency or network exposure change
- Novel architecture decision not covered by any existing `ARCHITECTURE.md`

## Core commands

```bash
make test-unit          # unit tests (no stack required)
make score              # self-score staged changes against 4-dimension rubrics
make task ISSUE=N       # isolated git worktree for a backlog task (full pipeline)
make doc-check          # validate internal markdown links
ruff check . && ruff format .
```

## Branching model

```
main ← develop ← module/<component> ← task/<N>-slug
```

Use `make task ISSUE=N` to create a `task/N-slug` branch from the right module branch. Task branches PR into their module branch; module branches PR into develop. Never do module-specific work on `develop` directly.

**Sync the module branch with develop *before* you branch off it.** Module branches drift behind `develop` fast because we iterate on develop constantly — and a task branch cut from a stale module branch edits dead code. (Real incident, 2026-06-17: `module/digiquant` was ~2 months / ~400 commits behind, predating the `apps/digiquant-atlas → digiquant/src/digiquant/olympus` migration; backend PRs cut from it touched files that no longer exist on develop.) `make task ISSUE=N` does **not** sync for you — check first:

```bash
git fetch origin
git rev-list --count origin/module/<component>..origin/develop   # 0 = current; >0 = stale, sync before branching
```

Module branches are guarded by the `module-branch-protection` ruleset: **no force-push, no deletion, PR required (0 approvals)**. So you cannot `git push --force` to refresh a stale module branch. To sync one, open a normal PR into `base=module/<component>` — either `head=develop`, or a `chore/sync-*` branch whose tree equals develop (a `-s ours` merge with the index reset to develop's tree preserves the module branch's prior history) — and merge it (no approval needed). Branch names must match `{feat,fix,docs,chore}/<slug>` or `task/<N>-slug`.

The **Check linkage** CI gate (the `Require Fixes` check) is separate from the branch-name rule: it only auto-links a PR via a `task/<N>-slug` branch **or** a `Fixes/Closes/Resolves #N` keyword in the body. A `feat|fix|docs|chore/<slug>` branch passes the name rule but still **fails linkage** unless the body says `Fixes #N` — so prefer `task/<N>-slug` for issue-linked work (and never `Closes #N` against an umbrella tracking issue you don't want auto-closed).

## Liveness vs status

- `GET /healthz` — liveness probe, auth-exempt, always `{"ok": true}`, no downstream checks
- `GET /v1/status` (DigiSmith) — operator diagnostic, may report config/versions; not for load balancers

## Deployments (static sites)

- **digithings.ai** — Cloudflare Pages via `scripts/build-digithings.sh`. The legacy `static.yml` GitHub Pages workflow was **removed** in the 2026-06 workflow cleanup; do not use GitHub Pages for this domain.
- **digiquant.io** — Cloudflare Pages (`scripts/build-digiquant.sh`) and/or split-repo publish per [docs/adr/0012-digiquant-io-split-repo.md](docs/adr/0012-digiquant-io-split-repo.md). There is no `deploy-digiquant.yml` in this monorepo; see `.github/workflows/deploy-digiquant-cloudflare.yml` when present.

## Agent surface

Skills, subagents, and slash commands under `.claude/` are generated from `agents/sources/` by `make agents-init`. Never hand-edit `.claude/agents/`, `.claude/skills/`, or `.claude/commands/` — edit the sources and run `make agents-init`. CI enforces idempotence.

Active slash commands: `/score`, `/triage <pr-number>`, `/spec`, `/task <issue-number>`, `/normalize`
