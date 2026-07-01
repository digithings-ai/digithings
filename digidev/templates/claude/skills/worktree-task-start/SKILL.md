---
name: worktree-task-start
description: Use when the user asks to start a backlog task, begin work on an issue, pick up issue N, or run `make task`. Triggers on "start task", "begin issue", "pick up issue N", "work on #N".
---

# Worktree task start

Pre-flight checklist before running `make task ISSUE=N`.

## Before you run

1. **Confirm the issue number** — the user should supply `N` explicitly.
2. **Read the issue** to understand scope. Note the `primary component` field and acceptance criteria.
3. **Check for an existing worktree** — running `make task` twice for the same issue creates a conflict:
   ```bash
   git worktree list
   ```
   If a worktree for `task/<N>-*` already exists, switch into it instead of creating a new one.

4. **Confirm the base branch is up to date**:
   ```bash
   git fetch origin
   git status
   ```

## Run the task

```bash
make task ISSUE=N
```

This command:
- Creates branch `task/<N>-<slug>` from the appropriate base (`module/<component>` or `develop`).
- Creates an isolated git worktree at `../digithings-task-<N>/` (or equivalent).
- Prints the worktree path and branch name.

## After the worktree is created

1. `cd` into the worktree directory printed by `make task`.
2. Read `{component}/AGENTS.md` — mandatory pre-flight for every component.
3. Read `{component}/ARCHITECTURE.md` — understand the structure before touching code.
4. Confirm the test suite is green on the fresh branch:
   ```bash
   <test command from AGENTS.md>
   ```
5. Begin the red/green/refactor loop (see `test-first-implementer` agent).

## Branch routing rules

| Issue component | Base branch |
|---|---|
| Single module (`digiquant`, `digichat`, etc.) | `module/<component>` |
| Cross-cutting (`root`, `website`, `ci`) | `develop` |

The `make task` script reads `scripts/project_routing.json` to determine the base automatically.

## Finishing

When all acceptance criteria have passing tests:
1. Run `make score` from inside the worktree.
2. Invoke the `finish-task` skill to commit, push, and open the PR.

The PR is automatically targeted at the correct base branch.
