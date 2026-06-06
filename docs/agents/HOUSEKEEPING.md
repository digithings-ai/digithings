# Housekeeping — Copilot Tier 1 Automation Index

Tier 1 (Copilot / scheduled automation) owns all the repo's housekeeping.
Every item here runs on a cron, event, or reaction — no human trigger
required. This document is the single index of what's covered, so gaps
get noticed.

Source: `.github/workflows/` — see `docs/agents/EXECUTION_TIERS.md` for
the broader delegation framework.

## Task-board hygiene

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Orphan issues (not in any project board) | `enforce-project-assignment.yml` | daily 09:00 UTC | Comments on unlisted issues so the routing workflow picks them up |
| New issue → correct project board | `route-issues-to-projects.yml` | on `issues: labeled/opened` | Maps `component:*` label to the right module project; epics also go to digithings #1 |
| Issue status transitions | `project-status-automation.yml` | on issue assign / branch push / PR open / PR merge | Todo → In Progress → Review → Done across all 11 project boards |
| Stale issues (>90d no activity) | `scheduled-maintenance.yml` — `stale-issues` job | weekly Mon 08:00 UTC | Adds `stale` label + a reminder comment. Not auto-closed. Blocked issues use a 7d threshold |
| Stale PRs (>14d no activity) | `scheduled-maintenance.yml` — `stale-prs` job | weekly Mon 08:00 UTC | Posts an escalation comment on task/cursor/claude/module branches |
| Label coverage drift | `scheduled-maintenance.yml` — `label-coverage` job | weekly Mon 08:00 UTC | One tracker issue listing every open issue missing `exec:*`, `priority:*`, `component:*`, or (non-epic) `complexity:*` / `risk:*` |
| Project-field coverage | `project-fields-coverage.yml` | scheduled | Ensures required project fields are populated |
| Agent backlog snapshot | `agent-backlog-snapshot.yml` | weekly Mon 06:00 UTC | Regenerates `docs/agent-backlog/generated-snapshot.md` |

## Documentation hygiene

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Broken internal doc links | `scheduled-maintenance.yml` — `doc-links` job | weekly Mon 08:00 UTC | Runs `python3 scripts/check_doc_links.py`, files `[housekeeping] Broken internal doc links — <date>` if any found |
| `agents.yml` ↔ `.claude/` drift | `scheduled-maintenance.yml` — `agents-drift` job | weekly Mon 08:00 UTC | Runs `make agents-init --check`, files an issue if regeneration is needed |
| Doc-link check on every PR | `docs.yml` | on PR | Same check as above, gates PRs with broken links |

## Security

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Python dependency CVEs | `scheduled-maintenance.yml` — `dependency-audit` job + `pip-audit.yml` | weekly + on PR | Runs `pip-audit`, files an `exec:claude` + `risk:high` issue per weekly batch of findings |
| Secret leaks | `gitleaks.yml` | on push / PR | Scans for hard-coded secrets, fails CI if any found |
| Protected-path edits | `scripts/claude-hooks/protected-path-guard.sh` | PreToolUse hook | Blocks `.github/workflows/`, `SECURITY.md`, `docs/scoring/`, `digikey/` edits outside task branches |
| Live-trading path edits | `scripts/hooks/pre-push.sh` | pre-push | Requires `Human-Approved-By:` trailer on commits touching live-trading paths |

## Workflow health

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Scheduled-workflow failure digest | `scheduled-maintenance.yml` — `workflow-health` job | weekly Mon 08:00 UTC | Aggregates failed scheduled runs from the past 7 days, one tracker issue grouped by workflow name |
| PR-branch CI failures | `ci-failure-triage.yml` | on workflow_run failure | Files a Copilot triage issue per failed PR-branch workflow |
| DigiQuant prices pipeline | `digiquant-prices.yml` — tracker update on failure | per-run | Maintains one persistent tracker issue per job instead of new issue each failure |
| Stale branches | `scheduled-maintenance.yml` — `stale-branches` job | weekly | Identifies branches merged into develop >14d ago, files a cleanup issue |

## Continuous improvement

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Weekly improvement digest | `continuous-improvement.yml` | weekly Sun 22:00 UTC | Collects past-7d PR activity + reviews + scheduled-workflow failures + commit msgs. Feeds to Claude with a pattern-recognition prompt. Files/updates one tracker issue per week with 3-5 prioritized suggestions categorized by tier (copilot/cursor/claude) and effort (S/M/L). Humans review Monday and decide which suggestions become backlog issues via `/spec`. Labeled `exec:claude` — synthesis is judgment work |

