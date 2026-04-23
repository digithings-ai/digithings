# Execution Tiers — Agent Delegation Framework

Every DigiThings backlog task carries exactly one `exec:*` label identifying the **minimum-capability tier** allowed to execute it. A lower tier must never pick up a higher-tier task. A human on Claude Code can always take anything.

Source of truth: `agents.yml` → `execution_tiers` and `tier_routing`. Regenerate platform adapters (`CLAUDE.md`, `.github/copilot-instructions.md`, `.cursor/rules/digithings.mdc`) with `make agents-init` after edits.

## The three tiers

### `exec:copilot` — Tier 1 — GitHub Copilot

Triggered automation. Fixed rule, no judgment. Runs on a schedule or event inside GitHub Actions.

**Fits:** Dependabot bumps, `pip-audit`, `gitleaks`, `ruff format`, `mypy` reports, stale issue/PR cleanup, coverage PR comments, structured CI-failure triage comments.

**Never:** judgment calls, multi-file code changes, live-trading, auth, cryptography.

### `exec:cursor` — Tier 2 — Cursor Cloud Agent

Autonomous, asynchronous. Describable in one paragraph with clear acceptance criteria. Opens a PR for human review.

**Fits:** bug fixes with a concrete repro; unit tests for a specified module; docstrings; typed-model migrations; scoped refactors inside a single component; small MCP tools with defined signatures.

**Never:** cross-module integration, ambiguous success criteria, novel design, anything requiring mid-task dialogue.

**Setup & operations:** see `docs/agents/CURSOR_AGENT_ONBOARDING.md`.  
**Dispatch:** applying the `exec:cursor` label triggers `.github/workflows/cursor-agent-dispatch.yml`, which posts a preflight checklist and "Open in Cursor" deep-link on the issue. Set the `CURSOR_API_KEY` repo secret to enable fully-automated dispatch.

### `exec:claude` — Tier 3 — Claude Code Max (human-supervised)

Interactive, local, human-in-the-loop. The top tier; takes everything above and adds judgment-heavy work.

**Fits:** architecture and new-module scaffolding; complex debugging; cross-module integration; security review; strategy/iterative design; milestone decomposition; reviewing agent PRs.

**Setup & operations:** see `docs/agents/CLAUDE_CODE_ONBOARDING.md`.
**Dispatch:** applying the `exec:claude` label triggers `.github/workflows/claude-code-dispatch.yml`.
When `ANTHROPIC_API_KEY` is set in repo secrets, Claude Code is dispatched in the cloud via the
official `anthropics/claude-code-action`. Without the key, the workflow is silently disabled and
the label serves as a tier marker for the local path: `make task ISSUE=N`.

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
- **Claude Code (you)** decomposes milestones, writes issue bodies via `/spec`, assigns tiers, and reviews PRs from the lower tiers.

## Workflow

1. **Claude Code** — read milestone, decompose, write issues via `/spec`, tier each one.
2. **Cursor Cloud Agents** — execute `exec:cursor` issues in parallel; open PRs.
3. **Claude Code** — review PRs; merge clean ones; re-issue broken ones with corrected spec.
4. **Copilot** — runs continuously, catches regressions, opens tiered follow-up issues.

## Cursor Pro setup (one-time)

1. Open Cursor → **Settings → Integrations → GitHub** → authenticate with the org account
2. Enable **Settings → Beta → Background Agents**
3. Verify `.cursor/rules/digithings.mdc` is loaded (run `make agents-init` if stale)
4. *(Optional — fully automated dispatch)* Add `CURSOR_API_KEY` to GitHub repo secrets
   - Retrieve from Cursor **Settings → Account → API Keys**
   - Add to: GitHub repo **Settings → Secrets → Actions → New repository secret**

See `docs/agents/CURSOR_AGENT_ONBOARDING.md` for the full agent operating protocol.

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

## Cost note

- Copilot: flat subscription — use freely.
- Cursor: burns compute credits — keep tasks scoped; 15 min good, 2 h bad.
- Claude Code Max: reserve for the hard work. Cloud dispatch via GH Action is feature-flagged off
  by default (no `ANTHROPIC_API_KEY`); local dispatch via `make task ISSUE=N` always works.
