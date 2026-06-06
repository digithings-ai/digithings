# Execution Tiers — Agent Delegation Framework

Every DigiThings backlog task carries exactly one `exec:*` label identifying the **minimum-capability tier** allowed to execute it. A lower tier must never pick up a higher-tier task. A human on Claude Code can always take anything.

Source of truth: `agents.yml` → `execution_tiers` and `tier_routing`. Regenerate platform adapters (`CLAUDE.md`, `.github/copilot-instructions.md`, `.cursor/rules/digithings.mdc`) with `make agents-init` after edits.

## The three tiers

### `exec:copilot` — Tier 1 — GitHub Copilot + scheduled automation

Triggered automation. Fixed rule, no judgment. Runs on a schedule or event inside GitHub Actions.

**Fits:** Dependabot bumps, `pip-audit`, `gitleaks`, `ruff format`, stale issue/PR sweeps, label-coverage drift, orphan-issue routing, project-status transitions, scheduled-workflow failure digests, `digiquant-prices` failure dedup, CI-failure triage, **PR code review** (primary reviewer on all PRs), housekeeping tasks (duplicate issues, project backfill, doc links).

**Full coverage index:** see `docs/agents/HOUSEKEEPING.md` — every scheduled sweep, its cadence, and what it escalates.

**Dispatch — how `exec:copilot` actually fires:**
Copilot is triggered by being **assigned** to an issue, not by a label alone. The bridge is:

1. Apply `exec:copilot` label to an issue (or create the issue with that label).
2. `.github/workflows/auto-assign-copilot.yml` fires on `labeled`, `opened`, or `reopened`, checks quota-state issue #387, and assigns the Copilot coding agent via `scripts/assign_copilot_agent.py` (GraphQL `replaceActorsForAssignable`).
3. GitHub Copilot coding agent picks up the assignment and starts working.

The quota check (step 2) uses the same escalation matrix as `cursor-agent-dispatch.yml`:
- Quota ok → assign `@Copilot`
- Quota exhausted + `priority:high|critical` → swap `exec:copilot` → `exec:claude`, post local dispatch instructions
- Quota exhausted + lower priority → add `pending:quota`, park until monthly reset

**PR code review:** every PR that opens/becomes ready triggers `ci.yml → request-copilot-review`, which requests a Copilot code review via `gh pr edit --add-reviewer "Copilot"`. Copilot is the **primary** reviewer; Claude is a secondary opt-in (see below).

**PR auto-merge (low-risk agent PRs):** when CI is green on a `cursor/*` or `copilot/*` branch linked to a non-`risk:high` issue, `agent-pr-autolabel.yml` adds `automerge-agent`. `automerge-agent-prs.yml` verifies paths (no `digikey/`, workflows, scoring rubrics) and enables squash auto-merge. Human-gated issues keep the `needs-human` or `risk:high` label to block merge.

**Copilot PR orchestrator (end-to-end):** GitHub blocks bot-triggered `pull_request` CI on Copilot PRs (`action_required`). `copilot-pr-orchestrator.yml` runs every 10 minutes as a trusted actor and drives the full loop:

1. Patch `Fixes #N` when missing (inferred from branch/title)
2. Mark draft PRs ready when they have changes
3. Dispatch `copilot-pr-targeted-ci.yml` — path-filtered tests for changed files only
4. Request Copilot code review
5. Re-assign Copilot on review/CI failures (max 3 rounds)
6. Add `automerge-agent` + enable squash merge when `Copilot targeted CI` passes

**Daily PR finalizer:** `agent-pr-finalizer.yml` runs at 07:00 UTC for `cursor/*` PRs and as a backstop.

**Never:** judgment calls, multi-file code changes, live-trading, auth, cryptography.

### `exec:cursor` — Tier 2 — Cursor Cloud Agent

Autonomous, asynchronous. Describable in one paragraph with clear acceptance criteria. Opens a PR for human review.

**Fits:** bug fixes with a concrete repro; unit tests for a specified module; docstrings; typed-model migrations; scoped refactors inside a single component; small MCP tools with defined signatures.

**Never:** cross-module integration, ambiguous success criteria, novel design, anything requiring mid-task dialogue.

**Setup & operations:** see `docs/agents/CURSOR_AGENT_ONBOARDING.md`.  
**Dispatch:** applying the `exec:cursor` label (or creating an issue with it) triggers `.github/workflows/cursor-agent-dispatch.yml`, which runs the Cursor CLI when `CURSOR_API_KEY` is set (org or repo secret) and posts a dispatch summary comment. Stuck backlog: run **Agent dispatch replay** workflow (`agent-dispatch-replay.yml`).

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

