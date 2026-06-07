# Execution Tiers — Agent Delegation Framework

Every DigiThings backlog task carries exactly one `exec:*` label identifying the **minimum-capability tier** allowed to execute it. A lower tier must never pick up a higher-tier task. A human on Claude Code can always take anything.

Source of truth: `agents.yml` → `execution_tiers` and `tier_routing`. Regenerate platform adapters (`CLAUDE.md`, `.github/copilot-instructions.md`, `.cursor/rules/digithings.mdc`) with `make agents-init` after edits.

## The three tiers

### `exec:copilot` — Tier 1 — GitHub Copilot + gh-aw automation

Triggered automation. Fixed rule, no judgment. Runs on a schedule or event inside GitHub Actions.

**Fits:** Dependabot bumps, `pip-audit`, `gitleaks`, `ruff format`, stale issue/PR sweeps, label-coverage drift, orphan-issue routing, project-status transitions, scheduled-workflow failure digests, `digiquant-prices` failure dedup, CI-failure triage, **PR code review** (primary reviewer on all PRs), housekeeping tasks (duplicate issues, project backfill, doc links).

**Full coverage index:** see `docs/agents/HOUSEKEEPING.md` — every scheduled sweep, its cadence, and what it escalates.

**Dispatch — how `exec:copilot` actually fires (Tier C):**
Copilot is triggered by being **assigned** to an issue, not by a label alone. The bridge is:

1. Apply `exec:copilot` label to an issue (or create the issue with that label).
2. `.github/workflows/copilot-issue-dispatch.lock.yml` (compiled from `copilot-issue-dispatch.md`) fires via the [GitHub Agentic Workflows](https://github.github.com/gh-aw/) runtime. The gh-aw agent checks quota-state issue #387 and calls the `assign-to-agent` safe output with Copilot's custom instructions.
3. GitHub Copilot coding agent picks up the assignment and starts working.

If Copilot is not already assigned and the issue has `exec:copilot`, the agent calls `assign-to-agent`. If quota is exhausted, the Copilot session will fail naturally — the issue and any in-progress PR simply remain incomplete until quota resets.

**PR code review:** every PR that opens/becomes ready triggers `ci.yml → request-copilot-review`, which requests a Copilot code review via `gh pr edit --add-reviewer "Copilot"`. Copilot is the **primary** reviewer; Claude is a secondary opt-in (see below).

**PR auto-merge (low-risk agent PRs):** when CI is green on a `cursor/*` or `copilot/*` branch linked to a non-`risk:high` issue, `agent-pr-autolabel.yml` adds `automerge-agent`. `automerge-agent-prs.yml` verifies paths (no `digikey/`, workflows, scoring rubrics) and enables squash auto-merge. Human-gated issues keep the `needs-human` or `risk:high` label to block merge.

**Copilot PR lifecycle (end-to-end, Tier C):** GitHub's **Skip approval for Copilot coding agent Actions workflows** repo setting is enabled so main `CI` runs directly on Copilot PRs. `.github/workflows/copilot-pr-lifecycle.lock.yml` (compiled from `copilot-pr-lifecycle.md`) drives the full loop:

1. Patch `Fixes #N` when missing (inferred from branch/title)
2. Mark draft PRs ready when they have changes and are ≥10 min old
3. Check CI status — dispatch `copilot-pr-targeted-ci.yml` only when main CI is still missing/action_required
4. Request Copilot code review
5. Re-assign Copilot on review/CI failures (max 3 rounds)
6. Add `automerge-agent` + enable squash merge when CI passes

`copilot-pr-targeted-ci.yml` is kept as a fallback — triggered by the lifecycle only when main CI has not run.

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

**PR code review (secondary, opt-in):** Claude's `/code-review` plugin via `.github/workflows/claude-code-review.yml` is **off by default**. Enable it by setting repo variable `ENABLE_CLAUDE_PR_REVIEW = true` (Settings → Secrets and variables → Actions → Variables). Also requires `CLAUDE_CODE_OAUTH_TOKEN` secret. Use Copilot review first; enable Claude review only for projects that need deeper analysis.

**Weekly continuous-improvement digest:** `.github/workflows/continuous-improvement.yml` runs every Sunday 22:00 UTC, synthesizes the past 7 days of PR/CI/review activity, and files a single tracker issue with 3–5 prioritized suggestions. See [HOUSEKEEPING.md](HOUSEKEEPING.md#continuous-improvement) — synthesis is judgment work, so it lives at Tier 3.

**Setup & operations:** see `docs/agents/CLAUDE_CODE_ONBOARDING.md`.
**Dispatch (local only):** applying the `exec:claude` label triggers `.github/workflows/claude-code-dispatch.yml`, which posts a comment pointing at the local command:

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

1. Go to repo **Settings → Copilot → Coding agent** — enable it.
2. Enable **Settings → Actions → General → Skip approval for Copilot coding agent Actions workflows**.
3. Confirm `@Copilot` appears as an assignable user on issues.
4. Confirm `DIGITHINGS_PROJECT_TOKEN` secret is set (needed for maintenance workflows).

The `copilot-issue-dispatch.lock.yml` workflow fires automatically on `exec:copilot` label application.

## Project-board status automation

Tier labels pair with project-board status transitions. `.github/workflows/project-status-automation.yml`
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
