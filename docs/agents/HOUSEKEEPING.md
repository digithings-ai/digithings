# Housekeeping — Scheduled Automation Index

Scheduled automation owns all the repo's housekeeping. Every item here runs
on a cron, event, or reaction — no human trigger required. This document is
the single index of what's covered, so gaps get noticed.

Label simplification 2026-09 (#3533): the `exec:*`, `risk:*`, `type:*`,
`pipeline:*`, `phase:*`, `needs-human*`, `maintenance`, and `housekeeping`
labels are deleted. Dispatch fires on the `agent-task` label with the tier from
`tiers` in `scripts/project_routing.json` (everything cursor-tier except
digikey). Automation-created issues carry `agent-task` + `component:root` +
`priority:*`. Dedup is by title search or body marker, never by label.

Source: `.github/workflows/` — see `docs/agents/EXECUTION_TIERS.md` for
the broader delegation framework.

## Task-board hygiene

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Orphan issues (not in any project board) | `project-enforce-assignment.yml` | daily 09:23 UTC (digithings-cron) | Comments on unlisted issues so the routing workflow picks them up |
| New issue → correct project board | `project-route-issues.yml` | on `issues: labeled/opened` | Maps `component:*` label to the right module project; epics also go to digithings #1 |
| Issue status transitions | `project-status.yml` | on issue assign / branch push / PR open / PR merge | Todo → In Progress → Review → Done across all 11 project boards |
| Stale issues (>90d no activity) | `pipeline-maintenance.yml` — `stale-issues` job | weekly Mon 08:00 UTC | Adds `stale` label + a reminder comment. Not auto-closed. Blocked issues use a 7d threshold |
| Stale PRs (>14d no activity) | `pipeline-maintenance.yml` — `stale-prs` job | weekly Mon 08:00 UTC | Posts an escalation comment on task/cursor/claude/module branches |
| Label coverage drift | `pipeline-maintenance.yml` — `label-coverage` job | weekly Mon 08:00 UTC | One tracker issue listing every open issue missing `priority:*` or `component:*` |
| Project-field coverage | the `coverage` job in `ci-pr-hygiene.yml` | daily 06:00 UTC + on PR | Runs `scripts/check_project_fields_coverage.py`: every agent-task issue in the TSV with a real phase and a valid model |
| Agent backlog snapshot | `agent-backlog-snapshot.yml` | weekly Mon 06:13 UTC (digithings-cron) | Regenerates `docs/agent-backlog/generated-snapshot.md` |

## Documentation hygiene

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Broken internal doc links | `pipeline-maintenance.yml` — `doc-links` job | weekly Mon 08:00 UTC | Runs `python3 scripts/check_doc_links.py`, files `[housekeeping] Broken internal doc links — <date>` if any found |
| `agents.yml` ↔ `.claude/` drift | `pipeline-maintenance.yml` — `agents-drift` job | weekly Mon 08:00 UTC | Runs `make agents-init --check`, files an issue if regeneration is needed |
| Per-module `ARCHITECTURE.md` drift | `pipeline-maintenance.yml` — `architecture-drift` job | weekly Mon 08:00 UTC | Runs `scripts/check_architecture_drift.py`: flags modules whose public-interface paths moved ≥3d after their `ARCHITECTURE.md` did (last 30d), one tracker issue for **human** triage. Advisory only — never edits docs |
| ADR numbering | `pipeline-maintenance.yml` — `adr-numbering` job + `ci-docs.yml` | weekly + on PR | Runs `scripts/check_adr_numbering.py`: `docs/adr/NNNN-*.md` must be zero-padded, unique and gap-free; files `[housekeeping] ADR numbering violation — <date>` on breach |
| Doc-link check on every PR | `ci-docs.yml` | on PR | Same check as above, gates PRs with broken links |

## Security

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Python dependency CVEs | `pipeline-maintenance.yml` — `dependency-audit` job + `security-pip-audit.yml` | weekly + on PR | Runs `pip-audit`, files one batched tracker issue (`security:finding`, dispatched at the cursor tier) |
| npm dependency CVEs | `security-npm-audit.yml` (dispatched weekly by the cron Worker) + `ci.yml` — `npm-audit` lane | weekly Mon 06:37 UTC + on PR | Runs `npm audit` on the root `apps/*` + `packages/*` workspace closure, blocks HIGH/CRITICAL, surfaces lower severities (accepted advisories in `npm-audit-ignore.txt`) |
| Secret leaks | `security-gitleaks.yml` | on push / PR | Scans for hard-coded secrets, fails CI if any found |
| Protected-path edits | `scripts/claude-hooks/protected-path-guard.sh` | PreToolUse hook | Blocks `.github/workflows/`, `SECURITY.md`, `docs/scoring/`, `config/litellm.yaml`, `projects/` edits outside properly-named branches — in both the current checkout and the primary tree when the session is rooted in a linked worktree |
| Live-trading path edits | `scripts/hooks/pre-push.sh` | pre-push | Requires `Human-Approved-By:` trailer on commits touching live-trading paths |

## Workflow health

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Scheduled-workflow credential expiry | `token-canary.yml` (dispatched daily by the cron Worker) | daily 06:41 UTC | Runs `scripts/check_workflow_tokens.py`: validates `DIGITHINGS_PROJECT_TOKEN` (`GET /user`) and `GH_DISPATCH_TOKEN` (read-only Actions-permissions probe) without spend; files one `priority:high` tracker on failure. `CLAUDE_CODE_OAUTH_TOKEN` / `CURSOR_API_KEY` are presence-checked only — neither has a quota-free introspection endpoint (#3522) |
| Environment gate drift | `secret-staleness-check.yml` (dispatched monthly by the cron Worker) | monthly, 1st 06:17 UTC | Runs `scripts/secret_staleness_check.py --gates-only`. It does exactly one thing: re-read the live environment protection rules against `.github/environments.json` and fail if `cron` has been given a reviewer or a wait timer, which would queue 32 scheduled pipelines instead of running them (#2541). Secret ageing is **not** automated (Paperclip DIG-477, option D): the Actions secrets endpoints need a token with the `repo` scope and a workflow's `GITHUB_TOKEN` never has one, so the run no longer attempts that read at all rather than reporting three levels NOT CHECKED and opening no tracker. Age them by hand from an operator's shell on the Mac via `make secrets-staleness`, where `gh auth` already carries `repo` and `admin:org`. That hand run touches the tracker only if it read something: a run that reads nothing exits 2 and leaves an open tracker alone, because the note it would close it with blames CI, which is no longer the caller. Last measured by hand, 2026-10-04: 16 of 33 names past 90 days, held in `docs/ops/SECRETS_INVENTORY.md` |
| Scheduled-workflow failure digest | `pipeline-maintenance.yml` — `workflow-health` job | weekly Mon 08:00 UTC | Aggregates failed scheduled runs from the past 7 days, one tracker issue (dedup by title) |
| PR-branch CI failures | `agent-ci-failure-triage.yml` | on workflow_run failure | Files a `ci:failure` triage issue per failed PR-branch workflow (dispatched at the cursor tier) |
| digiquant pipeline trackers | `pipeline-digiquant-{prices,onchain,tearsheets}.yml` — tracker update on failure | per-run | Maintains one persistent tracker issue per pipeline (dedup by body marker, paginated) instead of a new issue each failure |
| Stale branches | `pipeline-maintenance.yml` — `stale-branches` job | weekly | Identifies branches merged into develop >14d ago, files a cleanup issue |

## Continuous improvement

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Weekly improvement digest | `pipeline-continuous-improvement.yml` | weekly Sun 22:00 UTC | Collects past-7d PR activity + reviews + scheduled-workflow failures + commit msgs. Feeds to Claude with a pattern-recognition prompt. Files/updates one tracker issue per week with 3-5 prioritized suggestions and effort (S/M/L). Humans review Monday and decide which suggestions become backlog issues via `/spec`. Synthesis is judgment work |

**Why Claude**: pattern recognition across a week of PRs is judgment work, and the cost (1 Claude invocation/week) is trivial. Output is always suggestions for human review — never automated changes.

## Code review

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Auto PR review | `agent-claude-review.yml` | on PR open / sync / reopened / ready_for_review | Runs Claude's `/code-review` plugin on the PR diff. Member-gated, 15-min timeout, concurrency-cancelled on updates |
| `@claude` mention | `agent-claude.yml` | on issue / comment / review `@claude` mention | Targeted help |
| claude-tier dispatch | `agent-claude-dispatch.yml` | on `agent-task` where component tier is claude | Local instructions (`make task ISSUE=N`) |
| cursor-tier dispatch | `agent-cursor-dispatch.yml` | on `agent-task` where component tier is cursor | Posts `@cursor` mention with task prompt; GitHub App starts a Cloud Agent session |
| Stuck dispatch replay | `agent-dispatch-replay.yml` | manual `workflow_dispatch` | Bounces `agent-task` on stuck backlog issues (dry-run default) |
| Agent PR autolabel | `agent-pr-autolabel.yml` | on CI success | Adds `automerge-agent` to agent-branch PRs |
| Agent PR auto-merge | `agent-pr-automerge.yml` | on `automerge-agent` label + green CI | Squash auto-merge for agent PRs clearing the path-based safety gate (`verify_agent_automerge_pr.py`) |
| Agent PR finalizer | `agent-pr-finalizer.yml` | daily 07:11 UTC (digithings-cron) + manual | Backstop for agent PRs; triage, fix dispatch, automerge when eligible |
| PR quality gate | **removed** | — | A `/simplify` + `/review` checkbox gate on `task/*` merges existed as `pr-quality-gate.yml` from #131 (`abc7e541`) until #378 (`5abc4f41`) replaced it with the finish-task skill. Nothing enforces it in CI today. Listed rather than deleted so the gap is visible instead of assumed-covered. |
| PR issue linkage | removed 2026-08 per `docs/adr/0024-drop-pr-linkage-enforcement.md` (was `check-linkage` in `ci-pr-hygiene.yml`) | — | Convention only: `task/<N>-slug` branch or `Fixes #N` in PR body; nothing enforces it |

## Paperclip board (host-resident clocks)

Everything above runs in GitHub Actions, which cannot see the Paperclip
board at all: Paperclip is loopback-only and private
(`server.bind: loopback`, 127.0.0.1:3100), so no off-host clock can read its
routines API. Its automation is a family of launchd jobs on the operator's Mac
(`~/paperclip-workspace/kit/bin/dt-*`, `StartInterval`, logs under
`~/.config/digithings/`). Until DIG-1220 this index had no row for that board at
all, which is the same class of gap the index exists to make visible.

| Coverage | Clock | Cadence | What it does |
|---|---|---|---|
| Paperclip routines on a `schedule` trigger that never fire | `dt-routine-watch` (kit: `~/paperclip-workspace/kit/bin/dt-routine-watch`) | launchd, every 300 s | Reads each watched trigger's own `nextRunAt`; once past the boundary plus grace it asks **another system** whether the firing is visible — the routine's run history and the trigger's `lastFiredAt` / `lastResult`. No run and no `lastFiredAt` files an issue. Watches every active, enabled, non-archived schedule trigger (21 of 29 as of 2026-10-06), derived from the board rather than hardcoded, so a routine created tomorrow is watched tomorrow. Also files on its own silence (`self-gap`) and on its own lookup failing (`api-gap`). Runbook: [paperclip-routine-watch.md](../ops/paperclip-routine-watch.md) |
| Paperclip board agent routine runs | **none** | — | A routine that *does* fire writes a run row and creates an execution issue, so its activity is visible on the board; what nothing watched was the firing that never happened. Listed so the remaining half of the gap is visible instead of assumed covered |

Two known limits are accepted on the board (2026-10-06) and documented in the
runbook rather than papered over: pages are unauthenticated and land as
`local-board` (Paperclip mints no durable credential for a daemon; each issue
names the agent that installed it), and a powered-off host cannot report its own
silence — sleep is covered by `self-gap`, power-off is not observable at all.

## Escalation paths

There are no label-based escalation paths any more. Priority and spec quality
are the planning-time levers; merge-time safety is path-based
(`verify_agent_automerge_pr.py` deny-list) plus review coverage
(`ci-review-coverage.yml`). The minimal do-not-merge set (AGENTS.md): digikey
auth/crypto, brokers/live-trading, new external network exposure, PRs into
`main`, release-please PRs.

## Coverage gaps (follow-up)

Tracked as issues (see #3533): none currently open — token validity monitoring
(#3522), npm audit for `apps/` + `packages/` (#3523) and the ADR numbering audit
(#3524) are all implemented.

## Reference

- Tier framework: `docs/agents/EXECUTION_TIERS.md`
- Component routing: `docs/agents/COMPONENT_ROUTING.md`
- Agent workflow: `docs/agents/AGENT_WORKFLOW.md`
- Claude onboarding: `docs/agents/CLAUDE_CODE_ONBOARDING.md`
- Cursor onboarding: `docs/agents/CURSOR_AGENT_ONBOARDING.md`