## Cursor Pro setup (one-time)

1. Open Cursor → **Settings → Integrations → GitHub** → authenticate with the org account
2. Enable **Settings → Beta → Background Agents**
3. Verify `.cursor/rules/digithings.mdc` is loaded (run `make agents-init` if stale)
4. Add `CURSOR_API_KEY` to GitHub org or repo secrets (required for CLI dispatch)
   - Retrieve from Cursor **Settings → Account → API Keys**
   - Grant the secret to the `digithings` repository

See `docs/agents/CURSOR_AGENT_ONBOARDING.md` for the full agent operating protocol.

## Copilot setup (one-time)

1. Go to repo **Settings → Copilot → Coding agent** — enable it.
2. Confirm `@Copilot` appears as an assignable user on issues.
3. Confirm `DIGITHINGS_PROJECT_TOKEN` secret is set (needed for maintenance workflows to assign Copilot).
4. The `auto-assign-copilot.yml` workflow fires automatically on `exec:copilot` label application.

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

## Quota exhaustion — state, escalation, reset

Copilot (premium requests) and Cursor (Background Agent tokens) both have monthly-reset subscription quotas. When a tier is out of quota, dispatching to it wastes cycles and leaves tasks silently stalled. The quota-management system below makes this visible and handles escalation.

### State

The singleton issue [#387 `[meta] Agent quota state — DO NOT CLOSE`](../../../issues/387) carries the live state as labels:

- `quota:cursor-exhausted` — set when the Cursor Background Agent is out of tokens
- `quota:copilot-exhausted` — set when Copilot premium requests are exhausted

v1 is **human-flippable**: when you notice either service hitting quota, add the label. Example:

```bash
gh issue edit 387 --add-label "quota:cursor-exhausted"
```

Auto-detection is v2 — deferred until we've captured real error text from each service. Building a sweeper on a guessed error string trips on the wrong text.

### Dispatch-time behavior

- **Copilot** (`auto-assign-copilot.yml`) reads state before assigning `@Copilot`:
  - If `quota:copilot-exhausted` + task is `priority:high|critical` → swap `exec:copilot` for `exec:claude` (local Tier 3 dispatch).
  - If exhausted + lower priority → add `pending:quota`, post a park notice with the predicted reset date (~1st of next month).
  - Otherwise → assign `@Copilot` normally.
- **`copilot-quota-gate.yml`** intercepts on `issues.assigned` for Copilot-variant logins as a second line of defense (catches manual @Copilot assignments that bypass the label workflow).
- **Cursor** (`cursor-agent-dispatch.yml`) reads state before calling the CLI:
  - If `quota:cursor-exhausted` + task is `priority:high|critical` → swap `exec:cursor` for `exec:claude`.
  - If exhausted + lower priority → add `pending:quota`, park until reset.
  - Otherwise → dispatch normally.

### Monthly reset

`agent-quota-reset.yml` runs 1st of the month at 09:00 UTC:
1. Removes both `quota:*` labels from the state issue.
2. For parked issues with `exec:cursor`: bounces the label to re-fire dispatch.
3. For parked issues with `exec:copilot`: bounces the label to re-fire `auto-assign-copilot.yml` (which re-checks quota and assigns `@Copilot` if clear).

Reset date is **hardcoded** to "1st of next month, 00:00 UTC" because neither Cursor nor Copilot exposes a quota-reset API. If the actual reset is a few days off, the monthly cron cleans up anyway.

### Quick reference

| Situation | Action |
|---|---|
| Notice Cursor failing — out of tokens | `gh issue edit 387 --add-label "quota:cursor-exhausted"` |
| Notice Copilot failing — out of requests | `gh issue edit 387 --add-label "quota:copilot-exhausted"` |
| Parked task is actually urgent | Add `priority:high` + re-fire the tier label |
| Quota reset mid-month (rare) | Run `gh workflow run agent-quota-reset.yml` |

## Cost note

- Copilot: flat subscription — use freely. Primary PR reviewer and housekeeping agent.
- Cursor: burns compute credits — keep tasks scoped; 15 min good, 2 h bad. Prefer over Claude for implementable tasks.
- Claude Code Max: reserve for the hard work (architecture, judgment, security). PR review is opt-in (`ENABLE_CLAUDE_PR_REVIEW`). Cloud dispatch via GH Action is disabled (policy, issue #384); local dispatch via `make task ISSUE=N` always works.
