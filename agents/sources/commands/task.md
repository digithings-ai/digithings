---
description: Start a backlog task end-to-end via `make task ISSUE=N` with pre-flight checks.
argument-hint: <issue-number>
---

Use the `worktree-task-start` skill to run the pre-flight checklist for issue #$ARGUMENTS, then invoke `make task ISSUE=$ARGUMENTS`. Do not modify `make task` behavior — the Makefile target is the source of truth.
