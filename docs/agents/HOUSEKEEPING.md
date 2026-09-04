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
| Orphan issues (not in any project board) | `project-enforce-assignment.yml` | daily 09:00 UTC | Comments on unlisted issues so the routing workflow picks them up |
| New issue → correct project board | `project-route-issues.yml` | on `issues: labeled/opened` | Maps `component:*` label to the right module project; epics also go to digithings #1 |
| Issue status transitions | `project-status.yml` | on issue assign / branch push / PR open / PR merge | Todo → In Progress → Review → Done across all 11 project boards |
| Stale issues (>90d no activity) | `pipeline-maintenance.yml` — `stale-issues` job | weekly Mon 08:00 UTC | Adds `stale` label + a reminder comment. Not auto-closed. Blocked issues use a 7d threshold |
| Stale PRs (>14d no activity) | `pipeline-maintenance.yml` — `stale-prs` job | weekly Mon 08:00 UTC | Posts an escalation comment on task/cursor/claude/module branches |
| Label coverage drift | `pipeline-maintenance.yml` — `label-coverage` job | weekly Mon 08:00 UTC | One tracker issue listing every open issue missing `priority:*` or `component:*` |
| Project-field coverage | the `coverage` job in `ci-pr-hygiene.yml` | daily 06:00 UTC + on PR | Runs `scripts/check_project_fields_coverage.py`: every agent-task issue in the TSV with a real phase and a valid model |
| Agent backlog snapshot | `agent-backlog-snapshot.yml` | weekly Mon 06:00 UTC | Regenerates `docs/agent-backlog/generated-snapshot.md` |

## Documentation hygiene

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Broken internal doc links | `pipeline-maintenance.yml` — `doc-links` job | weekly Mon 08:00 UTC | Runs `python3 scripts/check_doc_links.py`, files `[housekeeping] Broken internal doc links — <date>` if any found |
| `agents.yml` ↔ `.claude/` drift | `pipeline-maintenance.yml` — `agents-drift` job | weekly Mon 08:00 UTC | Runs `make agents-init --check`, files an issue if regeneration is needed |
| Doc-link check on every PR | `ci-docs.yml` | on PR | Same check as above, gates PRs with broken links |

## Security

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Python dependency CVEs | `pipeline-maintenance.yml` — `dependency-audit` job + `security-pip-audit.yml` | weekly + on PR | Runs `pip-audit`, files one batched tracker issue (`security:finding`, dispatched at the cursor tier) |
| Secret leaks | `security-gitleaks.yml` | on push / PR | Scans for hard-coded secrets, fails CI if any found |
| Protected-path edits | `scripts/claude-hooks/protected-path-guard.sh` | PreToolUse hook | Blocks `.github/workflows/`, `SECURITY.md`, `docs/scoring/`, `config/litellm.yaml`, `projects/` edits outside properly-named branches — in both the current checkout and the primary tree when the session is rooted in a linked worktree |
| Live-trading path edits | `scripts/hooks/pre-push.sh` | pre-push | Requires `Human-Approved-By:` trailer on commits touching live-trading paths |

## Workflow health

| Coverage | Workflow | Cadence | What it does |
|---|---|---|---|
| Scheduled-workflow failure digest | `pipeline-maintenance.yml` — `workflow-health` job | weekly Mon 08:00 UTC | Aggregates failed scheduled runs from the past 7 days, one tracker issue (dedup by title) |
| PR-branch CI failures | `agent-ci-failure-triage.yml` | on workflow_run failure | Files a `ci:failure` triage issue per failed PR-branch workflow (dispatched at the cursor tier) |
| digiquant pipeline trackers | `pipeline-digiquant-{prices,onchain,tearsheets}.yml` — tracker update on failure | per-run | Maintains one persistent tracker issue per pipeline (dedup by exact title + marker) instead of a new issue each failure |
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
| Agent PR finalizer | `agent-pr-finalizer.yml` | daily 07:00 UTC + manual | Backstop for agent PRs; triage, fix dispatch, automerge when eligible |
| PR quality gate | **removed** | — | A `/simplify` + `/review` checkbox gate on `task/*` merges existed as `pr-quality-gate.yml` from #131 (`abc7e541`) until #378 (`5abc4f41`) replaced it with the finish-task skill. Nothing enforces it in CI today. Listed rather than deleted so the gap is visible instead of assumed-covered. |
| PR issue linkage | removed 2026-08 per ADR-0024 (was `check-linkage` in `ci-pr-hygiene.yml`) | — | Convention only: `task/<N>-slug` branch or `Fixes #N` in PR body; nothing enforces it |

## Escalation paths

There are no label-based escalation paths any more. Priority and spec quality
are the planning-time levers; merge-time safety is path-based
(`verify_agent_automerge_pr.py` deny-list) plus review coverage
(`ci-review-coverage.yml`). The minimal do-not-merge set (AGENTS.md): digikey
auth/crypto, brokers/live-trading, new external network exposure, PRs into
`main`, release-please PRs.

## Coverage gaps (follow-up)

Tracked as issues (see #3533):

- **Token validity monitoring** — no active test that credentials haven't expired; failure signal is correlated scheduled failures. → #3522
- **npm audit for `frontend/`** — only Python CVEs are scanned today. → #3523
- **ADR numbering audit** — no check that `docs/adr/NNNN-*.md` files are sequentially numbered or without duplicates. → #3524
- **Per-module ARCHITECTURE.md drift** — no check that module architecture docs are updated when the module's public interface changes. → #3525

## Reference

- Tier framework: `docs/agents/EXECUTION_TIERS.md`
- Component routing: `docs/agents/COMPONENT_ROUTING.md`
- Agent workflow: `docs/agents/AGENT_WORKFLOW.md`
- Claude onboarding: `docs/agents/CLAUDE_CODE_ONBOARDING.md`
- Cursor onboarding: `docs/agents/CURSOR_AGENT_ONBOARDING.md`