**Why Claude, not Copilot**: pattern recognition across a week of PRs is judgment work, Copilot Chat isn't reachable from scheduled workflows the same way, and the cost (1 Claude invocation/week) is trivial. Output is always suggestions for human review — never automated changes.

## Code review

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Auto PR review | `claude-code-review.yml` | on PR open / sync / reopened / ready_for_review | Runs Claude's `/code-review` plugin on the PR diff. Member-gated, 15-min timeout, concurrency-cancelled on updates |
| `@claude` mention | `claude.yml` | on issue / comment / review `@claude` mention | Targeted Tier 3 help |
| `exec:claude` label dispatch | `claude-code-dispatch.yml` | on `exec:claude` / `opened` | Local Tier-3 instructions (`make task ISSUE=N`) |
| `exec:cursor` label dispatch | Cursor Automation (cloud) | on `exec:cursor` label event | Starts Cursor Cloud Agent session; quota-checked; fallback: `agent-dispatch-replay.yml` |
| `exec:copilot` assign bridge | `copilot-issue-dispatch.lock.yml` (gh-aw) | on `exec:copilot` / `opened` | Assigns `@Copilot` via `assign-to-agent` safe output when quota allows |
| Stuck dispatch replay | `agent-dispatch-replay.yml` | manual `workflow_dispatch` | Bounces `exec:*` labels on backlog issues |
| Agent PR autolabel | `agent-pr-autolabel.yml` | on CI success | Adds `automerge-agent` to `cursor/*` / `copilot/*` PRs |
| Agent PR auto-merge | `automerge-agent-prs.yml` | on `automerge-agent` label + green CI | Squash auto-merge for low-risk agent PRs |
| Copilot PR lifecycle | `copilot-pr-lifecycle.lock.yml` (gh-aw) | every 10 min + manual | End-to-end `copilot/*` loop: issue link, mark-ready, CI, review, fix rounds, automerge |
| Copilot targeted CI | `copilot-pr-targeted-ci.yml` | lifecycle dispatch (fallback) | Path-filtered checks when main CI has not run; posts `Copilot targeted CI` check on PR head SHA |
| Agent PR finalizer | `agent-pr-finalizer.yml` | daily 07:00 UTC + manual | Backstop for `cursor/*` PRs; triage, fix dispatch, automerge when eligible |
| PR quality gate | `pr-quality-gate.yml` | on PR open/edit | Blocks task/* branch merges without `/simplify` + `/review` checkboxes |
| PR issue linkage | `pr-linkage.yml` | on PR open/edit | Blocks merge without `Fixes #N` / `Closes #N` |

## Escalation paths

Any housekeeping finding can escalate up a tier by changing its label:

- **Default**: housekeeping issues carry `exec:copilot` — scheduled automation or Copilot chat-agent-assigned human resolves
- **Escalated**: if the finding needs judgment (e.g., CVE patch breaks dependency constraints) the scheduled job labels the issue `exec:claude` + `risk:high` directly
- **Human gate**: issues labeled `needs-human` are never auto-merged; require explicit human approval on the PR

## Coverage gaps (follow-up)

These are known not-yet-covered and belong on future housekeeping PRs:

- **Token validity monitoring** — no active test that `DIGITHINGS_PROJECT_TOKEN` / `CLAUDE_CODE_OAUTH_TOKEN` / `CURSOR_API_KEY` haven't expired; failure signal is "all scheduled workflows started failing simultaneously." Mitigation: `workflow-health` digest will surface this as a correlated failure cluster
- **npm audit for `frontend/`** — only Python CVEs are scanned today; digichat + digithings frontends go uncovered
- **ADR numbering audit** — no check that `docs/adr/NNNN-*.md` files are sequentially numbered or without duplicates
- **Per-module ARCHITECTURE.md drift** — no check that module architecture docs are updated when the module's public interface changes

## Reference

- Tier framework: `docs/agents/EXECUTION_TIERS.md`
- Component routing: `docs/agents/COMPONENT_ROUTING.md`
- Agent workflow: `docs/agents/AGENT_WORKFLOW.md`
- Claude onboarding: `docs/agents/CLAUDE_CODE_ONBOARDING.md`
- Cursor onboarding: `docs/agents/CURSOR_AGENT_ONBOARDING.md`
