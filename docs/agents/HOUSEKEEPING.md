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

## Code review

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Auto PR review | `claude-code-review.yml` | on PR open / sync / reopened / ready_for_review | Runs Claude's `/code-review` plugin on the PR diff. Member-gated, 15-min timeout, concurrency-cancelled on updates |
| `@claude` mention | `claude.yml` | on issue / comment / review `@claude` mention | Targeted Tier 3 help |
| `exec:claude` label dispatch | `claude-code-dispatch.yml` | on `exec:claude` label | Structured tier-3 task execution |
| `exec:cursor` label dispatch | `cursor-agent-dispatch.yml` | on `exec:cursor` label | Tier 2 scoped task execution |
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
