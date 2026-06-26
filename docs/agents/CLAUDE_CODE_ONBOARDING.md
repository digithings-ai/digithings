# Claude Code Onboarding — Tier 3 Delegation

This document covers everything needed to dispatch Claude Code (Tier 3) against
DigiThings backlog issues — both the local interactive path and the cloud
GitHub-Action path.

Parallel to `docs/agents/CURSOR_AGENT_ONBOARDING.md`, but Claude is reserved
for the highest-judgment tier: architecture, cross-module, security-sensitive,
and milestone-decomposition work.

## Prerequisites

- Claude Code Max subscription (for local dispatch) **or** an Anthropic API
  key (for cloud dispatch via GitHub Action)
- GitHub account with write access to `digithings-ai/digithings`
- `develop` branch checked out locally (Claude branches from it)

---

## 1. Two dispatch paths

### 1a. Local dispatch (primary path)

Applying the `exec:claude` label to a GitHub issue marks it as Tier 3. From a
Claude Code session on the local machine:

```bash
make task ISSUE=<N>
```

This creates a task worktree on `task/N-<slug>` from `develop` (or the active
`module/<component>` branch), pre-loads the component's `AGENTS.md` /
`ARCHITECTURE.md`, and lands Claude in the worktree with the branch already set
up for workflow-edit permissions. Implement, run `make score`, commit, and
open the PR via `make pr`.

