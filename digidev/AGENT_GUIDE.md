# Agent Guide — digidev workflow

This document is the single file a coding agent reads to understand the complete development workflow. It covers task lifecycle, branch taxonomy, scoring gate, guardrails, and how to set up the kit in a fresh repo.

---

## What this kit is

**digidev** installs a structured agentic development workflow on any GitHub repository. It standardises:

- How tasks are written and labelled (GitHub issues with structured fields)
- Which agent tier handles which kind of task (Copilot / Cursor / Claude)
- How branches are named and protected
- How code quality is scored before a PR is opened
- What guardrails prevent destructive or dangerous changes
- How the complete task lifecycle runs from start to PR

The project-specific configuration lives in `agents.yml` at the repo root. Read that file first — it declares the components, scoring thresholds, execution tiers, and human gates for this specific repo.

---

## Task lifecycle

Every unit of work follows this pipeline:

```
1. Issue created (make new-task or GitHub UI)
   → structured fields: component, risk, exec tier, goal, acceptance criteria

2. Task picked up (make task ISSUE=N)
   → worktree created at .worktrees/task-N-{slug}
   → branch task/N-{slug} checked out

3. Implementation
   → read {component}/AGENTS.md first (pre-flight checklist)
   → read relevant ARCHITECTURE.md sections
   → implement, test iteratively

4. Test (make test-unit or component test command)
   → must pass zero failures before scoring

5. Score (make score)
   → Security ≥ threshold, Quality ≥ threshold, Optimization ≥ threshold, Accuracy ≥ threshold
   → thresholds defined in agents.yml under scoring_thresholds
   → fix any failing dimension before proceeding

6. Commit (make commit MSG="type(component): description")
   → conventional commit format required

7. PR (make pr)
   → template pre-filled; self-score checklist in body
   → human gate section must be honestly filled

8. Cleanup
   → worktree removed after PR is open
```

---

## Execution tiers

Three tiers exist. A task's `exec` label sets the tier ceiling — a lower tier must never pick up a higher-tier task.

### Tier 1 — Copilot (`exec:copilot`)
Triggered automation. Fixed rules, no judgment.

**Do:** dependency bumps, format fixes, stale issue cleanup, coverage PR comments, structured CI triage comments.

**Never:** judgment calls about correctness, changes spanning multiple files, auth or sensitive code.

When the `exec:copilot` label is applied to an issue, the GitHub workflow auto-assigns `@Copilot` (if quota is available).

### Tier 2 — Cursor (`exec:cursor`)
One-paragraph spec, clear acceptance criteria, no mid-task dialogue.

**Do:** bug fixes with concrete repro, unit tests for a specified module, typed models, docstrings, scoped refactors inside a single component.

**Never:** cross-module integration, ambiguous success criteria, architectural decisions.

### Tier 3 — Claude Code (`exec:claude`)
Interactive, cross-module, architectural, or human-gated work. **Local only** — cloud auto-dispatch is disabled for this tier.

**Do:** architecture scaffolding, complex debugging, security review, strategy design, decomposing milestones.

**Never:** auto-execute from a GitHub label. Execution happens via `make task ISSUE=N` on a human's machine.

When the `exec:claude` label is applied, the GitHub workflow posts a comment with copy-paste-ready local execution instructions.

---

## Branch taxonomy

```
main  ←  {default_branch}  ←  module/<component>  ←  task/<N>-<slug>
```

| Pattern | Purpose |
|---|---|
| `main` | Production — protected |
| `{default_branch}` | Integration — cross-cutting work, releases |
| `module/<component>` | Focused sprint on a single component |
| `task/<N>-<slug>` | Individual backlog task (created by `make task`) |
| `claude/<slug>` | Claude Code session branches |
| `feat/<slug>`, `fix/<slug>` | Human feature / bugfix branches |

`task/*` branches PR into their module branch (or directly to `{default_branch}` for root tasks). Module branches PR into `{default_branch}` at sprint end.

---

## Scoring gate

Every PR requires passing a four-dimension score. Thresholds are defined in `agents.yml`.

Run `make score` on staged changes. This scores the diff against rubrics in `digidev/docs/scoring/`.

| Dimension | Typical threshold | Rubric file |
|---|---|---|
| Security | ≥ 8/10 | `digidev/docs/scoring/SECURITY.md` |
| Quality | ≥ 8/10 | `digidev/docs/scoring/QUALITY.md` |
| Optimization | ≥ 7/10 | `digidev/docs/scoring/OPTIMIZATION.md` |
| Accuracy | ≥ 9/10 | `digidev/docs/scoring/ACCURACY.md` |

Score honestly. The self-score checklist in the PR template is an audit surface, not a rubber stamp.

---

## Guardrails

Four Claude Code PreToolUse hooks fire before every write or bash operation:

### Write / Edit / NotebookEdit hooks

**project-root-guard** — Blocks writes outside the project root. Exceptions: `~/.claude/plans/` and `/tmp/`.

**protected-path-guard** — Blocks writes to protected paths (`.github/workflows/`, scoring docs, confidential dirs, live-trading code) unless on a `task/N-*` branch. Human override: set `ALLOW_PROTECTED=1` in a human session (never agent-set).

**branch-warn** — Non-blocking warning when editing on `main` or `{default_branch}`. Does not block.

**component-router-preflight** — Non-blocking reminder to read `{component}/AGENTS.md` before editing files in that component. Does not block.

### Bash hooks

**remote-guard** — Blocks `git push` or `git remote add/set-url` to any remote that isn't the pinned origin URL. Prevents accidental pushes to forks.

