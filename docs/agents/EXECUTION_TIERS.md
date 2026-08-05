# Execution Tiers — Agent Delegation Framework

Every digithings backlog task carries exactly one `exec:*` label identifying the **minimum-capability tier** allowed to execute it. A lower tier must never pick up a higher-tier task. A human on Claude Code can always take anything.

Source of truth: `agents.yml` → `execution_tiers` and `tier_routing`. Regenerate platform adapters (`CLAUDE.md`, `.github/copilot-instructions.md`, `.cursor/rules/digithings.mdc`) with `make agents-init` after edits.

## The three tiers

### `exec:copilot` — Tier 1 — GitHub Copilot + gh-aw automation

Triggered automation. Fixed rule, no judgment. Runs on a schedule or event inside GitHub Actions.

**Fits:** Dependabot bumps, `pip-audit`, `gitleaks`, `ruff format`, stale issue/PR sweeps, label-coverage drift, orphan-issue routing, project-status transitions, scheduled-workflow failure digests, `digiquant-prices` failure dedup, CI-failure triage, **PR code review** (primary reviewer on all PRs), housekeeping tasks (duplicate issues, project backfill, doc links).

**Full coverage index:** see `docs/agents/HOUSEKEEPING.md` — every scheduled sweep, its cadence, and what it escalates.

**Copilot execution is retired (2026-08-05).** The subscription lapsed, and with it
`copilot-issue-dispatch`, `copilot-pr-lifecycle`, `copilot-pr-mark-ready`,
`copilot-pr-targeted-ci` and `copilot-quota-gate` were deleted. Nothing dispatches
`exec:copilot` now — issues carrying that label are not picked up by anything, so
`pipeline-maintenance.yml` and `pipeline-digiquant-prices.yml` still applying it is a
known loose end. Moving that automation to Cursor is open work.

**PR code review:** Cursor Bugbot, invoked by hand with a `bugbot run` comment once a
diff is final. Never at PR open and never per push — Bugbot went usage-based in June
2026 at roughly $1.00–$1.50 a run. `ci.yml`'s `request-copilot-review` job was removed
in #1894; it had been reporting success while attaching no reviewer. Claude review
remains a secondary opt-in (see below). Every commit reaching `main` must clear
`ci-review-coverage.yml`, which is a required status check.

**PR auto-merge (low-risk agent PRs):** when CI is green on a `cursor/*` or `copilot/*` branch linked to a non-`risk:high` issue, `agent-pr-autolabel.yml` adds `automerge-agent`. `automerge-agent-prs.yml` verifies paths (no `digikey/`, workflows, scoring rubrics) and enables squash auto-merge. Human-gated issues keep the `needs-human` or `risk:high` label to block merge.

**Daily PR finalizer:** `agent-pr-finalizer.yml` runs at 07:00 UTC as backstop for `cursor/*` PRs.

**Never:** judgment calls, multi-file code changes, live-trading, auth, cryptography.

### `exec:cursor` — Tier 2 — Cursor Cloud Agent (Cursor Automations)

Autonomous, asynchronous. Describable in one paragraph with clear acceptance criteria. Opens a PR for human review.

**Fits:** bug fixes with a concrete repro; unit tests for a specified module; docstrings; typed-model migrations; scoped refactors inside a single component; small MCP tools with defined signatures.

**Never:** cross-module integration, ambiguous success criteria, novel design, anything requiring mid-task dialogue.

