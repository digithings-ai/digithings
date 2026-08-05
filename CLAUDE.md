# CLAUDE.md

Rules and context for Claude Code in this repo. See also [docs/agents/AGENT_WORKFLOW.md](docs/agents/AGENT_WORKFLOW.md) for the full development protocol.

## What this is

digithings — open-core agentic stack (quant finance, RAG, chat). Services: **digigraph** (8000, LangGraph orchestration), **digiquant** (8001, NautilusTrader quant + Atlas + Hermes sub-graphs), **digisearch** (8002, RAG), **digikey** (8005, JWT + API keys), **digismith** (8003, tracing), **digivault** (8004, Obsidian-style markdown vault management — profile `digivault`), **digiclaw** (heartbeat + audit), **digibase** (shared library). Frontends: **digichat** (3005, chat UI), **olympus** (Atlas + Hermes dashboard). Sub-graphs in digiquant: Atlas at `digiquant/src/digiquant/olympus/atlas/`, Hermes at `digiquant/src/digiquant/olympus/hermes/`. Old `apps/digiquant-atlas/` is gone.

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

**Exception — presentation-only frontend** (`frontend/digiweb/design/**`, `**.css`, static
marketing pages): `make score` does **not** apply — its rubrics are Python-oriented
and misfire on CSS/JS. `frontend/**` is excluded from the `score` CI filter and
`frontend/digiweb/design/` is in `score.py`'s skip list. Iterate design on **one branch off
`develop`** with a live preview (`.claude/launch.json` dev servers) and open a
single PR when the look is approved. Gates that still apply: gitleaks (secrets),
app builds, the digithings deploy build-check. (See #1310.)

## Human gate (always requires human review)

- Auth, JWT, or crypto changes (`digikey/`)
- Broker adapters or live-trading paths
- Score below threshold after two fix attempts
- New external service dependency or network exposure change
- Novel architecture decision not covered by any existing `ARCHITECTURE.md`

## Review coverage (the gate before production)

PR review runs on **Cursor Bugbot, invoked by hand** — comment `bugbot run` (or
`cursor review`) once a diff is final, and again only if scope changes mid-PR.
Never at PR open, and never per push: Bugbot went usage-based in June 2026 at
roughly $1.00–$1.50 a run, so a review on every push is a real monthly cost. The
Copilot request job was removed from `ci.yml` when that subscription lapsed
(#1894) — it had been reporting success while attaching no reviewer.

Reviewing the *promotion* is the wrong moment: a promotion diff is an accumulation
of already-merged work (PR #1877 was 52 files, 12k lines), so it is the priciest
review Cursor will quote and the least actionable, since a finding needs a fresh
task PR plus another promotion. So `ci-review-coverage.yml` asserts the cheaper
invariant on every PR into `main` — **each commit in the range was reviewed at its
own task PR** — via `scripts/check_review_coverage.py`. A commit clears it with a
completed Bugbot run, a human approval, or the `risk:low` label; merge commits and
bot-authored commits are exempt by nature.

Note what is deliberately *not* done: `Cursor Bugbot` is **not** a required status
check on `main`. It reports `neutral` on a usage-limit skip and a required check
must report success, so on 2026-08-05 that would have made all ten promotions
unmergeable — including the one carrying a fix for false copy already live. Never
let a metered third-party service hold a veto over deploys; this gate reads only
the repo's own history, labels and reviews, and a label always clears it.

Do not gate on Cursor's Low/Medium/High risk label. It measures code blast radius:
PR #1891 was rated **Low** at 2 files and +14/−8, and it shipped two false public
claims to production. Gate on paths (`digikey/`, brokers, migrations, workflows)
and on whether behaviour or a public factual claim changed.

## Dependency version bounds

**Tools whose output gates CI carry an upper bound; runtime libraries do not.**

A new `ruff` turned ~981 lint findings red across an unchanged codebase, then
started reformatting Markdown; `mcp` 2.0 removed a module two servers import.
Three CI breakages, one cause: an unpinned tool changing behaviour under a green
build (#1701, #1705, #1711). So `ruff`, `mypy`, `pytest` and `pytest-cov` are
bounded to their current major, as is `mcp`.

Runtime dependencies are deliberately **left unbounded**. `digibase`, `digillm`,
`digifetch`, `digiskills` and `digivault` are installable libraries, and an upper
bound in a library propagates to every consumer and causes resolution conflicts —
capping `pydantic<3` in ten places would create more breakage than it prevents.
Cap a runtime dep only when there is a *known* incompatibility, and say so in a
comment next to it (see the `mcp` extras).

When a bound blocks an upgrade, raise it deliberately in its own PR with the
resulting fixes reviewed — the same rule the `ruff.toml` rule selection follows.

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

**Not every component is two-hop.** `scripts/project_routing.json` maps each `component:` label to its base branch, and five route **straight to `develop`**, skipping the module tier (as does the `default` fallback):

- `component:root` — repo-level files, including this one. A change to `CLAUDE.md`, `Makefile`, or `.github/` has no module hop to make.
- `component:digivault` — routed to `develop` despite being a backend service.
- `component:website`, `component:digiquant-web`, `component:design-system` — frontend is one-hop (#1310): it has no auth/live-trading surface to isolate, and the `module/website` hop was the source of the redesign epic's sync/conflict churn.

Task branches for these PR into `develop` directly. The two-hop model applies to the remaining backend modules (`module/digiquant`, `module/digikey`, `module/digigraph`, etc.).

**Sync the module branch with develop *before* you branch off it.** Module branches drift behind `develop` fast because we iterate on develop constantly — and a task branch cut from a stale module branch edits dead code. (Real incident, 2026-06-17: `module/digiquant` was ~2 months / ~400 commits behind, predating the `apps/digiquant-atlas → digiquant/src/digiquant/olympus` migration; backend PRs cut from it touched files that no longer exist on develop.) `make task ISSUE=N` does **not** sync for you — check first:

```bash
git fetch origin
git rev-list --count origin/module/<component>..origin/develop   # 0 = current; >0 = stale, sync before branching
```

Don't re-run the full review pipeline at every hop — see [AGENT_WORKFLOW.md §9](docs/agents/AGENT_WORKFLOW.md) for which stage gets the full review vs. a diff-scoped check.

Module branches are guarded by the `module-branch-protection` ruleset: **no force-push, no deletion, PR required (0 approvals)**. So you cannot `git push --force` to refresh a stale module branch. To sync one, open a normal PR into `base=module/<component>` — either `head=develop`, or a `chore/sync-*` branch whose tree equals develop (a `-s ours` merge with the index reset to develop's tree preserves the module branch's prior history) — and merge it (no approval needed).

Branch names must match the taxonomy in [BRANCHING.md](BRANCHING.md), enforced by the `scripts/hooks/pre-push.sh` hook (`make hooks-install`): `main`, `develop`, `module/<component>`, `release/vX.Y.Z`, `task/<N>-slug`, `{feat,fix,docs,chore}/<slug>`, `{claude,codex,cursor,copilot}/<slug>` for agent-driven work outside the task system, and `<handle>/<slug>` for a named human contributor. Agent session branches are valid names — `claude/<slug>` pushes fine; it is *linkage*, below, that it does not satisfy.

The **Check linkage** CI gate (the `Require Fixes` check) is separate from the branch-name rule. It passes on any one of these, in the order `.github/workflows/ci-pr-hygiene.yml` tests them:

1. Head branch is `module/*` — umbrella PR; the underlying task PRs already carried linkage.
2. Head branch is `docs/*` or `chore/*` — **bypassed outright**, no issue required. A `CLAUDE.md` tweak or a CI dedupe does not need a backlog item.
3. Head branch is `task/<N>-slug` — implicit link to issue #N.
4. A `Fixes/Closes/Resolves #N` keyword appears in the PR **body or title** (either one).

So `feat/<slug>` and `fix/<slug>` are the only name-rule-valid patterns that still need an explicit keyword — as are the agent namespaces (`claude/<slug>` et al.), which no rule bypasses. Prefer `task/<N>-slug` for issue-linked work, and never `Closes #N` against an umbrella tracking issue you don't want auto-closed — use `Refs #N` when the PR should not close the issue, which satisfies no gate on its own and so pairs with a `docs/`, `chore/`, or `task/` branch.

## Liveness vs status

- `GET /healthz` — liveness probe, auth-exempt, always `{"ok": true}`, no downstream checks
- `GET /v1/status` (digismith) — operator diagnostic, may report config/versions; not for load balancers

## Deployments (static sites)

- **digithings.ai** — Cloudflare Pages via `scripts/build-digithings.sh`. The legacy `static.yml` GitHub Pages workflow was **removed** in the 2026-06 workflow cleanup; do not use GitHub Pages for this domain.
- **digiquant.io** — Cloudflare Pages git-integration on this monorepo, building `dist/` via `scripts/build-digiquant.sh` from `main` (per `deploy-digiquant-cloudflare.yml`'s header; the Cloudflare dashboard is authoritative). That is the sole delivery path — the split publish repo in [docs/adr/0012-digiquant-io-split-repo.md](docs/adr/0012-digiquant-io-split-repo.md) was never created, and `.github/workflows/deploy-digiquant-cloudflare.yml` is a PR build check, not the deploy.

## Agent surface

Skills, subagents, and slash commands under `.claude/` are generated from `agents/sources/` by `make agents-init`. Never hand-edit `.claude/agents/`, `.claude/skills/`, or `.claude/commands/` — edit the sources and run `make agents-init`. CI enforces idempotence.

Active slash commands: `/score`, `/triage <pr-number>`, `/spec`, `/task <issue-number>`, `/normalize`, and the OpenSpec trio `/opsx-propose`, `/opsx-apply`, `/opsx-archive`.
