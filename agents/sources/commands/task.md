---
description: Start a backlog task end-to-end via `make task ISSUE=N` with pre-flight checks.
argument-hint: <issue-number>
---

Invoke `make task ISSUE=$ARGUMENTS`. The Makefile target is the source of truth for the full pipeline — it creates an isolated worktree, pauses for implementation, runs tests, scores, and opens a PR.
