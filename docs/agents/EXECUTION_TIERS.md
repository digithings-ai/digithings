# Execution Tiers — Agent Delegation Framework

Every digithings backlog task carries the `agent-task` label. Applying it (or
opening an issue with it) fires dispatch. **Which** dispatcher picks it up is a
property of the *component*, not the issue: `tiers` in
`scripts/project_routing.json` maps each `component:*` label to `cursor`
(cloud auto-execution) or `claude` (human-supervised, local only). A human on
Claude Code can always take anything.

Source of truth: `scripts/project_routing.json` → `tiers`. Canonical agent rules
live in `AGENTS.md`. Regenerate platform adapters
(`.github/copilot-instructions.md`, `.cursor/rules/digithings.mdc`,
`.claude/*`) with `make agents-init` after edits. `CLAUDE.md` is a pointer at
AGENTS.md, not a generated adapter.

## The two tiers

There used to be label-based tiers (`exec:cursor`, `exec:claude`, and long ago
`exec:copilot`, retired 2026-08-05 with the subscription, #1904). The whole
`exec:*` family — along with `risk:*`, `type:*`, `pipeline:*`, `phase:*`, and
`needs-human*` — was deleted in the 2026-09 label simplification (#3533), which
kept the bare minimum: `component:*`, `priority:*`, `reviewed:*`,
`autorelease:*`, plus a flat set (`epic`, `agent-task`, `bug`,
`security:finding`, `ci:failure`, `automerge-*`, `provider-review`,
`client-pilot`).

The tier distinction survives, minus the labels:

- **cursor** (default, every component except digikey): the issue auto-executes
  via Cursor Automation. Judgment that used to be expressed per-issue with
  `risk:high` is now expressed in planning (priority, spec quality) and
  enforced at merge (review coverage + path-based safety gate).
- **claude** (`component:digikey` only): auth/crypto needs supervised hands.
  Dispatch posts local `make task ISSUE=N` instructions; a human runs them.
  Claude never auto-executes issues.

**Full coverage index:** see `docs/agents/HOUSEKEEPING.md` — every scheduled
sweep, its cadence, and what it escalates.

**Caveat worth knowing before relying on dispatch:** the backlog is deep and
the Cursor Automation is metered. Retargeting stops work being stranded on a
queue with no consumer; it does not by itself mean the work gets done. Whether
the Automation is actually running is a separate question — the weekly
continuous-improvement digest and the dispatch-replay workflow exist for that.

**PR code review:** default is in-session (see [CODE_REVIEW_POLICY.md](CODE_REVIEW_POLICY.md)).
Cursor Bugbot, when available, is invoked by hand with a `bugbot run` comment once a
diff is final. Never at PR open and never per push — Bugbot went usage-based in June
2026 at roughly $1.00–$1.50 a run ([Cursor Bugbot](https://cursor.com/docs/bugbot);
usage-based pricing as of that month). CodeRabbit is optional/sunset — do not re-request
it for small follow-up commits. Claude review
remains a secondary opt-in (see below). Every commit reaching `main` must clear
`ci-review-coverage.yml`, which is a required status check.

**PR auto-merge (agent PRs):** when CI is green on an agent branch linked to an
issue, `agent-pr-autolabel.yml` adds `automerge-agent`.
`agent-pr-automerge.yml` verifies paths against the safety deny-list
(`scripts/verify_agent_automerge_pr.py`: no `digikey/`, `digiquant/brokers/`,
live-trading, workflows, scoring rubrics) and enables squash auto-merge.
Minimal-gate paths never auto-merge — that is path-based now, not label-based.

**Daily PR finalizer:** `agent-pr-finalizer.yml` runs at 07:00 UTC as backstop for agent PRs.

### cursor tier — Cursor Cloud Agent (Cursor Automations)

Autonomous, asynchronous. Describable in one paragraph with clear acceptance criteria. Opens a PR for human review.

**Fits:** bug fixes with a concrete repro; unit tests for a specified module; docstrings; typed-model migrations; scoped refactors inside a single component; small MCP tools with defined signatures.

**Never:** anything requiring mid-task dialogue; auth/crypto (digikey is claude-tier).

**Setup & operations:** see `docs/agents/CURSOR_AGENT_ONBOARDING.md`.
**Dispatch:** applying the `agent-task` label to an issue whose component routes
to the cursor tier (everything except digikey) triggers a **Cursor Automation**
configured at [cursor.com/settings/automations](https://cursor.com/settings/automations).
The Automation fires a Cloud Agent session with the task context and custom
instructions. **One-time manual step:** the Automation trigger must listen for
the `agent-task` label (it used to listen for `exec:cursor`). If quota is
exhausted the session fails naturally; the issue stays open until quota resets.
Stuck backlog: run **Agent dispatch replay** workflow (`agent-dispatch-replay.yml`).

### claude tier — Claude Code (human-supervised, LOCAL only)

Interactive, local, human-in-the-loop. Currently only `component:digikey`.
**Claude never auto-executes issues.** Execution is always a human on a workstation.

**Fits:** auth/crypto changes, plus anything a human explicitly pulls locally
via `make task ISSUE=N` regardless of component.

**PR code review (secondary, opt-in):** Claude's `/code-review` plugin via `.github/workflows/agent-claude-review.yml` is **off by default**. Enable it by setting repo variable `ENABLE_CLAUDE_PR_REVIEW = true` (Settings → Secrets and variables → Actions → Variables). Also requires `CLAUDE_CODE_OAUTH_TOKEN` secret. Default review is in-session (`/review <N>`, fresh-context subagent — see `CODE_REVIEW_POLICY.md`); Bugbot is the on-demand external option, invoked by hand once a diff is final. Enable this Claude plugin only for projects that need a standing automated pass on top of that.

**Weekly continuous-improvement digest:** `.github/workflows/pipeline-continuous-improvement.yml` runs every Sunday 22:00 UTC, synthesizes the past 7 days of PR/CI/review activity, and files a single tracker issue with 3–5 prioritized suggestions. See [HOUSEKEEPING.md](HOUSEKEEPING.md#continuous-improvement) — synthesis is judgment work, so a human curates it.

**Setup & operations:** see `docs/agents/CLAUDE_CODE_ONBOARDING.md`.
**Dispatch (local only):** the `agent-task` label on a claude-tier issue triggers `.github/workflows/agent-claude-dispatch.yml`, which posts a comment pointing at the local command:

```
make task ISSUE=N
```

Cloud dispatch via the Claude Code Action is **intentionally disabled** (policy, issue #384).

## Decision tree

```
Fully automatable with a trigger + fixed rule?
├── YES → no dispatch at all; it is a scheduled workflow, not a backlog task
└── NO
    └── Touches digikey/ auth or crypto?
        ├── YES → claude tier (human runs make task locally)
        └── NO  → cursor tier (auto-executes; safety enforced at merge)
```

## Default routing when the creator doesn't classify

Applied by `scripts/create_issue.sh`: tier is derived from the component via
`tiers` in `scripts/project_routing.json` — there is nothing to classify
per-issue any more. Priority and spec quality are the planning-time levers.

## Responsibilities

- **Maintenance workflows** (`pipeline-maintenance.yml`, `agent-ci-failure-triage.yml`) tag every issue they open `agent-task` (+ `component:root`, `priority:*`) so dispatch fires. CVE bumps, lint drift and CI failures needing code fixes auto-execute at the cursor tier. Architectural findings get a high priority and a spec that says what judgment is needed.
- **Cursor Cloud Agents** pick up cursor-tier `agent-task` issues. If a task feels larger than the one-paragraph spec implied, comment why and stop — do not proceed.
- **Claude Code (you)** decomposes milestones, writes issue bodies via `/spec`, and reviews PRs only when `ENABLE_CLAUDE_PR_REVIEW` is set.

## Workflow

1. **Claude Code** — read milestone, decompose, write issues via `/spec`.
2. **Cursor Cloud Agents** — execute cursor-tier issues in parallel; open PRs.
3. **Review** — Cursor Bugbot on demand (`bugbot run`), or `/review <N>` in-session when Bugbot is out of quota. Recorded by a `reviewed:*` label and asserted before `main` by `ci-review-coverage.yml`.
4. **Claude Code** — handles digikey/supervised tasks locally; secondary PR reviewer when enabled.

## Cursor setup (one-time)

1. Configure the Cursor Automation as described in `docs/agents/CURSOR_AGENT_ONBOARDING.md` — trigger on the **`agent-task`** label.
2. Verify `.cursor/rules/digithings.mdc` is loaded (run `make agents-init` if stale).

See `docs/agents/CURSOR_AGENT_ONBOARDING.md` for the full agent operating protocol.

## Bugbot / maintenance setup (one-time)

1. Confirm `DIGITHINGS_PROJECT_TOKEN` secret is set (needed for maintenance workflows).
2. Raise the Cursor spend limit if Bugbot reports `usage limit reached`, and set
   `manualTriggerOnly: true` on the repo so it does not fire on every PR.

## Project-board status automation

Dispatch pairs with project-board status transitions. `.github/workflows/project-status.yml`
drives the pipeline across all 11 org project boards:

| Event | Target status |
|---|---|
| Issue opened / reopened | `Todo` |
| Issue assigned to a user | `In Progress` |
| Branch pushed to `task/N-*`, `cursor/N-*`, or `claude/N-*` | `In Progress` |
| PR opened that `Closes #N` / `Fixes #N` / `Resolves #N` | `Review` |
| That PR merged | `Done` |

Epics appear on multiple boards; the workflow updates every project that contains the issue.
Requires `DIGITHINGS_PROJECT_TOKEN` (PAT with `project` + `repo` scopes); workflow exits silently
if the token is missing.

## Quota exhaustion

Cursor has a monthly-reset subscription quota. When quota is exhausted, the agent session fails and the issue/PR stays incomplete — no automatic escalation or parking. When quota resets, bounce the `agent-task` label (or use **Agent dispatch replay**) to re-fire dispatch.

## Cost note

- Cursor: burns compute credits — keep tasks scoped; 15 min good, 2 h bad. Prefer over Claude for implementable tasks.
- Cursor Bugbot: usage-based since June 2026, roughly $1.00–$1.50 a run. Invoke by hand with `bugbot run` once a diff is final — never at PR open, never per push.
- Claude Code Max: reserve for the hard work (architecture, judgment, security). PR review is opt-in (`ENABLE_CLAUDE_PR_REVIEW`). Cloud dispatch via GH Action is disabled (policy, issue #384); local dispatch via `make task ISSUE=N` always works.