**Setup & operations:** see `docs/agents/CURSOR_AGENT_ONBOARDING.md`.  
**Dispatch (Tier C):** applying the `exec:cursor` label (or creating an issue with it) triggers a **Cursor Automation** configured at [cursor.com/settings/automations](https://cursor.com/settings/automations). The Automation fires a Cloud Agent session with the task context and custom instructions. If quota is exhausted the session fails naturally; the issue stays open until quota resets. Stuck backlog: run **Agent dispatch replay** workflow (`agent-dispatch-replay.yml`).

### `exec:claude` — Tier 3 — Claude Code (human-supervised, LOCAL only)

Interactive, local, human-in-the-loop. The top tier; takes everything above and adds judgment-heavy work. **Claude never auto-executes issues — only Copilot (Tier 1) and Cursor (Tier 2) do.** The label is a tier *marker*; execution is always a human on a workstation.

**Fits:** architecture and new-module scaffolding; complex debugging; cross-module integration; security review; strategy/iterative design; milestone decomposition; targeted `@claude` help.

**PR code review (secondary, opt-in):** Claude's `/code-review` plugin via `.github/workflows/agent-claude-review.yml` is **off by default**. Enable it by setting repo variable `ENABLE_CLAUDE_PR_REVIEW = true` (Settings → Secrets and variables → Actions → Variables). Also requires `CLAUDE_CODE_OAUTH_TOKEN` secret. Use Copilot review first; enable Claude review only for projects that need deeper analysis.

**Weekly continuous-improvement digest:** `.github/workflows/pipeline-continuous-improvement.yml` runs every Sunday 22:00 UTC, synthesizes the past 7 days of PR/CI/review activity, and files a single tracker issue with 3–5 prioritized suggestions. See [HOUSEKEEPING.md](HOUSEKEEPING.md#continuous-improvement) — synthesis is judgment work, so it lives at Tier 3.

**Setup & operations:** see `docs/agents/CLAUDE_CODE_ONBOARDING.md`.
**Dispatch (local only):** applying the `exec:claude` label triggers `.github/workflows/agent-claude-dispatch.yml`, which posts a comment pointing at the local command:

```
make task ISSUE=N
```

Cloud dispatch via the Claude Code Action is **intentionally disabled** (policy, issue #384). If a task is cursor-sized, relabel `exec:cursor` and stop. If it genuinely needs Tier 3, a human runs `make task` locally.

## Decision tree

```
Fully automatable with a trigger + fixed rule?
├── YES → exec:copilot
└── NO
    └── Spec fits one paragraph, no mid-task dialogue, clear acceptance?
        ├── YES → exec:cursor
        └── NO  → exec:claude
```

## Default routing when the creator doesn't classify

Applied by `scripts/create_issue.sh` and the `spec-writer` subagent:

| Condition | Default tier |
|---|---|
| `risk:high`, matches a human gate, or touches `digikey/` auth / live-trading paths | `exec:claude` |
| Labelled `security:finding`, `housekeeping:deps`, `housekeeping:format`, `stale` | `exec:copilot` |
| Everything else | `exec:cursor` |

## Responsibilities by tier

- **Copilot workflows** (`scheduled-maintenance.yml`, `ci-failure-triage.yml`) must tag every issue they open with an `exec:*` label. CVE bumps and lint drift → `exec:copilot`. CI failures needing code fixes → `exec:cursor`. Architectural findings → `exec:claude` plus `needs-human`.
- **Cursor Cloud Agents** must only pick up issues labelled `exec:cursor` or `exec:copilot`. If a task feels larger than the one-paragraph spec implied, relabel it `exec:claude` and comment why — do not proceed.
- **Claude Code (you)** decomposes milestones, writes issue bodies via `/spec`, assigns tiers, and reviews PRs only when `ENABLE_CLAUDE_PR_REVIEW` is set.

## Workflow

1. **Claude Code** — read milestone, decompose, write issues via `/spec`, tier each one.
2. **Cursor Cloud Agents** — execute `exec:cursor` issues in parallel; open PRs.
3. **Copilot** — reviews every PR as primary reviewer; picks up `exec:copilot` issues continuously.
4. **Claude Code** — handles judgment-heavy tasks locally; secondary PR reviewer when enabled.

## Cursor setup (one-time, Tier C)

1. Configure the Cursor Automation as described in `docs/agents/CURSOR_AGENT_ONBOARDING.md`.
2. Verify `.cursor/rules/digithings.mdc` is loaded (run `make agents-init` if stale).

See `docs/agents/CURSOR_AGENT_ONBOARDING.md` for the full agent operating protocol.

## Copilot setup (one-time)

1. Confirm `DIGITHINGS_PROJECT_TOKEN` secret is set (needed for maintenance workflows).
2. Raise the Cursor spend limit if Bugbot reports `usage limit reached`, and set
   `manualTriggerOnly: true` on the repo so it does not fire on every PR.

The Copilot coding-agent setup steps that used to be here are gone with the
subscription — there is no `@Copilot` assignment bridge any more.

## Project-board status automation

Tier labels pair with project-board status transitions. `.github/workflows/project-status.yml`
drives the pipeline across all 11 org project boards:

| Event | Target status |
|---|---|
| Issue opened / reopened | `Todo` |
| Issue assigned to a user (incl. `@Copilot`) | `In Progress` |
| Branch pushed to `task/N-*`, `cursor/N-*`, or `claude/N-*` | `In Progress` |
| PR opened that `Closes #N` / `Fixes #N` / `Resolves #N` | `Review` |
| That PR merged | `Done` |

Epics appear on multiple boards; the workflow updates every project that contains the issue.
Requires `DIGITHINGS_PROJECT_TOKEN` (PAT with `project` + `repo` scopes); workflow exits silently
if the token is missing.

## Quota exhaustion

Copilot and Cursor both have monthly-reset subscription quotas. When quota is exhausted, the agent session fails and the issue/PR stays incomplete — no automatic escalation or parking. When quota resets, re-apply the `exec:*` label (or use **Agent dispatch replay**) to re-fire dispatch.

If you want to track quota state manually, `agent-quota-reset.yml` runs on the 1st of each month and can clean up any stale labels on issue #387.

## Cost note

- Copilot: flat subscription — use freely. Primary PR reviewer and housekeeping agent.
- Cursor: burns compute credits — keep tasks scoped; 15 min good, 2 h bad. Prefer over Claude for implementable tasks.
- Claude Code Max: reserve for the hard work (architecture, judgment, security). PR review is opt-in (`ENABLE_CLAUDE_PR_REVIEW`). Cloud dispatch via GH Action is disabled (policy, issue #384); local dispatch via `make task ISSUE=N` always works.