**network-host-guard** — Blocks `curl`/`wget`/`http` calls to hosts not in the allowlist. Add legitimate hosts to `scripts/claude-hooks/network-host-guard.sh`.

**protected-path-bash-guard** — Blocks shell-redirect writes (`>`, `>>`, `tee`, `sed -i`, `mv`, `cp`) to protected paths. Mirrors `protected-path-guard` for Bash commands.

### Git pre-push hook

Installed by `make hooks-install`. Rejects:
- Pushes to any remote URL that isn't the pinned origin
- Pushes to `main` without `ALLOW_MAIN_PUSH=1`
- Pushes to `{default_branch}` without `ALLOW_MAIN_PUSH=1`
- Pushes touching sensitive paths without a `Human-Approved-By:` commit trailer

---

## Human gates

These changes require explicit human approval before merge. If you touch any of them, check the relevant box in the PR template's Human Gate section and do not self-merge.

- Auth, JWT, or cryptographic code
- Live-trading paths (order execution, position management)
- Score below threshold on any dimension
- New external service dependency
- Novel architecture not covered by existing ARCHITECTURE.md
- Database migrations (irreversible in production)
- New network exposure (new bound ports, new public endpoints)

---

## Issue labeling

Labels are the routing mechanism for the entire workflow. Key labels:

| Label | Meaning |
|---|---|
| `agent-task` | This issue is work for a coding agent |
| `component:<name>` | Which component owns this issue |
| `exec:copilot` | Tier 1 — auto-assigns @Copilot |
| `exec:cursor` | Tier 2 — Cursor cloud agent |
| `exec:claude` | Tier 3 — Claude Code (local) |
| `risk:low` / `risk:med` / `risk:high` | Risk level (high → Tier 3) |
| `housekeeping:*` | Exempt from some project-board field requirements |
| `priority:high` / `priority:critical` | Affects quota swap decisions |

Tier routing defaults (when not explicitly labelled):
- `risk:high` or human gate → `exec:claude`
- Housekeeping (deps, format, stale) → `exec:copilot`
- Everything else → `exec:cursor`

---

## Makefile targets

| Target | What it does |
|---|---|
| `make task ISSUE=N` | Create worktree + branch for issue N, run through pipeline |
| `make score` | Self-score staged changes against four-dimension rubrics |
| `make status` | List open agent-task issues (add `COMPONENT=x` to filter) |
| `make new-task` | Interactive issue creator |
| `make commit MSG="..."` | Validated conventional commit |
| `make pr` | Open PR with template pre-filled |
| `make hooks-install` | Install `.git/hooks/pre-push` |
| `make agents-init` | Regenerate platform adapter files from `agents.yml` |
| `make batch-candidates` | Group open tasks by area for parallel execution |
| `make parse-error` | Parse Python traceback and identify component |
| `make module-switch MODULE=x` | Switch to focused module branch |
| `make module-status` | Show all module branches vs `{default_branch}` |

---

## File map (after install)

```
repo/
├── agents.yml                    machine-readable project manifest
├── AGENTS.md                     human-readable rules + workflow overview
├── {component}/AGENTS.md         per-component pre-flight checklist
├── .claude/
│   ├── settings.json             Claude Code guardrails (hooks + permissions)
│   ├── agents/                   subagent specs (component-router, spec-writer, etc.)
│   ├── skills/                   skill definitions (finish-task, score-and-fix, etc.)
│   └── commands/                 slash commands (/normalize, /spec, /score, /task)
├── scripts/
│   ├── claude-hooks/             PreToolUse hook scripts
│   ├── hooks/                    Git hook scripts
│   ├── score.py                  four-dimension scorer
│   ├── run_task.sh               worktree manager
│   ├── create_issue.sh           interactive issue creator
│   ├── create_pr.sh              PR creator with template
│   ├── list_tasks.sh             list open agent-task issues
│   └── commit_helper.sh          conventional commit validator
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   └── agent_task.yml        structured task form
│   ├── PULL_REQUEST_TEMPLATE.md  self-score checklist + human gates
│   └── workflows/
│       ├── claude-code-dispatch.yml    exec:claude → local instructions comment
│       ├── auto-assign-copilot.yml     exec:copilot → @Copilot assignment
│       └── route-issues-to-projects.yml  label → project board routing
└── digidev/docs/scoring/         four-dimension rubric docs
```

---

## How pre-flight works (component-router)

Before editing any file in a component directory (`{component}/`), read that component's `AGENTS.md`. It contains:
- Pre-flight checklist (what to read, what to check)
- Component-specific rules and anti-patterns
- Test command for this component
- Architecture doc location

The `component-router-preflight` hook will warn you if you skip this step.

---

## Installation (for agents setting up a new repo)

If you are a coding agent asked to install digidev in a new repository:

1. **Read `digidev/digidev.yml`** (or `digidev/digidev.example.yml` if the former doesn't exist). This contains the project configuration — fill in any missing required fields.

2. **Run the installer:**
   ```bash
   bash digidev/install.sh
   ```
   The installer will:
   - Copy template files to their target locations
   - Substitute project-specific values from `digidev.yml`
   - Make all hook scripts executable
   - Create the `.claude/` directory structure

3. **Install git hooks:**
   ```bash
   make hooks-install
   ```

4. **Verify:**
   ```bash
   make status   # should list open agent-task issues (may be empty in a new repo)
   make score    # should run without error (no staged changes to score yet)
   ```

5. **Commit the installed files:**
   ```bash
   git add .claude/ .github/ scripts/claude-hooks/ scripts/hooks/ agents.yml AGENTS.md
   git commit -m "chore: install digidev agentic workflow kit"
   ```

If `digidev.yml` has no values yet, stop and ask the human for the project configuration before proceeding.