The local path does **not** require any repo secret. The Claude Code Max
subscription covers compute; the `CLAUDE_CODE_OAUTH_TOKEN` repo secret
is unrelated to this path and is only used by the `@claude`-mention comment
workflow (PR #253).

### 1b. Cloud dispatch (feature-flagged)

Applying `exec:claude` to an issue fires `.github/workflows/agent-claude-dispatch.yml`,
which runs `anthropics/claude-code-action@v1` (pinned to the GA v1 tag). Claude
executes in the Action runner, creates a `task/N-*` branch, and opens a PR.

The workflow accepts two auth paths, preferring the subscription one:

1. **`CLAUDE_CODE_OAUTH_TOKEN` (preferred)** — authenticates against a Claude
   Code Max subscription. No separate billing, uses the seat you already pay
   for. Generate with `claude setup-token` in a local Claude Code session.
2. **`ANTHROPIC_API_KEY` (fallback)** — direct Anthropic API billing. Use
   this only if you don't have a Claude Code Max seat.

When neither secret is set (default state), the workflow exits silently with a
`::notice::` in the run log. No issue comment is posted; the label still
serves as a tier marker for the local path.

**To enable cloud dispatch:**

```bash
# In a Claude Code session on your machine:
claude setup-token
# copy the printed token

# Then add to repo secrets:
gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo digithings-ai/digithings
# paste the token when prompted
```

Apply `exec:claude` to a test issue to verify dispatch fires. OAuth tokens
expire periodically — re-run `claude setup-token` and update the secret
when that happens.

### 1c. Related workflows (installed by the Claude Code GitHub App)

If the official Claude Code GitHub App is installed on the repo, it ships two
more workflows that share the same `CLAUDE_CODE_OAUTH_TOKEN`:

- `.github/workflows/agent-claude.yml` — fires on `@claude` mentions in issue /
  PR-review / comment bodies, or in issue titles and bodies. Claude reads
  the surrounding context and executes the mentioned instruction.
- `.github/workflows/agent-claude-review.yml` — auto-runs `/code-review` on
  every PR open / sync / ready-for-review / reopen.

All three Claude workflows (`claude.yml`, `claude-code-review.yml`, and this
repo's `claude-code-dispatch.yml`) share the same OAuth token and subscription
compute.

---

## 2. What the agent must do

Claude Code operating on this repo (local or cloud) **must follow this sequence**:

### 2a. Pre-flight (before writing any code)

```
1. Read CLAUDE.md                         ← repo rules + workflows
2. Read {component}/AGENTS.md             ← per-module pre-flight checklist
3. Read {component}/ARCHITECTURE.md       ← module map, extension points
4. Read docs/agents/EXECUTION_TIERS.md    ← confirm this task actually needs Tier 3
5. If the task is cursor-sized (single paragraph, clear criteria, <5 files):
   relabel exec:cursor, comment why, stop.
```

### 2b. Branch naming

```bash
git checkout -b task/<issue-number>-<slug>
# Example: task/208-org-project-membership-api
```

Branch from `develop` (or the active `module/<component>` branch if one is
ahead). The cloud action does this automatically; for local, `make task
ISSUE=N` handles it.

### 2c. Implementation rules

Canonical rules in `CLAUDE.md` + `agents.yml`. Key constraints:

- **Polars only** — never import pandas
- **Pydantic v2** — model_validator, field_validator; no v1 syntax
- **LangGraph supervisor + sub-graphs** for orchestration
- **LiteLLM** for LLM routing with caching
- **NautilusTrader** for quant
- **No comments** unless the WHY is non-obvious
- **No error handling for impossible scenarios** — trust framework guarantees
- **Ruff clean** — `ruff check . && ruff format .` must pass
- **Tests required** — every change needs a unit test where applicable
- **Never touch without human approval:** `SECURITY.md`, `docs/scoring/`,
  `config/litellm.yaml`, `projects/`, live-trading paths

### 2d. Scoring gate

Before opening the PR, run the self-score:

```bash
make score          # must pass: Security ≥8, Quality ≥8, Optimization ≥7, Accuracy ≥9
make test-unit      # all unit tests green (or component-specific test-cmd)
ruff check .        # zero violations
```

### 2e. PR submission

```bash
git push origin task/<issue-number>-<slug>
make pr             # opens PR via gh CLI, pre-fills template
```

PR must:
- Target `develop` (or the active `module/<component>` branch)
- Body must contain `Closes #<issue-number>`
- Body must fill the PR template checklist (scoring, test evidence, doc flag)
- Title format: `feat(<component>): <description> (#<issue-number>)`

The `PR quality gate` CI check enforces scoring and linkage.

---

## 3. Scope constraints — what even Claude Code must escalate

| Constraint | Required |
|---|---|
| Live-trading path edits | `Human-Approved-By:` commit trailer |
| Any `digikey/` auth or crypto change | security-review comment before PR |
| New external service dependency | ADR in `docs/adr/` |
| Novel architecture not covered by existing ARCHITECTURE.md | ADR + human sign-off |
| Changes to `SECURITY.md`, `docs/scoring/`, `config/litellm.yaml` | DIGI_ALLOW_PROTECTED=1 override |

---

## 4. Issue quality checklist (for the human filing exec:claude issues)

For Claude to succeed, the issue body must have:

- [ ] **Component** field filled in (from the issue template dropdown)
- [ ] **Goal** — one paragraph, ambiguity acceptable here (that's why it's Tier 3)
- [ ] **Acceptance criteria** — can include "design an approach for X"
- [ ] **Risk** set honestly (`high` requires human gate at merge time)
- [ ] **Related ADRs / epics** linked

Use `/spec` in Claude Code to generate a compliant issue body.

---

## 5. Monitoring running agents

- **Local:** the Claude Code session itself
- **Cloud:** Actions tab → `Claude Code dispatch` workflow
- **Issue board:** the dispatch comment is posted with a run-log link when
  cloud dispatch fires with a valid key
- **PR board:** branches named `task/N-*` (both local and cloud) appear in the
  PR list and are subject to the standard PR quality gate

If a cloud dispatch appears stuck or wrong, cancel the Action run and file a
follow-up `exec:claude` issue with the error logs.

---

## 6. Reference

| Resource | Path |
|---|---|
| Execution tiers | `docs/agents/EXECUTION_TIERS.md` |
| Cursor tier onboarding | `docs/agents/CURSOR_AGENT_ONBOARDING.md` |
| Component routing | `docs/agents/COMPONENT_ROUTING.md` |
| Agent workflow | `docs/agents/AGENT_WORKFLOW.md` |
| Claude rules | `CLAUDE.md` + `.claude/agents/` + `.claude/skills/` |
| Scoring rubrics | `docs/scoring/` |
| Cloud dispatch | `.github/workflows/agent-claude-dispatch.yml` |
| Project-status automation | `.github/workflows/project-status.yml` |
| Issue template | `.github/ISSUE_TEMPLATE/agent_task.yml` |
