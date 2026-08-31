# CLAUDE.md

Rules and context for Claude Code in this repo. See also [docs/agents/AGENT_WORKFLOW.md](docs/agents/AGENT_WORKFLOW.md) for the full development protocol.

## What this is

digithings — open-core agentic stack (quant finance, RAG, chat). Services: **digigraph** (8000, LangGraph orchestration), **digiquant** (8001, NautilusTrader quant + research / portfolio / execution sub-graphs), **digisearch** (8002, RAG), **digikey** (8005, JWT + API keys), **digismith** (8003, tracing), **digivault** (8004, Obsidian-style markdown vault management — profile `digivault`), **digiclaw** (heartbeat + audit), **digibase** (shared library). Frontends: **digichat** (3005, chat UI), **digiquant dashboard** (`frontend/olympus`, public path `/dashboard/` with 308s from `/olympus/` — ADR-0026). Sub-graphs live at `digiquant/src/digiquant/olympus/atlas/` (research), `…/hermes/` (portfolio), `…/kairos/` (execution). Package paths keep the old names until a dedicated rename PR. Old `apps/digiquant-atlas/` is gone.

## Non-negotiable rules

- Polars only — never pandas
- Pydantic v2 everywhere; strict typing; ruff-compliant (line length 100)
- LangGraph supervisor + sub-graph orchestration; LiteLLM with caching
- NautilusTrader for all backtest / optimize / live paths
- MCP-first: every capability is a discoverable tool
- Every change traces to a GitHub Issue: `task/<N>-slug` branch or `Fixes #N` in the PR body
- Never touch live-trading paths without explicit human approval
- `projects/` is confidential — never push to public remotes
- **Digi names are always lowercase** — see [Naming](#naming--digi-modules) below

## Naming — Digi modules

Every Digi product, module, package, and service name is **always lowercase** in prose, docs, agent instructions, commit messages, and PR text — including at the start of a sentence and in headings.

| Correct | Incorrect (do not use) |
|---------|------------------------|
| digithings | DigiThings, Digithings, Digi Things |
| digichat | DigiChat, Digichat |
| digivault | DigiVault, Digivault |
| digigraph | DigiGraph, Digigraph |
| digiquant | DigiQuant, Digiquant |
| digisearch | DigiSearch, Digisearch |
| digikey | DigiKey, Digikey |
| digismith | DigiSmith, Digismith |
| digiclaw | DigiClaw, Digiclaw |
| digibase | DigiBase, Digibase |
| digiskills | DigiSkills, Digiskills |
| digiweb | DigiWeb, Digiweb |
| digillm | DigiLLM, Digillm |
| digifetch | DigiFetch, Digifetch |

Same rule for any future Digi* module (digiball, digicraft, …): `digi` + lowercase rest, no spaces, no CamelCase in prose.

**Exception — code identifiers only.** Language-idiomatic symbols keep their language’s casing: TypeScript/React `DigiChatSession`, `requireDigiChatAuth()`, Python `DigiAuthMiddleware`, HTTP header literals like `X-Digichat-Session`. Do not “fix” those to lowercase; do not invent CamelCase product names in docs to match them.

Wrong vocabulary causes routing mistakes (wrong component folder, wrong AGENTS.md, wrong package name). When in doubt, match the directory / PyPI / npm name.

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

**Org policy (all digithings-ai repos):** [docs/agents/CODE_REVIEW_POLICY.md](docs/agents/CODE_REVIEW_POLICY.md).
Default is **in-session** review on a fresh-context subagent (`/review <N>`). Metered
bots are optional; do not burn their quota on small follow-up commits.

**Cursor Bugbot** (when available) is the primary *external* option — comment
`bugbot run` (or `cursor review`) once a diff is final, and again only if scope
changes mid-PR. Never at PR open, and never per push: Bugbot went usage-based in
June 2026 at roughly $1.00–$1.50 a run ([Cursor Bugbot](https://cursor.com/docs/bugbot)).
The Copilot request job was removed from `ci.yml` when that subscription lapsed
(#1894). Usage-limit `neutral` is not a review — run `/review` instead.

**CodeRabbit is optional / sunset.** While it still runs, it auto-reviews only
bases listed in [`.coderabbit.yaml`](.coderabbit.yaml) (`develop` default plus
`main`, `module/*`, `release/*`). Do **not** `@coderabbitai review` for CI nits,
docs, or one-line fixes. Re-request **only** when a prior **major** finding was
fixed and needs verification. A green CodeRabbit status check is not an approving
review — check `gh pr view --json reviewDecision` / open threads before merge.

Reviewing the *promotion* is the wrong moment: a promotion diff is an accumulation
of already-merged work (PR #1877 was 52 files, 12k lines), so it is the priciest
review Cursor will quote and the least actionable, since a finding needs a fresh
task PR plus another promotion. So `ci-review-coverage.yml` asserts the cheaper
invariant on every PR into `main` — **each commit in the range was reviewed at its
own task PR** — via `scripts/check_review_coverage.py`. Merge commits and bot-authored
commits are exempt by nature; every other commit clears it, strongest first:

| hatch | claim | self-grantable? |
|-------|-------|-----------------|
| `Cursor Bugbot` concluded **success** | a machine reviewed it | **no** |
| an **APPROVED** review | someone else read it | no |
| a completed **agent-tool review** (CodeRabbit, Claude `/code-review`, Copilot, …) | a PR-review bot finished a pass, not a skip/rate-limit/failure notice | no |
| label **`reviewed:agent`** + a findings comment | an in-session review ran in a **fresh-context** subagent or new session | yes, but it costs a real review — the label without the comment is refused |
| label **`reviewed:owner`** | "I read this myself" | yes — so the verdict names who applied it and when |
| label **`risk:low`** | "this did not warrant a review" | yes |

**When Bugbot / CodeRabbit are unavailable or out of quota, review in-session —
do not skip.** Bugbot `neutral` is not a review. Run `/review <N>`: tiered
fresh-context subagents (token-efficient scope pass, then strong model only on
flagged areas — see CODE_REVIEW_POLICY.md and `agents/sources/commands/review.md`).
Author session must not review its own work. Verify each finding with a command,
refute, then post survivors as a PR comment opening with
`<!-- in-session-review -->` and apply `reviewed:agent`.

Every line here is written by a coding agent, so an agent reviewing it is not weaker
in kind than Bugbot — which is also an agent. What matters is that the reviewer did
not write the code and that its output is on the record.
`scripts/check_review_coverage.py` therefore looks for the comment, not just the
label, and **refuses `reviewed:agent` when the findings are missing**. Fix what the
review finds on the same branch before merge; that is the whole reason review
belongs at the task PR and not at the promotion.

`reviewed:owner` exists because of a hole the gate's own first run exposed: a
solo maintainer cannot self-approve, Bugbot was out of quota, and the only
remaining option was to label a blocking CI change `risk:low`. **Never use
`risk:low` to mean `reviewed:owner`** — "I read it" and "it needed no reading" are
different claims, and collapsing them destroys the only signal worth having. With
one account holding write access, the label hatches are accountability records
rather than enforcement — though `reviewed:agent` at least cannot be claimed without
posting a review. Bugbot, CodeRabbit, and Claude reviews are the hatches nobody
can grant themselves.

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

## Model & subagent policy

**General rule:** pick the **best model for the job**, prefer the **token-efficient**
choice that still clears the bar, and **do not use fast mode** (no `*-fast` /
speed-optimized Cursor slugs). Quality of fit first; cost second; latency never
overrides either.

Unpinned subagents inherit the orchestrator's model — an unset `model:` under an
Opus/Fable session silently runs every subagent at that price. Every subagent
under `agents/sources/subagents/` already pins one; keep doing it:

| Role | Model | Examples |
|------|-------|----------|
| Routing, dispatch, dictation cleanup, small/mechanical verification | haiku, or sonnet when the check has any real complexity — pick by task, not by habit | `component-router`, `dictation-normalizer`, a lint/type-check triage pass |
| Implementation, spec-writing (the heavy lifting) | sonnet | `spec-writer`, `test-first-implementer` |
| Review **scope** pass — map diff, list risk areas, skip clean files | haiku or sonnet (Claude); token-efficient Cursor model (not `*-fast`) | `/review` first pass |
| Review **deep** pass / security / architecture — only on flagged areas | opus (Claude); stronger Cursor model or dedicated review agent (not `*-fast`) | `/review` deep lenses, security paths |
| Ad-hoc design/architecture consult ("advisor" role — a second opinion outside a formal review, a judge-panel comparison of approaches) | opus for anything hard-to-reverse or architecturally significant; sonnet default otherwise | a `Plan`/`Explore` agent, an `AskUserQuestion` decision point with real trade-offs, a "which approach is better" comparison |

There is deliberately no standing `pr-reviewer`/`security-reviewer` subagent in
`agents/sources/` — that job already has three owners (Cursor Bugbot, the
`/review` command's fresh-context lens fan-out, and the `pr-review-toolkit` and
`superpowers:requesting-code-review` plugin skills), and a fourth would only add
ambiguity about which one the harness should pick. Route review work through
one of those instead of adding a new custom subagent for it.

**Two of those three review paths are not actually pinned — check before trusting
the table above.** `pr-review-toolkit`'s six agents split: `code-reviewer` and
`code-simplifier` pin `model: opus`, but `comment-analyzer`, `pr-test-analyzer`,
`silent-failure-hunter`, and `type-design-analyzer` are `model: inherit` — they
silently ride whatever the session is on, same as an unpinned custom subagent
would. The `/review` command's lens fan-out has no subagent file to pin at all
(it dispatches ad hoc via the `Agent` tool at runtime), so its instructions
explicitly tier models: sonnet/haiku for the scope pass, `model: opus` only on
flagged deep lenses — check `agents/sources/commands/review.md` before assuming
every lens still runs at opus. Don't assume a plugin or ad-hoc dispatch is
pinned just because a custom subagent would be; verify the specific agent file.

**Advisors get the same treatment as review, not the implementation default.**
A second-opinion/design-consult moment reads like "quick advice," so it's easy to
let it silently ride the session's tier — but a wrong architectural call costs
more to unwind than a wrong implementation does, so treat "should I do A or B"
the same way as a review: name the model explicitly rather than let it default.
A judge-panel comparison (multiple independent takes scored against each other)
is exactly the "architecturally significant" case — pin each panelist to opus,
not whatever the orchestrator happens to be running.

Orchestrator itself: sonnet by default. Reserve opus/fable for the session only
when the orchestration/decomposition step is the hard part — a hard subagent
task gets its own opus pin regardless of what the orchestrator runs. This cuts
both ways: an opus/fable orchestrator does **not** mean its subagents should
inherit that tier either — most implementation and routing work under an opus
session should still be pinned down to sonnet/haiku explicitly. "The
orchestrator is expensive" and "every subagent should be expensive" are
independent decisions; make each one on its own merits, not by inheritance in
either direction. Before fanning out more than ~5 subagents in one turn, name
each one's model out loud; a silent fan-out is how a quota disappears in one
prompt. Spot-check a subagent's actual model via its transcript
(`~/.claude/projects/<proj>/<session>/subagents/agent-<id>.jsonl`) after any
Claude Code upgrade — pins have regressed silently before.

## Context & compaction policy

`.claude/settings.json` sets `autoCompactWindow: 150000` — deliberately tight
(the allowed range is 100k–1M; unset defaults to a much larger model-tuned
window). A big context isn't free just because the quota allows it: model
performance degrades as the window fills, so compacting early is a
performance choice, not just a cost one. Override per-session with
`--autocompact` or the `CLAUDE_CODE_AUTO_COMPACT_WINDOW` env var when a task
genuinely needs more room (e.g. a large migration reading many files at
once) — don't loosen the committed default for everyone to fix one session.

**Plan compaction points on a long implementation instead of letting it
happen wherever the window fills.** Before starting multi-step work
(`/task`, a multi-file migration, a long debugging session), decide up front
where the natural step boundaries are — after each phase of a plan, after
each file in a batch, after each subagent's results land — and compact at
those boundaries deliberately rather than mid-step. Right before compacting,
write down what the next steps need and nothing else: the specific
files/lines still to touch, decisions already made and why (not the full
exploration that led to them), and what's already verified so it isn't
re-derived. A `TaskUpdate`/todo-list entry or a short note in the turn is
enough — the goal is that compaction loses exploration, not state.

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

**A task branch must be cut from a current base.** Module branches drift behind `develop` fast because we iterate on develop constantly — and a task branch cut from a stale module branch edits dead code. (Real incident, 2026-06-17: `module/digiquant` was ~2 months / ~400 commits behind, predating the `apps/digiquant-atlas → digiquant/src/digiquant/olympus` migration; backend PRs cut from it touched files that no longer exist on develop.) The same hazard applied to the one-hop components until 2026-08-20: `scripts/worktree_task.sh` fetched the base branch only when no *local* ref of that name existed, and `refs/heads/develop` always exists, so `make task` handed out worktrees cut from whatever stale local `develop` you last pulled — one was measured 50 commits behind `origin/develop` (#2547).

`make task ISSUE=N` now enforces this itself, so there is no manual pre-flight check to remember:

- it runs `git fetch origin` first, then branches from `refs/remotes/origin/<base>` — never from the local branch of the same name;
- if the resolved base is a `module/*` branch behind `origin/develop`, it prints the behind-count and **refuses**, with the `gh pr create` recipe for syncing it (below);
- `WORKTREE_TASK_OFFLINE=1` skips the fetch and `WORKTREE_TASK_ALLOW_STALE_MODULE=1` downgrades the refusal to a warning. Both are loud, and both exist so this is a detour rather than a dead end.

`tests/scripts/test_worktree_task_base_ref.py` pins that behaviour, deriving its one-hop and two-hop fixtures from `project_routing.json` rather than hard-coding a component.

Don't re-run the full review pipeline at every hop — see [AGENT_WORKFLOW.md §9](docs/agents/AGENT_WORKFLOW.md) for which stage gets the full review vs. a diff-scoped check.

Module branches are guarded by the `module-branch-protection` ruleset: **no force-push, no deletion, PR required (0 approvals)**. So you cannot `git push --force` to refresh a stale module branch. To sync one, open a normal PR into `base=module/<component>` — either `head=develop`, or a `chore/sync-*` branch whose tree equals develop (a `-s ours` merge with the index reset to develop's tree preserves the module branch's prior history) — and merge it (no approval needed).

Branch names must match the taxonomy in [BRANCHING.md](BRANCHING.md), enforced by the `scripts/hooks/pre-push.sh` hook (`make hooks-install`): `main`, `develop`, `module/<component>`, `release/vX.Y.Z`, `task/<N>-slug`, `{feat,fix,docs,chore}/<slug>`, `{claude,codex,cursor,copilot}/<slug>` for agent-driven work outside the task system, `bot/<slug>` for branches the workflows push, and `<handle>/<slug>` for a named human contributor.

**Issue linkage is a convention, not a CI gate.** Prefer a `task/<N>-slug` branch (created by `make task ISSUE=N`, implicitly linking to issue #N), or a `Fixes #N` / `Closes #N` / `Resolves #N` line in the PR body for anything else, so shipped work traces back to the backlog. Nothing in CI enforces this — a `check-linkage` job used to run on every PR, but it was never a required status check on `main` or `develop`, so a failure never blocked a merge; it just produced rework when a PR had to be re-edited to satisfy it, and merged unchanged when it wasn't. Removed 2026-08; see [docs/adr/0024-drop-pr-linkage-enforcement.md](docs/adr/0024-drop-pr-linkage-enforcement.md) for the audit and the full historical bypass logic. `ci-review-coverage.yml`'s "every commit reaching main was reviewed" check is unrelated and still required — that one asserts review happened, not that an issue is linked.

## Liveness vs status

- `GET /healthz` — liveness probe, auth-exempt, always `{"ok": true}`, no downstream checks
- `GET /v1/status` (digismith) — operator diagnostic, may report config/versions; not for load balancers

## Deployments (static sites)

- **digithings.ai** — Cloudflare Pages via `scripts/build-digithings.sh`. The legacy `static.yml` GitHub Pages workflow was **removed** in the 2026-06 workflow cleanup; do not use GitHub Pages for this domain.
- **digiquant.io** — Cloudflare Pages git-integration on this monorepo, building `dist/` via `scripts/build-digiquant.sh` from `main` (per `deploy-digiquant-cloudflare.yml`'s header; the Cloudflare dashboard is authoritative). That is the sole delivery path — the split publish repo in [docs/adr/0012-digiquant-io-split-repo.md](docs/adr/0012-digiquant-io-split-repo.md) was never created, and `.github/workflows/deploy-digiquant-cloudflare.yml` is a PR build check, not the deploy.

## Release cadence (release-please)

`release-please-*.yml` workflows (digichat, digiskills, …) propose a release PR on
every qualifying push to `develop` and keep updating that **same** PR as more
commits land — that accumulation is the intended design. The version-bump math
(feat → minor, fix → patch, BREAKING CHANGE → major) is Conventional Commits
doing its job; don't second-guess it.

**Merging that PR is a separate, deliberate decision — not routine PR hygiene.**
Treat a green, mergeable release-please PR the same as any other unmerged
proposal: leave it open until a release is actually intended (e.g. paired with a
real deploy), not because CI passed. Merging early forecloses accumulation and
forces the next commit into a brand-new release — three digichat releases (1.1.0,
1.2.0, and a same-day 1.2.1 proposal) landed within ~48 hours this way, none of
them tied to a deliberate release decision (2026-08-13).

## Agent surface

Skills, subagents, and slash commands under `.claude/` are generated from `agents/sources/` by `make agents-init`. Never hand-edit `.claude/agents/`, `.claude/skills/`, or `.claude/commands/` — edit the sources and run `make agents-init`. CI enforces idempotence.

Active slash commands: `/score`, `/triage <pr-number>`, `/spec`, `/task <issue-number>`, `/normalize`, `/review <pr-number>`, and the OpenSpec trio `/opsx-propose`, `/opsx-apply`, `/opsx-archive`.
