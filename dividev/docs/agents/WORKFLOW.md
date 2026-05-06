# Agent Workflow

Step-by-step guide for executing a backlog task from start to PR.

---

## Prerequisites

- `git`, `bash`, `python3`, `gh` CLI installed
- `gh auth login` completed
- `make hooks-install` run at least once in this repo
- A GitHub issue with `agent-task` label and required fields filled in

---

## Step 0 — Identify the task

```bash
make status                    # list all open agent-task issues
make status COMPONENT=api      # filter by component
```

Pick an issue. Note its number.

---

## Step 1 — Start the task

```bash
make task ISSUE=42
```

This creates `.worktrees/task-42-{slug}` and checks out branch `task/42-{slug}` from the current module branch (or `develop`/`main` if no module branch is active).

You are now working in an isolated worktree. Changes here do not affect the main working tree.

---

## Step 2 — Pre-flight

Before writing any code:

1. Read `{component}/AGENTS.md` — the hook will remind you if you skip this.
2. Read the relevant `ARCHITECTURE.md` section for your change area.
3. Run the test command to confirm a green baseline:
   ```bash
   make test-unit   # or the component-specific test command
   ```

---

## Step 3 — Implement

Work normally. Commit incrementally with `make commit MSG="..."`.

Commit message format: `type(component): description`

Valid types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`

Example: `feat(api): add /health endpoint`

---

## Step 4 — Test

```bash
make test-unit
```

Must pass zero failures. If tests fail, fix before proceeding — do not try to score failing code.

---

## Step 5 — Score

```bash
make score
```

This runs the four-dimension rubric against your staged changes. Output shows per-dimension scores.

Required minimums (from `agents.yml`):
- Security: ≥ threshold
- Quality: ≥ threshold
- Optimization: ≥ threshold
- Accuracy: ≥ threshold

If any dimension fails, read the corresponding rubric in `dividev/docs/scoring/` and fix the issues. Common fixes:
- Security: add input validation, remove hardcoded secrets, check error paths
- Quality: add types, add tests, clean up removed symbols
- Optimization: fix N+1 queries, add caching, use async correctly
- Accuracy: fix spec mismatches, add meaningful test assertions

Re-score after fixing: `make score`

---

## Step 6 — Commit

```bash
make commit MSG="feat(api): add /health endpoint with structured response"
```

The commit helper validates the conventional commit format and rejects malformed messages.

---

## Step 7 — Open PR

```bash
make pr
```

This opens a PR with the template pre-filled. You must:
1. Fill in the self-score checklist (honest scores, not rubber stamps)
2. Fill in the Human Gate section (check any applicable boxes)
3. Paste the test output in the Testing Evidence section

---

## Step 8 — Cleanup

After the PR is open, the worktree is cleaned up:

```bash
git worktree remove .worktrees/task-42-{slug}
```

`make task` does this automatically after `make pr` succeeds.

---

## Module branch workflow

For focused sprints on a single component:

```bash
make module-switch MODULE=api   # creates/switches to module/api
make task ISSUE=42              # branches task/42-slug from module/api
# ... implement, test, score, pr ...
make module-pr MODULE=api       # when sprint is done: PR module/api → develop
```

---

## Quick reference

```bash
make task ISSUE=N          start task in isolated worktree
make test-unit             run unit tests (zero failures required)
make score                 score staged changes (must pass all thresholds)
make commit MSG="..."      validated conventional commit
make pr                    open PR with pre-filled template
make status                list open agent-task issues
make new-task              create a new issue interactively
make batch-candidates      find tasks suitable for parallel execution
```
